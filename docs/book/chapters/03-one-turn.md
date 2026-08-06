# 一轮受治理的工作

LoopX 的核心不是“让 Agent 无限循环”，而是把当前项目事实编译成一轮有边界、可验证、可写回的
工作协议。本章从 `quota should-run` 的 decision 开始，解释 user、agent 与 CLI 如何在同一轮中
承担不同义务。

## 本章目标

读完后，你应该能：

- 解释 quota 为什么是 decision kernel，而不只是余额检查；
- 读取 `interaction_contract` 的 user、agent 与 CLI 三个 channel；
- 区分 bounded delivery、user gate、monitor quiet、replan、repair 与 terminal；
- 判断一次 Agent 输出是否足以支持 canonical writeback；
- 解释 validation、refresh、receipt 与 spend 为什么必须按顺序发生；
- 说明 scheduler hint 为什么不是执行授权。

## 从 Source Facts 到 Interaction Contract

每一轮先读取当前事实，而不是沿用上一轮 prompt 中的判断：

```text
registry and goal boundary
  + todo frontier and claims
  + decision scopes and gates
  + capability and workspace
  + evidence freshness and run history
  + quota and scheduler context
  + vision / replan obligations
  -> interaction_contract
```

`loopx quota should-run` 是这个决策面的主要入口。历史兼容字段可能仍提供 `should_run`、
`action_required` 或 `recommended_action`，但新读者应优先读取：

1. `interaction_contract.mode`；
2. user、agent、CLI 三个 channel；
3. selected Todo、goal boundary 与 guard；
4. scheduler hint 和 spend policy；
5. 再使用兼容字段辅助展示。

单看 `should_run: false` 无法区分“等待用户”“monitor 未到期”“当前 Agent 没有 in-scope work”或
“控制面需要修复”。这些状态要求完全不同的下一步。

## 三个 Channel 可以同时成立

