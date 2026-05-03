# Contributing to SeaTrades

## Development Workflow

1. Create a feature branch for your work
2. Make commits with clear messages
3. Create a PR when ready for review
4. Gavin reviews and merges in GitHub UI

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

## Testing

Run tests with:
```bash
pytest
```

## Documentation

- Domain glossary: `CONTEXT.md`
- ADRs: `docs/adr/`
- PRDs: `docs/prd/`