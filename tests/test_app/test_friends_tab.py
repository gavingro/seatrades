"""Friends tab tests — relationship seeding and rendering via Streamlit AppTest."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import PRESOLVE_TIMEOUT_SECONDS

APP_SCRIPT = str(Path(__file__).resolve().parents[2] / "app.py")


class TestFriendsTab:
    def test_app_seeds_a_besties_pair_for_the_default_roster(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        assert not at.exception
        relationships = at.session_state["camper_relationships"]
        assert (relationships["relationship"] == "besties").any()

    def test_seeded_besties_pair_is_same_cabin(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        relationships = at.session_state["camper_relationships"]
        besties = relationships[relationships["relationship"] == "besties"]
        assert (besties["cabin_1"] == besties["cabin_2"]).all()

    def test_friends_tab_renders_relationship_editor(self):
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        assert not at.exception
        # The editable relationships grid is present (data_editor renders no exception).
        assert any("Friends" in m.value for m in at.subheader)
