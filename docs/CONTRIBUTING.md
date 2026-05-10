# Contributing to SeaTrades

## Branching Strategy

SeaTrades uses a three-pattern branching strategy. See [ADR 0005](docs/adr/0005-git-branching-strategy.md) for the full rationale.

### Branch types

| Type | Prefix | Source | Merges into | Has PRD doc? | Purpose |
|---|---|---|---|---|---|
| Large feature (PRD) | `feature/13-csv-import` | `main` | `main` | Yes | Long-lived: stages QA for a full PRD |
| Dev (standalone) | `dev/55-small-fix` | `main` | `main` | No | Short-lived: independent small work |
| Bug fix | `fix/56-header-crash` | `main` | `main` | No | Short-lived: bug fix |

Sub-issues of a PRD are **commits on the feature branch**, not separate branches. The `dev/` prefix is only for standalone work unrelated to any PRD.

### Merge rules

- **All merges use squash merge** — one clean commit per PRD or standalone unit of work.
- **All merges require a PR** — for traceability and auto-closing issues.
- `feature/` → `main`: requires approval (branch protection). One formal review at the end; informal mid-feature reviews are optional.
- `dev/` → `main`: requires approval (branch protection).
- `fix/` → `main`: requires approval (branch protection).

### Commit messages for sub-issues

Each sub-issue on a feature branch references its issue number in the commit message for GitHub auto-close (loose convention, e.g. `Implement CSV upload (#42)`). The final PR body can also close multiple issues at once using GitHub keywords.

### Branch naming

All branches follow `{prefix}/{issue}-{name}`. This is convention, not programmatically enforced.

### Syncing long-lived branches

When `main` moves ahead of a `feature/` branch, merge `main` into the `feature/` branch (do not rebase). This preserves history for in-progress work.

### Branch cleanup

- Delete remote branches after merge.
- Keep local branches until manually cleaned up.

### Example workflow

```
main
 ├── feature/13-csv-import          ← PRD branch (created when issue opens, long-lived)
 │     commit: "Implement CSV upload (#42)"
 │     commit: "Add CSV validation (#43)"
 │     commit: "Handle CSV errors (#51)"
 │     (QA complete)
 ├── feature/13-csv-import PR → main (squash merge, approval required)
 │
 └── dev/55-small-fix              ← standalone, sources from main, PR → main (approval required)
```

## Development Workflow

1. Create a branch with the right prefix (`feature/`, `dev/`, or `fix/`). Source from the parent branch — `main` for standalone work, parent `feature/` for PRD work.
2. Make commits with clear messages.
3. Open a PR targeting the correct branch (`main` for standalone `dev/`, `feature/`, and `fix/`; parent `feature/` for `dev/` supporting a PRD).
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

## Development Setup

Activate the virtual environment and install dev dependencies:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Dev dependencies include: `ruff`, `mypy`, `pandas-stubs`, `types-PyYAML`, `pandera[mypy]`, `pre-commit`, `pytest`, `pytest-cov`.

Install pre-commit hooks (runs automatically on every commit):

```bash
pre-commit install
```

## Linting & Type Checking

Run these before pushing. CI enforces all of them:

```bash
ruff check .          # lint
ruff format .         # auto-format
mypy .                # type check
pytest                # tests
pre-commit run --all-files  # all of the above via hooks
```

CI runs two parallel jobs: **lint** (ruff + mypy) and **test** (pytest). Both must pass.

### Pandera type suppressions

Mypy doesn't fully understand pandera `DataFrameModel` subclasses — they're DataFrames at runtime but mypy can't verify DataFrame method access on them. When working with pandera models, use targeted `# type: ignore` comments and document each suppression at the module level:

```python
"""Module docstring.

Pandera mypy suppressions:
- type: ignore[attr-defined] on .set_index(): pandera DataFrameModel subclasses
  are DataFrames at runtime but mypy doesn't recognize set_index as a valid method.
- type: ignore[index] on bracket indexing: same root cause.

Revisit if pandera mypy plugin improves or pandas-stubs adds DataFrameModel support.
"""
```

This keeps suppressions discoverable and easy to clean up when pandera's type support improves.

## Documentation

- Domain glossary: `CONTEXT.md`
- ADRs: `docs/adr/`
- PRDs: `docs/prd/`