[`loopx_interaction_contract_v0`](https://github.com/huangruiteng/loopx/blob/main/docs/quota-allocation.md)
把一轮义务拆成三个视角：

### User channel

回答：

- 用户现在是否必须行动；
- 应该通知还是保持安静；
- 具体问题、decision scope 与原因是什么；
- 该 Gate 只阻塞哪个 action、lane 或整个 Goal。

### Agent channel

回答：

- 当前 Agent 是否必须尝试工作；
- 是否允许 delivery；
- 是否允许 quiet no-op；
- 唯一 primary action 是什么；
- 这是普通交付、观察、repair 还是 replan。

### CLI channel

回答：

- 哪些 lifecycle command 是下一步；
- validation 后如何 refresh/writeback；
- 何时允许 spend；
- Gate、wait 或 no-change 为什么不应 spend。

三个 channel 不是互斥布尔。例如：

```text
user channel:
  action_required = true
  action = approve homepage publication

agent channel:
  must_attempt = true
  primary_action = run an independent link check

CLI channel:
  spend_after_validation = true
```

这表示用户 Gate 仍然可见，但它没有覆盖独立的 link-check Todo。把三个 channel 压成“有用户
Todo，所以 Agent 停止”会丢失 scoped fallback；压成“Agent 可以做事，所以不通知用户”也同样错误。

## 常见 Interaction Modes

Mode 将一组相互关联的状态压成可测试协议。外部开发者至少要能识别：

| Mode | Agent 行为 | User 行为 | Spend |
| --- | --- | --- | --- |
| `bounded_delivery` | 完成一个有界 artifact、blocker 或 state delta | 通常无需打断 | validation + writeback 后一次 |
| `user_gate` | 不运行被 Gate 覆盖的路径 | 回答、拒绝、取消或改向 | 不 spend |
| `scoped_user_gate_fallback` | 只运行不依赖该 Gate 的 selected fallback | Gate 仍可见 | fallback 验证后一次 |
| `external_evidence_observation` | 读取 bounded handle/readback，不发明交付 | 必要时提供缺失 handle | material transition 后才可能 spend |
| `monitor_quiet_skip` | 未到期或无 material change 时保持安静 | 无需打断 | 不 spend |
| `agent_scope_wait` | 当前 peer 没有 in-scope candidate，等待重分配 | 通常无需行动 | 不 spend |
| `autonomous_replan` | 写入 Todo、Vision、acceptance 或 no-follow-up delta | 只有 owner-held 决策才打断 | 有 accountable delta 后 |
| `outcome_floor_recovery` | 只恢复缺失的 outcome evidence 或写 blocker | 视 blocker owner 而定 | 通过恢复验证后 |
| `blocked_health` / repair | 先修复 registry、projection 或 boundary | 仅在需要 owner authority 时介入 | 无有效 delta 不 spend |

具体 mode 会随协议演进。书中要保存的是判别方法：谁拥有下一 transition、什么行为被允许、什么
证据允许 writeback，而不是背诵一个永久不变的枚举列表。

## Bounded Delivery 的五段闭环

一次正常交付至少包含五段：

```text
Decide
  -> Act
  -> Validate
  -> Write back
  -> Account
```

### 1. Decide

读取 current decision，选择 `agent_channel.primary_action` 对应的 Todo。不得用旧 prompt、旧
dashboard 卡片或上一次 `recommended_action` 覆盖当前 contract。

### 2. Act

完成一个可恢复的 bounded segment。Bounded 不等于“只改一行”，而是这个工作段：

- 有明确输入与边界；
- 产生 coherent artifact、observation 或 blocker；
- 能独立验证；
- 能形成下一项 Todo、等待条件或 no-follow-up。

只读一个文件、重复“正在分析”或运行无关命令不构成交付。

### 3. Validate

验证必须检查真实 postcondition，而不是相信执行者自述：

- 代码：focused test、contract test、smoke 或 build；
- 文档：构建、链接、命令表面与 public-boundary scan；
- 外部 effect：远端 readback、revision 或 service state；
- blocker：缺失依赖、权限或可观察 handle 的明确证据。

`process exited 0` 可能只证明工具启动成功。它不自动证明目标行为、外部状态或 acceptance。

### 4. Write back

验证后，通过 Todo lifecycle、event、evidence 或 `refresh-state` 把 compact truth 写回。写回至少
说明：

- 交付了什么；
- 依据什么 revision / command / readback；
- 哪个 acceptance 或 blocker 被推进；
- 下一步、successor、replan 或 no-follow-up；
- per-Agent Vision 是否改变。

Raw transcript 和大段日志不应进入 public-safe state。

### 5. Account

只有 validated writeback 已经存在，才按 CLI channel 记录一次 quota spend。Gate notification、
dry-run、失败 preflight、未变化 monitor poll、scheduler cadence change 和重复 writeback 都不应
冒充 delivery spend。

顺序不能倒置：

```text
wrong: act -> spend -> later decide whether it worked
right: act -> independent validation -> durable writeback -> spend once
```

## Evidence、Receipt 与 Observation

三个概念在一轮中承担不同责任：

| 对象 | 证明什么 | 不证明什么 |
| --- | --- | --- |
| Observation | 某个时刻看到了什么 | 结论已被接受或仍然新鲜 |
| Evidence | 哪些材料支持一个判断 | 状态转换已实际写入 |
| Receipt | 某个 action/transition 在绑定输入与 revision 下被接受 | 外部世界永远不变 |

例如 `git push` 超时后：

- tool invocation 是 attempt；
- `git ls-remote` 的结果是 readback observation；
- remote ref 与 expected commit 相同可以成为 evidence；
- LoopX 记录发布 transition 才形成 durable receipt。

Proposal 也不是 effect。一个协议声明“建议 publish”不会自动授予凭据、权限或证明远端已经改变。

## TurnEnvelope 与 LoopX Turn

完整 quota decision 可能包含大量诊断信息。可选的
[`loopx_turn_envelope_v0`](https://github.com/huangruiteng/loopx/blob/main/docs/reference/protocols/turn-envelope-v0.md)
把已经计算出的 decision 压缩成 bounded read model，保留：

- selected Todo 与 effective action；
- Gate、required reads 与 goal boundary；
- capability/workspace guard；
- validation、writeback 与 spend policy；
- scheduler action；
- compact contract capsule。

TurnEnvelope 是 projection，不重新选择工作，也不改变 quota semantics。

[`LoopX Turn`](https://github.com/huangruiteng/loopx/blob/main/docs/reference/protocols/loopx-turn-v0.md)
进一步定义可选的 governed transaction：

```text
live decision
  -> typed host request
  -> Agent/Host candidate result
  -> independent validator
  -> durable writeback
  -> one spend
```

Codex App heartbeat、Codex CLI visible Goal 或其他 Host 不必都用同一种 adapter 实现，但应保持同一
控制语义：Host 负责执行与唤醒，LoopX decision 负责合法下一步，validator 不直接相信 Host 的
完成声明。

!!! info "当前成熟度"
    TurnEnvelope 目前是显式启用的 bounded projection，不是默认 quota 输出；LoopX Turn 是
    experimental protocol 和 implementation target。它们适合贡献者理解边界和做集成实验，不应被
    描述成所有 Host 已经统一采用的稳定 runtime。

## Monitor 与 Scheduler Hint

当 frontier 只剩外部条件时，建立 `continuous_monitor`，而不是反复让 Agent 问“有变化吗”。一个
Monitor 至少需要：

- stable target key；
- cadence 与 next due；
- bounded observation handle；
- material-change 判据；
- expiry 或终止条件；
- no-change accounting policy。

`scheduler_hint` 把当前状态投影为 Host cadence，例如现在运行、等待 fresh evidence、等待重分配或
按 monitor cadence 唤醒。它不是 execution permission：

```text
scheduler hint: when to wake
interaction contract: what this turn may do
```

Host 即使在正确时间唤醒，也必须重新运行 current decision。旧 scheduler proposal、旧
`should_run` 或旧 selected Todo 不能跨状态变化直接复用。

### Scheduler 需要 apply、readback 与 ACK

以 Codex App heartbeat 为例，`recommended_rrule` 只是目标 cadence。完整收敛链是：

```text
LoopX proposes recommended_rrule
  -> Host applies one automation update
  -> Host result / observed RRULE proves the actual cadence
  -> run the exact ack_hint.cli_args
  -> LoopX records reset token, identity and applied RRULE
```

协议上的几个关键分支：

- `apply_needed=true`：Host 最多尝试一次 update；成功后执行 packet 中完整的
  `ack_hint.cli_args`，失败或超时则不 ACK，并执行一次 `failure_hint.cli_args`；
- `apply_needed=false, ack_needed=true`：Host readback 已精确匹配 proposal，跳过 no-op update，
  直接执行绑定的 ACK；
- `host_observation.status=drift_detected`：实际 cadence 与 ledger 不一致，旧 ACK 不能压过当前
  readback，需要重新 repair；
- terminal pause/stop：按 Host contract 验证停止结果，不把它伪装成普通 RRULE ACK。

当前 ACK 使用 `quota scheduler-ack-current` 重新读取 latest hint。Host 必须执行 packet 给出的完整
argv，因为其中可能绑定 registry、runtime profile、Agent identity 和 capability envelope；手抄
reset token 或删掉全局参数会把 ACK 写到错误状态。

Scheduler state 还绑定 `reset_token` 与 `identity_signature`。用户反馈、新 Todo、reassignment、
Gate resolution 或 material evidence transition 会改变 identity，并把 cadence 恢复到当前 profile
的初始值；连续 unchanged polls 才继续 backoff。Cadence apply、failure writeback 和 ACK 都不产生
delivery quota spend。

## 一轮何时结束

当前 Turn 可以以不同结果结束：

- validated delivery + writeback + spend；
- concrete blocker + recovery condition；
- user Gate notification；
- bounded external observation；
- quiet monitor/no-candidate wait；
- replan/repair delta；
- terminal audit 后停止。

“没有写代码”不一定是失败；Gate、wait 和 quiet no-op 可能正是协议要求的合法结果。反过来，写了
很多代码也不代表这轮有效，如果它绕过 selected Todo、authority、workspace 或 validation。

下一章解释跨 Turn 的恢复、自修复和 terminal closure，并把 Agent、Capability、Provider、
Extension 与外部系统的运行责任放回同一事实边界。
