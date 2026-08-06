# One governed turn

LoopX is not an instruction to run an Agent forever. It compiles current project facts into one bounded,
verifiable, writable work contract. This chapter starts from the `quota should-run` decision and separates
the obligations of the user, Agent, and CLI.

## What you should learn

After this chapter, you should be able to:

- explain why quota is a decision kernel rather than only a budget check;
- read the user, Agent, and CLI channels in an `interaction_contract`;
- distinguish bounded delivery, user Gate, monitor quiet, replan, repair, and terminal outcomes;
- decide whether an Agent result is sufficient for canonical writeback;
- explain why validation, refresh, receipt, and spend happen in that order;
- explain why a scheduler hint is not execution authority.

## From source facts to an Interaction Contract

Every turn starts from current facts, not a conclusion copied from the previous prompt:

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

`loopx quota should-run` is the main entrypoint for this decision surface. Compatibility fields may still
expose `should_run`, `action_required`, or `recommended_action`, but a new consumer should prioritize:

1. `interaction_contract.mode`;
2. the user, Agent, and CLI channels;
3. selected Todo, Goal boundary, and guards;
4. scheduler hint and spend policy;
5. compatibility fields only as supporting display data.

`should_run: false` alone cannot distinguish waiting for a user, an early monitor, no in-scope work for the
current Agent, or required control-plane repair. Those states have different legal next actions.

## Three channels can be true at once

The LoopX interaction contract separates one decision into three reader views.

### User channel

It answers:

- whether the user must act now;
- whether to notify or remain quiet;
- the concrete question, decision scope, and reason;
- whether the Gate blocks an action, lane, or entire Goal.

### Agent channel

It answers:

- whether this Agent must attempt work;
- whether delivery is allowed;
- whether a quiet no-op is allowed;
- which single primary action owns the turn;
- whether the action is delivery, observation, repair, or replan.

### CLI channel

It answers:

- which lifecycle operation comes next;
- how validation leads to refresh or writeback;
- when spend is allowed;
- why a Gate, wait, or no-change poll must not spend.

The channels are not mutually exclusive:

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

The homepage Gate remains visible, but it does not cover the independent link-check Todo. Collapsing the
channels into “a user Todo exists, so stop the Agent” loses safe scoped fallback. Collapsing them into “the
Agent can run, so hide the Gate” loses the open decision.

## Common interaction modes

A mode compresses a related set of states into a testable contract. External contributors should at least
recognize these categories:

| Mode | Agent behavior | User behavior | Spend |
| --- | --- | --- | --- |
| `bounded_delivery` | Produce one bounded artifact, blocker, or state delta | Usually no interruption | Once after validation and writeback |
| `user_gate` | Do not run the covered action | Approve, reject, defer, cancel, or redirect | No |
| `scoped_user_gate_fallback` | Run only the selected independent fallback | Keep the Gate visible | Once after fallback validation |
| `external_evidence_observation` | Read one bounded handle or readback | Supply a missing handle only when needed | Only after material transition |
| `monitor_quiet_skip` | Stay quiet when not due or unchanged | No interruption | No |
| `agent_scope_wait` | Wait for reassignment or in-scope work | Usually no action | No |
| `autonomous_replan` | Write a Todo, Vision, acceptance, or no-follow-up delta | Interrupt only for owner-held decisions | After an accountable delta |
| `outcome_floor_recovery` | Recover missing outcome evidence or write a blocker | Depends on blocker ownership | After validated recovery |
| `blocked_health` / repair | Repair registry, projection, or boundary first | Intervene only for owner authority | No valid delta, no spend |

Exact mode names can evolve. Preserve the reasoning method: who owns the next transition, which behavior is
allowed, and what evidence permits writeback.

## The five-stage bounded-delivery loop

A normal delivery turn has at least five stages:

```text
Decide
  -> Act
  -> Validate
  -> Write back
  -> Account
```

### 1. Decide

Read the current decision and select the Todo named by the Agent channel. Do not let an old prompt, stale
dashboard card, or prior `recommended_action` override the current contract.

### 2. Act

Complete one recoverable bounded segment. Bounded does not mean one line. It means the segment:

- has an explicit input and boundary;
- produces a coherent artifact, observation, or blocker;
- can be independently validated;
- can lead to a successor, wait condition, replan, or no-follow-up.

Reading one file, repeating “still analyzing,” or running unrelated commands is not delivery.

### 3. Validate

Validation checks the real postcondition rather than trusting the executor:

- code: focused test, contract test, smoke, or build;
- documentation: build, links, command surface, and public-boundary scan;
- external effect: remote readback, revision, or service state;
- blocker: concrete evidence for the missing dependency, permission, or observable handle.

`process exited 0` may prove only that a tool started. It does not automatically prove the target behavior,
external state, or acceptance.

### 4. Write back

After validation, write compact truth through Todo lifecycle, event, evidence, or `refresh-state` paths.
Writeback should identify:

- what was delivered;
- the relevant revision, command, or readback;
- which acceptance condition or blocker advanced;
- successor, replan, or no-follow-up;
- whether per-Agent Vision changed.

Raw transcripts and large log tails do not belong in public-safe state.

### 5. Account

