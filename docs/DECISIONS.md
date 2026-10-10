# Project A engineering decisions

Archived: 2026-10-09. These decisions describe the implemented M0 baseline.
They do not freeze M1 architecture or claim later system capabilities.

M0 decisions below are retained as their milestone baseline. The subsequent
M1 Task 1 decisions at the end extend that baseline under Owner authorization.
The 2026-10-10 direction update below supersedes the earlier proposed next-step
ordering and resolves the product-level Agent direction. Comparative benefit
is still unmeasured; historical implementation and verification facts remain unchanged.

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

## M1 Task 1 — second controlled dependency

- Context: A second real failure should share the symptom of waiting but need
  evidence different from application DB pool saturation.
- Decision: Add one small FastAPI downstream process, reuse existing dependencies
  and Dockerfile, and issue real requests via a lifespan-scoped httpx client.
  Delay actual responses for 3s against a 1s read budget; catch ReadTimeout as
  504. Other HTTP errors keep distinct 502 codes.
- Reason: Prove a request arrived at the dependency while the DB pool was idle;
  avoid simulated exceptions and prevent error-class conflation.
- Cost: Compose now has three services; native tests need two subprocesses.
  HTTP read timeout is per IO read, not an overall deadline. No retry policy is
  introduced and this is still a dedicated local lab.

## M1 Task 1 — bounded injection and explicit cleanup

- Context: A client timeout does not imply downstream work stops; an interrupted
  reproduction must not leave an indefinite fault.
- Decision: A single-process response-delay setting has a monotonic TTL and
  explicit reset. Existing requests retain their arrival-time delay snapshot.
  The script confirms fault state, resets in `finally`, polls request drain,
  and then checks recovery. Lab endpoints require the flag in each process.
- Reason: Deterministic readiness, bounded mutation and observable cleanup.
- Cost: In-memory state and last request receipt apply only to an idle single
  dependency instance; this control surface is not production monitoring.

## M1 Task 1 — observation contract and ground-truth separation

- Context: Two faults need comparable evidence without a full incident service.
- Decision: Share a Pydantic evidence model in request JSON logs and both
  reproduction exports; keep source/event type, UTC timestamp, IDs, dependency,
  error, duration and case-specific observations. Unknown incident IDs are null
  in application events; run IDs exist only in controller records.
- Reason: Preserve provenance and correlate request IDs without inventing
  timestamps, phase timings or incident persistence.
- Cost: There is no automatic ingestion/correlation/store. Scenario labels and
  injector state reveal lab ground truth and cannot be treated as a blind
  diagnosis result. Snapshots and latencies come from different observation scopes.

## M1 Task 1 — catalog before Agent investment

- Context: A list of distinguishable failures does not itself justify an Agent.
- Decision: Define six cases with confounders, evidence/tool requirements and
  diagnosis criteria; implement only DB pool exhaustion and HTTP response delay.
  Keep four designs Proposed and explicitly discuss deterministic baselines.
- Reason: Lock/query delay can cause secondary pool symptoms; broad worker stalls
  can resemble dependency timeouts. Future benefit must be tested against such
  ambiguity with ground truth hidden.
- Cost: The current two cases can be distinguished with simple rules. Agent
  necessity, persistence and general evaluation architecture remain undecided.

## 2026-10-10 — Adaptive Root-Cause Investigation direction

- Context: M0 and M1 Task 1 establish reproducible faults and observations.
  Their two explicit error classes are easy to distinguish; treating that as
  the final product would reduce investigation to a fixed fault classifier.
- Decision: Keep Incident Investigator as Project A. Target backend/on-call
  engineers investigating symptoms with an unknown root cause through dynamic,
  multi-step, controlled read-only evidence gathering. Reports cite evidence,
  retain unresolved hypotheses, admit insufficient evidence, and suggest human
  next steps. First version performs no production remediation.
- Reason: Investigation quality depends on hypothesis revision and selecting
  useful next observations, not the number of catalog labels.
- Cost: The Agent investigation is a confirmed product target, not yet built.
  Root-cause claims need evidence; the existing lab cannot demonstrate Agent
  benefit or production generalization. Model and implementation choices remain open.
- Authority: Owner-provided [dated handoff](handoffs/2026-10-10/PROJECT_A_DIRECTION_HANDOFF_20261010.md),
  consolidated in [PROJECT_DIRECTION.md](PROJECT_DIRECTION.md).

## 2026-10-10 — Agent reasoning and deterministic execution

