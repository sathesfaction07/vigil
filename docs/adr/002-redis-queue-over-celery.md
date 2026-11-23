# ADR-002: Redis + RQ Over Celery

## Status
Accepted

## Context
Need async job processing to decouple API response time from classification latency (~3-8 seconds per product). Options: Celery, RQ (Redis Queue), or custom Redis-based queue.

## Decision
Use **RQ (Redis Queue)** with raw Redis for pub/sub progress streaming.

## Consequences

**Why RQ over Celery:**
- Celery's broker abstraction adds complexity we don't need (we're already on Redis)
- RQ's API is simpler: `queue.enqueue(func, args)` vs Celery's decorator + config
- We need Redis PubSub for SSE streaming anyway — using same Redis instance avoids a second dependency
- RQ workers are single-threaded Python processes — easier to reason about resource usage
- Celery's beat scheduler, result backends, and serialization options are features we don't use

**Why not custom only:**
- RQ gives us retry logic, failure tracking, and job TTL out of the box
- Worker lifecycle management (graceful shutdown) is handled

**Costs:**
- RQ is Python-only (if we ever need polyglot workers, would need to switch)
- Less ecosystem than Celery (fewer monitoring tools)
