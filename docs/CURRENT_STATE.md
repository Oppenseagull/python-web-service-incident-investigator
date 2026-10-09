# Current project state

Updated: 2026-10-09. This file is the authoritative progress checkpoint for
subsequent work on Python Web Service Incident Investigator / Project A.

## Current milestone: M0 Completed

M0's technical spike established a controlled, reproducible PostgreSQL
application connection pool exhaustion lab. Implementation and the real core
scenario are complete. Overall Project A is **not complete**. No M1 implementation
or architecture is approved by this closeout. Personal learning checks do not
change the completed milestone status or create acceptance blockers.

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
- One automated scenario polls actual pool occupancy before checking timeout
  and recovery; two lightweight tests and one real integration test exist.
- Docker Compose contains only `app` and `postgres`, with initialization SQL,
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

This is retained user-provided evidence, not a new closeout execution. Initial
Docker failures remain historical. No raw build/application-log export or exact
successful execution date was retained; the successful excerpt and owner
confirmation are sufficient to close this spike. Today's runtime availability
was not checked and is not an unresolved M0 acceptance task.

## Code baseline and entry points

Implementation baseline: Git commit `1a85657` (`Implement M0 PostgreSQL pool
exhaustion fault lab`). This closeout changes documents only.

| Location | Purpose |
| --- | --- |
| [app/main.py](../app/main.py) | `create_app`, routes, request middleware, timeout handler, lab diagnostics |
| [app/database.py](../app/database.py) | Engine pool and request-scoped session cleanup |
| [app/config.py](../app/config.py) | Environment settings and connection URL |
| [app/logging.json](../app/logging.json) | Standard logging configuration |
| [scripts/reproduce_db_pool_exhaustion.py](../scripts/reproduce_db_pool_exhaustion.py) | Standalone reproduction and shared integration scenario |
| [tests/test_lightweight.py](../tests/test_lightweight.py) | Database-independent behavior and programming error checks |
| [tests/test_integration.py](../tests/test_integration.py) | Real HTTP/PostgreSQL scenario, enabled by `RUN_INTEGRATION=1` |
| [db/init.sql](../db/init.sql) | Minimal schema and seed baseline |
| [compose.yaml](../compose.yaml), [Dockerfile](../Dockerfile) | Local runtime; one app worker |
| [requirements.lock](../requirements.lock), [pyproject.toml](../pyproject.toml) | Pinned dependencies and direct dependency declarations |
| [README.md](../README.md), [VERIFICATION.md](../VERIFICATION.md), [DECISIONS.md](DECISIONS.md) | Usage, evidence, and M0 decisions |

Optional rerun entry points, when needed for later work (not new M0 gates):

```powershell
docker compose up --build --wait
docker compose exec app python scripts/reproduce_db_pool_exhaustion.py
docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s
```

Keep the existing ignored `.env`; `.env.example` is a first-setup reference.
Active code stays in `app/`, the seed baseline in `db/`, and project state in
`docs/`. No duplicate source snapshot or additional generated run directory
was created for closeout; the existing terminal evidence is retained centrally.

## Known technical limits

- Exactly one fault and one read path. Reproduction requires an idle, dedicated
  instance with size 2, overflow 0, timeout 1; the script rejects other settings.
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

## System capabilities not yet implemented

Agent/LLM integration, incident diagnosis, Incident Persistence, a general
Eval Runner, additional fault scenarios, evidence ingestion/correlation,
workers/queues, distributed tracing/metrics infrastructure, and a frontend
are not implemented. The M0 scenario script is not a general evaluation system.

## Questions for the next phase

Await the next development instruction. The next phase must define its concrete
user-facing outcome and acceptance criteria, what evidence it consumes from
M0, whether any evidence persistence or evaluation is needed, and the smallest
implementation boundary. These are open design questions, not an approved M1
feature list or technology architecture. Project Master Context is unchanged.
