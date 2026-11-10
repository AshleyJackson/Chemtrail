# Architecture Decision Records

A single ADR records one decision, the forces acting on it, and what we accept
by choosing it. ADRs are numbered sequentially and never renumbered.

## Status values

| Status | Meaning |
|--------|---------|
| `Proposed` | Written, not yet agreed. May change freely. |
| `Accepted` | Agreed. Implementation should follow it. |
| `Rejected` | Considered and declined; kept for the record. |
| `Superseded by ADR-XXXX` | Replaced. Do not follow; read the replacement. |
| `Deprecated` | Still true but no longer relevant. |

An `Accepted` ADR is **not edited** except to change its status line. If the
decision changes, write a new ADR that supersedes it. The history of being wrong
is more valuable than a tidy document.

## Template

Copy this into `NNNN-short-slug.md`.

```markdown
# ADR-NNNN: Title

- **Status:** Proposed
- **Date:** YYYY-MM-DD
- **Deciders:** names or roles
- **Supersedes:** —
- **Superseded by:** —

## Context

The situation and the forces at play. Facts, constraints, and what makes this
non-obvious. Include dates for anything that may become stale.

## Decision

What we will do, in the active voice. Specific enough that a reviewer can tell
whether implementation matches it.

## Consequences

### Positive
### Negative / costs
### Neutral / follow-on

## Alternatives considered

For each: what it was, and the specific reason it lost. "Worse" is not a reason.

## Follow-ups

Unresolved work this decision creates.
```

## Index

See [../README.md](../README.md#decision-log).
