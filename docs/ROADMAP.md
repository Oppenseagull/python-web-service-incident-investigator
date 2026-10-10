# Project A — Development Roadmap

> 整合来源：[Owner 提供的规划原文](handoffs/2026-10-10/PROJECT_A_ROADMAP_20261010.md)（原件完整归档）。本次仅同步文档，未重新运行测试；M0 Completed、M1 Task 1 implemented / awaiting Owner review 的实际状态保持不变。

> 规划版 2026-10-10。此文档定义实施顺序和验收关口，不等于授权开发，也不代表目标已实现。代码真实状态以 [CURRENT_STATE.md](CURRENT_STATE.md) 和测试为准；总体设计见 [ARCHITECTURE.md](ARCHITECTURE.md)。工作量是粗估的**专注开发日**（含 Codex、调试与本人理解），不是期限承诺。用户优先：尽快达到 **实习可投的可信闭环**；再扩展校招深度。

## 0. 当前基线与下一阶段决策

**已实现并验证**：M0 Fault Lab（DB 应用连接池耗尽）；M1 Task 1（真实下游 HTTP ReadTimeout、Evidence Contract、Case Catalog）。截至 2026-10-10，仓库状态仍记录 M1 Task 1 **implemented / awaiting Owner review**；Compose 历史结果为 9 passed。不是整个 M1 已完成。

**尚未实现**：Investigation API、LLM/Agent loop、只读 Agent tools 和盲测投影、任务级 Eval Runner、Incident store、Worker/Queue、分布式 telemetry。现有四个额外案例均为 Proposed。

**当前最近任务**：Owner review 现有 M1 Task 1，核对真实测试结果和理解；然后设计并实现 Agent 可见证据投影及最小只读工具（下文 S1），紧接 S2 Agent Vertical Slice。无需为了 Roadmap 推翻历史编号，`S*` 是独立的下一阶段规划代号，正式开发编号可按仓库既有规范落地。

## 1. 实习版路线（核心优先）

| 阶段 | 交付问题与成果 | 验收标准 | Owner 必学/面试资产 | 粗估 |
| --- | --- | --- | --- | --- |
| **G0 — Owner review（待确认）** | Review 已实现 M1 Task 1：真实 HTTP timeout、证据类型、清理恢复。批准下一步最小范围。 | 能独立复述正常 → 注入 → 504 → 恢复，以及 DB pool 场景的不同原因；旧测试复跑或核对原始结果，记录 Owner Review。 | HTTPX ReadTimeout 与 ConnectTimeout；async client lifecycle；连接池/事务；何为 Controller Ground Truth。 | 0.5–1 天 |
| **S1 — Safe investigator tools** | 设计接收症状输入和受控只读工具契约；屏蔽注入标签、控制端点与预期答案。复用有限 app/downstream/DB 诊断证据。 | 受控函数可实际获取观察值及稳定 evidence ID；tool schema 有严格参数校验、time/window 限制、错误/缺失状态；自动泄漏测试证明 Agent 看不到 scenario_id、controller/export/fault-control 状态；现有测试无回归。 | Typed tools / Pydantic、白名单、信任边界、日志查询与证据溯源、测试隔离。 | 1–2 天 |
| **S2 — First Agent Investigation Vertical Slice** | 从无答案标签的 IncidentInput 开始，LLM 选择工具，Runner 验证执行，支持多轮取证、停止或 inconclusive，输出带证据引用的结构化报告及完整步骤轨迹。 | 对现有两种真实故障各跑通至少一轮真实工具选择 → 执行 → 返回 → 继续/停止；模型错误/无效入参/工具超时/步数超限有受控结果；结构化报告中的 evidence IDs 均能映射实际 ToolResult；可演示且可复跑。此阶段**不宣称优于规则**。 | Function/tool calling、structured output、上下文、停止条件、成本预算、为什么 Agent 不可直接执行高危命令。 | 2–4 天 |
| **S3 — Causal / confusing cases** | 扩展少量真正有因果联系的场景，优先相同或相近症状下的不同根因，并支持多源只读观察。优先评估 DB 锁等待、长查询、慢下游导致连接占用中的可控组合。 | 至少实现并验证 2 个有区分度的新根因/复合案例；记录注入、实际症状、支持/反证、恢复；固定 controller 元数据不能通过 Agent 工具泄漏；有相同首发症状而取证路径不同的示例。具体方案取决于真实可行性。 | 锁等待、事务与连接使用范围、故障传播、应用与 DB 的观测能力。 | 2–4 天 |
| **S4 — Deterministic baseline + Eval** | 固定工作流/规则 baseline（明确其可用输入与 tool 权限），建立带隐藏答案的场景执行/评分器。加入失败分类和回归重跑。 | 固定开发回归集 + 未用于 prompt 微调的保留场景；每组至少记录根因是否正确、证据引用支撑、unsupported claims、tool 次数、时延/成本；保留 agent 失败与 baseline 胜出的案例；同配置重复运行并说明小样本不确定性。 | Eval 指标、任务级对照、公平基线、证据泄漏、误差分析、可重复实验。 | 2–4 天 |
| **S5 — Internship-ready reliability & presentation** | 对当前闭环进行必要可靠性收口；补文档、测试、演示脚本、简历 Bullet。按实际缺陷考虑最小 Run/Step 状态保存，但不强制 MQ/Redis。 | 新环境按 README 可启动并跑演示；至少一个失败路径可展示结构化处理；单元/集成/Eval 可复跑；有真实结果表与 Bad Cases；本人能无 AI 讲清关键调用链及设计取舍；简历只描述实际完成成果。 | API / DB / async / tests / Docker / 任务状态 / Agent+Eval 全链路 defend。 | 2–4 天 |

