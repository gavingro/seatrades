# Contributing to SeaTrades

## Branching Strategy

SeaTrades uses a tiered branching strategy. See [ADR 0005](docs/adr/0005-git-branching-strategy.md) for the full rationale.

### Branch types

| Type | Prefix | Source | Merges into | Purpose |
|---|---|---|---|---|
| PRD / large feature | `feature/13-csv-import` | `main` | `main` | Long-lived: stages QA for a full PRD |
| Issue (part of PRD) | `dev/42-csv-upload` | Parent `feature/` | Parent `feature/` | Short-lived: one issue, one PR |
| Standalone feature | `feature/55-add-thing` | `main` | `main` | Short-lived: independent feature |
| Bug fix | `fix/56-header-crash` | `main` | `main` | Short-lived: bug fix |

### Merge rules

- **All merges use squash merge** — one clean commit per unit of work.
- **All merges require a PR** — for traceability and auto-closing issues.
- `dev/` → `feature/`: self-merge (no approval needed on PRD branches).
- `feature/` → `main`: requires approval (branch protection).
- `fix/` → `main`: requires approval (branch protection).

### Syncing long-lived branches

When `main` moves ahead of a `feature/` branch, merge `main` into the `feature/` branch (do not rebase). This preserves history for any `dev/` branches based on it.

### Branch cleanup

- Delete remote branches after merge.
- Keep local branches until manually cleaned up.

### Example workflow

```
main
 └── feature/13-csv-import          ← PRD branch (long-lived)
       ├── dev/42-csv-upload         ← issue branch, PR → feature/13
       ├── dev/43-csv-validation     ← issue branch, PR → feature/13
       └── dev/51-csv-error-handling ← added during QA, PR → feature/13
       (QA complete)
 └── feature/13-csv-import PR → main (squash merge, approval required)
```

## Development Workflow

1. Create a branch with the right prefix (`feature/`, `dev/`, or `fix/`).
2. Make commits with clear messages.
3. Open a PR targeting the correct branch (`main` for `feature/` and `fix/`, parent `feature/` for `dev/`).
4. Gavin reviews and merges in GitHub UI.

## Git / GitHub Setup

### Shared Credentials

Gavin and Claude share the same GitHub credentials (`gavingro` account). This has implications:

- All commits show "Gavin Grochowski" as author
- All PRs show "gavingro" as creator
- **Neither can approve their own PRs** — GitHub sees the same account as both creator and reviewer

### Branch Protection

The `main` branch has a ruleset requiring:
- Pull request before merging
- 1 approval

Since credentials are shared, Gavin must manually review and merge in GitHub UI:

1. Claude creates branch and PR via CLI
2. Gavin reviews in GitHub UI
3. Gavin clicks "Approve" then "Merge"

**Do NOT attempt to bypass protection** — `--admin` flag, self-approval, and API workarounds will all fail.

## Code Style

- Default to no comments — let code be self-documenting
- Small, focused commits
- Follow existing patterns in the codebase
- No AAA phase labels in tests (`# Arrange`, `# Act`, `# Assert`) — the structure is implied by the code. Test names should make the scenario clear; if something needs explaining, put it in the docstring, not a phase comment.

## Testing

Run tests with:
```bash
pytest
```

## Documentation

- Domain glossary: `CONTEXT.md`
- ADRs: `docs/adr/`
- PRDs: `docs/prd/`