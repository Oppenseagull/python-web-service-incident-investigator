# S1 safe investigator tool verification — 2026-10-10

Baseline: `c6d77cbe67dbbefa6aee6b124b1d357a33b66452`. S1 source, documentation
and these artifacts are committed together. [source-manifest.json](source-manifest.json)
records all 23 Python/dependency files and confirms equality with the freshly
built app container after CRLF-to-LF normalization. There was no test-file copy
into an old image. Folder date is Asia/Shanghai; observations use UTC.

## Native run

- [pytest output](s1-native/pytest.txt): **43 passed, 2 deselected in 11.47s**.
- [Safe HTTP tool results](s1-native/safe-http-evidence.json): 200 → 504
  (application latency 1006.80ms) → 200, plus current health and pool observations.
- [Original real HTTP fixture logs and controller export](s1-native/legacy-http/):
  regression evidence, privileged lab data. Never a tool input.

```powershell
$env:S1_RUN_DIR = 'D:\job\artifacts\runs\2026-10-10\s1-native'
$env:LAB_RUN_DIR = 'D:\job\artifacts\runs\2026-10-10\s1-native\legacy-http'
.\.venv\Scripts\python -m pytest -q -s -m 'not integration'
```

## Fresh Compose run

- [Build/start output](s1-compose/startup.txt): successful fresh source build and
  health wait. No dependency/configuration/DB-volume change.
- [pytest output](s1-compose/pytest.txt): **45 passed in 20.68s**.
- [Safe HTTP results](s1-compose/safe-http-evidence.json): 200 → 504
  (1004.30ms application duration) → 200. Real ReadTimeout, safe request/evidence
  IDs, dependency duration, current health 200, no DB checkout.
- [Safe DB results](s1-compose/safe-db-evidence.json): 200 → 503
  (1004.07ms application duration) → 200. Timeout evidence pool 2/0;
  recovered live tool pool 0/2. IDs resolve in the tested cache during each run.
- [Original HTTP fixture logs/export](s1-compose/legacy-http/): privileged
  regression artifacts, excluded from Registry access.
- [Compose service status](s1-compose/services.txt): all three healthy.

```powershell
docker compose up --build --wait
docker compose exec -T -e RUN_INTEGRATION=1 -e S1_RUN_DIR=/tmp/s1-tools -e LAB_RUN_DIR=/tmp/s1-legacy-http app python -m pytest -q -s
docker compose cp app:/tmp/s1-tools/safe-db-evidence.json artifacts/runs/2026-10-10/s1-compose/safe-db-evidence.json
docker compose cp app:/tmp/s1-tools/safe-http-evidence.json artifacts/runs/2026-10-10/s1-compose/safe-http-evidence.json
docker compose cp app:/tmp/s1-legacy-http artifacts/runs/2026-10-10/s1-compose/legacy-http
```

Safe exports contain validated ToolResults with only projected observations.
Tests use controller calls to arrange/clean faults; the Registry reads only the
app's projected cache, public pool methods and fixed downstream health endpoint.
Application event durations differ in scope from client round-trip timings in
the original reproduction output. Live snapshots are separate from historical
timeout observations. File exports are review artifacts, not a persistence service.

## Coverage and limitations

34 new contract/security cases plus two real fault tool integrations; all nine
original tests retained. Cases include input/output validation, nested leakage,
control-path exclusion, window/quantity/retention limits, ID lookup, missing data,
errors, timeouts, redirects and limited response reads. Mock transports only
exercise error boundaries; core fault evidence comes from real HTTP/PostgreSQL.

Single process/worker, 2,000 safe observations, 600s retention, FIFO eviction and
restart loss. No historical log import, downstream receipt query, DB activity
inspection, public Investigation API, process sandbox, LLM or Agent Eval.
M0 Completed; M1 Task 1 and S1 await Owner Review. S2 unstarted.

Docker startup initially failed at its runtime socket. No socket was removed;
normal launch of the per-user installation recovered engine availability.
Services remain running for review; `docker compose down` preserves the DB volume.
