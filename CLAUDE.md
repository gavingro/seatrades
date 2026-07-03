# SeaTrades

A Streamlit app for Keats Camp seatrade scheduling.

## Quick Reference

- **Issue tracker:** GitHub Issues
- **Domain docs:** `CONTEXT.md` + `docs/adr/` at repo root.
- **Contributing and Development:** See `docs/CONTRIBUTING.md`

## Setup

This project uses a `.venv` virtual environment.
Check if it is already active with `which python`.

If not, activate it before running Python:

```bash
source .venv/bin/activate
```

## Testing

Run tests directly from the venv — no need to activate it first.

```bash
.venv/bin/pytest                    # fast loop — slow (real-solve) tests deselected by default
.venv/bin/pytest tests/test_foo.py  # single file
.venv/bin/pytest -k "test_bar"      # single test
.venv/bin/pytest -m slow            # the slow real-solve tests; run before pushing
```

The default run skips `@pytest.mark.slow` tests (real CBC solves) so the loop stays
fast — iterate on it, then run `-m slow` before you push. CI runs both. See "Fast loop
vs. slow tests" in `docs/CONTRIBUTING.md`.

## Seeing the app

Behavior is tested headlessly with Streamlit `AppTest`; visual checks use a real browser via the Playwright MCP server (`.mcp.json`). To launch and view the running app, see "Viewing the running app" in `docs/CONTRIBUTING.md`. Rationale: `docs/adr/0007-agent-visual-verification.md`.

## Documentation updates

Doc updates (`CONTEXT.md`, `docs/adr/`, etc.) are welcome in any PR. Don't skip them.

## Agent skills

- Issue tracker: `docs/agents/issue-tracker.md`
- Triage labels: `docs/agents/triage-labels.md`
- Domain docs: `docs/agents/domain.md`
