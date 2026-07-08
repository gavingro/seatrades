"""Tests for the pty-backed live CBC log tee (``live_cbc_log``).

These lock the *external behavior* — the log file grows while the writing
subprocess is still alive — not the pty internals.
"""

import subprocess
import sys
import time
from types import SimpleNamespace

from seatrades.live_cbc_log import live_cbc_log

# A stand-in child that mimics cbc: emit a line, flush, stay alive, then emit more.
_STREAMING_CHILD = (
    "import sys, time\n"
    "sys.stdout.write('STREAMING\\n'); sys.stdout.flush()\n"
    "time.sleep(1.0)\n"
    "sys.stdout.write('DONE\\n'); sys.stdout.flush()\n"
)


def _wait_until(predicate, timeout):
    """Poll ``predicate`` until true or timeout; return whether it became true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class TestLiveCbcLogStreams:
    def test_log_grows_before_subprocess_exits(self, tmp_path):
        """The tee'd log holds an early line while the writer is still running.

        Reproduces PuLP's exact contract — ``open(optionsDict["logPath"], "w")`` on
        the raw option value — so this fails loudly if a future PuLP change stops
        opening that value (the silent-regression risk) without needing a real solve.
        """
        log_path = tmp_path / "live.log"
        solver_cmd = SimpleNamespace(optionsDict={})

        with live_cbc_log(solver_cmd, log_path):
            pipe = open(solver_cmd.optionsDict["logPath"], "w")  # PuLP does exactly this
            proc = subprocess.Popen([sys.executable, "-c", _STREAMING_CHILD], stdout=pipe, stderr=pipe)

            appeared = _wait_until(
                lambda: log_path.exists() and "STREAMING" in log_path.read_text(),
                timeout=3.0,
            )
            assert appeared, "log did not stream during the subprocess run"
            assert proc.poll() is None, "subprocess already exited — streaming not proven live"

            proc.wait()
            pipe.close()

        assert "DONE" in log_path.read_text()

    def test_strips_pty_carriage_returns(self, tmp_path):
        """The pty rewrites \\n to \\r\\n; the tee'd log must read back clean \\n-only.

        The gap regex uses a fixed-width lookbehind and the panel renders raw text, so a
        stray \\r would corrupt both. Also confirms the full stream survives drain-on-exit.
        """
        log_path = tmp_path / "clean.log"
        solver_cmd = SimpleNamespace(optionsDict={})

        with live_cbc_log(solver_cmd, log_path):
            pipe = open(solver_cmd.optionsDict["logPath"], "w")
            proc = subprocess.Popen([sys.executable, "-c", _STREAMING_CHILD], stdout=pipe, stderr=pipe)
            proc.wait()
            pipe.close()

        text = log_path.read_text()
        assert "\r" not in text
        assert "STREAMING" in text and "DONE" in text
