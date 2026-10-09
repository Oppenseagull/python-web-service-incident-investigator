# Evidence contract v1 — M1 / Task 1

Runtime model: [app/evidence.py](../app/evidence.py). The two implemented cases
use the same structure for application request events and reproduction exports.
No incident persistence or collection service exists.

| Field | Semantics / current availability |
| --- | --- |
| `schema_version` | Integer 1; schema changes require version review |
| `source` | `application` or `reproduction`; provenance must remain visible |
| `event_type` | `http_request` or `scenario_observation` |
| `incident_id` | Reproduction-run UUID hex; application events are null because there is no incident service or propagation |
| `scenario_id` | Catalog ID; controller labels every phase of its known scenario; application labels known timeout classes, not a proven hidden root cause |
| `request_id` | App-generated UUID hex, response header and logs; forwarded to controlled downstream; null for observations without a request |
| `timestamp` | UTC ISO-8601 creation time; application event ends the request, controller event follows its diagnostic reads; not a server request-start timestamp |
| `service` | `investigator-app`, the service being observed |
| `dependency` | `postgres`, `controlled-http`, or null when no dependency is known |
| `error_type` | Stable observed code, null on success; `UNHANDLED_ERROR` is not a diagnosis |
| `latency_ms` | Nonnegative duration or null if unavailable; app measures middleware handling, reproduction measures client round trip; do not compare as identical metrics |
| `observations` | Case-specific observed values, configuration, status and provenance; no fabricated metrics |

Unknown values are **null or omitted observation keys**, not zero. Zero is a real
measurement. Timestamps are wall-clock UTC; durations use monotonic clocks.
Application logs emit `evidence=<JSON>` through standard logging, along with
the existing human-readable request/timeout log messages. Files exported by
the controller contain arrays of contract records; no database record is created.

## Application observations

- All requests: `path`, `status_code` and any known dependency/error. Normal
  requests have null scenario ID; they are not automatically assigned an incident.
- `DB_POOL_TIMEOUT`: SQLAlchemy exception class and `db_pool` snapshot from
  public pool methods at timeout. Configured size/overflow/timeout, checked-out,
  checked-in and raw overflow values are observable. Holder identity/checkout
  duration, PostgreSQL wait events, server-wide sessions and query execution
  timing are **not available** from this snapshot.
- HTTP dependency path: target `/value`, configured read timeout and measured
  `dependency_latency_ms`; ReadTimeout has its exception class; network errors
  retain their actual exception class; HTTP status failures retain downstream
  status. No full URL/credential/raw exception is exported. DNS/connect/TLS
  phase timing and packet-level response-path evidence are **not available**.

## Reproduction observations

The HTTP script exports normal/fault/recovered phases under one incident ID,
with response status/body, request ID, client timing, DB pool snapshots and
dependency state. Fault state exposes delay/expiry, active request count, last
receipt time and propagated request ID; it is **privileged controlled-lab evidence**.
It proves correlation in an idle single instance, not diagnosis in arbitrary traffic.

The DB script remains compatible with its original exact error body. It now
exports contract records for its same phases and can write them with `--output`.
Existing M0 output is historical evidence and is not retroactively converted
into a fictitious application timestamp or newly correlated incident record.

## Diagnosis versus observations

`DB_POOL_TIMEOUT` establishes inability to borrow an application connection;
it does not identify why holders retained connections. `ReadTimeout` establishes
waiting too long for response data; it does not distinguish slow work, response
network trouble, or all downstream stalls. Scenario IDs in application logs
are coarse catalog associations, not automated diagnosis results. Controller
injection metadata supplies known ground truth and should be withheld from any
future blind diagnostic evaluation.

## Practical use and limits

Correlate exported fault `request_id` with the app evidence log and (for HTTP)
the dependency receipt log. `incident_id` groups controller phases only. There
is no authenticated public evidence endpoint, event store, tracing backend,
automatic ingestion, or agent. Pool/dependency state is process-local and
snapshots are not atomic with requests. A timed-out HTTP request can still run
in the downstream until its original delay ends; reset affects future arrivals.
The script waits for that in-flight count to drain before recording recovery.

HTTPX read timeout means waiting for response data/chunks, not an overall
request deadline. This dependency delays before sending a response, so the
lab's timeout is a deterministic ReadTimeout. Connect/network/httpx pool errors
are handled distinctly; no retries obscure the failure.
References: [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/),
[exception hierarchy](https://www.python-httpx.org/exceptions/).
