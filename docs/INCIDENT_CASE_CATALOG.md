# Incident Case Catalog — M1 / Task 1

Status meanings: **Implemented** means injection and an executable real scenario
exist. **Proposed** means design only; no injection/tool/error mapping is implied.
Verification provenance is in [VERIFICATION.md](../VERIFICATION.md).
Scenario IDs identify catalog cases, not automatically proven root causes.

| Scenario ID | Case | Status | Similar symptom / distinguishing evidence |
| --- | --- | --- | --- |
| `db-pool-exhaustion` | Application PostgreSQL pool exhausted | Implemented (M0) | ~1s wait, 503; no connection available, query does not reach DB |
| `downstream-http-timeout` | Downstream HTTP response delayed | Implemented (M1 Task 1) | ~1s wait, 504; real correlated HTTP receipt, ReadTimeout, DB pool unchanged |
| `db-lock-wait` | Item read waits on a PostgreSQL lock | Proposed | Slow/failed item query; connection already acquired, blocking PID/lock evidence |
| `db-slow-query` | Long-running PostgreSQL operation | Proposed | Slow/failed item query; active statement, no blocking lock, query duration evidence |
| `event-loop-blocked` | Blocking code stalls async worker | Proposed | Multiple routes slow, including health; scheduling delay/stack evidence |
| `downstream-connect-refused` | Downstream TCP listener unavailable | Proposed | HTTP dependency failure; ConnectError, no matching downstream receipt |

## 1. Application pool exhaustion

- Scenario ID: `db-pool-exhaustion`.
- Injection: Concurrently POST twice to `/lab/faults/db-pool/hold` with
  `hold_seconds=5`, using size 2, overflow 0, timeout 1. Real `SELECT 1` ensures
  each session borrows a connection and retains its transaction during the wait.
- Expected symptoms: `/items/1` waits ~1s then returns 503 `DB_POOL_TIMEOUT`;
  `/healthz` remains 200; item reads recover after holds finish.
- Ground truth/root cause: Both connections in this application's pool are
  held; overflow is disabled. This is not server-wide PostgreSQL connection exhaustion.
- Observable evidence: Error/request ID/latency logs; pool snapshot at timeout;
  `checked_out=2`, `checked_in=0` during injection and 0/2 after recovery.
- Read-only tools: `/lab/diagnostics/db-pool`, `/healthz`, existing request logs.
- Confounders: Leaked sessions, genuinely slow queries/lock waits occupying the
  pool, high concurrent traffic, or PostgreSQL connectivity problems. A pool
  timeout alone does not prove *why* borrowers held the connections.
- Correct diagnosis: Establish waiting for an application connection, saturated
  pool/no overflow, independent liveness, controlled holders as the known cause,
  and release/recovery. Do not call this a database query timeout or DB outage.
- Status: **Implemented**; [M0 scenario](../scripts/reproduce_db_pool_exhaustion.py).

## 2. Downstream HTTP response timeout

- Scenario ID: `downstream-http-timeout`.
- Injection: In the dedicated downstream process, POST
  `/lab/faults/response-delay` with `delay_seconds=3`, `duration_seconds=10`.
  It actually delays `/value`; app `/downstream/value` uses a 1s HTTP read timeout.
  DELETE resets future requests; monotonic TTL expires abandoned injections.
- Expected symptoms: Normal 200, then 504 `DOWNSTREAM_HTTP_TIMEOUT` after ~1s,
  then 200 after reset and in-flight request drain. App/downstream health stay live.
- Ground truth/root cause: Dependency accepted the HTTP request but its response
  delay exceeded the client's read budget. No synthetic timeout is raised.
- Observable evidence: App ReadTimeout and dependency duration; propagated request
  ID appears in downstream receipt log/state while it is still serving the request;
  DB pool remains unchanged. Logs/exports correlate normal, fault, recovery.
- Read-only tools: App `/lab/diagnostics/downstream` (client configuration),
  `/lab/diagnostics/db-pool`, downstream `/lab/diagnostics/state`, both health
  endpoints, both processes' logs. Dependency control state is privileged lab
  ground truth, not an unrestricted future diagnostic input.
- Confounders: Slow real downstream work, response-path network issues, too-short
  read timeout, downstream loop stall. HTTP connection refusal, ConnectTimeout,
  and httpx PoolTimeout require different paths and are not labeled ReadTimeout.
- Correct diagnosis: Confirm ReadTimeout/read budget, accepted correlated request,
  ongoing delayed dependency work, no DB-pool consumption, and recovery after
  removal of known delay. ReadTimeout alone does not prove artificial delay.
- Status: **Implemented**; [HTTP scenario](../scripts/reproduce_downstream_timeout.py).

## 3. PostgreSQL lock wait

- Scenario ID: `db-lock-wait`.
- Injection (design): A separate controlled PostgreSQL connection starts a
  transaction and holds `LOCK TABLE items IN ACCESS EXCLUSIVE MODE` while a
  normal item read executes. Use a bounded statement timeout and explicit cleanup.
- Expected symptoms (design): Item latency increases; a query timeout may occur
  after connection acquisition; independent health stays live. Error mapping has
  not been implemented. Enough blocked reads can secondarily saturate the app pool.
