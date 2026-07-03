"""Camper CSV upload workflows: identity, preferences, and malformed uploads (#90).

Drives the real upload paths through AppTest's file_uploader (unlocked by the #86
Streamlit upgrade) and asserts observable behavior — a valid upload replaces its
session_state input with no exception; a malformed upload surfaces a validation
error and leaves the app usable — mirroring the pre-solve assertion style.
"""

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import APP_SCRIPT

# A distinctive camper name that never appears in the simulated default roster,
# so its presence after an upload unambiguously proves the input was replaced.
UPLOADED_CAMPER = "ZZ_Uploaded"

VALID_IDENTITY_CSV = (
    f"cabin,camper,gender,age\nSpindrift,{UPLOADED_CAMPER},male,12\nSpindrift,QQ_Second,female,13\n"
).encode()


def _valid_prefs_csv(seatrade_names) -> bytes:
    """Build a schema-valid preferences CSV (4 distinct seatrades) for one camper."""
    top4 = list(seatrade_names)[:4]
    header = "camper,seatrade_1,seatrade_2,seatrade_3,seatrade_4\n"
    row = ",".join([UPLOADED_CAMPER, *top4]) + "\n"
    return (header + row).encode()


class TestValidUpload:
    def test_identity_csv_upload_replaces_roster(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()

        at.file_uploader(key="identity_uploader").upload("identity.csv", VALID_IDENTITY_CSV)
        at.run()

        assert not at.exception
        assert UPLOADED_CAMPER in at.session_state["camper_identity"]["camper"].values

    def test_preferences_csv_upload_replaces_prefs(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()

        seatrades = at.session_state["seatrade_preferences"]["seatrade"]
        at.file_uploader(key="prefs_uploader").upload("prefs.csv", _valid_prefs_csv(seatrades))
        at.run()

        assert not at.exception
        assert UPLOADED_CAMPER in at.session_state["camper_preferences"]["camper"].values


class TestMalformedUpload:
    def test_malformed_identity_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()
        roster_before = at.session_state["camper_identity"].copy()

        missing_age_csv = b"cabin,camper,gender\nSpindrift,NoAge,male\n"
        at.file_uploader(key="identity_uploader").upload("bad.csv", missing_age_csv)
        at.run()

        assert not at.exception
        assert any("Continuing without updating Camper Identity." in t.value for t in at.toast)
        # The malformed upload was rejected: the previous roster is untouched.
        assert at.session_state["camper_identity"].equals(roster_before)
        # App stays usable for a retry — the uploader is still on the page.
        assert at.file_uploader(key="identity_uploader") is not None

    def test_malformed_preferences_upload_warns_no_crash(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=60)
        at.run()
        prefs_before = at.session_state["camper_preferences"].copy()

        missing_seatrade_csv = b"camper,seatrade_1,seatrade_2,seatrade_3\nSomeone,A,B,C\n"
        at.file_uploader(key="prefs_uploader").upload("bad.csv", missing_seatrade_csv)
        at.run()

        assert not at.exception
        assert any("Continuing without updating Camper Preferences." in t.value for t in at.toast)
        assert at.session_state["camper_preferences"].equals(prefs_before)