Only validated durable writeback permits one quota spend. Gate notification, dry-run, failed preflight,
unchanged monitor polling, cadence changes, and duplicate writeback must not count as delivery spend.

```text
wrong: act -> spend -> later decide whether it worked
right: act -> independent validation -> durable writeback -> spend once
```

## Observation, evidence, and receipt

These objects prove different things:

| Object | What it proves | What it does not prove |
| --- | --- | --- |
| Observation | What was seen at one moment | That a conclusion was accepted or remains fresh |
| Evidence | Which material supports a judgment | That the transition was written |
| Receipt | An action or transition was accepted for bound input and revision | That the external world stays unchanged forever |

After a timed-out `git push`:

- the invocation is an attempt;
- `git ls-remote` provides a readback observation;
- a matching remote ref can become evidence;
- a LoopX publication transition creates the durable receipt.

A proposal is not an effect either. Recommending publication does not grant credentials, authorize the
action, or prove that the remote changed.

## TurnEnvelope and LoopX Turn

A full quota decision can contain substantial diagnostics. The optional
[`loopx_turn_envelope_v0`](https://github.com/huangruiteng/loopx/blob/main/docs/reference/protocols/turn-envelope-v0.md)
compresses an already computed decision into a bounded read model that preserves:

- selected Todo and effective action;
- Gate, required reads, and Goal boundary;
- capability and workspace guards;
- validation, writeback, and spend policy;
- scheduler action;
- a compact contract capsule.

TurnEnvelope is a projection. It does not select different work or change quota semantics.

[`LoopX Turn`](https://github.com/huangruiteng/loopx/blob/main/docs/reference/protocols/loopx-turn-v0.md)
defines an optional governed transaction:

```text
live decision
  -> typed host request
  -> Agent/Host candidate result
  -> independent validator
  -> durable writeback
  -> one spend
```

Codex App heartbeat, a visible Codex CLI Goal, and another Host do not need identical adapters. They do
need the same control semantics: the Host executes and wakes, LoopX selects the legal next action, and the
validator does not trust a Host completion claim by itself.

!!! info "Current maturity"
    TurnEnvelope is an opt-in bounded projection, not the default quota output. LoopX Turn is an experimental
    protocol and implementation target. Contributors can use them to reason about boundaries and build
    integration experiments, but should not describe them as a stable runtime already adopted by every Host.

## Monitor and scheduler hint

When the frontier depends only on an external condition, create a `continuous_monitor` instead of asking an
Agent repeatedly whether anything changed. A monitor needs:

- a stable target key;
- cadence and next due time;
- a bounded observation handle;
- a material-change rule;
- expiry or terminal conditions;
- a no-change accounting policy.

`scheduler_hint` projects current state into Host cadence: run now, wait for fresh evidence, wait for
reassignment, or wake at monitor cadence. It is not execution permission:

```text
scheduler hint: when to wake
interaction contract: what this turn may do
```

Even a correctly timed Host wake-up must obtain a fresh decision. An old scheduler proposal, old
`should_run`, or old selected Todo cannot survive material state changes by default.

### Scheduler convergence requires apply, readback, and ACK

For a Codex App heartbeat, `recommended_rrule` is the target cadence, not proof that the Host applied it.
The complete convergence chain is:

```text
LoopX proposes recommended_rrule
  -> Host applies one automation update
  -> Host result or observed RRULE proves the actual cadence
  -> run the exact ack_hint.cli_args
  -> LoopX records reset token, identity, and applied RRULE
```

The important protocol branches are:

- when `apply_needed=true`, the Host attempts at most one update; after success it runs the packet's full
  `ack_hint.cli_args`; after failure or timeout it does not ACK and runs `failure_hint.cli_args` once;
- when `apply_needed=false` and `ack_needed=true`, exact Host readback already matches the proposal, so the
  Host skips a no-op update and runs the bound ACK directly;
- when `host_observation.status=drift_detected`, the current readback outranks an old ACK and the cadence
  needs repair;
- terminal pause or stop uses the Host's stop contract and readback rather than pretending to be a normal
  RRULE ACK.

The current ACK route, `quota scheduler-ack-current`, rereads the latest hint. Execute the complete argv
from the packet because it may bind the registry, runtime profile, Agent identity, and capability
envelope. Copying only a reset token or dropping global arguments can acknowledge the wrong state.

Scheduler state binds a `reset_token` and `identity_signature`. User feedback, a new Todo, reassignment,
Gate resolution, or material evidence changes the identity and restores the current profile's initial
cadence; only consecutive unchanged polls continue backoff. Cadence application, failure writeback, and ACK
are control-plane housekeeping and do not consume delivery quota.

## How a turn ends

A governed turn can end with:

- validated delivery, writeback, and spend;
- a concrete blocker and recovery condition;
- a user Gate notification;
- one bounded external observation;
- quiet monitor or no-candidate wait;
- a replan or repair delta;
- stop after terminal audit.

“No code changed” is not automatically failure. A Gate, wait, or quiet no-op may be the legal result.
Conversely, a large code diff is not valid delivery if it bypasses the selected Todo, authority, workspace,
or validation.

The next chapter covers recovery across Turns, self-repair, terminal closure, and the responsibility
boundaries among Agents, Capabilities, Providers, Extensions, Hosts, and external systems.
