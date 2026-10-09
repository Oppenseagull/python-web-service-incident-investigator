# M0 engineering decisions

Archived: 2026-10-09. These decisions describe the implemented M0 baseline.
They do not freeze M1 architecture or claim later system capabilities.

## 1. Controlled Python web service fault lab

- Context: The project needs a small backend failure that can be understood
  and reproduced before building an investigator.
- Decision: One FastAPI app, one PostgreSQL database, one item-read path,
  and one pool-exhaustion scenario.
- Reason: Keep request behavior, failure cause, and recovery easy to trace.
- Cost: This proves one technical spike, not overall Project A or production readiness.

## 2. Real PostgreSQL application pool exhaustion

- Context: The fault must arise from actual resource contention.
- Decision: Default to pool size 2, overflow 0, timeout 1 second. Two concurrent
  hold requests execute `SELECT 1` through the same pool as normal requests
  and retain their transactions while waiting.
- Reason: A third request must wait for a real connection, then time out.
- Cost: These are intentionally unrealistic settings; the scenario requires
  an isolated idle lab and a live PostgreSQL instance.

## 3. FastAPI + SQLAlchemy async API + asyncpg

- Context: Holds and other requests must overlap without blocking the service's
  event loop during the artificial wait.
- Decision: Use Python 3.12+, FastAPI, SQLAlchemy 2.x async sessions, asyncpg,
  and `asyncio.sleep` for the hold duration.
- Reason: Preserve a real PostgreSQL query path and permit concurrent requests.
- Cost: Correct async scheduling and explicit session/transaction lifetime matter;
  async waiting does not itself release a database connection.

## 4. Application pool and request-scoped session lifecycle

- Context: Normal reads and injection must share a resource limit, and requests
  must return their connections when finished.
- Decision: One engine/session factory per app process; a fresh session in an
  `async with` dependency per database request; dispose the engine on shutdown.
- Reason: The session borrows a connection when executing SQL, holds it during
  its transaction, and closes/rolls back during cleanup to return the connection.
- Cost: Session existence alone does not indicate connection occupancy. Each
  worker has its own pool, so M0 runs one worker and one app instance.

## 5. Real failure rather than a simulated error response

- Context: An injected 503 would not establish pool timeout or recovery behavior.
- Decision: Let actual connection acquisition raise SQLAlchemy's timeout;
  explicitly map that exception type to a stable `DB_POOL_TIMEOUT` 503.
- Reason: Test the causal path from contention to timeout and cleanup.
- Cost: Requires integration execution and timing bounds. Unexpected programming
  errors remain server errors rather than being relabeled as pool exhaustion.

## 6. Read-only, lab-only diagnostics

- Context: Reproduction needs evidence of occupancy while the pool is full.
- Decision: Expose public SQLAlchemy pool statistics without borrowing a
  connection; register both lab endpoints only with `FAULT_LAB_ENABLED=true`.
- Reason: Observe the saturated pool without consuming its resources or
  inventing metrics. Use standard logs/request IDs for minimal correlation.
- Cost: Statistics are process-local snapshots, not production monitoring;
  raw overflow can be negative during lazy initialization. Local lab routes
  have no authentication.

## 7. Condition-driven automated reproduction

- Context: A fixed sleep after starting holds cannot prove both connections
  have been acquired.
- Decision: Check health and baseline query, launch two holds, poll diagnostics
  until both connections are occupied, verify timed structured 503, await holds,
  then verify query recovery and zero checked-out connections.
- Reason: Tie the test to observed state and validate resource release as well
  as functionality. Reuse this scenario in the integration test.
- Cost: The script intentionally rejects non-default pool settings and enforces
  short timing bounds; unrelated traffic or severe scheduling delays can fail it.

## 8. Minimum necessary components

- Context: M0's goal is a reproducible fault, not a complete incident platform.
- Decision: Use only the app/database runtime, settings, standard logging,
  Docker Compose, pytest, and httpx; retain pinned dependencies and seed SQL.
  Add no agents, queues, metrics stack, frontend, or speculative architecture.
- Reason: Keep the entire milestone understandable and reproducible by one person.
- Cost: No durable incident/evidence store, general evaluation runner, migrations,
  or investigation automation exists. Whether and how to add later capabilities
  must be decided in a subsequent phase.
