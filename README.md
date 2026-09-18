# Python Web Service Incident Investigator — M0

M0 reproduces **application PostgreSQL connection pool exhaustion**. It contains
one FastAPI process, one PostgreSQL database, one read endpoint, and one fault.
There is no diagnosis logic, AI, worker, or monitoring stack.

## Start (PowerShell, Docker Desktop running with Linux containers)

```powershell
Copy-Item .env.example .env
# Edit .env: choose a local POSTGRES_PASSWORD; keep FAULT_LAB_ENABLED=true.
docker compose up --build --wait
curl.exe http://127.0.0.1:8000/healthz
curl.exe http://127.0.0.1:8000/items/1
```

Item 1 returns `{"id":1,"name":"Notebook"}`. Unknown IDs return 404.
`/healthz` never queries PostgreSQL; it is a liveness check, not DB readiness.
The password is read from the ignored `.env`; no real credential is committed.
The app binds to localhost and PostgreSQL is not published to the host.

## Reproduce

Use an otherwise idle lab with the default pool configuration:

```powershell
docker compose exec app python scripts/reproduce_db_pool_exhaustion.py
docker compose logs app
```

The script first verifies health and item 1, starts two concurrent five-second
hold requests, then polls `/lab/diagnostics/db-pool` until `checked_out=2` and
`checked_in=0`. It allows two seconds to acquire both connections, leaving time
for the one-second pool timeout before either hold ends. The polling interval
is not the readiness test. It fails non-zero if setup, timing, error response,
connection release, or recovery differs from expectations. The HTTP client's
connection capacity exceeds the database pool capacity.

Expected evidence (timing and request ID vary):

```text
normal: 200 {'id': 1, 'name': 'Notebook'}
occupied: {"configured_pool_size": 2, ..., "checked_out": 2, "checked_in": 0, "overflow": 0}
fault: status=503 latency_ms=1005.12 request_id=... body={"error":{"code":"DB_POOL_TIMEOUT","message":"Database connection pool temporarily exhausted"}}
recovered: 200; after: {..., "checked_out": 0, "checked_in": 2, "overflow": 0}
PASS: real pool exhaustion produced structured 503, then recovered
```

Standard logs contain path, status, generated request ID, and latency in
milliseconds. Responses include `X-Request-ID`. Pool timeouts also emit a
`DB_POOL_TIMEOUT` warning with the same ID. Other exceptions are not mapped to
that code and remain server errors; raw exceptions are not returned to clients.

## Tests

Inside the running stack (no host Python required):

```powershell
docker compose exec app python -m pytest -m "not integration" -q
docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s
```

The second command runs both lightweight tests and the real HTTP/PostgreSQL
integration scenario: found/missing items, invalid hold durations, actual pool
timeout, DB-independent health during exhaustion, and recovery. No pool mock is
used. Run integration tests serially against an idle dedicated lab.

Alternatively, with Python 3.12+ installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python scripts/reproduce_db_pool_exhaustion.py
$env:RUN_INTEGRATION = '1'
.\.venv\Scripts\python -m pytest -q -s
```

Without `RUN_INTEGRATION=1`, the database test is explicitly skipped. Dependencies
are pinned in `requirements.lock`; `pyproject.toml` records direct dependency
ranges. Uvicorn is the ASGI server; the remaining dependencies are limited to
the requested stack. Pytest and httpx are included in the lab image so verification
can run there.

## Pool configuration and lab boundaries

`DB_POOL_SIZE=2`, `DB_MAX_OVERFLOW=0`, and `DB_POOL_TIMEOUT=1` are deliberately
tiny lab defaults, not production sizing advice. Two holds consume all available
connections, no overflow connection may be created, and another request waits
about one second before SQLAlchemy raises `sqlalchemy.exc.TimeoutError`.
Settings validate positive pool size/timeout and nonnegative overflow. The script
requires these exact defaults; change them back before running it.

`FAULT_LAB_ENABLED` defaults to false in code and Compose. Both lab routes are
absent, including from OpenAPI, unless explicitly enabled. `.env.example`
explicitly enables them for local use. A hold runs `SELECT 1` through the same
`AsyncSession` factory as `/items`, then asynchronously sleeps while its
transaction owns the connection. Session cleanup rolls back and returns it.
Hold duration is limited to `(0, 60]` seconds.

Diagnostics read public SQLAlchemy pool methods without querying PostgreSQL.
`overflow` is the raw SQLAlchemy value and can initially be negative because
connections are created lazily; it is not a count of failed requests. Statistics
describe this process's pool, not all PostgreSQL connections. Keep **one Uvicorn
worker and one app instance**: each process has its own pool. This is a local,
unauthenticated lab surface, not a production monitoring API.

Reference: [SQLAlchemy async connection pools](https://docs.sqlalchemy.org/en/20/core/pooling.html)
and [pool timeout explanation](https://docs.sqlalchemy.org/en/20/errors.html#queuepool-limit-of-size-x-overflow-y-reached-connection-timed-out-timeout-z).

## Request data flow

Normal: HTTP request → request ID/timer middleware → FastAPI `/items/{item_id}`
→ `get_session` creates an `AsyncSession` → parameterized `SELECT` asks the
SQLAlchemy async pool for a connection → asyncpg → PostgreSQL `items` table
→ row (200) or no row (404) → session closes/transaction rolls back/connection
returns to pool → response with request ID and request log.

Fault: two concurrent HTTP hold requests → two `AsyncSession` objects → each
executes `SELECT 1` and retains its connection while sleeping → diagnostics
confirms both connections checked out → `/items/1` asks the same pool for a
third connection → no overflow allowed → waits one second → SQLAlchemy pool
timeout → explicit exception handler logs `DB_POOL_TIMEOUT` → structured 503
with request ID → hold requests finish → sessions return both connections
→ subsequent `/items/1` gets a connection and returns 200. The failed item
request never reaches PostgreSQL; the pool cannot lend it a connection.

## Read these files

- `app/config.py`: validated environment settings and tiny pool defaults.
- `app/database.py`: engine and session lifetime.
- `app/main.py`: request logging, query, timeout handler, hold and diagnostics.
- `scripts/reproduce_db_pool_exhaustion.py`: the complete reproducible scenario.
- `tests/`: lightweight checks and real integration scenario.
- `db/init.sql`, `compose.yaml`, `Dockerfile`: seed data and runtime.

PostgreSQL initializes the table and seed rows on the first start of its named
volume. `docker compose down` stops the lab while preserving its data. For a
deliberate fresh reset, `docker compose down -v` deletes **this lab's database**;
the next startup recreates it. Stop after M0; no other fault is implemented.
