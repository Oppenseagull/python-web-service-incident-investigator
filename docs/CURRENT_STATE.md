# Current project state

Updated: 2026-10-10 (S1 implementation and verification). This file is the authoritative progress checkpoint for
subsequent work on Python Web Service Incident Investigator / Project A.

Owner-confirmed product definition and future priorities:
[PROJECT_DIRECTION.md](PROJECT_DIRECTION.md). Design intent is separate from
the implemented capabilities and retained verification results below.

## Current milestone: S1 implemented and verified — awaiting Owner review

M0 remains **Completed**. M1 Task 1 adds a second real fault, six-case catalog,
and an evidence foundation under the Owner's explicit development instruction.
This first increment is implemented and verified, then stopped for review.
Overall Project A and the rest of M1 are **not complete**. Personal learning
checks do not change completed technical milestone status.

S1 was explicitly authorized after the Owner approved the implementation plan.
It adds safe Python investigation tools; it does not mark M1 Task 1 Owner Review
as passed. M1 Task 1 remains awaiting Owner review. **S2 has not started.**

## S1 implemented capabilities and new evidence

- `Validated ToolCall → ToolRegistry → safe evidence access → ToolResult`, using
  closed Pydantic schemas; no LLM, investigation API or diagnosis report.
- Three tools: recent application events, instantaneous application DB pool
  snapshot without acquiring a connection, fixed downstream `/healthz` probe.
- Explicit nested allowlist projection before storage: application request data
  only, approved business paths, bounded numeric/enum observations. No controller
  exports, scenario/run IDs, injector state, raw exception text, arbitrary URLs,
  SQL, shell or filesystem access. All `/lab/*` request events are excluded.
- Up to 2,000 projected observations retained for 600 seconds, with monotonic
  expiry, FIFO capacity eviction and short locked memory operations. Single-process,
  non-durable; restart loses records, no historical log ingestion or shared cache.
- Each retained observation has a stable `evidence_id`; repeated queries and
  `get_evidence(id)` resolve the same safe record. New snapshots get new IDs.
  Evicted/expired/unknown lookup returns `None`; tool no-data results are structured
  `unavailable`. Unknown values remain null; measured zero is preserved.
- Event query: request ID and/or timezone-aware window of at most 300 seconds,
  1–50 results; truncation and possible incomplete retained history are disclosed.
- Registry execution budget: 2s cooperative async deadline; downstream probe IO
  timeout 1s, response cap 4 KiB, no redirects or caller-provided URL. Health means
  current liveness, not historical `/value` readiness or proof of a root cause.
- Native final suite: **43 passed, 2 deselected in 11.47s**. Full freshly built
  Compose suite: **45 passed in 20.68s**, including all nine original cases.
- Tool-visible HTTP evidence: **200 → 504 (1004.30ms) → 200**, actual ReadTimeout;
  DB evidence: **200 → 503 (1004.07ms) → 200**, historical timeout pool 2/0,
  recovered live pool 0/2. Both include request/evidence IDs, safe provenance and
  control-data exclusion. These are tool/integration tests, not Agent Eval.
- [S1 run index, commands, safe exports and source manifest](../artifacts/runs/2026-10-10/README.md).
  All 23 Python/dependency files match the tested container after LF normalization.

S1 entry points: [contracts](../app/investigator/contracts.py),
[projection/store](../app/investigator/evidence.py), [registry](../app/investigator/tools.py),
[unit tests](../tests/test_investigator_tools.py),
[real HTTP/DB tests](../tests/test_investigator_integration.py).
Registry is available as `app.state.investigator_tools` during the app lifespan,
in the same process as the observed app. A separate Python process cannot read it.

G0 engineering check found no code/evidence contradiction; prior faults and cleanup
are confirmed by the new regression. Owner learning review is still pending:
Session versus connection, read versus connect timeout, client timeout versus
downstream work cancellation, and operational evidence versus controller answers.
This records implementation approval, not successful independent Owner explanation.

The sections below retain the M0/M1 baseline and original evidence. References
there to unimplemented tools/ingestion describe that earlier milestone; S1's
bounded safe view above supersedes them. Raw Evidence v1 logs/exports are unchanged.

## Implemented capabilities

- Python 3.12+ FastAPI service backed by PostgreSQL through SQLAlchemy 2.x
  async sessions and asyncpg. `items` has three seed rows; there is no CRUD API.
- `GET /healthz` reports process liveness without a database query.
- `GET /items/{item_id}` reads a row, returning 200 or 404.
- Application engine pool defaults: size 2, overflow 0, timeout 1 second;
  settings are configurable through environment variables.
- With `FAULT_LAB_ENABLED=true`, `POST /lab/faults/db-pool/hold` executes
  `SELECT 1`, holds the real session transaction/connection for a bounded
  duration, and releases it through session cleanup. The route is absent
  when the lab is disabled.
- Lab-only `GET /lab/diagnostics/db-pool` reads public pool statistics without
  borrowing a connection. Pool timeouts map to structured 503
  `DB_POOL_TIMEOUT`; unrelated programming errors remain server errors.
