# ADR 0005: Git Branching Strategy

**Date:** 2026-05-06
**Status:** Accepted

## Context

SeaTrades uses a shared GitHub account (`gavingro`) with branch protection on `main` (PR + 1 approval). Work is tracked as GitHub issues. Some features are large (PRD-level) and need QA as a coherent whole before merging to main. Previously, all branches were flat off main with no hierarchy.

## Decision

Adopt a tiered branching strategy with three branch prefixes:

| Branch type | Prefix | Source | Merges into | Lifecycle |
|---|---|---|---|---|
| PRD / large feature | `feature/13-csv-import` | `main` | `main` | Long-lived until QA complete |
| Issue (part of PRD) | `dev/42-csv-upload` | Parent `feature/` branch | Parent `feature/` branch | Short-lived |
| Standalone feature | `feature/55-add-thing` | `main` | `main` | Short-lived |
| Bug fix | `fix/56-header-crash` | `main` | `main` | Short-lived |

### Merge strategy

- **All merges use squash merge** — one clean commit per issue on the PRD branch, one clean commit per PRD on main.
- **All merges require a PR** — for traceability and auto-closing issues via GitHub keywords.
- **`dev/` → `feature/`**: PR created, self-merged (no approval required).
- **`feature/` → `main`**: PR created, requires approval (existing branch protection).
- **`fix/` → `main`**: PR created, requires approval (same as any merge to main).

### Syncing

Long-lived `feature/` branches stay current by **merging `main` into `feature/`** (not rebasing). This preserves history and avoids breaking any `dev/` branches based on the feature branch.

### Branch cleanup

- Delete remote branches after merge.
- Keep local branches around until manually cleaned up.

### PRD tracking

PRDs are tracked as GitHub issues. No milestones for now.

## Consequences

### Positive

- QA can validate a full feature before it reaches main.
- New issues discovered during QA can be added to the PRD branch mid-flight.
- One commit per issue on PRD branches keeps history readable.
- PRs auto-close issues, keeping the tracker current.

### Negative

- Long-lived feature branches can drift from main and require merge commits to sync.
- More branch management overhead than trunk-based development.
- Squash-merge loses granular commit history (preserved in closed PRs on GitHub).