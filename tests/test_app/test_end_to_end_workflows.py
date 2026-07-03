"""End-to-end workflow AppTest coverage for issue #70 (slow, real CBC solves).

The PRD's headline workflows each end in *export*: get camper data into the app
(generate or upload) → run the assignment → read the exported schedule. The
pre-solve, done-view, and upload suites each protect one leg in isolation (they
seed past the solver or stop before it). These two tests join the legs in a
single AppTest run and drive a *real* solve end to end, asserting both export
tables render populated afterward: "By Camper" (Captain's Book) and "By Seatrade"
(Seatrade Leaders).

Both run a real CBC solve, so both carry ``@pytest.mark.slow`` — the fast loop
deselects them; CI and a pre-push ``-m slow`` run exercise them.
"""

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_app.helpers import (
    APP_SCRIPT,
    SOLVE_TIMEOUT_SECONDS,
    click_assign,
    find_button,
    find_seatrade_uploader,
    find_slider,
    poll_until_solution,
)

# A deterministic 4-camper / 2-cabin week known to solve OPTIMAL under the default
# config (mirrors the roster in test_assignments_done_view.py), expressed as the
# three CSVs a Captain would upload.
SEATRADE_CSV = ("seatrade,campers_min,campers_max\nArchery,0,10\nSailing,0,10\nClimbing,0,10\nKayaking,0,10\n").encode()
IDENTITY_CSV = (
    "cabin,camper,gender,age\nCabin1,Alice,F,13\nCabin1,Bob,M,14\nCabin2,Carol,F,15\nCabin2,Dave,M,16\n"
).encode()
PREFERENCES_CSV = (
    "camper,seatrade_1,seatrade_2,seatrade_3,seatrade_4\n"
    "Alice,Archery,Sailing,Climbing,Kayaking\n"
    "Bob,Climbing,Archery,Sailing,Kayaking\n"
    "Carol,Sailing,Archery,Climbing,Kayaking\n"
    "Dave,Archery,Climbing,Sailing,Kayaking\n"
).encode()


def _assert_both_export_tables_render(at: AppTest) -> None:
    """The done view shows a populated Captain's Book and Seatrade Leaders export."""
    assert at.session_state["optimization_success"] is True
    # The done view opens on the By Camper (Captain's Book) export. The Assignments
    # tab renders first, so its st.dataframe is at.dataframe[0] (the other tabs'
    # data_editors follow it).
    assert at.selectbox(key="assignment_view_selector").value == "By Camper"
    assert at.dataframe, "expected a rendered By Camper export table"
    assert not at.dataframe[0].value.empty, "By Camper export should hold schedule rows"

    # Toggling to By Seatrade (Seatrade Leaders) re-renders a populated table.
    at.selectbox(key="assignment_view_selector").set_value("By Seatrade").run()
    assert not at.exception
    assert not at.dataframe[0].value.empty, "By Seatrade export should hold schedule rows"


@pytest.mark.slow
class TestGenerateAssignExport:
    def test_regenerate_then_assign_renders_both_exports(self):
        """Generate a fresh roster in the UI, solve it for real, read both exports."""
        at = AppTest.from_file(APP_SCRIPT, default_timeout=SOLVE_TIMEOUT_SECONDS)
        at.run()
        assert not at.exception

        # Shrink to a 2-cabin roster before regenerating so the real solve proves
        # optimality fast; the full 8-cabin default can hit the solver time/gap limit
        # and return a non-OPTIMAL (still feasible) result.
        find_slider(at, "Number of cabins").set_value(2)
        at.run()

        # Regenerate the camper roster (and its relationships/join) through the form.
        find_button(at, "Simulate Campers").click()
        at.run()
        assert not at.exception

        click_assign(at)
        assert not at.exception
        poll_until_solution(at, SOLVE_TIMEOUT_SECONDS)

        _assert_both_export_tables_render(at)


@pytest.mark.slow
class TestUploadAssignExport:
    def test_upload_week_then_assign_renders_both_exports(self):
        """Upload a full week through the file_uploaders, solve for real, read exports."""
        at = AppTest.from_file(APP_SCRIPT, default_timeout=SOLVE_TIMEOUT_SECONDS)
        at.run()
        assert not at.exception

        # Replace the simulated defaults by uploading through the real widgets.
        find_seatrade_uploader(at).upload("seatrades.csv", SEATRADE_CSV)
        at.run()
        at.file_uploader(key="identity_uploader").upload("identity.csv", IDENTITY_CSV)
        at.run()
        at.file_uploader(key="prefs_uploader").upload("prefs.csv", PREFERENCES_CSV)
        at.run()
        assert not at.exception

        # Drop the stale simulated relationships (they reference the old roster). The
        # app re-seeds feasible ones for the uploaded campers, but the assign that
        # follows runs before that with no relationship constraints.
        del at.session_state["camper_relationships"]

        click_assign(at)
        assert not at.exception
        poll_until_solution(at, SOLVE_TIMEOUT_SECONDS)

        _assert_both_export_tables_render(at)
        # The export reflects the uploaded roster, not the simulated default.
        assert "Alice" in at.session_state["assigned_solution"].campers
