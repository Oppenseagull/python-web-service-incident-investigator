# Project A — 当前项目方向

Owner 确认日期：2026-10-10。本文记录经确认的产品定义、职责边界和开发优先级，
不构成实现报告，也不授权直接开始开发。

决策依据：[PROJECT_A_DIRECTION_HANDOFF_20261010.md 原文](handoffs/2026-10-10/PROJECT_A_DIRECTION_HANDOFF_20261010.md)。
原文件来源：`C:/Users/Dell/Desktop/求职/PROJECT_A_DIRECTION_HANDOFF_20261010.md`；
归档副本逐字节保留，SHA256：
`10939277cc8bca900427771d72acec3736994a457aaa2c4971d9f7e3244b20fb`。
交接原文中的 GitHub 进度是当时的描述；本文不据此宣称已推送或远端已同步。
实际本地进度以 [CURRENT_STATE.md](CURRENT_STATE.md)、代码 commit 和
[VERIFICATION.md](../VERIFICATION.md) 为准。

## 项目定义与中心任务

Project A 继续采用 **Evidence-Driven Incident Investigation Agent /
Python Web Service Incident Investigator**，不重新选题。

目标使用者是维护 Python Web 服务的后端工程师或值班工程师。中心任务为
**Adaptive Root-Cause Investigation**：从未知根因的异常症状出发，通过受控只读
工具动态进行多步取证，形成和修正假设，并输出有证据支持的诊断报告。

- 输入：告警或异常症状，可以只有受影响接口、时间窗口、延迟、错误率等线索；
  不提供注入场景标签或预设正确根因。
- 过程：根据当前证据选择下一项检查，读取并分析结果，修正或保留假设，判断是否
  继续调查、停止或需要人工补充证据。合理的工具错误和证据缺失必须能够表达。
- 输出：最可能根因与证据引用、尚未排除的假设、证据不足状态，以及建议的下一步
  人工操作。不得把错误类型或未验证假设直接写成已经证明的上游根因。
- 第一版只读；不自动修复生产系统。具体报告 schema 和执行预算尚未确定。

## Fault Lab 与 Investigator 的边界

Fault Lab / Evaluation Controller 是开发与评测环境，负责故障注入、恢复、
场景标签和隐藏 Ground Truth。Investigator 是目标产品，只读取实际可合理
观测到的运行证据。六个候选场景是案例储备，场景数量不能替代调查质量。

后续必须建立独立的 Agent 可见证据视图：

- 不向盲测上下文暴露 `scenario_id`、预期根因、注入器控制状态、Controller
  场景记录或能直接透露答案的字段、工具描述和文件名称。
- 真实运行错误类、请求 ID、延迟和经过许可的日志或状态观测可以作为线索；
  例如 `DB_POOL_TIMEOUT` 说明借连接失败，不能直接证明连接被占用的上游原因。
- 当前导出记录和诊断接口用于已知故障的复现，其中包含 Ground Truth 信息。
  **现有 Evidence Contract 不是已经隔离答案的 Agent Tool Contract**；安全投影、
  工具封装和泄漏检查均尚未实现。

参见 [案例目录](INCIDENT_CASE_CATALOG.md) 和 [当前证据契约](EVIDENCE_CONTRACT.md)。
两者已有的技术事实仍有效；其中对当前简单案例的判断，不应再作为暂缓整个
Investigator 方向或机械补齐六个故障的理由。

## Agent 与确定性后端的职责

| Agent 负责的判断 | 确定性程序负责的执行与约束 |
| --- | --- |
| 形成、比较、修正假设 | 只读权限、工具白名单、参数和返回 schema 校验 |
| 选择下一步诊断工具 | 实际工具执行、数据范围限制、隔离与错误返回 |
| 多轮分析与关联证据 | 请求/事件关联、受控状态记录和上下文提供 |
| 决定继续、停止或待确认 | 步数/时间预算、超时、重试策略和停止约束 |
| 输出带证据引用的调查报告 | 报告结构校验、测试和 Eval 数据采集 |

