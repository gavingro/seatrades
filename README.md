# Seatrades

![Github Actions Workflow Status](https://github.com/gavingro/seatrades/actions/workflows/ci.yaml/badge.svg)

A scheduling tool that assigns campers to seatrade activities at Keats Camps using mathematical optimization.

## Demo

Try it live: [https://keats-seatrades.streamlit.app/](https://keats-seatrades.streamlit.app/)

The app opens pre-loaded with mock data, so you can hit **Assign Seatrades** and see a full schedule immediately — no setup required.

## What it does

Every week, Keats Camps hosts ~250 campers across ~22 cabins. On the first day, each camper submits their top seatrade preferences, and the Scheduling Captain must sort every camper into two fleets and their preferred activities — dozens of hours of manual work. Seatrades automates this by:

1. **Configuring** seatrades (capacity per session)
2. **Configuring** campers (cabin, gender, age, ranked preferences)
3. **Pairing** campers who should (or shouldn't) end up together
4. **Optimizing** assignments to balance camper preferences, cabin cohesion, staffing load, and age grouping
5. **Reviewing** the schedule and a quality report card, then exporting it

## Key terms

- **Seatrade** — an activity offered at camp (Sailing, Kayaking, …).
- **Fleet** — a time-of-day grouping: Fleet 1 = Morning, Fleet 2 = Afternoon.
- **Block** — one of the 4 time slots in a week (`1a`, `1b`, `2a`, `2b`): the digit is the half of the week, the letter is the fleet.
- **Session** — a seatrade running in a specific fleet + block (e.g. "Sailing in 1a"). Each camper gets two sessions per week.
- **Fleet Time** — the large-group activity a cabin does in the slot it isn't on a seatrade.

## How to Use

The app has five tabs.

### 1. Assignments

Where you run the optimizer and read the results. Click **Assign Seatrades** and a live progress bar tracks the solve (the solver log is available in an expander if you want the detail). When it finishes you get:

- **The Schedule**
    - **Fleet Assignments** — a Cabin × Block grid showing each cabin's week at a glance (on a Seatrade vs. on Fleet Time).
    - **Seatrade Staffing Schedule** — a Seatrade × Block grid of which seatrades run each block; a fully "Not offered" row is a seatrade nobody picked.
    - **Master grid** — every camper's two assignments, colored by satisfaction (green = 1st-choice pick → red = lower-ranked), with each camper's submitted preference numbers shown.
- **Schedule Quality** — a report card scoring the schedule across six independent goals (see below), plus a Solver Optimality gauge. Pick "Overview" for the summary or drill into any single area.
- **Assignment Data** — the exportable table, viewable **By Camper** or **By Seatrade**.

### 2. Seatrade Setup

Configure the available seatrade activities. Upload a CSV or use the built-in simulator. For each seatrade, set:

- Name
- Minimum campers per session (0 = the session may run empty / not at all)
- Maximum campers per session

### 3. Camper Setup

Configure the campers and their preferences. Upload a CSV or use the built-in simulator. For each camper, set:

- Name
- Cabin assignment
- Gender
- Age
- Four ranked seatrade preferences (required)

### 4. Friends

Pair up campers with a relationship. Type rows directly in the grid or upload a CSV. All three types are hard constraints enforced by the solver:

- **Besties** — the pair gets an identical schedule (both sessions shared)
- **Friends** — the pair shares at least one session
- **Frenemies** — the pair shares no sessions

Besties and friends need enough overlap in their preferred seatrades to be satisfiable; the app flags an infeasible pair (naming both campers) before you optimize.

### 5. Scheduling Setup

Tune how the optimizer balances competing priorities. The main sliders are **soft preferences** the optimizer trades off against each other:

- **Give Campers their Favourite Picks** — push for #1–2 ranked seatrades
- **Keep Cabinmates Together** — cabin cohesion / easier supervision
- **Fewer seatrades to staff** — run fewer distinct seatrades (less staffing load)
- **Keep similar ages together** — group similar-aged campers within sessions and fleets

**Advanced settings** add hard limits and solver controls: max seatrades per fleet, the age-grouping balance (fleet-wide ↔ per-session), a toggle to keep each cabin in the same fleet all week (the hand-scheduled arrangement), minimum solution quality, and the solver time limit.

## Schedule Quality metrics

After each solve the app scores the schedule (higher is always better) across:

- **Preference** — % of campers who got a #1 pick in at least one session
- **Cohesion** — % of campers with a cabinmate in their session(s)
- **Sparsity** — how few of the available seatrades you have to staff
- **Age spread** — how close in age the campers in each seatrade are
- **Within-cabin fairness** — did everyone in a cabin get similarly good picks?
- **Between-cabin fairness** — did some whole cabins get better picks than others?

## Tech Stack

- **Frontend:** Streamlit (Python)
- **Optimizer:** Mixed-integer linear programming (PuLP + CBC)
- **Deployment:** Streamlit Cloud (free, public)

## Deployment

For MVP user testing: deploy from `main` to streamlit cloud, not from feature branches. This ensures:

- Stable, tested code reaches users
- CI runs on merge to `main` before deployment
- Clear release points for feedback

Streamlit Cloud is configured to auto-deploy on push to `main`.

## Development

See `docs/CONTRIBUTING.md` for setup and testing, `CONTEXT.md` for the domain glossary, and `docs/adr/` for architecture decisions.

## License

MIT