- Ground truth/root cause: An external transaction's lock blocks the item SELECT.
- Observable evidence (required): Active query, wait_event_type `Lock`, blocking
  PID from `pg_blocking_pids`, blocker transaction lifetime; pool already checked out.
- Read-only tools (proposed): Narrow read-only queries of `pg_stat_activity`,
  `pg_locks`, `pg_blocking_pids`, existing pool diagnostics, request logs. Required
  PostgreSQL visibility permissions must be assessed before implementation.
- Confounders: Slow query, app pool exhaustion, heavy load, event-loop delays.
- Correct diagnosis: Demonstrate a waiting DB query with a specific blocking
  transaction and lock relationship; release blocker and establish recovery.
  Saturated pool alone is insufficient to identify the originating lock.
- Status: **Proposed**; no lock injector/DB activity diagnostic implemented.

## 4. Long-running database query

- Scenario ID: `db-slow-query`.
- Injection (design): Temporarily execute a controlled `SELECT pg_sleep(...)`
  in a real request transaction before the item read, with duration beyond a
  bounded PostgreSQL statement budget. This models delay, not a proved bad index.
- Expected symptoms (design): Slow/failed item path despite successful checkout;
  health remains live. Concurrent slow queries may produce secondary pool timeouts.
- Ground truth/root cause: The injected long-running DB operation exceeds the
  chosen query budget, without an external blocking lock.
- Observable evidence (required): SQL/query duration, DB cancellation/error class,
  active statement and `Timeout/PgSleep` wait event for this synthetic injection,
  no blocking PID, pool occupancy and eventual recovery.
- Read-only tools (proposed): Narrow DB activity/blocker queries, request timing
  and statement timeout configuration. Pool diagnostics already exist.
- Confounders: Lock contention, DB/network overload, connection acquisition wait,
  application scheduling delays. pg_sleep does not establish real query-plan cost.
- Correct diagnosis: Separate checkout time from execution time; confirm the
  slow DB statement and lack of lock blocker; recovery when injection ends.
- Status: **Proposed**; no slow-query injector/statement-budget mapping implemented.

## 5. Async worker event-loop blocking

- Scenario ID: `event-loop-blocked`.
- Injection (design): Bounded `time.sleep` inside one async route on a single
  worker, in an explicitly enabled lab; avoid unbounded CPU loops.
- Expected symptoms (design): Even `/healthz` and diagnostic routes are delayed;
  caller timeouts may occur on unrelated DB/HTTP routes. Handlers may only log
  after the stall ends, so immediate in-process diagnostics cannot be relied on.
- Ground truth/root cause: Synchronous blocking operation runs on the event-loop thread.
- Observable evidence (required): External cross-route latency and process-alive
  evidence; loop scheduling lag or a contemporaneous stack/sample if available.
- Read-only tools (proposed): External health/request probes, minimal scheduling
  lag observation, bounded process-stack inspection where supported. These are
  not currently implemented as investigator tools.
- Confounders: CPU starvation, process suspension, proxy/network delay, worker
  crash, dependency wait. Async sleep/normal async IO should not stall all routes.
- Correct diagnosis: Establish broad scheduling delay and a blocking call on
  the event-loop thread; do not infer it solely from a slow DB request.
- Status: **Proposed**; no blocking injector/lag tool implemented.

## 6. Downstream connection refusal

- Scenario ID: `downstream-connect-refused`.
- Injection (design): Stop the dedicated downstream listener, then restart it;
  keep the configured host/port stable and avoid global network changes.
- Expected symptoms (design): `/downstream/value` fails, often quickly, with
  502 `DOWNSTREAM_UNAVAILABLE`; app health and DB reads can remain normal.
- Ground truth/root cause: Target TCP port has no listening service.
- Observable evidence (required): httpx ConnectError, no receipt in downstream,
  listener/process status and connection probe. Missing log alone is not proof.
- Read-only tools (proposed): Listener/process inspection, direct downstream
  health/reachability probe, correlated logs. App client config diagnostic exists.
- Confounders: DNS failure, route/firewall rejection, wrong port/configuration;
  all can yield ConnectError, unlike an accepted request's ReadTimeout.
- Correct diagnosis: Establish refused target connection plus absent listener
  at the configured address and recovery after restarting it. Do not equate all
  ConnectError instances with a crashed dependency.
- Status: **Proposed**. Defensive app error mapping exists, but there is no
  dedicated refusal injector, reproduction, or proven catalog scenario yet.

## Similar symptoms and Agent necessity

Pool exhaustion, lock waits and long DB work can all present as slow item reads;
lock/query delay can cause pool exhaustion as a secondary symptom. HTTP response
delay and a blocked downstream loop can both yield ReadTimeout. Blocking the
main event loop can delay all evidence routes and obscure the originating fault.
These cases require timing across layers and multiple observations, not only status.

However, the **two currently implemented cases** are intentionally easy to
distinguish using error class, route/dependency and pool state. Most proposed
cases also admit small deterministic checks when all privileged lab tools are
available. This currently supports rule-based baselines, **not demonstrated
necessity for an LLM Agent**. Explicit error codes, injector state and controller
scenario labels can leak the answer. Future evaluation should separate visible
operational evidence from ground truth and test confounders, secondary effects
and missing evidence before deciding whether agentic investigation adds value.
No such evaluation/agent is implemented in this increment.