- Context: Adaptive investigation requires discretionary next-step choices
  while tool execution and service constraints must remain reliable.
- Decision: Agent forms/revises hypotheses, chooses tools, analyzes evidence,
  and decides whether to continue/stop/request confirmation. Deterministic
  code owns permissions, schemas, tool execution, validation, state, timeouts,
  budgets, retry policy, correlation and any future persistence.
- Reason: Explicit programmatic boundaries make tool calling inspectable and
  testable without relying on the model to enforce its own permissions.
- Cost: Tool and report contracts, context/state design and failure handling
  still require development. This decision adds no framework or runtime component.

## 2026-10-10 — Ground Truth separation and honest Eval

- Context: Scenario IDs, injector state and controller exports can expose the
  answer. Distinguishing known lab faults is not a blind investigation evaluation.
- Decision: Fault Lab/Controller retains injection, labels and hidden Ground
  Truth; Investigator sees only reasonably observable, authorized evidence.
  Exclude answer-revealing metadata from blind context. Real error classes may
  remain operational clues but do not establish the upstream root cause.
  Establish repeatable fixed/rule baseline versus multi-step Agent Eval later;
  do not require Agent superiority in every scenario or assert benefit in advance.
- Reason: Evaluate root-cause/evidence quality, unsupported claims, redundant
  or ineffective tools, latency/cost and difficult cases with faithful provenance.
- Cost: Evidence projection, leakage checks and general Eval Runner are unbuilt.
  Synthetic case suites are development/regression tests, not production-scale
  generalization evidence. Existing schema and nine tests are retained as lab work.

## 2026-10-10 — Investigation Vertical Slice before catalog expansion

- Context: Mechanically implementing all six candidates postpones testing the
  core investigation loop. Four Proposed cases are a design reserve, not a gate.
- Decision: After Owner review, prioritize a label-free incident → LLM tool
  choice → backend validation/execution → further evidence or stop → cited report
  vertical slice using the two existing faults. Follow with selected causal
  confounders and hidden-answer Eval rather than completing a fixed six-class list.
- Reason: First prove a working investigation loop, then evaluate and improve
  it using measured evidence; do not make universal superiority over rules a prerequisite.
- Cost: The first slice proves execution, not comparative diagnostic gain.
  Framework, model, storage, budgets, Eval design and additional infrastructure
  remain unfrozen. No new project selection or parallel Project B is started.

## 2026-10-10 — S1 closed read-only tools and safe evidence projection

- Context: Raw Evidence v1 and lab diagnostics contain scenario/control metadata;
  S2 needs actual observations without receiving the test answer.
- Decision: Owner approved three Python tools: bounded application-event query,
  connection-free application pool snapshot, and fixed downstream `/healthz`
  probe. Use existing Pydantic/httpx; closed schemas, nested field allowlists,
  approved paths/enums, no raw text/exports, no redirects or caller URLs. Exclude
  all lab request events, scenario/run IDs and injector metadata before caching.
- Reason: A small, executable boundary can be tested with the two real faults
  while preserving useful error classes, timing, correlation and pool evidence.
- Cost: Health checks show current liveness only. No downstream receipt tool,
  DB server activity queries, historical file ingestion or arbitrary data access.
  This is an interface/data boundary, not independent process/container or
  production permission isolation. Existing privileged lab interfaces still exist.
- Authority: Owner explicitly approved the proposed S1 plan in this session;
  this approval does not certify their independent M1 learning review.

## 2026-10-10 — S1 bounded memory, citations and execution limits

- Context: Standard logs cannot currently be queried through a safe tool, and
  adding a storage platform would delay the first investigation slice.
- Decision: Capture the actual middleware Evidence through projection into a
  process-local store, capacity 2,000 observations, 600s monotonic retention,
  FIFO eviction, locked bounded operations with no IO under the lock. Store safe
  request events and tool snapshots; observation UUIDs remain stable while retained.
  Query by request ID and/or aware window <=300s, max 50 results. Report truncation,
  nulls, missing/unavailable/error states. Use a 2s async execution deadline,
  1s probe IO timeout, 4 KiB health response limit and sanitized error codes.
- Reason: Stable citations and bounded reads support S2 without a new dependency,
  persistence schema, public API or plugin architecture.
- Cost: Restart/eviction loses evidence; each process owns its store and pool.
  A returned record can expire before later lookup. Async deadlines cannot stop
  event-loop blocking code. Unknown lookup is `None`, not a fabricated observation.
  Agent/Eval/model/storage/queue decisions remain outside S1.
