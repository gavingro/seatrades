# Issue Tracker

**Type:** GitHub Issues

**CLI used:** `gh` (GitHub CLI)

**Repository:** gavingro/seatrades

## Workflow

- Creating issues: `gh issue create --title "..." --body "..." --label "..."`
- Listing issues: `gh issue list --state all`
- Adding labels: `gh issue edit <number> --add-label "..."`
- Linking parent issues: see "Parent and Child" below
- Viewing issue: `gh issue view <number>`

## Parent and Child

- Higher level PRD issues should have a 'PRD:' prefix in their title.
- Child issues of PRD's should link back to their parent PRD issue.
- GitHub Issues supports sub-issue relationships natively, but `gh sub-issue` is **not** a released CLI command yet. Use the REST API instead:

### Add a sub-issue

```bash
# Get the database ID of the child issue first
CHILD_ID=$(gh api repos/gavingro/seatrades/issues/<child_number> -q '.id')

# Add it as a sub-issue of the parent
gh api repos/gavingro/seatrades/issues/<parent_number>/sub_issues \
  -X POST \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -F sub_issue_id="$CHILD_ID"
```

### Remove a sub-issue

```bash
CHILD_ID=$(gh api repos/gavingro/seatrades/issues/<child_number> -q '.id')

gh api repos/gavingro/seatrades/issues/<parent_number>/sub_issue \
  -X DELETE \
  -H "X-GitHub-Api-Version: 2026-03-10" \
  -F sub_issue_id="$CHILD_ID"
```

### List sub-issues

```bash
gh api repos/gavingro/seatrades/issues/<parent_number>/sub_issues \
  -q '.[].number'
```

### Get parent issue

```bash
gh api repos/gavingro/seatrades/issues/<child_number>/parent \
  -q '.number'
```

## When to use

Issues represent work items (bugs, features, tasks). The following skills read from and write to this tracker:

- `to-issues` — converts plans/specs into issues
- `triage` — moves issues through the triage workflow
- `to-prd` — creates PRDs from conversation context
- `review` — adds review comments as issues
- `security-review` — creates security review issues
