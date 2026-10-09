# M1 Task 1 run evidence — 2026-10-09

Source baseline: M0 closeout `aab5cba810c0b6b3e14dd25836ec14178962d5d4`.
M1 source and these artifacts are committed together. [source-manifest.json](source-manifest.json)
records normalized source SHA256 values and an exact match against the tested
running container; it avoids an impossible self-referential commit hash.
Times inside evidence records are UTC; the folder date is Asia/Shanghai.
Exports use normalized UTF-8/LF text; trailing build-output whitespace was
removed. Measurements, request IDs and substantive output are preserved.

## Native real HTTP run

- [pytest output](m1-task1-local/pytest.txt): **8 passed, 1 deselected in 6.21s**.
- [scenario records](m1-task1-local/scenario.json): independently spawned app
  and downstream, normal 200 → ReadTimeout 504 → recovery 200. No PostgreSQL
  connection is needed (DB address intentionally points to an unused test port).
- [app log](m1-task1-local/app.log), [downstream log](m1-task1-local/downstream.log):
  correlated actual TCP requests and contract records, captured by the fixture.

Command used with existing Python 3.12.13 `.venv`:

```powershell
$env:LAB_RUN_DIR = 'D:\job\artifacts\runs\2026-10-09\m1-task1-local'
.\.venv\Scripts\python -m pytest -q -s -m 'not integration'
```

## Compose / PostgreSQL run

- [pytest output](m1-task1-compose/pytest.txt): **9 passed in 9.51s**, including
  real DB pool scenario and independent HTTP subprocess scenario.
- [standalone HTTP export](m1-task1-compose/downstream-scenario.json),
  [script stdout](m1-task1-compose/downstream-reproduction.txt): against the
  Compose services, **200 → 504 (1006.09ms) → 200**. DB pool unchanged at 0
  checked out / 2 checked in, propagated fault request ID
  `b8b0f50537704139a66f699257055eb3`, actual delayed work still active at timeout,
  then drained and injection cleared.
- [selected app events](m1-task1-compose/app-events.log),
  [selected dependency events](m1-task1-compose/downstream-events.log): original
  log lines filtered to relevant request/error/evidence/receipt events, not a
  full log export. The DB fault evidence correlates to the pytest request ID.
- [services](m1-task1-compose/services.txt): all three services healthy.
- [last build attempt](m1-task1-compose/startup.txt): Docker Hub anonymous-token
  EOF when resolving the base image. A prior build had succeeded after a PyPI
  TLS retry and started the services. This file is a **failed later attempt**,
  not the successful image-build log.
- [container source hashes](m1-task1-compose/container-source.json): the final
  integration test assertions were synced into the already-built app with
  `docker compose cp tests/test_integration.py app:/service/tests/test_integration.py`
  after network failures prevented rebuild. Source comparison confirms all
  tested Python files and dependency declarations match the final workspace.
  The container test-file sync is not a permanent image layer modification.

Commands:

```powershell
docker compose exec -T -e RUN_INTEGRATION=1 app python -m pytest -q -s
docker compose exec -T app python scripts/reproduce_downstream_timeout.py --output /tmp/downstream-scenario.json
docker compose cp app:/tmp/downstream-scenario.json artifacts/runs/2026-10-09/m1-task1-compose/downstream-scenario.json
```

No global Docker settings or existing DB data were reset. Services are left
running for Owner inspection; use `docker compose down` to stop while preserving
the PostgreSQL volume. Old M0 evidence remains in `VERIFICATION.md`.
