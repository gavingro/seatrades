# Seatrades

![Github Actions Workflow Status](https://github.com/gavingro/seatrades/actions/workflows/ci.yaml/badge.svg)

A scheduling tool that assigns campers to seatrade activities at Keats Camps using mathematical optimization.

## Demo

Try it live: [https://keats-seatrades.streamlit.app/](https://keats-seatrades.streamlit.app/)

## What it does

The scheduling captain spends dozens of hours manually assigning hundreds of campers to their preferred seatrade activities each week. Seatrades automates this by:

1. **Configuring** seatrades (capacity, blocks, preferences)
2. **Configuring** campers (cabin assignments, demographics, preferences)
3. **Optimizing** assignments to maximize camper preferences while balancing cabin groupings, fleet gender balance, and age diversity
4. **Viewing** assignment results

## How to Use

The app has four tabs:

### 1. Assignments
View the optimized results. The app comes pre-loaded with demo data so you can immediately see the optimizer in action. Results update automatically when configuration changes:
- Assignments by camper
- Assignments by cabin
- Assignments by seatrade

### 2. Seatrade Setup
Configure the available seatrade activities. Upload a CSV or use the built-in simulator. For each seatrade, set:
- Name
- Minimum campers (0 = optional)
- Maximum campers per session

### 3. Camper Setup
Configure the campers and their preferences. Upload a CSV or use the built-in simulator. For each camper, set:
- Name
- Cabin assignment
- Gender
- Four seatrade preferences (required)

### 4. Optimization Setup
Adjust how the optimizer balances competing priorities:
- Preference weight (how much to prioritize camper choices)
- Cabin weight (how much to keep cabin groups together)
- Sparsity weight (reward for fewer seatrades per fleet)
- Timeout settings

## Current Limitations

- All 4 seatrade choices are required; campers cannot be assigned to an unselected seatrade
- No age constraint implemented yet — each seatrade may have age diversity

## Development Status

Core optimization is working with CSV import. Roadmap items and bugs are tracked in GitHub Issues.

### Next

- Export assignments to CSV
- Add age constraint to ensure seatrades have similar age ranges
- Add constraint: single girl can't be alone in a seatrade of all boys (and vice versa)

### Later

- Save multiple optimization scenarios for comparison
- Google Forms integration for preference collection
- Infer seatrade popularity from preferences and balance across protected categories

## Tech Stack

- **Frontend:** Streamlit (Python)
- **Optimizer:** Mixed-integer linear programming (PuLP)
- **Deployment:** Streamlit Cloud (free, public)

## License

MIT