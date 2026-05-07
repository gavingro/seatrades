# ADR 0005: Git Branching Strategy

**Date:** 2026-05-06
**Status:** Accepted

## Context

SeaTrades uses a shared GitHub account (`gavingro`) with branch protection on `main` (PR + 1 approval). Work is tracked as GitHub issues. Some features are large (PRD-level) and need QA as a coherent whole before merging to main. Previously, all branches were flat off main with no hierarchy.

## Decision

Adopt a tiered branching strategy with four branch patterns:

| Branch type | Prefix | Source | Merges into | Has PRD doc? | Lifecycle |
|---|---|---|---|---|---|
| Large feature (PRD) | `feature/13-csv-import` | `main` | `main` | Yes | Long-lived until QA complete |
| Dev (part of PRD) | `dev/42-csv-upload` | Parent `feature/` branch | Parent `feature/` branch | No (links to parent PRD issue) | Short-lived |
| Dev (standalone) | `dev/55-small-fix` | `main` | `main` | No | Short-lived |
| Bug fix | `fix/56-header-crash` | `main` | `main` | No | Short-lived |

The `dev/` prefix is for small-scope work regardless of target. A `dev/` branch sources from its parent `feature/` when it supports a PRD, or from `main` when standalone.

### Merge strategy

- **All merges use squash merge** — one clean commit per issue on the PRD branch, one clean commit per PRD on main.
- **All merges require a PR** — for traceability and auto-closing issues via GitHub keywords.
- **`dev/` → `feature/`**: PR created, self-merged (no approval required).
- **`dev/` → `main`**: PR created, requires approval (branch protection).
- **`feature/` → `main`**: PR created, requires approval (existing branch protection).
- **`fix/` → `main`**: PR created, requires approval (same as any merge to main).

### Syncing

Long-lived `feature/` branches stay current by **merging `main` into `feature/`** (not rebasing). This preserves history and avoids breaking any `dev/` branches based on the feature branch.

### Branch cleanup

- Delete remote branches after merge.
- Keep local branches around until manually cleaned up.

### Branch naming

All branches follow `{prefix}/{issue}-{name}` format. This is convention, not programmatically enforced.

### PRD branches as landing zones

Create a `feature/` branch when the PRD issue is opened, before any dev work starts. This gives incoming `dev/` branches a target to branch from and PR into. If a PRD is abandoned, delete the branch manually along with the issue.

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
- Empty feature branches may accumulate if PRDs are abandoned without cleanup.
- Squash-merge loses granular commit history (preserved in closed PRs on GitHub).