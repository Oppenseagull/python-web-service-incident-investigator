# M0 verification — 2026-09-18

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

**Not verified here:** Docker image build, PostgreSQL startup/seed data, normal
database request, real pool exhaustion/503 timing, connection return/recovery,
and the database integration test. The implementation and executable scenario
are present, but these behaviors must not be treated as verified successes.

After Docker Desktop can run Linux containers:

```powershell
docker compose up --build --wait
docker compose exec app python scripts/reproduce_db_pool_exhaustion.py
docker compose exec -e RUN_INTEGRATION=1 app python -m pytest -q -s
```
