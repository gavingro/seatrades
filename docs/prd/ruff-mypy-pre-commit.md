# PRD: Add ruff, mypy, and pre-commit hooks

## Problem Statement

SeaTrades has no linting, formatting, or type-checking enforcement. There's no pre-commit config, no CI lint step, and no mypy. This means style inconsistencies (unsorted imports, mixed quote styles, trailing whitespace) accumulate silently, and type errors are only caught at runtime or by manual review.

## Solution

Add ruff (lint + format), mypy (type checking), and pre-commit hooks. Configure ruff with a moderate rule set and line length 120. Run `ruff format` on the existing codebase once. Start lint rules as warnings (non-blocking) so violations are visible but don't block development. Add a GitHub Actions workflow step to enforce ruff and mypy in CI.

## User Stories

1. As a developer, I want `ruff format` to run on every commit, so that code style is consistent without manual effort.
2. As a developer, I want `ruff check` to run on every commit, so that lint violations are caught before they reach CI.
3. As a developer, I want trailing whitespace and missing newlines fixed on commit, so that diff noise is minimized.
4. As a developer, I want a `no-commit-to-main` hook, so that I don't accidentally push directly to the main branch.
5. As a developer, I want mypy to run on every commit, so that type errors are caught early.
6. As a reviewer, I want ruff and mypy to run in CI, so that violations cannot be merged even if a hook is skipped.
7. As a developer, I want lint rules to start as warnings (not errors), so that I can adopt the tooling without a blocking cleanup sweep.
8. As a developer, I want the existing codebase formatted in a single commit, so that future diffs are clean.
9. As a developer, I want import sorting enforced by ruff, so that imports are consistently ordered.
10. As a developer, I want line length set to 120, so that longer lines are permitted without noise.
11. As a developer, I want dev dependencies declared in pyproject.toml, so that setting up the project includes lint and type tools.

## Implementation Decisions

- **Formatter:** ruff format only — no separate Black dependency. Ruff's formatter is Black-compatible.
- **Lint rule set:** Moderate — `E, F, W, I, ARG, B` (pyflakes, pycodestyle errors, pycodestyle warnings, isort, unused arguments, bugbears). Currently 22 violations, all auto-fixable.
- **Line length:** 120 (more permissive than Black's default 88, reduces E501 noise).
- **Import sorting:** Enabled via ruff's isort integration (`I001`).
- **Type checker:** mypy with permissive defaults (no `--strict`). Annotations on existing code are out of scope.
- **Initial cleanup strategy:** Run `ruff format` on all files in a single commit. Lint violations start as warnings — not blocking commits or CI.
- **CI integration:** Add ruff check + mypy steps to the existing `build-test` workflow. Lint runs as warnings initially; transition to blocking is a future decision.
- **Pre-commit hooks:** ruff check, ruff format, trailing-whitespace-fixer, end-of-file-fixer, no-commit-to-main.
- **Dev dependencies:** `ruff`, `mypy`, `pre-commit`, and `types-*` stubs added to pyproject.toml as optional dev deps.
- **Python version target:** 3.10+ (matching existing CI).

### Modules

1. **Ruff + mypy config** — `pyproject.toml` sections for `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, `[tool.mypy]`, and `[project.optional-dependencies]` dev group. Test: verify config is valid by running `ruff check --config pyproject.toml` and `mypy --config-file pyproject.toml` against a fixture file with intentional violations.

2. **Pre-commit config** — New `.pre-commit-config.yaml` with all five hooks. Test: `pre-commit run --all-files` passes after the initial format commit.

3. **CI workflow** — Modify `.github/workflows/ci.yaml` to add ruff check + mypy steps after the existing pytest step. No dedicated test — CI itself validates the config on every push.

4. **Codebase formatting** — One-time `ruff format` run across all `.py` files. Not a persistent module; result is a single commit with formatted code.

## Testing Decisions

- **What makes a good test:** Test that config is valid and tools run without error, not that specific violations are caught (ruff and mypy already test their own rules).
- **Modules tested:** Ruff config (verify rule selection, line length, isort settings parse correctly), pre-commit config (verify hooks are valid and can run against the repo).
- **Prior art:** ADR 0002 dictates tests mirror code structure. Config tests live in `tests/test_lint_config.py` (or similar) — one test module for the ruff/mypy config validation.
- **Smoke tests for pre-commit:** Run `pre-commit run --all-files` as a test step. This validates the config is well-formed and all hooks can execute.
- **No tests for:** CI workflow (CI itself is the test), one-time formatting (transient operation).

## Out of Scope

- Adding type annotations to existing code (separate issue).
- Strict mypy mode (`--strict`, `--disallow-untyped-defs`, etc.) — start permissive, tighten later.
- Coverage enforcement in CI.
- Adding more ruff rule categories beyond E, F, W, I, ARG, B.
- Converting existing code to pass mypy errors (defer until lint warnings are promoted to errors).

## Further Notes

- The transition from "warnings" to "blocking" is intentionally left as a future decision. Once violations are near zero, add `--strict` or `select = [...]` with error severity.
- The `no-commit-to-main` hook aligns with ADR 0005 (git branching strategy) which requires PRs for all merges to main.
- The existing CI workflow uses Python 3.10. Ruff and mypy config should be compatible with 3.10+.