# ADR 0005: Git Branching Strategy

**Date:** 2026-05-06
**Updated:** 2026-05-10
**Status:** Accepted

## Context

SeaTrades uses a shared GitHub account (`gavingro`) with branch protection on `main` (PR + 1 approval). Work is tracked as GitHub issues. Some features are large (PRD-level) and need QA as a coherent whole before merging to main.

We initially adopted a tiered branching model with `dev/` branches forking off `feature/` branches for each sub-issue. In practice, creating a separate branch and PR for every small sub-issue was tedious and slowed the working rhythm. Sub-issues are now implemented as commits directly on the feature branch instead.

## Decision

Adopt a three-pattern branching strategy:

| Branch type | Prefix | Source | Merges into | Has PRD doc? | Lifecycle |
|---|---|---|---|---|---|
| Large feature (PRD) | `feature/13-csv-import` | `main` | `main` | Yes | Long-lived until QA complete |
| Dev (standalone) | `dev/55-small-fix` | `main` | `main` | No | Short-lived |
| Bug fix | `fix/56-header-crash` | `main` | `main` | No | Short-lived |

Sub-issues of a PRD are implemented as **commits on the feature branch**, not as separate `dev/` branches. The `dev/` prefix is only for standalone small work unrelated to any PRD.

### Sub-issue commits on feature branches

Each sub-issue is a commit on the feature branch. Commit messages reference the issue number for GitHub auto-close (loose convention, e.g. `Implement CSV upload (#42)`). The final PR body can also close multiple issues at once using GitHub keywords.

### Merge strategy

- **All merges use squash merge** — one clean commit per PRD on main, one clean commit per standalone dev/fix on main.
- **All merges require a PR** — for traceability and auto-closing issues via GitHub keywords.
- **`feature/` → `main`**: PR created, requires approval (branch protection). One formal review at the end; informal mid-feature reviews are optional.
- **`dev/` → `main`**: PR created, requires approval (branch protection).
- **`fix/` → `main`**: PR created, requires approval (branch protection).

### Syncing

Long-lived `feature/` branches stay current by **merging `main` into `feature/`** (not rebasing). This preserves history and avoids breaking in-progress work.

### Branch cleanup

- Delete remote branches after merge.
- Keep local branches around until manually cleaned up.

### Branch naming

All branches follow `{prefix}/{issue}-{name}` format. This is convention, not programmatically enforced.

### PRD tracking

PRDs are tracked as GitHub issues. No milestones for now.

## Consequences

### Positive

- QA can validate a full feature before it reaches main.
- Simpler workflow — no sub-branch management for PRD work.
- Commit-per-sub-issue on feature branches keeps history readable.
- PRs auto-close issues, keeping the tracker current.
- Fewer branches and PRs to manage.

### Negative

- Long-lived feature branches can drift from main and require merge commits to sync.
- More branch management overhead than trunk-based development.
- Sub-issue work on feature branches is unreviewed until the final PR (informal mid-feature reviews are optional, not required).
- Squash-merge loses granular commit history (preserved in closed PR on GitHub).
- Empty feature branches may accumulate if PRDs are abandoned without cleanup.
