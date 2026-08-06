# 恢复、自修复与运行边界

长程系统的难点不是“永远继续”，而是在 session、Host、Agent、workspace 与外部事实都可能变化
时，仍能重新判断合法下一步。本章解释恢复、replan、self-repair 与 terminal closure，并用清晰的
运行责任避免 Extension、Provider 或 projection 越过 authority boundary。

## 本章目标

读完后，你应该能：

- 说明中断后需要 replay 什么、必须重新探测什么；
- 区分 continuation、replan、self-repair 与 retry；
- 识别 projection gap、stale evidence 与 workspace drift；
- 区分 Agent、Provider、Capability、Kernel 与 Extension；
- 判断何时 Goal 可以 terminal，而不只是 Todo 全部勾选；
- 识别 public/private boundary 被破坏的情况。

## 恢复的是行动条件，不是旧思维过程

假设 Codex CLI 在本地测试通过后关闭，第二天由 Codex App 接手。新 session 不需要逐字获得旧
transcript，但至少需要重建：

- Goal、acceptance 与当前 per-Agent Vision；
- open Todo、dependency、claim 与 continuation；
- unresolved Gate 与 decision scope；
- evidence 所绑定的 command、revision 与 freshness；
- current worktree、Host capability 与 write scope；
- external handle、readback 与 monitor due state；
- current interaction contract 与 stop condition。

其中一些来自 durable project state，一些必须重新探测：

| 可 replay 的事实 | 必须重新探测的事实 |
| --- | --- |
| Goal identity、Todo lineage、Gate resolution | 当前 checkout 与 uncommitted diff |
| run/evidence refs、旧 receipt | 当前 CI、PR、Issue 或 cloud state |
| registered Agent 与 policy | 当前 Host capability 与登录状态 |
| previous scheduler proposal | 当前时间、monitor due 与 execution context |

旧 receipt 证明某个动作曾在绑定输入和 revision 下成功，不证明外部世界仍保持不变。旧 claim 也不
证明 Agent 仍在运行。

## Continuation、Retry、Replan 与 Self-Repair

四个动作解决不同问题：

### Continuation

目标、frontier 和协议没有实质变化；下一轮沿已有 Todo 继续一个新的 bounded segment。即使
Host session 可以 resume，也要重新运行 current guard。

### Retry

目标动作仍然合法，但 transport、timeout 或临时环境失败。Retry 必须有幂等边界、attempt identity
和 readback，避免把第一次已成功但响应丢失的 effect 再执行一次。

### Replan

工作语义需要改变，例如：

- Goal / acceptance / Vision 漂移；
- frontier 耗尽但 acceptance 仍未满足；
- dependency 已满足，但旧 Todo 需要 successor；
- 新 evidence 推翻旧方案；
- 多轮只产生 surface progress；
- 当前 peer 的 role scope 不再覆盖下一步。

Replan 必须产生可观察 delta：更新 Todo、Vision、acceptance、successor、supersede 或
no-follow-up。只写“已重新评估，继续原计划”不一定能清除 replan obligation。

### Self-Repair

目标工作可能仍然正确，但控制面本身存在不一致，例如：

- event source 与 status projection 不一致；
- user Todo count 存在，具体 Gate payload 缺失；
- stale Next Action 指向已完成 Todo；
- wrong worktree 仍被当成 delivery workspace；
- monitor 无 target、cadence 或 bounded observation handle；
- writeback/spend lineage 不完整。

Self-repair 修复状态、projection 或 boundary，不降低 Gate，也不凭猜测补 permission。

## Projection Gap 的处理顺序

当两个表面冲突时：

```text
detect mismatch
  -> identify authoritative source
  -> classify source-write / projection / migration / freshness failure
  -> repair through the owning protocol
  -> recompute and validate
  -> rerun quota
```

例如 active-state Markdown 中 Todo 已完成，但 event projection 仍 open：

1. 检查完成动作是否通过 lifecycle command 形成 event；
2. 如果只是手工改 Markdown，将有效 evidence 转成规范 transition；
3. 如果 event 已存在，修复 projection head/sequence；
4. 重新运行 status 与 quota；
5. 在一致前不继续依赖该 Todo 的 successor。

不要同时手工修改 Markdown、dashboard fixture 和 status cache 来“让页面看起来一致”。

## Vision Checkpoint 与 Acceptance Gap