持久化若后续需要，应由确定性后端负责；它目前尚未实现，也不是此次同步
冻结的前置架构。模型不能通过自主生成命令绕开工具边界。后端校验和权限约束
不能依靠模型自觉遵守。

## Eval 与收益声明

不要求 Agent 在所有场景中优于规则，也不把当前两个案例容易区分解释为取消
Agent 产品目标。下一条 Vertical Slice 首先验证工程闭环，不能据此宣称 Agent
收益或生产泛化能力。

后续必须建立真实可重复 Eval，区分隐藏 Ground Truth 与调查可见证据，并保留
固定流程/规则基线与动态多步 Agent 对照。评估至少考虑：

- 根因判断与证据引用质量、证据不足时的处理。
- 无依据断言、无效或重复取证、困难或混淆案例结果。
- 调查时延、工具调用和模型成本。

小型合成 Case Suite 应描述为开发/回归测试，不冒充生产规模泛化评测。
当前复现脚本和九个测试证明 Fault Lab 与证据基础可工作，**不是 Agent Eval**。
只有完成真实对照实验后才报告收益或局限，不预设优于规则的结论。

## 当前实际进度

- **M0 Completed**。
- **M1 Task 1 implemented, awaiting Owner review**，不代表整个 M1 完成。
- 已实现：两个真实故障、基础日志/请求关联、共同 Evidence Contract、复现脚本
  和测试。案例目录为 **2 Implemented + 4 Proposed**。
- 既有结果：2026-10-09 Compose full suite **9 passed in 9.51s**；本机 suite
  **8 passed, 1 deselected in 6.21s**。此次文档同步未重跑测试。
- 尚未实现：LLM/Agent 调查、只读调查 Tool Contract 与答案隔离、Incident
  Persistence、通用 Eval Runner、自动证据收集/关联、新的四个候选故障、
  Worker/Queue、分布式 Trace/Metrics 栈和前端。

## 下一阶段的优先级

1. Owner Review 现有 M1 Task 1 和此次方向同步；后续开发需另行指令。
2. 明确只读诊断 Tool Contract，并隔离注入/评测答案与调查可见证据。
3. 优先实现第一条 **Investigation Vertical Slice**：无场景标签的 incident
   → LLM 选择只读工具 → 后端校验、执行并返回证据 → LLM 继续查证或停止
   → 输出引用证据的报告。复用现有两个真实故障，不以新增场景数量为首要目标。
4. 再按取证缺口增加少数有真实因果关系、相似表象但根因不同的案例，并建立
   确定性 baseline 和隐藏答案的 Eval Suite；不机械补齐六类故障。
5. 根据真实实验决定是否增加持久化、后台任务和更多可靠性机制。

这些是后续顺序与目标，不是本次已交付功能或冻结的完整架构。

## 仍未确定的技术决策

- LLM 提供方、模型、API/SDK 与是否需要任何 Agent 框架。
- 第一条 incident 输入、调查报告和工具调用/返回的具体 schema，以及证据引用方式。
- 首批只读工具、允许的数据范围、敏感字段/标签过滤与泄漏检查方式。
- 多轮上下文、状态保存形式、步数/时间/成本预算、停止与重试策略。
- Eval 的案例组成、困难案例、baseline 实现、评分与通过标准。
- 持久化、后台执行、更多场景和可观测性机制的引入时机。

原则已经确认，具体实现需在后续任务中选择，不能把这些选项登记为已实现。

## 项目定位与复用纪律

第一阶段目标是可信、可解释、可测试且本人能接受技术面试追问的实习可投版本，
技术主线为 Python AI Application 与实质性 Backend 工程。允许按许可证参考或
复用成熟实现，但应清楚归属，并说明个人改动与取舍。

Dependency Migration & CI Validation 仅保留为未来 Project B / Backup 候选，
不在此次任务并行启动，也不重新开展项目选型。此次同步不修改 Project Master
Context，不添加运行能力，完成后等待 Owner Review。
