# ADR 0007: Agents verify the app — behavior via AppTest, visuals via Playwright MCP

## Status: proposed

## Context

The test suite covers logic and pure render functions well (e.g. `render_view()` is tested at the function level). But some verification still requires a human to launch the Streamlit app and point-and-click: confirming the dashboard *behaves* correctly through real interaction, and confirming it *looks* correct (charts actually draw, layout isn't broken, nothing fishy).

Today that human is the maintainer. We want an agent to be able to do it too — at minimum, to *see* the running dashboard rather than reasoning blind.

Two distinct gaps hide in "let an agent check the app":

- **(A) Behavior** — clicking X updates state Y / shows the right rows. Reachable headlessly.
- **(B) Visuals / exploration** — the Altair chart renders, the layout holds, the assignments table looks right. Only a real browser shows this; a headless test passes happily while a chart renders as a blank box.

The question is which tools own which gap.

## Considered Options

1. **Streamlit `AppTest` (`streamlit.testing.v1`)** — runs the app headless, simulates clicks/inputs, inspects widget and element values. Cheap, runs in CI. Cannot render — "simulates a running app without browser UI." Covers A, not B.

2. **Playwright MCP server** (`@playwright/mcp`) — the agent drives a real browser live, in-session: navigate, click, read the accessibility snapshot, screenshot. Renders the *actual* app, so it covers B. Interactive only — an MCP server is a tool the agent calls; it does **not** run in CI.

3. **pytest-playwright** — scripted browser tests, repeatable, run in CI, produce pass/fail + screenshot artifacts. Covers B, but only what you script — it can't "look around."

## Decision

**Split responsibility: AppTest owns A, Playwright MCP owns B. No pytest-playwright.**

- **AppTest** is the default for behavior. Automate as much point-and-click as possible here — it's headless, fast, and CI-enforced.
- **Playwright MCP** gives the agent eyes for the visual and exploratory remainder. Configured in a project-level `.mcp.json` (checked in) so the capability travels with the repo, like the `.venv` convention and `docs/agents/`.
- **Accessibility snapshot first, screenshot second.** `browser_snapshot` (the a11y tree) is more informative than a screenshot and is the only thing actions can be performed against. `browser_take_screenshot` is reserved for genuine visual/layout confirmation.
- **No pytest-playwright for now.** The need is exploratory ("the *possibility* to see the app"), not a frozen suite. When a B-check stabilizes into something worth repeating, graduate it — preferably down into AppTest, or into pytest-playwright only if it truly needs a browser.

Rationale:
- Most manual verification is behavior (A), which AppTest automates today with zero new infrastructure. Reserving the browser for the genuinely visual remainder keeps the expensive tool thin.
- "Let the agent look around like I do" is interactive by nature — that's what an MCP server is for, and what scripted tests structurally can't do.
- A scripted browser suite has a real maintenance cost and would encode requirements we don't have yet.

## Consequences

- A Playwright MCP server appears in `.mcp.json` but **no browser tests run in CI** — this is intentional, not an oversight. CI remains lint + AppTest/pytest.
- Prerequisites for the browser capability (node/`npx`, a one-time `npx playwright install`) are documented in `docs/CONTRIBUTING.md`, alongside the launch procedure (run the app headless on a known port; the app auto-seeds mock data on load; click through to trigger the solve before the Assignments tab has anything to show).
- `CLAUDE.md` carries a short pointer to that procedure so agents discover it; the built-in run/verify flows pick up the documented launch convention.
- CONTEXT.md is untouched — this is dev-process tooling, not camp-domain vocabulary, so it does not belong in the glossary.
- If exploratory visual checks later stabilize into must-not-regress cases, revisit pytest-playwright then — and supersede this ADR if that changes the no-CI-browser-tests stance.
