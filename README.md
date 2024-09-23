# seatrades

![Github Actions Workflow Status](https://github.com/gavingro/seatrades/actions/workflows/ci.yaml/badge.svg)

A tool to help assign seatrades at Keats Camps using math.

## Objective

> *Every week at Keats camp begins with hundreds of campers arriving to the island, learning about the seatrade activities they can pursue during the week, and selecting which seatrades they prefer. A scheduling captain then takes all of these preferences, parses through them, and assigns which camper gets to participate in which seatrade.*
>
> *This process takes the Scheduling captain dozens of hours.*
>
> *Our work here in this repository aims to provide the captain a tool to obtain optimal camper-seatrade assignments in a reasonable amount of time.*

## Roadmap

### Currently Implementing

### To Implement

- [ ] Introduce camper/cabin age to optimizer to ensure each seatrade is approximately the same ages.
- [ ] Create demo web app.
- [ ] Introduce .csv import/export to web app.
- [ ] Allow for "temperature" knobs on optimizer cost function areas (preferences vs cabin vs age, etc).
- [ ] Implement basic visualization for seatrade preferences to allow for better seatrade config.
- [ ] Implement seatrade selection for week. If problem is infeasible based on minimum seatrade numbers, remove least preferable seatrade and re-run.
- [ ] Infer popularity of seatrade from preferences, and balance popuparity between protected categories (genders? Ages?)
- [ ] Use indicator function to count number of seatrades with non-zero member counts, and penalize for amount of total seatrades (encourage sparsity).

### Implemented

- [x] Basic Data structures to hold Cabin preferences and Seatrades configurations.
- [x] Penalize assigning campers from the same cabin to different seatrades (eg reward friends being placed together).
- [x] Max cabin limits on a per-seatrade basis. Penalize OR constrain having too many campers of the same cabin assigned to the same seatrade.
- [x] Assign each camper to a block-1 or block-2 fleet time. This should be done in an optimal manner, perhaps as a first pass with a separate optimizer.
- [x] Introduce Genders to the cabins, and ensure each fleet is has roughly the same amount of girls and boys.

---

## Math

*TBC*
