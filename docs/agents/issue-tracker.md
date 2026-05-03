# Issue Tracker

**Type:** GitHub Issues

**CLI used:** `gh` (GitHub CLI)

**Repository:** gavingro/seatrades

## Workflow

- Creating issues: `gh issue create --title "..." --body "..." --label "..."`
- Listing issues: `gh issue list --state all`
- Adding labels: `gh issue edit <number> --add-label "..."`
- Viewing issue: `gh issue view <number>`

## When to use

Issues represent work items (bugs, features, tasks). The following skills read from and write to this tracker:
- `to-issues` — converts plans/specs into issues
- `triage` — moves issues through the triage workflow
- `to-prd` — creates PRDs from conversation context
- `review` — adds review comments as issues
- `security-review` — creates security review issues