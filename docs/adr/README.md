# Architecture Decision Records

Short, dated records of decisions that are expensive to reverse. New entry
per decision; never rewrite history — supersede with a new ADR.

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-polyglot-envelope-v2.md) | Ship `.epi` as an HTML+ZIP polyglot (envelope-v2) | Accepted |
| [0002](0002-no-per-call-tsa.md) | No per-call TSA anchoring; seal-time + heartbeat checkpoints instead | Accepted |
| [0003](0003-witness-first.md) | Customer witness (hash-only, outbox-first) instead of file escrow | Accepted |

Format: context → decision → alternatives → consequences. One page each.
