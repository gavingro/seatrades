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

Run tests directly from the venv — no need to activate it first:
```bash
.venv/bin/pytest
```

### Fast loop vs. slow tests

The default `.venv/bin/pytest` is already the **fast loop**: `pyproject.toml` sets
`addopts = "... -m 'not slow'"`, so every `@pytest.mark.slow` test (the ones that run
a real CBC solve end-to-end — minutes, not seconds) is deselected by default. Iterate
on this; you get the full non-solve suite, including the headless `AppTest` integration
tests, in seconds.

Only pay for the slow tests when it matters — **before pushing** (and CI runs them for you):
```bash
.venv/bin/pytest            # fast loop — slow tests deselected; use while iterating
.venv/bin/pytest -m slow    # the real-solve tests; run before you push
.venv/bin/pytest -m ''      # everything (fast + slow), overriding the default filter
```
CI runs both selections, so a green fast loop plus one `-m slow` pass before pushing
matches what CI will check. When you add a test that runs a real solve (or is otherwise
expensive), mark it `@pytest.mark.slow` so the fast loop stays fast.

### Behavior vs. visual verification

Two layers, two tools — see [ADR 0007](adr/0007-agent-visual-verification.md) for the why.

- **Behavior** is verified headlessly with Streamlit's `AppTest` (`streamlit.testing.v1`) and runs in CI. Automate as much point-and-click as possible here — it's fast and cannot render, so it covers logic and state, not pixels.
- **Visual / exploratory** checks (does the Altair chart actually draw, is the layout intact) need a real browser. An agent does this live via the **Playwright MCP** server wired in `.mcp.json` — there is no scripted browser suite and CI runs no browser tests.

### Viewing the running app (Playwright MCP)

One-time prerequisite — install the browser the MCP server drives. `.mcp.json` pins `--browser chromium`, which playwright-mcp resolves to its **chrome-for-testing** build; install it with the MCP's *own* installer (no `sudo`). Note: a plain `npx playwright install chromium` is *not* enough — it fetches a headless-shell the MCP won't use.

```bash
npx @playwright/mcp@latest install-browser chrome-for-testing
```

Launch the app for the browser to hit (headless flag stops Streamlit opening its own browser tab):

```bash
.venv/bin/streamlit run app.py --server.headless true --server.port 8501
```

Then point the Playwright MCP browser at `http://localhost:8501`. Notes for whoever (or whatever) is looking:

- On first load a **welcome modal** ("Welcome to the Keats Seatrade Scheduler") overlays the app. Dismiss it (click "Don't show this again." or the ✕) before the tabs are reachable.
- On load the app **auto-seeds mock data** (`_initial_page_setup` in `app.py`), so the setup tabs are populated immediately (underneath the modal).
- The **Assignments** tab is empty until you trigger the solve — click through and run it before expecting assignments to show.
- Prefer the **accessibility snapshot** (`browser_snapshot`) over screenshots — it's more informative and is the only thing you can act on. Use a screenshot only to confirm something genuinely visual.

#### Gotchas

Each of these was found by actually driving the browser — none would surface in an `AppTest`:

- **Wrong browser binary.** playwright-mcp defaults to the system-Chrome channel (`npx playwright install chrome`), which needs `sudo`. We pin `--browser chromium` in `.mcp.json` instead — but that resolves to a **chrome-for-testing** build installed by the MCP's *own* `install-browser` command. A plain `npx playwright install chromium` installs a headless-shell the MCP won't use, so navigation still fails. Use the command above.
- **Welcome modal blocks everything.** First load shows a "Welcome to the Keats Seatrade Scheduler" dialog over the whole app. `browser_navigate` succeeds but every tab/button is unclickable until you dismiss it ("Don't show this again." or ✕).
- **Config changes need a session restart.** Editing `.mcp.json` (e.g. the `--browser` flag) has no effect until Claude Code restarts — the MCP server is spawned once at session start. A mid-session edit looks applied but isn't.
- **Browser output is git-noise.** The MCP writes snapshots/screenshots to `.playwright-mcp/` (and screenshots may land at repo root). Both are gitignored; don't commit them.

## Development Setup

Activate the virtual environment and install dev dependencies:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Dev dependencies include: `ruff`, `mypy`, `pandas-stubs`, `types-PyYAML`, `pandera[mypy]`, `pre-commit`, `pytest`, `pytest-cov`.

Requires Python **3.10+** (matches CI and `pyproject.toml`'s `requires-python`).

### Regenerating `requirements.txt`

`requirements.txt` is a fully pinned runtime lock (no dev tools). To bump a
runtime dependency, regenerate it under **Python 3.10** (CI's version) so the
pins match what CI installs — a lock frozen under a newer Python resolves to
versions that may not install on 3.10:

```bash
# fresh Python 3.10 venv, then:
pip install <the deps from pyproject [project].dependencies, with your bump pinned>
pip freeze > requirements.txt   # then drop any local/editable (-e) self line
```

To move **only one** dependency without dragging everything else forward, hold
the current pins as constraints and let just the target (and its required
transitive deps) move — see `docs/adr/0009-streamlit-floor-apptest-file-uploader.md`.

Install pre-commit hooks (runs automatically on every commit):

```bash
pre-commit install
```

## Linting & Type Checking

Run these before pushing. CI enforces all of them:

```bash
.venv/bin/ruff check .          # lint
.venv/bin/ruff format .         # auto-format
.venv/bin/mypy .                # type check
.venv/bin/pytest                # tests
.venv/bin/pre-commit run --all-files  # all of the above via hooks
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
