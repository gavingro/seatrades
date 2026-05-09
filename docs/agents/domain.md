# Domain Docs

**Layout:** Single-context

## Structure

- `CONTEXT.md` — project domain language, terminology, and business logic overview
- `docs/adr/` — architectural decision records (ADRs)

## Consumer rules

The following skills read these files to understand the codebase:

- `improve-codebase-architecture` — reads CONTEXT.md for domain language, docs/adr/ for past decisions
- `diagnose` — reads CONTEXT.md to understand domain concepts when debugging
- `tdd` — reads CONTEXT.md to understand domain language for writing tests

## Location

- `/Users/gavin/Coding/seatrades/CONTEXT.md` - Domain language and glossary
- `/Users/gavin/Coding/seatrades/docs/adr/` - Architectural decision records
