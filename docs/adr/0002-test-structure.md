# ADR 0002: Unit Test Structure

**Date:** 2026-05-02
**Status:** Accepted

## Context

We need a consistent convention for where Python unit tests live and how they're organized as the codebase grows.

## Decision

Tests mirror code directory structure — one test file per Python module, with a test package (directory) for each code package. Split test files live alongside the original within the same package.

## Details

- `seatrades/seatrades.py` → `tests/test_seatrades/test_seatrades.py`
- `seatrades/results.py` → `tests/test_seatrades/test_results.py`
- `seatrades_app/tabs/campers_tab.py` → `tests/test_seatrades_app/test_campers_tab.py`
- Use Classes for stict unit tests within a function. my_function() is unit tested in a TestMyFuncion class.

### Fixtures and conftest.py

- Wherever possible, identify where data can be reused between unit tests, and extract to a module level fixtures.
- Fixtures start in the same test file as they are used in (eg, test_module.py), until we identify that they can be reused in a different file as well. If there are 3 files that could use the same file-level fixtures, we extract to a conftext.py at the module level.
- One `conftest.py` per test package, created when fixture groups diverge (3+ distinct groups)
- Fixtures start as raw data (dict/DataFrame) inline, refactored to factories if they grow unwieldy

### Split Trigger

When a test file grows beyond what one file can handle, split along conceptual boundaries or when fixture divergence occurs (3+ distinct groups). When splitting, the original `test_<module>.py` stays in the package alongside new split files.

### No Formal Unit/Integration Split

Keep tests flat. Add `test_<module>_integration.py` at the package level when a test spans submodules.

### Running Tests

Run via `pytest` CLI only (no nox/tox for now).

## Out of Scope (Noted for Later)

- App-level/UI tests (Streamlit components)
- Pandera schema validation in tests
