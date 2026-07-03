# Streamlit floor raised to 1.58.0 to unlock AppTest `file_uploader`

The app's upload workflows (camper identity, camper preferences, seatrade preferences, friends) all go through `st.file_uploader`. Until now they could only be tested by writing straight to `st.session_state`, bypassing the widget — because the pinned Streamlit (1.50.0) had no `AppTest` support for `file_uploader`. This raises the version floor so those flows can be driven headlessly, and is the step-0 prerequisite for the #70 app-integration tests (upload stories 5–7).

**Status: accepted**

## Context

`streamlit.testing.v1.AppTest` gained a `file_uploader` property with a `set_value((filename, content, mime_type))` injection path in **Streamlit 1.56.0** (released 2026-03-31, [PR #14341](https://github.com/streamlit/streamlit/pull/14341) / [issue #8093](https://github.com/streamlit/streamlit/issues/8093)). This is the verified minimum — confirmed against the official [2026 release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2026), not guessed. (Issue #86 estimated "~1.54"; that estimate was wrong.)

We pin to **1.58.0** (latest 2026 release, 2026-05-28) rather than the 1.56.0 floor, to also pick up the 1.57.0 AppTest additions (`pills`, `segmented_control`, `dataframe` key lookups) as headroom for later slices, at the cost of a slightly larger upgrade jump.

A throwaway spike confirmed the mechanism against the real app: `AppTest.from_file("app.py").run()`, then `at.file_uploader(key="identity_uploader").set_value(("campers.csv", csv_bytes, "text/csv")).run()`, lands the parsed DataFrame in `st.session_state["camper_identity"]`. The spike code is not committed (per #86).

## Decision

1. **Pin `streamlit==1.58.0`** in `requirements.txt` (up from `1.50.0`). `pyproject.toml` keeps `streamlit` unconstrained; `requirements.txt` is the lock CI actually installs.

2. **Regenerate the lock as a minimal, constrained diff — not an unconstrained `pip freeze`.** `requirements.txt` is a full runtime freeze, so the regeneration holds every existing pin as a constraint and lets only Streamlit and its *strictly required* transitive deps move:
   - **Bumped:** `streamlit` 1.50.0 → 1.58.0.
   - **Added** (Streamlit 1.58's ASGI server stack, replacing tornado): `anyio`, `exceptiongroup` (anyio needs it on Python < 3.11), `h11`, `httptools`, `itsdangerous`, `python-multipart`, `starlette`, `uvicorn`, `websockets`.
   - **Removed:** `tornado`, `importlib_metadata` (no longer in Streamlit's closure).
   - **Held at current versions:** `pandera` 0.26.1, `altair` 5.5.0, `pandas` 2.3.3, `numpy` 2.0.2, `pydantic` 2.13.3, `protobuf` 6.33.6, and the rest. Streamlit 1.58's own constraints (`altair<7`, `numpy<3`, `pandas<4`, `protobuf<8`, …) are loose enough that none of these need to move.

   Reproduce with: in a clean venv, `pip download --python-version 310 --only-binary=:all: -c <old-requirements-as-constraints> pandera pandas pulp altair "streamlit==1.58.0" faker`, then read the resolved wheel versions. (Generating a Python-3.10 lock from a different host Python requires care: `--python-version 310` sets wheel-compat tags but evaluates `python_version` environment markers against the *running* interpreter, so marker-gated deps like `exceptiongroup` must be pulled in explicitly.)

3. **Python floor is effectively 3.10.** Streamlit 1.58.0 requires `python >=3.10`. This matches `pyproject.toml` (`requires-python >=3.10`) and CI (Python 3.10). Local `.venv`s still on Python 3.9 must be recreated on 3.10+.

## Why not just bump the one `streamlit==` line?

Because `requirements.txt` is a full pinned closure. Editing only the Streamlit line would leave the old transitive pins in place — including `tornado`, which Streamlit 1.58 no longer uses, and omitting the new ASGI deps Streamlit 1.58 requires — producing an inconsistent, unresolvable lock.

## Why not a plain `pip freeze` of a fresh install?

An unconstrained resolution bumps *everything* to latest: it dragged `pandera` 0.26.1 → 0.32.1, `altair` 5 → 6, `protobuf` 6 → 7, `pydantic`, etc. The `pandera` bump alone changed validation-error surfacing (`SchemaError` → lazy `SchemaErrors`) and broke tests — churn and regression risk unrelated to the `file_uploader` goal. Holding the existing pins keeps the diff to "Streamlit and what Streamlit needs."

## Why not pin to the 1.56.0 minimum?

1.56.0 is the smallest bump that unlocks `file_uploader`, but 1.58.0 additionally unlocks AppTest for `pills`, `segmented_control`, and `dataframe` key lookups (1.57.0) — reach we expect later slices to use. The marginal extra upgrade surface is acceptable given the constrained, minimal lock above.

## Consequences

- **Unlocked now:** headless testing of every `st.file_uploader` flow (camper identity/preferences, seatrade preferences, friends) via `AppTest` — the point of this change. #70 upload stories 5–7 are now writable.
- **Unlocked as headroom:** AppTest `pills` / `segmented_control` / `dataframe` key lookups (1.57.0). `data_editor`-driven relationship editing on the Friends tab is a plausible follow-up but is **not** yet covered — it would need its own verification.
- **Verification gate is CI (Python 3.10).** All Streamlit-touching tests (the AppTest tab tests and the slow end-to-end smoke, `tests/test_app/test_app_smoke.py`) pass on Streamlit 1.58.0. The suite must be confirmed green on CI's Python 3.10 with this exact lock — `.venv/bin/pytest` and `.venv/bin/pytest -m slow`.
- **Deprecation warnings to watch (not failures):** the app's `use_container_width=` (Streamlit is migrating to `width=`), pandera's `import pandera` (moving to `import pandera.pandas`), and PuLP 4.0 deprecations. None block this change; each is a candidate for a later cleanup.