- Standard request logs carry path, status, request ID, and latency; a pool
  timeout emits a distinct warning. Handled responses carry `X-Request-ID`.
- The DB scenario still polls actual pool occupancy and now emits shared
  evidence records with optional export.
- `/downstream/value` uses a process-lifetime httpx client for real HTTP IO.
  ReadTimeout returns structured 504 `DOWNSTREAM_HTTP_TIMEOUT`; other HTTP
  connection/transport/status errors have distinct 502 handling.
- A minimal independent `downstream/` process offers `/value`, bounded
  response-delay injection with TTL/reset, and read-only receipt/fault state.
  Lab mutation/diagnostic endpoints require the explicit flag in that process.
- Both fault types emit request IDs, UTC timestamps, dependency, error, latency
  and observations. Controllers assign run IDs; app incident IDs remain null.
- [Catalog](INCIDENT_CASE_CATALOG.md): two Implemented, four Proposed cases.
  [Contract](EVIDENCE_CONTRACT.md): schema and unavailable data.
- Tests: seven lightweight cases, one independently spawned real HTTP test,
  one Compose/PostgreSQL integration test (nine total).
- Docker Compose contains `app`, `postgres`, and `downstream`, with initialization SQL,
  health checks, localhost app binding, and a persistent PostgreSQL volume.

## Verified technical behavior

The owner supplied the complete test terminal excerpt retained in
[VERIFICATION.md](../VERIFICATION.md):

1. Item 1 returns 200 before injection.
2. Two concurrent holds consume the two real application pool connections;
   diagnostics report `checked_out=2`, `checked_in=0`, `overflow=0`.
3. A new item query waits for a connection and returns structured 503
   `DB_POOL_TIMEOUT` after a measured 1006.88 ms. Its SQL cannot run before
   a connection is acquired.
4. Holds finish; item 1 returns 200 again. Diagnostics report
   `checked_out=0`, `checked_in=2`, `overflow=0`.
5. `docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s`
   reports **3 passed in 5.55s**.

The M0 result above is retained user-provided evidence. Initial
Docker failures remain historical. No raw build/application-log export or exact
successful execution date was retained; the successful excerpt and owner
confirmation closed that spike. This history remains distinct from the new
M1 execution below.

New M1 Task 1 execution on 2026-10-09:

- Native TCP + lightweight suite: **8 passed, 1 deselected in 6.21s**.
- Compose full suite: **9 passed in 9.51s**, including current DB scenario and
  independent real HTTP timeout/recovery. DB regression returned a ~1003.55ms
  503 and recovered, checking the shared logging/export changes.
- Standalone script against Compose app/downstream: **200 → 504 → 200**;
  timeout **1006.09ms**, correlated dependency request ID, unchanged DB pool
  (`checked_out=0`, `checked_in=2`). Delayed work and fault state cleared.
- Docker initially unavailable, later responded after the Owner's launch;
  a build succeeded after retrying PyPI TLS/network errors. Later metadata
  resolution hit Docker Hub auth EOF. The final test-only change was copied
  into the already-built app before testing. No global Docker settings changed.

Source identity, raw/exported evidence: [run index](../artifacts/runs/2026-10-09/README.md).

## Code baseline and entry points

M0 implementation baseline: Git commit `1a85657`; M0 closeout: `aab5cba`.
M1 Task 1 source and evidence are committed together after verification.

| Location | Purpose |
| --- | --- |
| [app/main.py](../app/main.py) | `create_app`, routes, request middleware, timeout handler, lab diagnostics |
| [app/database.py](../app/database.py) | Engine pool and request-scoped session cleanup |
| [app/config.py](../app/config.py) | Environment settings and connection URL |
| [app/logging.json](../app/logging.json) | Standard logging configuration |
| [app/downstream.py](../app/downstream.py), [downstream/main.py](../downstream/main.py) | Real HTTP caller and controlled dependency |
| [app/evidence.py](../app/evidence.py) | Shared observation model |
| [scripts/reproduce_db_pool_exhaustion.py](../scripts/reproduce_db_pool_exhaustion.py) | Standalone reproduction and shared integration scenario |
| [tests/test_lightweight.py](../tests/test_lightweight.py) | Database-independent behavior and programming error checks |
| [tests/test_integration.py](../tests/test_integration.py) | Real HTTP/PostgreSQL scenario, enabled by `RUN_INTEGRATION=1` |
| [scripts/reproduce_downstream_timeout.py](../scripts/reproduce_downstream_timeout.py) | Second-fault controller/export |
| [tests/test_downstream_integration.py](../tests/test_downstream_integration.py), [tests/test_evidence_and_downstream.py](../tests/test_evidence_and_downstream.py) | Real TCP lifecycle/correlation, injection bounds and error discrimination |
| [db/init.sql](../db/init.sql) | Minimal schema and seed baseline |
| [compose.yaml](../compose.yaml), [Dockerfile](../Dockerfile) | Local runtime; one app worker |
| [requirements.lock](../requirements.lock), [pyproject.toml](../pyproject.toml) | Pinned dependencies and direct dependency declarations |
| [README.md](../README.md), [VERIFICATION.md](../VERIFICATION.md), [DECISIONS.md](DECISIONS.md) | Usage, evidence, and M0 decisions |