**实习可投 Gate**：S2、S3、S4、S5 核心验收满足；不用等待完整校招增强阶段。最低必须有：可交互调查闭环、真实受控系统与多源工具、可说明的 Agent/规则边界、几类有因果区分度的故障、可信 Eval、异常处理、文档和 Owner 独立解释能力。

**工作量风险**：合计为范围估算，可能受 Docker/环境、模型 API、OpenTelemetry/DB 权限等影响显著增加。优先缩场景数量/可视化，不削弱端到端闭环与 Owner 理解。

## 2. 校招增强路线（仅完成实习可投后按需启动）

| 阶段 | 可选主题 | 触发条件与验收证据 | 面试价值 |
| --- | --- | --- | --- |
| C1 — Durable investigation | PostgreSQL Incident/Run/Step persistence、重启后恢复/查询 | 真实中断或异步长任务导致内存状态不足；测试重启不丢已提交步骤，状态迁移一致。 | DB schema/transaction/state machine |
| C2 — Background execution | 独立 Worker、任务提交/取消、超时、幂等键和有限并发 | 调查超过 HTTP 请求预算；压测与 crash/duplicate requests 重现可靠性问题。 | async/queue/retry/idempotency/concurrency |
| C3 — Observability & optimization | 更完整 logs/metrics/traces、Context/Tool 策略实验、失败回放 | 具备稳定 workload；发现具体失败、Trace 定位并通过回归证明优化和代价。 | failure analysis/Eval/p95/cost/harness |
| C4 — Scope-driven extensions | 适量 RAG runbook、MCP Adapter、SSE、权限/多租户等 | 必须有业务问题和对照结果；禁止为了热门标签堆功能。 | 设计判断和技术演进 |

此表是**增强候选**，不是已确定全部实施。Project B（Dependency Migration & CI Validation）仍然是未来候选，不与本项目并行。

## 3. 每个 Task 如何交给 Codex

1. Project A 聊天读取最新 [CURRENT_STATE.md](CURRENT_STATE.md)、[DECISIONS.md](DECISIONS.md)、[ROADMAP.md](ROADMAP.md)、受影响源代码，提出**一个**下一 Task，明确现状、范围、排除项、接口候选、测试与学习目标。
2. Owner 理解、批准范围；Codex 先给变更计划和需要决定的问题，再实现代码。禁止未获授权同时启动下几个 Task。
3. Codex 运行必要单测/集成测试并保留命令与输出；无法运行须注明未验证，不能写成 passed。
4. Owner 做独立 Review：复述请求链路、至少一个失败链路、选择理由、替代方案，并能手动定位/改动一个小点。
5. Codex **只记录真实进展**到 [CURRENT_STATE.md](CURRENT_STATE.md)，已批准的技术决定写 [DECISIONS.md](DECISIONS.md)，必要时同步架构和 Roadmap；把验证证据链接到 README/VERIFICATION，提交后停下。

## 4. 文档冲突与变更规则

- [CURRENT_STATE.md](CURRENT_STATE.md) = 实际完成状态；不能因 Roadmap 中列出功能而宣称它已实现。
- [PROJECT_DIRECTION.md](PROJECT_DIRECTION.md) = 已确认产品边界；[ARCHITECTURE.md](ARCHITECTURE.md) = 现状和目标结构；[DECISIONS.md](DECISIONS.md) = 经授权的技术选择；[ROADMAP.md](ROADMAP.md) = 任务顺序；Case/Evidence 文档 = 技术事实与案例契约；Master Context = 长期求职战略。
- 新成果完成后仅修订受影响文档，避免一处改动引发全仓库无意义重写。
- 若 Roadmap 与当前实现冲突，先核 Git 提交、代码和测试，再更新 `CURRENT_STATE` 或 Roadmap；不要通过修改历史测试结果“解决矛盾”。
- 若新证据推翻项目定位或核心策略，提示 Owner 并建议更新 Master Context；若只是普通代码推进，不必改 Master Context。
- 对候选技术/功能使用 `Proposed/Undecided`，明确不是 `Decided/Implemented`。
