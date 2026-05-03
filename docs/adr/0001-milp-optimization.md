# ADR 0001: Mixed-Integer Linear Programming for Seatride Scheduling

**Date:** 2023-02-03
**Status:** Accepted

## Context

The problem requires assigning hundreds of campers to seatrade activities while satisfying multiple constraints:
- Camper preferences (ranked 1-4)
- Cabin groupings
- Fleet and gender balance
- Seatride capacity limits

## Decision

We use PuLP (a Python mixed-integer linear programming library) to solve this as an MILP problem.

### Why MILP?

1. **Constraint satisfaction** - MILP natively handles hard constraints (capacity, balance requirements) without needing heuristic workarounds
2. **Optimality** - Guarantees finding the best solution given the objective function
3. **Flexibility** - Easy to add/modify constraints (e.g., fleet balance, cabin max per seatrade)
4. **Fast enough** - Problem size (~hundreds of campers, ~4-8 seatrades) solves in seconds

### Alternatives Considered

- **Greedy algorithm**: Fast but produces poor solutions; can't balance competing objectives
- **Genetic algorithms**: Can handle constraints but no optimality guarantee; harder to debug
- **Constraint programming (CP-SAT)**: Also viable, but PuLP was more familiar

## Consequences

### Positive
- Optimal solutions guaranteed
- Easy to modify weights and constraints
- Well-tested solver (CBC) handles edge cases

### Negative
- Solver time scales worse than linear with problem size
- Requires careful constraint tuning to avoid infeasibility
- Less intuitive than greedy for debugging

## Implementation Notes

The solver uses binary decision variables:
- `camper_assignments[camper][seatrade_block]` - Did camper get assigned this seatrade in this block?
- `cabin_assignments[cabin][seatrade_block]` - Is any camper from cabin in this seatrade?
- `fleet_assignment[cabin][fleet]` - Which fleet is this cabin assigned to?

See `seatrades/seatrades.py` for the full constraint and objective formulation.