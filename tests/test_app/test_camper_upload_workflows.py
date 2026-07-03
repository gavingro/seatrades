"""Camper CSV upload workflows: identity, preferences, and malformed uploads (#90).

Drives the real upload paths through AppTest's file_uploader (unlocked by the #86
Streamlit upgrade) and asserts observable behavior — a valid upload replaces its
session_state input with no exception; a malformed upload surfaces a validation
error and leaves the app usable — mirroring the pre-solve assertion style.
"""

from collections.abc import Iterable

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import APP_SCRIPT, PRESOLVE_TIMEOUT_SECONDS

# A distinctive camper name that never appears in the simulated default roster,
# so its presence after an upload unambiguously proves the input was replaced.
UPLOADED_CAMPER = "ZZ_Uploaded"

VALID_IDENTITY_CSV = (
    f"cabin,camper,gender,age\nSpindrift,{UPLOADED_CAMPER},male,12\nSpindrift,QQ_Second,female,13\n"
).encode()


def _valid_prefs_csv(seatrade_names: Iterable[str]) -> bytes:
    """Build a schema-valid preferences CSV (4 distinct seatrades) for one camper."""
    top4 = list(seatrade_names)[:4]
    header = "camper,seatrade_1,seatrade_2,seatrade_3,seatrade_4\n"
    row = ",".join([UPLOADED_CAMPER, *top4]) + "\n"
    return (header + row).encode()


class TestValidUpload:
    def test_identity_csv_upload_replaces_roster(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        at.file_uploader(key="identity_uploader").upload("identity.csv", VALID_IDENTITY_CSV)
        at.run()

        assert not at.exception
        roster = at.session_state["camper_identity"]
        assert UPLOADED_CAMPER in roster["camper"].values
        # Replaced, not appended: only the 2 uploaded campers remain, not the default roster.
        assert len(roster) == 2

    def test_preferences_csv_upload_replaces_prefs(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        seatrades = at.session_state["seatrade_preferences"]["seatrade"]
        at.file_uploader(key="prefs_uploader").upload("prefs.csv", _valid_prefs_csv(seatrades))
        at.run()

        assert not at.exception
        prefs = at.session_state["camper_preferences"]
        assert UPLOADED_CAMPER in prefs["camper"].values
        # Replaced, not appended: only the 1 uploaded camper remains, not the default roster.
        assert len(prefs) == 1


class TestMalformedUpload:
    """Two failure modes surface a validation error without crashing: a bad *value*
    (reaches the pandera schema, exercising the ADR-0006 translation) and a missing
    *column* (caught earlier by read_csv_for_schema's usecols guard)."""

    def test_bad_value_identity_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        roster_before = at.session_state["camper_identity"].copy()

        # All columns present but age is non-numeric — reaches the schema's coerce
        # check, exercising the pandera→plain-language translation (ADR 0006).
        bad_age_csv = b"cabin,camper,gender,age\nSpindrift,BadAge,male,twelve\n"
        at.file_uploader(key="identity_uploader").upload("bad.csv", bad_age_csv)
        at.run()

        assert not at.exception
        # The translated, human-readable detail surfaces — not just a generic banner.
        assert any('invalid values in column "age"' in md.value for md in at.markdown)
        assert any("Continuing without updating Camper Identity." in t.value for t in at.toast)
        # The malformed upload was rejected: the previous roster is untouched.
        assert at.session_state["camper_identity"].equals(roster_before)
        # App stays usable for a retry — the uploader is still on the page.
        assert any(uploader.key == "identity_uploader" for uploader in at.file_uploader)

    def test_bad_value_preferences_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        prefs_before = at.session_state["camper_preferences"].copy()

        # All columns present but a ranked choice is blank — reaches the schema's
        # not-nullable check, exercising the pandera→plain-language translation (ADR 0006).
        blank_choice_csv = b"camper,seatrade_1,seatrade_2,seatrade_3,seatrade_4\nSomeone,Sailing,Archery,Crafts,\n"
        at.file_uploader(key="prefs_uploader").upload("bad.csv", blank_choice_csv)
        at.run()

        assert not at.exception
        # The translated, human-readable detail surfaces — not just a generic banner.
        assert any('missing or empty values in column "seatrade_4"' in md.value for md in at.markdown)
        assert any("Continuing without updating Camper Preferences." in t.value for t in at.toast)
        # The malformed upload was rejected: the previous preferences are untouched.
        assert at.session_state["camper_preferences"].equals(prefs_before)
        # App stays usable for a retry — the uploader is still on the page.
        assert any(uploader.key == "prefs_uploader" for uploader in at.file_uploader)

    def test_missing_column_identity_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        roster_before = at.session_state["camper_identity"].copy()

        # No age column at all — caught by read_csv_for_schema's usecols guard before
        # the schema runs, translated to a missing-column message.
        no_age_column_csv = b"cabin,camper,gender\nSpindrift,NoAge,male\n"
        at.file_uploader(key="identity_uploader").upload("bad.csv", no_age_column_csv)
        at.run()

        assert not at.exception
        assert any("missing required column(s): age" in md.value for md in at.markdown)
        assert any("Continuing without updating Camper Identity." in t.value for t in at.toast)
        assert at.session_state["camper_identity"].equals(roster_before)
        assert any(uploader.key == "identity_uploader" for uploader in at.file_uploader)

    def test_missing_column_preferences_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()
        prefs_before = at.session_state["camper_preferences"].copy()

        # Only three ranked choices — the fourth column is absent, caught by the
        # usecols guard and translated to a missing-column message.
        three_choices_csv = b"camper,seatrade_1,seatrade_2,seatrade_3\nSomeone,Sailing,Archery,Crafts\n"
        at.file_uploader(key="prefs_uploader").upload("bad.csv", three_choices_csv)
        at.run()

        assert not at.exception
        assert any("missing required column(s): seatrade_4" in md.value for md in at.markdown)
        assert any("Continuing without updating Camper Preferences." in t.value for t in at.toast)
        assert at.session_state["camper_preferences"].equals(prefs_before)
        assert any(uploader.key == "prefs_uploader" for uploader in at.file_uploader)
