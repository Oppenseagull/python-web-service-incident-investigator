# PROJECT A Decision Handoff — 2026-10-10

> **类型：设计方向/战略约束，非代码实现报告。** 用于向 Codex 和其他聊天同步最新裁决。实际已完成内容一律以仓库 `docs/CURRENT_STATE.md`、最新 commit 和测试结果为准。任何本文提及的目标架构、实验、功能，均不得自行解释成“已实现”。

## 1. 已确认的产品方向

- Project A：**Evidence-Driven Incident Investigation Agent / Python Web Service Incident Investigator**。
- 目标使用者：维护 Python Web 服务的后端工程师/值班工程师。
- 输入：无已知根因的告警/异常症状，可能只有接口、时间窗口、延迟、错误率等信息。
- 输出：最可能根因及证据引用、尚未排除的假设、证据不足状态、建议的下一步人工操作；第一版只读，不自动修复生产系统。
- 中心任务：**Adaptive Root-Cause Investigation**，不是按已知错误码完成固定六分类。
- 必须分离：**Fault Lab / Evaluation Controller**（注入、标签、隐藏 Ground Truth）与 **Investigator**（只见实际可合理观测的证据）。Lab 场景数量不等于 Agent 调查能力。

## 2. Agent / 规则边界与求职标准

- Agent 优先负责：形成/修正假设、选择下一诊断工具、多轮读取证据、决定停止/待确认、撰写带证据的结果。
- 后端确定性负责：权限、schema、工具执行、任务状态、超时、重试、隔离、事件关联、持久化、测试、指标采集。
- **不要求 Agent 在每个场景都比规则优秀**；工程层面可信的 Tool Calling、Context、Failure Handling、可重复 Eval 和合理的混合架构即可支撑实习项目。不要虚构 Agent 收益或已完成能力。
- Eval 应有固定/规则基线与多步 Agent 对照，评估根因/证据质量、无依据断言、无效/重复取证、时延/成本和困难场景结果；小型合成 Case Suite 只能如实描述为开发/回归测试，不冒充生产规模泛化。
- 允许参照成熟产品/开源实现、按许可证复用；必须归属清楚，能解释个人改动和设计取舍。

## 3. 当前已确认实现进度（截至 2026-10-09 GitHub main）

仓库：`Oppenseagull/python-web-service-incident-investigator`。

- `M0 Completed`；`M1 Task 1` **implemented, awaiting Owner review**，不是 M1 完成。
- 已实现：FastAPI + SQLAlchemy 2.x async + asyncpg + PostgreSQL、Docker Compose、基本日志/请求关联、真实应用 DB pool exhaustion、真实 downstream HTTP ReadTimeout、共同 Evidence Contract、对应复现脚本/测试。
- 当前 Catalog 为 **2 Implemented + 4 Proposed**；10 月 9 日仓库记录 Compose full suite 9 passed。
- 未实现：Agent/LLM investigation、Incident persistence、通用 Eval Runner、自动证据收集与关联、Worker/Queue、分布式 Trace/Metrics 栈、前端。
- 重要：`scenario_id`、注入器控制状态、Controller 记录等会泄露答案；严禁直接把它们放入 Agent 的盲测上下文。真实错误类如 `DB_POOL_TIMEOUT` 可以是可见运行线索，但不能直接当成上游根因的测试答案。
- 当前两种故障容易用确定性规则区分；它们证明 Fault Lab 与证据工作，不证明 Agent 增益。

以上仅为本次交接时快照。**开始实际工作前必须重新读取 GitHub CURRENT_STATE/DECISIONS/最新 commit。**

## 4. 下一阶段开发方向（尚未实现）

1. 先让 Owner 对现有 M1 Task 1 实现/测试做 Review，不擅自记为完成整个 M1。
2. 把注入/评测答案与 Agent 可见运行证据逻辑隔离，设计安全的只读诊断 Tool Contract。
3. **优先实现第一条 Agent Investigation Vertical Slice**：接收无场景标签的 incident → LLM 选择只读工具 → 后端验证、执行并返回结果 → LLM 可以继续查证或停止 → 输出引用证据的调查报告。复用现有两个真实故障；此阶段证明闭环可运行，不声称优于规则。
4. 再增加少数有真实因果关系的复杂场景，如锁等待/长查询/下游慢导致连接占用，形成相似表象、上游根因不同的任务；并建立简单的确定性 baseline 和隐藏答案的 Eval Suite。
5. 依据真实实验再增加状态持久化、后台任务、超时/重试/Trace、更多可靠性机制；这些是可选的后续迭代，不是当前已实现。

**停止以“先凑齐六类固定故障”为第一优先级。也不启动第二轮泛化项目选型。**

## 5. 职业与 Project B

- 第一阶段目标：较快形成可信、可解释、可测试的 **实习可投版本**，并确保本人能被技术面试连续追问。
- 长期技术主线：Python AI Application + 实质性 Backend 工程；Hot100/八股独立并行。
- **Dependency Migration & CI Validation** 仅保留为有价值的未来 Project B / Backup 候选；不并行启动、不视为已冻结或完成。

## 6. Codex 交接纪律

- 先阅读仓库 `docs/CURRENT_STATE.md`、`docs/DECISIONS.md`、`docs/INCIDENT_CASE_CATALOG.md`、`docs/EVIDENCE_CONTRACT.md` 和活跃代码；如没有 ROADMAP 文件，不虚构。
- 将本决策以**设计变更/后续方向**形式记入文档；保持 M0/M1 历史进度与测试记录真实。
- 第一次同步仅做文档修改，不在未获许可时实施 Agent、加新依赖、改实验场景或重构架构。
- 每次任务在变更后更新 CURRENT_STATE：实现/测试证据、尚未完成的东西、下一项待 Owner 决策。
