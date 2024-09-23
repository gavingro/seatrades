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

- [ ] Mock cabin/camper/seatrade preferences using actual keats cabins/ages/genders and actual seatrades/sizes/popularity for better tooling.
- [ ] Introduce constraint such that only one girl cannot be assigned to a seatrade of all boys (is this actually a problem? Currently our strategy of keeping cabins together would prioritize assigning cabins together, which would include friends).
- [ ] Introduce camper/cabin age to optimizer to ensure each seatrade is approximately the same ages.
- [ ] Create demo web app.
- [ ] Introduce .csv import/export to web app.
- [ ] Allow for "temperature" knobs on optimizer cost function areas (preferences vs cabin vs age, etc).
- [ ] Implement basic visualization for seatrade preferences to allow for better seatrade config.
- [ ] Infer popularity of seatrade from preferences, and balance popuparity between protected categories (genders? Ages?). Eg) Tubing shouldn't be JUST senior boys in all 4 blocks or something.

### Implemented

- [x] Implement early stopping with timeouts and "good enough" solutions.
- [x] Basic Data structures to hold Cabin preferences and Seatrades configurations.
- [x] Basic Linear Programming Optimizer to maximize
camper preferences with ideal seatrade assignments.
- [x] Penalize assigning campers from the same cabin to different seatrades (eg reward friends being placed together).
- [x] Max cabin limits on a per-seatrade basis. Penalize OR constrain having too many campers of the same cabin assigned to the same seatrade.
- [x] Assign each camper to a block-1 or block-2 fleet time. This should be done in an optimal manner, perhaps as a first pass with a separate optimizer.
- [x] Introduce Genders to the cabins, and ensure each fleet is has roughly the same amount of girls and boys.
- [x] Use indicator function to count number of seatrades with non-zero member counts, and penalize for amount of total seatrades (encourage sparsity).
- [x] Add constraints on max-seatrades-per-block.

---

## Math

*TBC*
