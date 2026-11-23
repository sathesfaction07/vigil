# ADR-001: Advisory-Only AI Design

## Status
Accepted

## Context
The system classifies product content as VIOLATION/COMPLIANT/UNCERTAIN using an LLM. The question is whether to allow automated enforcement (e.g., auto-suppress violating products) or restrict to advisory output.

## Decision
All AI classifications are **advisory only**. The system never takes enforcement actions. Human reviewers make all final decisions.

## Consequences

**Benefits:**
- Eliminates false-positive enforcement risk (wrongly removing compliant products)
- Maintains human accountability for every enforcement decision
- Provides audit trail (human reviewed AI recommendation → decided → acted)
- Allows the system to operate at LOW confidence thresholds without risk
- Satisfies regulatory requirements for human-in-the-loop AI decisions

**Costs:**
- Requires human reviewers (cannot fully automate)
- Throughput limited by human review capacity
- Some obvious violations still require human confirmation

## Alternatives Considered

1. **Auto-enforce HIGH confidence only** — Rejected. Even 94%+ confidence has ~6% error rate. At scale (1000s of products/day), this means dozens of wrong suppressions daily.
2. **Auto-enforce with appeal process** — Rejected. Burden shifts to merchant to prove innocence. Unacceptable for legitimate businesses.
3. **Tiered: auto-enforce RED, review AMBER** — Rejected. The line between RED and AMBER is exactly what humans disagree about most.
