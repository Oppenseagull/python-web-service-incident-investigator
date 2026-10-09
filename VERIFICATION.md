# M0 verification

## M1 Task 1 verification — 2026-10-09

M0 remains Completed. The new increment is implemented and awaiting Owner review.
These are newly executed results, separate from the owner's earlier M0 evidence.

- Native run: `.\.venv\Scripts\python -m pytest -q -s -m 'not integration'`
  with `LAB_RUN_DIR` set to the dated local run folder: **8 passed, 1 deselected
  in 6.21s**. Real TCP subprocesses reproduce HTTP timeout/recovery; core timeout
  is not mocked. Additional tests cover lab flags, delay/TTL bounds and expiration,
  non-read HTTP error discrimination, and unknown evidence fields/latency validation.
- Compose: `docker compose exec -T -e RUN_INTEGRATION=1 app python -m pytest -q -s`:
  **9 passed in 9.51s**. Includes normal/missing DB items, real pool exhaustion
  and recovery, shared DB evidence record validation, and real HTTP scenario.
  DB regression measured 1003.55ms to structured 503 and ended at pool state 0/2.
- Standalone second-fault script against actual Compose services:
  `docker compose exec -T app python scripts/reproduce_downstream_timeout.py --output /tmp/downstream-scenario.json`:
  **PASS**, normal 200 → structured 504 after **1006.09ms** → recovery 200.
  Ground truth: armed 3s downstream response delay; 1s app read timeout. The
  matching request ID was observed at the downstream with one request still
  active when the app timed out. DB pool stayed `checked_out=0`, `checked_in=2`.
  Reset and request drain completed before the recovered request.
- Fault request ID: `b8b0f50537704139a66f699257055eb3`; app evidence logs preserve
  `ReadTimeout`, dependency `controlled-http`, and actual client-call duration.
- Compose config validation passed; services were healthy. Docker initially
  lacked an engine pipe but subsequently responded with version 29.7.2. A
  successful build/start followed a transient PyPI TLS failure. Later rebuilds
  encountered Docker Hub auth EOF, so final test-only assertions were copied
  into the running app. Source hashes confirm tested code matches the workspace.

[Run index and retained raw/exported evidence](artifacts/runs/2026-10-09/README.md)
include provenance and the failed later build attempt. No new dependencies were
added. Current image rebuild may require working Docker Hub connectivity; this
is an environment limitation, not an unverified core HTTP/DB scenario.
No proposed catalog fault, Agent, persistence service or general Eval Runner was built.

## Final M0 verification — M0 Completed

Formally archived on 2026-10-09 from the owner's previously supplied terminal output.
The exact execution date was not supplied. This is user-provided evidence,
not a new test run by Codex today.

Command:

```powershell
docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s
```

Result: **3 passed in 5.55s**, including the real PostgreSQL-backed pool
exhaustion and recovery scenario.

```text
normal: 200 {'id': 1, 'name': 'Notebook'}
before: {"configured_pool_size": 2, "configured_max_overflow": 0, "pool_timeout_seconds": 1.0, "checked_out": 0, "checked_in": 2, "overflow": 0}
occupied: {"configured_pool_size": 2, "configured_max_overflow": 0, "pool_timeout_seconds": 1.0, "checked_out": 2, "checked_in": 0, "overflow": 0}
fault: status=503 latency_ms=1006.88 request_id=c9b8fc0e41e249d78e4f88bf2f3b4c25 body={"error":{"code":"DB_POOL_TIMEOUT","message":"Database connection pool temporarily exhausted"}}
recovered: 200; after: {"configured_pool_size": 2, "configured_max_overflow": 0, "pool_timeout_seconds": 1.0, "checked_out": 0, "checked_in": 2, "overflow": 0}
PASS: real pool exhaustion produced structured 503, then recovered
...
3 passed in 5.55s
```

### Verified behavior and evidence provenance

- The retained terminal excerpt is owner-provided evidence, preserved above.
  It shows a normal 200; two real pool connections checked out with none idle;
  a structured 503 `DB_POOL_TIMEOUT` after **1006.88 ms**; recovery to 200;
  and both connections returned (`checked_out=0`, `checked_in=2`).
- The owner explicitly confirmed running the complete real PostgreSQL fault
  injection and recovery flow. The current integration test calls the same
  reproduction function, whose holds execute `SELECT 1` through the application
  session factory; it does not simulate exhaustion with an error response.
- The exact pytest summary is **3 passed in 5.55s**. The current suite contains
  two lightweight tests and one integration test. Its assertions also cover
  health, found/missing items, invalid hold durations, disabled lab routes,
  request logging/ID, and unexpected errors remaining 500. These individual
  assertions are identified from source, not separately printed results.
- The printed fault request ID is retained for correlation. A matching raw
  application log export, Docker build log, server-side checkout timestamps,
  and exact execution date/environment versions for this successful run were
  not retained in the workspace; those details are not claimed as independent
  evidence. In particular, 1006.88 ms is the client's measured request latency.

The M0 technical spike is complete. The earlier Docker startup failure is
historical and is superseded for the tested behavior by this successful run.
Personal learning checks are not milestone blockers. Overall project progress
is maintained in [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md).

This documentation closeout did not rerun tests, restart containers, alter
application code, or verify today's Docker availability. No material evidence
contradiction was found that would require repeating M0 acceptance.

## Initial Codex verification — 2026-09-18 (historical)

Environment: Windows, Python 3.12.13 in `.venv`, dependencies installed from
`requirements.lock`.

Executed:

- `.\.venv\Scripts\python -m pytest -q`: **2 passed, 1 skipped in 0.62s**.
  The skipped test requires `RUN_INTEGRATION=1` and the running PostgreSQL lab.
- `.\.venv\Scripts\python -m compileall -q app scripts tests`: passed.
- `docker compose config --quiet`: passed with a locally generated password in
  ignored `.env` (not a committed credential).
- `docker desktop start`: attempted; backend failed to become available.
- `docker compose up --build --wait`: failed, exit 1, Docker Linux engine pipe
  `dockerDesktopLinuxEngine` not found.
- `.\.venv\Scripts\python scripts/reproduce_db_pool_exhaustion.py`: failed,
  exit 1, `FAIL: All connection attempts failed`, since the stack could not start.

Docker Desktop's backend log reported an inaccessible
`C:/Users/Dell/AppData/Local/Docker/run/sailor-ingest.sock` and shut down.
No system Docker files or settings were altered. No native PostgreSQL executable
was found on PATH.

**Not verified in that initial run:** Docker image build, PostgreSQL startup/seed data, normal
database request, real pool exhaustion/503 timing, connection return/recovery,
and the database integration test. At that time the implementation and executable
scenario were present, but these behaviors were not yet verified successes.
The final successful evidence above records the subsequent M0 result.

Historical suggested follow-up commands (subsequently run successfully by the
owner for the test command shown in the final record):

```powershell
docker compose up --build --wait
docker compose exec app python scripts/reproduce_db_pool_exhaustion.py
docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s
```
