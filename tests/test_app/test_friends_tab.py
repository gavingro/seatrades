"""Friends tab tests — relationship seeding, rendering, and CSV upload via Streamlit AppTest."""

from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import APP_SCRIPT, PRESOLVE_TIMEOUT_SECONDS


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

    def test_relationships_csv_upload_replaces_the_grid(self):
        """A valid CSV upload through the relationships uploader seeds the grid, no crash."""
        at = AppTest.from_file(APP_SCRIPT, default_timeout=PRESOLVE_TIMEOUT_SECONDS)
        at.run()

        # Pair two real campers from the default roster as frenemies — the one type
        # with no shared-preference precondition, so it validates against any two
        # distinct known campers. First and last rows are in different cabins.
        roster = at.session_state["camper_identity"]
        first, last = roster.iloc[0], roster.iloc[-1]
        relationships_csv = (
            "cabin_1,camper_1,cabin_2,camper_2,relationship\n"
            f"{first.cabin},{first.camper},{last.cabin},{last.camper},frenemies\n"
        ).encode()

        at.file_uploader(key="relationships_uploader").upload("relationships.csv", relationships_csv)
        at.run()

        assert not at.exception
        relationships = at.session_state["camper_relationships"]
        # Replaced, not appended: only the uploaded frenemies pair remains.
        assert list(relationships["relationship"]) == ["frenemies"]
        assert (relationships["camper_1"] == first.camper).any()
        assert any("Updating Camper Relationships" in t.value for t in at.toast)
