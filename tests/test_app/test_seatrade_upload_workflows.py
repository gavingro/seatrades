"""Seatrade preferences upload workflows: valid replace + malformed guards (#70 / ADR 0009).

Completes ADR 0009's promise to headlessly test *every* ``st.file_uploader`` flow —
the Seatrade Setup uploader was the one left without an AppTest. Mirrors the camper
upload suite: a valid upload replaces ``seatrade_preferences`` with no exception; a
malformed upload surfaces the ADR-0006 translated validation error without crashing
and leaves the prior offerings untouched.
"""

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import APP_SCRIPT, PRESOLVE_TIMEOUT_SECONDS

_VALID_SEATRADE_CSV = (
    "seatrade,campers_min,campers_max\nArchery,0,10\nSailing,0,10\nClimbing,0,10\nKayaking,0,10\n"
).encode()


def _seatrade_uploader(at: AppTest):
    """The Seatrade Setup uploader has no key; select it by its distinctive label."""
    return next(u for u in at.file_uploader if "this weeks seatrades" in u.label.lower())


class TestValidSeatradeUpload:
    def test_valid_seatrade_csv_replaces_offerings(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        _seatrade_uploader(at).upload("seatrades.csv", _VALID_SEATRADE_CSV)
        at.run()

        assert not at.exception
        offerings = at.session_state["seatrade_preferences"]
        # Replaced, not merged: only the 4 uploaded seatrades remain.
        assert set(offerings["seatrade"]) == {"Archery", "Sailing", "Climbing", "Kayaking"}
        assert any("Updating Seatrade Preferences" in t.value for t in at.toast)


class TestMalformedSeatradeUpload:
    """Two failure modes surface a validation error without crashing: a bad *value*
    (reaches the pandera schema, exercising the ADR-0006 translation) and a missing
    *column* (caught earlier by read_csv_for_schema's usecols guard)."""

    def test_bad_value_seatrade_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        offerings_before = at.session_state["seatrade_preferences"].copy()

        # All columns present but campers_min is non-numeric — reaches the schema's
        # coerce check, exercising the pandera→plain-language translation (ADR 0006).
        bad_min_csv = b"seatrade,campers_min,campers_max\nArchery,lots,10\n"
        _seatrade_uploader(at).upload("bad.csv", bad_min_csv)
        at.run()

        assert not at.exception
        # The translated, human-readable detail surfaces — not just a generic banner.
        assert any('invalid values in column "campers_min"' in md.value for md in at.markdown)
        assert any("Continuing without updating Seatrade Setup." in t.value for t in at.toast)
        # The malformed upload was rejected: the previous offerings are untouched.
        assert at.session_state["seatrade_preferences"].equals(offerings_before)

    def test_missing_column_seatrade_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        offerings_before = at.session_state["seatrade_preferences"].copy()

        # No campers_max column at all — caught by read_csv_for_schema's usecols guard
        # before the schema runs, translated to a missing-column message.
        no_max_column_csv = b"seatrade,campers_min\nArchery,0\n"
        _seatrade_uploader(at).upload("bad.csv", no_max_column_csv)
        at.run()

        assert not at.exception
        assert any("missing required column(s): campers_max" in md.value for md in at.markdown)
        assert any("Continuing without updating Seatrade Setup." in t.value for t in at.toast)
        assert at.session_state["seatrade_preferences"].equals(offerings_before)
