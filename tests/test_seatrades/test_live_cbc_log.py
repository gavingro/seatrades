"""Tests for the pty-backed live CBC log tee (``live_cbc_log``).

These lock the *external behavior* — the log file grows while the writing
subprocess is still alive — not the pty internals.
"""

import os
import subprocess
import sys
import time
from types import SimpleNamespace

from seatrades.live_cbc_log import live_cbc_log
from seatrades.solver import _extract_gap_from_log

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


# A stand-in child that emits cbc's MIP-gap line: 'Gap:' + 28 spaces + value.
_GAP_CHILD = "import sys\nsys.stdout.write('Gap:' + ' ' * 28 + '0.05\\n')\nsys.stdout.flush()\n"


class TestLiveCbcLogFdOwnership:
    def test_does_not_close_a_recycled_fd_on_exit(self, tmp_path):
        """PuLP closes the fd it is handed (``open(logPath, "w")`` then ``pipe.close()``).

        ``live_cbc_log`` must not *also* close that fd number on exit — if an unrelated
        ``open`` has recycled the number, the extra close would clobber that innocent
        handle (a valid close raises nothing, so the ``OSError`` guard can't catch it).
        The recycle is forced with ``os.dup2`` so the double-close is deterministic.
        """
        log_path = tmp_path / "live.log"
        solver_cmd = SimpleNamespace(optionsDict={})

        with live_cbc_log(solver_cmd, log_path):
            handed_fd = solver_cmd.optionsDict["logPath"]
            pipe = open(handed_fd, "w")  # PuLP: open(optionsDict["logPath"], "w")
            pipe.write("hi\n")
            pipe.flush()
            pipe.close()  # PuLP closes it -> frees handed_fd's number (EOFs the reader)

            # An unrelated fd claims the just-freed number.
            sentinel = os.open(os.devnull, os.O_WRONLY)
            os.dup2(sentinel, handed_fd)  # sentinel now also lives at handed_fd's number

        try:
            os.fstat(handed_fd)  # must not raise -> the number still belongs to sentinel
        finally:
            os.close(handed_fd)
            if sentinel != handed_fd:
                os.close(sentinel)
        assert "hi" in log_path.read_text()

    def test_restores_prior_logpath_option_on_exit(self, tmp_path):
        """A well-behaved context manager leaves the caller's solver option as it found it,
        not holding a stale (closed) fd."""
        solver_cmd = SimpleNamespace(optionsDict={"logPath": "original.log"})
        with live_cbc_log(solver_cmd, tmp_path / "live.log"):
            handed = solver_cmd.optionsDict["logPath"]
            assert handed != "original.log"  # the pty fd, temporarily
            os.close(handed)  # PuLP owns and closes the handed fd; do the same so the reader EOFs
        assert solver_cmd.optionsDict["logPath"] == "original.log"

    def test_leaves_no_logpath_option_when_none_existed(self, tmp_path):
        """If the solver had no logPath option, exiting must not leave one behind."""
        solver_cmd = SimpleNamespace(optionsDict={})
        with live_cbc_log(solver_cmd, tmp_path / "live.log"):
            assert "logPath" in solver_cmd.optionsDict  # set to the pty fd during the block
            os.close(solver_cmd.optionsDict["logPath"])  # PuLP would close it; let the reader EOF
        assert "logPath" not in solver_cmd.optionsDict


class TestLiveCbcLogParseTargets:
    def test_gap_line_survives_streaming(self, tmp_path):
        """The MIP-gap regex uses a fixed-width lookbehind ('Gap:' + 28 spaces); the pty's
        ``\\n``->``\\r\\n`` rewrite must not disturb that line, or optimality reporting
        breaks (issue #100 user story 7). Asserts a concrete non-None gap, not just 'no crash'."""
        log_path = tmp_path / "gap.log"
        solver_cmd = SimpleNamespace(optionsDict={})
        with live_cbc_log(solver_cmd, log_path):
            pipe = open(solver_cmd.optionsDict["logPath"], "w")
            proc = subprocess.Popen([sys.executable, "-c", _GAP_CHILD], stdout=pipe, stderr=pipe)
            proc.wait()
            pipe.close()
        assert _extract_gap_from_log(log_path) == 0.05
