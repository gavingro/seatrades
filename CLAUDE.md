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

Run tests with `pytest` (not `python -m pytest`). The venv provides a `pytest` binary directly.

```bash
pytest                    # full suite
pytest tests/test_foo.py  # single file
pytest -k "test_bar"      # single test
```

## Documentation updates

Doc updates (`CONTEXT.md`, `docs/adr/`, etc.) are welcome in any PR. Don't skip them.

## Agent skills

- Issue tracker: `docs/agents/issue-tracker.md`
- Triage labels: `docs/agents/triage-labels.md`
- Domain docs: `docs/agents/domain.md`