[`goal_vision_replan_contract_v0`](https://github.com/huangruiteng/loopx/blob/main/docs/reference/protocols/goal-vision-replan-contract-v0.md)
要求需要 Vision 的 Agent 在 material refresh 时说明：

- Vision 被 patch；
- Vision 保持不变，以及原因；
- Vision 已满足并 retired；
- 由 successor supersede；
- 当前 role 不需要 Vision。

缺失 required checkpoint 可以形成 `vision_checkpoint_missing` acceptance gap。这个 gap 的意义
不是强迫 Agent 写更多愿景 prose，而是要求它证明：本轮局部推进没有让自己的 lane 偏离 Goal。

Goal-level replan 先于 monitor quiet 或 agent-scope wait。否则系统可能在“当前没有可运行 Todo”
时静默等待，却遗漏 acceptance 仍未闭合的事实。

## Terminal Closure

Todo 全部 done 只说明当前列表结束，不自动证明 Goal 完成。Terminal audit 至少检查：

```text
open todos = 0
due monitors = 0
unresolved blocking gates = 0
pending successors = 0
replan obligations = 0
acceptance gaps = 0
retryable postconditions = 0
required external readbacks are fresh
```

如果 acceptance 已满足且没有 follow-up，记录结构化 no-follow-up；如果仍有工作，创建 successor；
如果外部结果尚未确定，保持 monitor 或 blocker。不要为了让 Goal “看起来完成”而删除未闭合状态。

## 四种运行责任

长期 Agent 系统容易把所有组件都称为“工具”或“插件”。LoopX 使用四种运行责任：

| 责任 | 合同 |
| --- | --- |
| Agent / Executor | 在 Host 中规划并执行一个被允许的 bounded action |
| Provider | 调用外部系统，返回 observation、effect result 或 readback |
| Capability | 定义 caller outcome，规范 Provider 输出，应用 domain policy |
| LoopX Kernel | 接受或拒绝 proposal，拥有通用 Goal/Todo/Gate/Quota/Recovery state |

正常流向不是“Agent 调工具后直接写完成”：

```text
Agent -> Capability -> Provider -> external system
Provider readback -> Capability validation/proposal -> LoopX transition
```

Capability 描述调用者可依赖的 outcome contract；Provider 实现或访问外部系统；Kernel 保持跨领域
生命周期。Issue-Fix、Explore 等领域结果可以拥有自己的 Domain State，但不能反向拥有通用 quota、
Gate 或 permission。

## Extension 是交付与生命周期边界

**Extension**拥有独立的：

- packaging；
- installation；
- enable / disable；
- upgrade / rollback；
- compatibility；
- provider ownership。

它不是第五种运行责任，也不自动获得 domain authority：

```text
Extension package
└── delivers Provider
      └── participates in Agent -> Capability -> Provider -> Kernel flow
```

对于零权限、确定性的 standalone Extension，LoopX 可以通过 managed runtime 调用 bounded
request/response command。一旦操作需要 read、write、send、publish 或 manage authority，就必须
进入能检查 permission、decision scope 与 domain policy 的 Capability 或领域命令。

“安装成功”“doctor ready”和“有权执行某次 effect”是三个不同状态。

## 谁拥有事实

### LoopX canonical state

LoopX 拥有工作生命周期事实：

- Goal、Todo、Gate；
- claim、lease、dependency 与 successor；
- quota、monitor、scheduler hint；
- accepted evidence pointer 与 receipt；
- event lineage、Vision checkpoint 和 projection inputs。

### 外部系统

外部系统继续拥有自己的事实：

- Git 拥有 commit 与 branch；
- GitHub 拥有 PR、Issue 与 check 当前状态；
- CI 拥有 job 结果；
- cloud service 拥有资源实际状态；
- Host 拥有 session 与真实唤醒效果。

LoopX 可以保存 bounded observation、readback 和 evidence pointer，但不能让一份过期复制品替代
外部权威。

### Host 与 Agent

Host 拥有 session、模型 Turn、工具表面和实际唤醒机制。Agent 拥有当前推理与临时计划。两者都
不能成为项目 Goal state 的唯一持有者。

Host 应服从 current `interaction_contract` 与 `scheduler_hint`，不能把项目专属控制逻辑永久复制
进 heartbeat prompt。Agent 也不能因为“上一轮做过类似动作”而推断本轮仍有 authority。

## Public 与 Private Boundary

项目状态常包含不能公开提交的内容：

- 本地 registry 与 active goal state；
- task lease、Host session handle；
- raw transcript、trajectory 与 verifier tail；
- credentials 与 provider private config；
- 本机路径、内部链接和私有组织叙事；
- 未脱敏的外部 evidence。

项目接入章要求将以下目录排除在 Git 外：

```text
.loopx/
.codex/goals/
.local/
```

忽略规则只是第一层保护。公开提交前仍要扫描 credentials、absolute paths、raw logs、private links
和 runtime artifacts。需要长期公开保存的结论应先压缩成 public-safe behavior、schema、fixture
或 evidence pointer。

Handoff 也不能把 private material 复制到另一个公开 packet。它只传 stable ids、bounded refs、
freshness、omission note 与重新获取材料所需的合法路由。

## LoopX 不替代什么

LoopX 不替代：

- Agent runtime：模型仍负责推理；
- Host scheduler：Host 仍负责实际唤醒；
- Git：代码历史和 branch 仍由 Git 管理；
- CI：测试执行和 check 状态仍由 CI 管理；
- 外部服务认证：TurnEnvelope 和 receipt 都不是 security token；
- domain system：LoopX 不伪造外部资源事实；
- independent validator：Executor 自述不能单独证明 completion。

这个边界会支撑后续两条实践主线：

1. **接入现有项目**：复用这些协议，不修改 LoopX 源码；
2. **开发者贡献**：从调用者结果和协议选择 owning boundary，可交付 Control Plane、
   Capability/Domain State、Provider、Host/Runner、Projection/Dashboard、Docs/fixtures 或
   Extension。

Extension 是开发者贡献中的独立 packaging/lifecycle 路径，不是所有贡献的统一抽象。两条主线共享
同一控制面模型，但不互相要求。下一部分先从最常见的项目接入开始。
