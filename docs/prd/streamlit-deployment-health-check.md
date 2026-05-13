# PRD: Streamlit Deployment Health Check

## Problem Statement

After pushing to `main`, there is no way to verify that the SeaTrades app has successfully deployed and is running on Streamlit Community Cloud. The app was recently down due to a Python version mismatch (3.14 selected on Cloud, but dependencies lack 3.14 wheels), and the failure was only discovered by manually visiting the URL. An agent or human pushing code has no signal that the deployment succeeded or failed.

Streamlit Community Cloud returns HTTP 200 even for error pages (e.g., "Error installing requirements"), making naive status-code checks unreliable. The Cloud platform has no CLI or API for checking app status — the only programmatic signal is the app's own health endpoints and page content.

## Solution

Create agent-facing documentation and lightweight check scripts that verify the Streamlit Community Cloud deployment is healthy. The documentation will describe how to check the app's status using Streamlit's built-in endpoints and page content analysis, and what common failure modes look like. The scripts will validate which checks actually work against the live app, then codify the reliable ones.

## User Stories

### Deployment Verification

1. As a maintainer pushing to `main`, I want to know if the app came back up after my deploy, so that I catch deployment failures early.
2. As an agent running triage, I want to check whether the Streamlit app is reachable and healthy, so that I can report the current status in issue comments.
3. As an agent, I want to distinguish between "app is running" and "app is showing an error page", so that I don't report a broken deployment as healthy.
4. As an agent, I want to identify the specific type of deployment failure (e.g., "Error installing requirements" vs. "Something went wrong"), so that I can route the issue appropriately.

### Agent Documentation

5. As an agent, I want a reference document that tells me which health check endpoints exist and what each response means, so that I can verify deployment status without trial and error.
6. As an agent, I want to know what I cannot do (e.g., change Streamlit Cloud settings), so that I escalate to the maintainer instead of attempting impossible actions.
7. As an agent, I want a list of common failure modes and their symptoms, so that I can diagnose issues quickly.

### Check Scripts

8. As a developer, I want a script that validates which health checks work against the live app, so that I don't rely on assumptions about Streamlit's behavior.
9. As a developer, I want minimal check scripts I can run from the command line, so that I can quickly verify deployment status without opening a browser.

## Implementation Decisions

### Part A — Immediate Fix (Already Applied)

- Changed Streamlit Cloud Python version setting from 3.14 to 3.12. The `requires-python = ">=3.10"` in `pyproject.toml` is correct; the issue was the Cloud-side setting only.

### Part B — Deployment Verification Documentation and Scripts

**Module: `docs/agents/deployment.md`**

- Agent-facing documentation describing deployment verification for Streamlit Community Cloud.
- Three verification methods, listed in reliability order:
  1. **`/_stcore/host-config`** — Most reliable. Returns JSON with `allowedOrigins` when the Streamlit server is up. Returns HTML or proxy error when app failed to start. If the response parses as JSON and contains `allowedOrigins`, the app is running.
  2. **`/_stcore/health`** — Returns `"ok"` (HTTP 200) when the app is running. Returns 503 or error HTML when the Streamlit server isn't ready. However, when the app never started (e.g., dependency install failure), this endpoint may not exist at all and the Cloud proxy may return HTTP 200 with an error page.
  3. **Root URL content check** — Fallback. Look for `<div id="root">` in the HTML response. Present means the Streamlit React app loaded. Absent means the Cloud proxy is serving an error page. Known error strings: "Error installing requirements", "Something went wrong", "Oh no".
- Document that agents cannot change Streamlit Cloud settings — that requires the maintainer via share.streamlit.io.
- Document the app URL: `https://keats-seatrades.streamlit.app/`

**Module: `docs/scripts/`**

- Minimal shell scripts for deployment verification.
- `docs/scripts/check-deploy.sh` — Runs the three checks against the live app and reports status. Uses `curl` only — no Python dependencies.
- Scripts are for manual use and agent use, not for CI (CI cannot reach Streamlit Cloud URLs from GitHub Actions in a meaningful way — the app may still be rebuilding).

**Investigation Required**

- Before writing the scripts, the implementer must validate which checks actually work against the live app by running each check while the app is healthy and while it's in a known-broken state (e.g., temporarily pointing the Cloud config at a broken branch).
- The `/_stcore/host-config` and `/_stcore/health` endpoints are known from Streamlit's source code, but their behavior on Community Cloud (as opposed to a self-hosted instance) must be confirmed empirically.

## Testing Decisions

- Good tests for this PRD: verify that the check scripts produce correct output when pointed at a known-healthy URL and a known-broken URL.
- The scripts themselves are simple `curl` wrappers — the main test is manual validation against the live app.
- No unit tests for documentation files.

## Out of Scope

- CI/CD integration for deployment verification (GitHub Actions cannot reliably check Streamlit Cloud status during a workflow run — the app may still be rebuilding).
- Automated deployment or redeployment via CLI or API (Streamlit Cloud has no deploy API).
- Changing Streamlit Cloud settings programmatically.
- Docker-based deployment or self-hosting infrastructure.
- The Python version fix on Streamlit Cloud (already applied manually by the maintainer).

## Further Notes

- Streamlit Community Cloud has no CLI or API for checking app status. The `streamlit cloud deploy` command is a draft PR and only opens a browser — it does not provide programmatic deploy or status checking.
- The app URL is `https://keats-seatrades.streamlit.app/` and the entry point is `app.py`.
- The `pyproject.toml` specifies `requires-python = ">=3.10"` which is correct. The deployment failure was caused by the Cloud-side Python version setting, not by the project configuration.
- This PRD covers issue #21 on GitHub. Part A (the Python version fix) is already applied. Part B is the documentation and scripts work.
