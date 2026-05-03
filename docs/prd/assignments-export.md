# PRD: CSV Export for Assignments

## Problem Statement

The scheduling captain needs to export the seatrade assignments to share with camp staff and for record-keeping. Currently, the app only displays assignments visually in an Altair chart, with no way to download them as a CSV file that can be opened in Excel or Google Sheets.

## Solution

Keep the existing Altair visualization as the primary view. Add three table views using Streamlit's built-in `st.dataframe` component, each with a different sort order and column arrangement. Each dataframe includes a built-in CSV download button. Use a selectbox to switch between the three views.

## User Stories

1. As a scheduling captain, I want to download assignments as a CSV file, so that I can share them with camp staff and keep records
2. As a scheduling captain, I want to see assignments sorted by camper (in upload order), so that I can do my own logistics and bookkeeping
3. As a scheduling captain, I want to see assignments sorted by cabin → block → camper, so that I can distribute to cabin leaders for their campers
4. As a scheduling captain, I want to see assignments sorted by block → seatrade → cabin → camper, so that cabin leaders running the seatrade can take attendance
5. As a scheduling captain, I want to see a clear message when optimization fails, so that I understand the result isn't usable and can investigate the configuration
6. As a scheduling captain, I want to switch between views easily, so that I can find the right format for the right audience

## Implementation Decisions

- **Module modified**: `seatrades_app/tabs/assignments_tab.py`
- **Keep existing**: Altair chart visualization (first in the tab)
- **Add new**: Three `st.dataframe` views after the chart
- **Navigation**: Use Streamlit `selectbox` to switch between the three dataframe views
- **Data source**: Use existing `wrangle_assignments_to_longform()` method which produces columns: camper, seatrade, assignment, preference, cabin, block
- **CSV download**: Streamlit's `st.dataframe` automatically includes a download button; no additional code needed
- **Dead code removal**: Removed unused `export_assignments_to_csv()` stub from `seatrades/seatrades.py`

### View Specifications

| View | Sort Order | Column Order |
|------|------------|--------------|
| A: Captain's Book | camper (upload order) | camper, cabin, block, seatrade, assignment, preference |
| B: Cabin Leaders | cabin → block → camper | cabin, block, camper, seatrade, assignment, preference |
| C: Seatrade Leaders | block → seatrade → cabin → camper | block, seatrade, cabin, camper, assignment, preference |

### Failure Handling

- When optimization fails, display "Optimization not successful" message
- Do NOT show partial assignments (they are not trustworthy)
- Add to backlog: "Diagnose why optimization fails to converge (show helpful error messages)"

## Testing Decisions

- Test that View A preserves camper upload order
- Test that View B groups correctly by cabin, then block
- Test that View C groups correctly by block, then seatrade, then cabin
- Test that CSV download produces valid CSV with correct column order
- Test that failure state shows appropriate message and no data
- Prior art: The existing Altair chart display can serve as a reference for data correctness

## Out of Scope

- Making assignment tables editable (read-only for MVP)
- Showing capacity utilization per seatrade
- Adding age constraint or gender safety constraint
- Multiple scenario comparison
- Help diagnosing why optimization failed (added to backlog)

## Further Notes

- This is the minimum viable feature to make the app useful for a real scheduling captain
- The three-view approach covers all the distribution use cases: internal bookkeeping (A), cabin distribution (B), and seatrade day-of attendance (C)
- Column reordering ensures the sort keys are visible first when viewing the CSV in Excel