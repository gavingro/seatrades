# PRD: CSV Export for Assignments

## Problem Statement

The scheduling captain needs to export the seatrade assignments to share with camp staff and for record-keeping. Currently, the app only displays assignments visually in an Altair chart, with no way to download them as a CSV file that can be opened in Excel or Google Sheets.

## Solution

Keep the existing Altair visualization as the primary view. Add two table views using Streamlit's built-in `st.dataframe` component. Each dataframe includes a built-in CSV download button. Use a selectbox to switch between the two views after the chart.

### Why two views instead of three

The original design had three views (Captain's Book, Cabin Leaders, Seatrade Leaders). After QA review, the Cabin Leaders view was removed because it was identical to the Captain's Book in columns — only the sort order differed. The Captain's Book now supports both sort orders: the default cabin → camper sort, and the uploaded camper order (which is what the Cabin Leaders view would have provided).

### Why wide form for the Captain's Book

The original long-form layout displayed one row per camper-seatrade assignment, meaning each camper appeared on multiple rows. The wide-form layout puts each camper on one row with sub-block columns (1a, 1b, 2a, 2b), making it immediately clear which fleet and seatrade each camper is assigned to. This matches how the scheduling captain actually reads and distributes the data.

The sub-block notation encodes fleet assignment: "a" means the cabin does their seatrade first (then fleet time), "b" means fleet time first (then seatrade). Each camper fills exactly 2 of the 4 columns; the other 2 are blank.

## User Stories

1. As a scheduling captain, I want to download assignments as a CSV file, so that I can share them with camp staff and keep records
2. As a scheduling captain, I want to see each camper on one row with their seatrade assignments across sub-blocks, so that I can do my own logistics and bookkeeping
3. As a scheduling captain, I want to see assignments sorted by block → seatrade → cabin → camper, so that cabin leaders running the seatrade can take attendance
4. As a scheduling captain, I want to see a clear message when optimization fails, so that I understand the result isn't usable and can investigate the configuration

## Implementation Decisions

- **Module modified**: `seatrades_app/tabs/assignments_tab.py`
- **Keep existing**: Altair chart visualization (first in the tab)
- **Add new**: Two `st.dataframe` views after the chart (selectbox to switch between them)
- **Data source**: New wide-form wrangling method for Captain's Book; existing long-form method for Seatrade Leaders
- **CSV download**: Streamlit's `st.dataframe` automatically includes a download button; no additional code needed
- **Dead code removal**: Remove `get_view_selection()` and the Cabin Leaders view path

### View Specifications

| View | Shape | Sort Order | Columns |
|------|-------|------------|---------|
| Captain's Book | Wide (1 row/camper) | uploaded camper order (default: cabin → camper) | cabin, camper, Seatrade 1a, Seatrade 1b, Seatrade 2a, Seatrade 2b |
| Seatrade Leaders | Long (1 row/assignment) | block → seatrade → cabin → camper | block, seatrade, camper, cabin |

Sub-block columns (1a, 1b, 2a, 2b) encode fleet assignment. Each camper fills exactly 2 of 4 seatrade columns; the rest are blank. Preference ranks are omitted from both views.

### Failure Handling

- When optimization fails, display "Optimization not successful" message
- Do NOT show partial assignments (they are not trustworthy)
- Add to backlog: "Diagnose why optimization fails to converge (show helpful error messages)"

## Testing Decisions

- Test that Captain's Book produces wide-form with correct columns (cabin, camper, Seatrade 1a, Seatrade 1b, Seatrade 2a, Seatrade 2b)
- Test that each camper row has exactly 2 of 4 seatrade columns filled
- Test that Captain's Book sorts by cabin → camper when no `camper_order` is provided
- Test that Captain's Book sorts by uploaded camper order when `camper_order` is passed
- Test that passing `camper_order` with a missing camper raises `ValueError`
- Test that Seatrade Leaders sorts by block → seatrade → cabin → camper
- Test that Seatrade Leaders has no preference or assignment columns
- Test that CSV download produces valid CSV with correct column order
- Test that failure state shows appropriate message and no data

## Out of Scope

- Making assignment tables editable (read-only for MVP)
- Showing capacity utilization per seatrade
- Adding age constraint or gender safety constraint
- Multiple scenario comparison
- Help diagnosing why optimization failed (added to backlog)
- Preference rank display in exports (available in the Altair chart)

## Further Notes

- This is the minimum viable feature to make the app useful for a real scheduling captain
- The two-view approach covers the two distinct distribution use cases: internal bookkeeping (Captain's Book, wide form) and day-of attendance (Seatrade Leaders, long form)
- Wide form was chosen for the Captain's Book because it eliminates duplicate rows per camper and shows fleet assignment at a glance