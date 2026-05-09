# Triage Labels

**Issue tracker:** GitHub Issues

## Label vocabulary

| Role | Label | Description |
|------|-------|--------------|
| needs-triage | `needs-triage` | Maintainer needs to evaluate the issue |
| needs-info | `needs-info` | Waiting on reporter for more information |
| ready-for-agent | `ready-for-agent` | Fully specified, AFK-ready (agent can pick it up with no human context) |
| ready-for-human | `ready-for-human` | Needs human implementation |
| wontfix | `wontfix` | Will not be actioned |

## Usage

The `triage` skill applies these labels as issues move through its state machine. Labels are created automatically when the skill first runs if they don't exist.
