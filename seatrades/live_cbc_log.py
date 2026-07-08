"""Stream cbc's log live by giving it a pty instead of a plain file.

cbc is a C++ binary: when its stdout is a plain file, C stdio block-buffers (~8 KB),
so the log only lands after the solve exits. When stdout is a tty it line-buffers, so
each line flushes as produced. ``live_cbc_log`` hands cbc a pty and tees the pty output
into the configured log file, so the existing ``SolveRun`` log polling sees it grow
line-by-line. Unix-only (macOS + Linux); Windows is out of scope.

The load-bearing trick: PuLP opens its ``logPath`` option with a bare ``open(...)``, and
``open()`` accepts an integer fd — so setting the option to the pty's *slave* fd makes PuLP
hand cbc a tty with no subclassing or monkeypatching.
"""

import os
import pty
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_READ_SIZE = 4096


@contextmanager
def live_cbc_log(solver_cmd, log_path: Path) -> Iterator[None]:
    """Give ``solver_cmd``'s cbc a pty and tee its output into ``log_path`` live.

    Sets ``solver_cmd.optionsDict["logPath"]`` to the pty slave fd for the duration of the
    block, so PuLP's ``open(logPath)`` hands cbc a tty (the original option value is
    restored on exit). A background reader relays the pty output into ``log_path``
    (unbuffered), normalizing the pty line discipline's ``\\r\\n`` back to ``\\n``. On exit
    the reader is drained and joined, so ``log_path`` is complete before the caller reads
    it (e.g. to parse the MIP gap).
    """
    master_fd, slave_fd = pty.openpty()
    # Hand PuLP the pty slave fd and let PuLP own closing it: PuLP does
    # ``open(logPath, "w") ... pipe.close()``, which closes this fd after the solve (on
    # both the success and the error path). We must NOT close it too — a double-close can
    # silently clobber an unrelated fd if the number was recycled in between, which the
    # `except OSError` guard cannot catch. PuLP closing the slave, plus cbc exiting, is
    # what EOFs the reader.
    had_log_path = "logPath" in solver_cmd.optionsDict
    prev_log_path = solver_cmd.optionsDict.get("logPath")
    solver_cmd.optionsDict["logPath"] = slave_fd

    def _relay() -> None:
        with open(log_path, "wb", buffering=0) as log:
            while True:
                try:
                    chunk = os.read(master_fd, _READ_SIZE)
                except OSError:  # Linux raises EIO on the master when the child exits
                    break
                if not chunk:  # macOS/BSD signal EOF with an empty read
                    break
                log.write(chunk.replace(b"\r\n", b"\n"))

    reader = threading.Thread(target=_relay, daemon=True)
    reader.start()
    try:
        yield
    finally:
        reader.join()  # PuLP's close of the slave (above) EOFs the reader
        os.close(master_fd)
        if had_log_path:  # leave the caller's solver option as we found it
            solver_cmd.optionsDict["logPath"] = prev_log_path
        else:
            solver_cmd.optionsDict.pop("logPath", None)