Optional rerun entry points, when needed for later work (not new M0 gates):

```powershell
docker compose up --build --wait
docker compose exec app python scripts/reproduce_db_pool_exhaustion.py
docker compose exec app python scripts/reproduce_downstream_timeout.py
docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s
```

Keep the existing ignored `.env`; `.env.example` is a first-setup reference.
Active code stays in `app/`, the seed baseline in `db/`, and project state in
`docs/`. Versioned M1 evidence is in `artifacts/runs/2026-10-09/`, separated
from active code and historical M0 evidence in `VERIFICATION.md`.

## Known technical limits

- Two implemented faults; four other cases are design only. Scripts require
  idle dedicated instances; DB requires size 2/overflow 0/timeout 1, and HTTP
  requires read timeout 1 second.
- One worker/instance: pools and diagnostic statistics are process-local.
  This does not exhaust PostgreSQL's server-wide connection limit.
- Occupancy must be confirmed within two seconds; holds last five seconds.
  Severe machine/network scheduling delays can make the script fail its bounds.
- Lab routes are unauthenticated and intended for local use. Small pool defaults
  are intentional fault settings, not production sizing.
- `/healthz` is liveness, not database readiness. Diagnostics are raw pool
  statistics, not atomic cross-process monitoring; overflow may be negative
  before connections are lazily created.
- PostgreSQL initialization runs on a new volume; there is no migration system.
- Request IDs/logs provide minimal evidence, not distributed tracing, metrics,
  or a durable incident/evidence store. The closeout does not claim production
  readiness or broader performance/cancellation coverage.
- Downstream state is process-local. ReadTimeout does not cancel its work;
  reset affects future arrivals and the script drains in-flight work. A TTL
  bounds abandoned injections. HTTP read budget is not an overall deadline.
- DB holder identities/wait events and DNS/TLS phase timing are unavailable.
  Controller case labels and injector state expose ground truth; future blind
  evaluation must separate them from visible operational evidence. Simple
  conditions distinguish these two cases; Agent necessity is not established.

## System capabilities not yet implemented

Agent/LLM integration, incident diagnosis, Incident Persistence, a general
Eval Runner, four Proposed fault scenarios, durable/cross-process evidence collection,
workers/queues, distributed tracing/metrics infrastructure, and a frontend
are not implemented. The M0 scenario script is not a general evaluation system.

## Next priorities — Owner-confirmed direction, not implemented

2026-10-10 strategic review retains Incident Investigator and confirms
**Adaptive Root-Cause Investigation** as the product task: unknown-root-cause
symptoms → dynamic read-only evidence gathering → an evidence-supported report.
Fault Lab is the development/evaluation environment. Case count is not a
measure of investigation quality. These choices supersede the earlier next-step
suggestion; they do not change M0 Completed or M1 Task 1 awaiting Owner review.

1. Await Owner Review of S1 and the still-unconfirmed M1 Task 1 learning review.
   S1 is implemented and verified; its approval does not automatically authorize S2.
2. S1 supplies controlled tools and an explicitly projected safe view. Review the
   schemas, leak tests, real fault evidence and process-local retention limits.
   Controller exports remain privileged and are never tool inputs.
3. After separate authorization, prioritize an **Investigation Vertical Slice** reusing the two real faults:
   label-free incident → LLM chooses tool → backend validates and executes →
   LLM continues or stops → report cites evidence and retains uncertainty.
   This will first prove the engineering loop, not superiority over rules.
4. Then select a few causal/confounding cases and build a repeatable hidden-answer
   Eval Suite with fixed/rule baselines. Measure diagnosis/evidence quality,
   unsupported assertions, ineffective/repeated tools, latency/cost and difficult
   cases. Do not mechanically implement all six candidates as the next priority.
5. Introduce persistence/background tasks/further reliability mechanisms only
   when justified by experiments; no such implementation is present today.

Agent responsibilities are hypothesis revision, tool choice, evidence analysis
and stop decisions. Deterministic code owns execution, permissions, validation,
state, timeouts/budgets, retry policy and correlation. Agent need not win every
case; comparative benefit remains unmeasured. The earlier limitation about
simple rules distinguishing today's faults is still technically valid and no
longer acts as a gate against the confirmed investigation product direction.

Open decisions: LLM/model/SDK/framework, incident/report schemas, expanded tool
scopes and stronger isolation, investigation context/state/budgets/stop policy,
baseline/Eval cases/scoring, and when to add storage or other infrastructure.
Agent investigation, general Eval Runner, persistence and the four Proposed
faults remain **not implemented**.

Historical M0/M1 results above are unchanged. S1 adds only the tool layer,
request capture integration and necessary tests/documentation. Dependencies,
runtime configuration, fault injectors and Project Master Context are unchanged.
No parallel Project B or S2 development starts. Wait for Owner Review.
