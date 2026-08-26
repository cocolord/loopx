# Codex Peer Task Orchestration

LoopX supports two different concepts that must not be conflated:

- durable registered agents are equal peers;
- a host runtime may launch an ephemeral child worker for one bounded task.

No registered identity owns the goal. Claims, leases, task boundaries,
capabilities, and continuation policy decide who acts. When parallel work is
useful, LoopX may choose one temporary task coordinator from the participating
peers. That responsibility ends with the task bundle.

## Peer Runtime Contract

A registered identity uses `agent_model=peer_v1`. It has no rank-bearing role,
implicit review authority, or permanent writeback ownership. A task coordinator
may:

- activate or resume eligible peer lanes;
- issue complete briefs to ephemeral child workers;
- aggregate returned evidence;
- write accepted task-bundle state and account for the completed turn.

It does not own durable goal authority. Repository policy, explicit decision
scopes, and todo continuation still govern review, merge, publication, and
production actions.

## When To Parallelize

The default policy is adaptive orchestration, not a user-selected
`single-agent` or `multi-agent` mode. LoopX projects ready work and hard
boundaries; the task coordinator decides whether parallel execution shortens
the critical path, which todos to delegate, and which qualified host context to
use.

Parallelize when it reduces uncertainty or latency:

- map disjoint code, docs, test, or runtime surfaces;
- implement isolated slices in independent worktrees;
- run an independent review or validation pass;
- inspect separate adapter, evidence, or boundary questions.

Keep tightly coupled decisions in one peer lane. Do not launch workers merely
to make the activity graph look busy, and never let worker count override
quota, user gates, write scope, or repository policy.

### Adaptive Admission

`task_orchestration_contract_v2` admits ephemeral child work only when the
current runtime explicitly reports `subagent_spawn` through observed
capabilities and at least two coordinator-owned or unclaimed ready advancement
todos remain. A host name or scheduler runtime profile is metadata and never
supplies `subagent_spawn` or `subagent_resume`. Each candidate is checked
against:

- `task_domain` and the goal's `allowed_domains`;
- todo status, `resume_ready`, and open user dependencies;
- `required_capabilities` and observed host capabilities;
- canonical `task_repository` identity when declared (otherwise the goal
  repository remains authoritative); and
- goal-authorized, mutually non-overlapping `required_write_scopes`.

Rejected candidates remain visible in `blocked_lanes` with typed reason codes.
Ready lanes beyond `max_children` remain visible as `capacity_deferred`.
To stay inside the TurnEnvelope budget, the signed contract carries one shared
`child_brief_defaults` block plus a bounded per-lane delta. The typed host
request combines them into a complete `subagent_control_plane_handoff_v0`
brief. The coordinator may still keep the work serial; admission is permission
and capacity, not a command to spawn.

Without `subagent_spawn`, LoopX preserves the existing
`task_orchestration_contract_v1` registered-peer activation path. This keeps
long-lived peer identity, leases, worktrees, and multi-round collaboration
explicit instead of turning them into the default child-worker mechanism.

### Execution Topology Selection

Admission and execution topology are separate decisions. This section concerns
subagents that parallelize multiple Todos inside one registered agent lane. It
does not describe orchestration among multiple registered LoopX agents.

The coordinator records or consumes
`multi_agent_execution_topology_v0` before launch:

- `serial` keeps tightly coupled work in the current registered peer;
- `ephemeral_children` uses host children that end with the parent Turn and
  return held evidence or held local work to the same registered agent.

If the selected Todo describes an aggregate batch, the registered agent first
materializes one ordinary LoopX Todo per executable child lane. Host-side prose
decomposition is not a substitute: `task_orchestration_contract_v2` needs real
Todo candidates to admit.

The user or Goal policy defines the allowed envelope: child permission,
maximum concurrency, domains, repositories, scopes, effect classes, and user
gates. Inside that envelope, the coordinator decides whether parallelism is
useful, how many child lanes to run, and whether an admitted lane uses a fresh
or resumed child. A conversational "multi-agent is allowed"
must be converted into a typed current-Turn allowance or reviewed Goal policy;
the host tool's availability is not that authorization.

Prefer ephemeral children for bounded mapping, independent review, validation,
and disjoint local implementation. A child result remains held in its isolated
worktree until the registered agent validates and accepts it. Durable external
effects such as pushing a branch, changing a pull-request state, publishing,
deploying, or starting a monitor remain with that registered agent in v0.

Multiple registered LoopX agents remain equal peers and use the separate
`task_orchestration_contract_v1` path, with their own identities, Todo
ownership, liveness, and explicit peer activation. Subagent cards or host
workers must never be reclassified as peer agents.

The complete decision and reconciliation contract is
[`generic_multi_agent_execution_topology_v0`](../architecture/rfcs/generic-multi-agent-execution-topology-v0.md).
It is a generic kernel contract. Domain capabilities may supply work semantics
and validation, but must not add their own coordinator or scheduler.

## Fresh, Fork, Or Resume

The temporary task coordinator chooses a worker context from the work shape:

| Work type | Context | Required task brief |
| --- | --- | --- |
| Broad mapping, prior-art search, risk discovery | Fresh worker | Objective, authority source, allowed sources, boundary, expected output, non-goals |
| Independent review or adversarial validation | Fresh worker | Claim under review, exact evidence, validation command, acceptance and merge rules |
| Failed-smoke repair or review-comment follow-up | Resume or fork | Worktree, failing evidence, latest patch, next bounded repair |
| Disjoint local implementation whose result remains held | Fresh worker in an independent worktree | Admitted Todo, allowed paths, write scope, validation, held-result boundary |
| Branch push, PR mutation, publication, deployment, or later follow-up | Registered parent agent | Accepted child evidence, current Todo authority, workspace readback, and controlled writeback |
| Long-running claimed lane | Resume the registered peer task | Agent id, todo or lease, latest accepted evidence |
| Production action or emergency rollback | No automatic worker | Operator approval, stop condition, reversible command plan |

Fresh workers are useful only when the task coordinator can provide a complete
brief. Missing authority, scope, expected output, or validation is a planning
gap, not a reason to launch an under-specified worker.

## Shared Control Plane Handoff

Every child-worker brief starts from the shared control plane. A worker must not
infer current authority from chat history, an old packet, or another worker's
summary.

The existing host-child packet name remains
`subagent_control_plane_handoff_v0` for compatibility. Its lineage fields do
not create durable rank:

- `parent_goal_id`: shared goal lineage, not an owner identity;
- `authority_artifact`: current goal, policy, or review authority;
- `latest_state_ref`: state hash, run id, or generated-at value to read first;
- `quota_gate_snapshot`: current eligibility, wait, or gate state;
- `evidence_boundary`: allowed sources, paths, and public/private rule;
- `writeback_spend_contract`: who may accept evidence and account for the turn;
- `child_decision`: `continue`, `wait`, or `reuse_existing_evidence`.

Only then should the brief include todo id, work scope, expected artifact,
validation, and continuation policy. The compact rule is: child worker reports
evidence only; the temporary task coordinator writes accepted state and spends.

```yaml
subagent_control_plane_handoff_v0:
  parent_goal_id: example-peer-task-goal
  authority_artifact: .codex/goals/example-peer-task-goal/ACTIVE_GOAL_STATE.md
  latest_state_ref: state_hash_or_run_id
  quota_gate_snapshot: eligible
  evidence_boundary: public-safe read-only repository map
  writeback_spend_contract: child worker reports evidence only; task coordinator writes accepted state and spends
  child_decision: continue
goal_id: example-peer-task-goal
todo_id: todo_docs_map
work_scope: inspect docs and return evidence paths
validation: cite files and residual risk; do not edit
continuation_policy: independent_handoff
```

After explicit capability admission, the signed Turn host request uses
legitimate host metadata only to map supported native context operations. The
host name does not admit child work. The task coordinator chooses from that
catalog:

- Codex exposes `fresh` and `resume`;
- Claude Code exposes `fresh` through its native Task surface;
- generic adapters expose no child capability unless the adapter declares one.

`fork` stays out of the public execution catalog until a real host adapter
proves versioned execution state, copy-on-write workspace isolation, capacity
reservation, branch lease, held-result settlement, cancellation, and recovery.
Context choice is advisory execution strategy and cannot widen LoopX authority.

## Claims, Leases, And Worktrees

Registered peers claim work through LoopX todos and leases. The control plane
allows one pending lease for `(goal_id, todo_id)`. `goal_id` is the shared
control-plane lane; `todo_id` is the work item being claimed. A host child may
carry the claim context in its brief, but it does not become a ranked agent.

Repository-writing peers and child workers use independent worktrees. A
worktree proves filesystem isolation; it does not prove LoopX admission,
identity, claim, lease, session continuity, or external-effect authority.
Overlap is resolved through task boundaries and repository policy, not through
a permanent controller. Completion uses typed continuation:

- `independent_handoff`: leave the successor available to peers;
- `same_agent_non_delivery`: keep a non-delivery follow-up with the same peer.

Review remains `action_kind=review` over `independent_handoff`. Add the author
to `excluded_agents` only when the successor should stay open for eligible peers
but must not be reclaimed by that author.

## Child Execution Receipts And Reconciliation

Every child launch should return one compact
`multi_agent_host_execution_receipt_v0`. The receipt binds the observed host
worker to:

- `bundle_id`, `lane_id`, `goal_id`, and `todo_id`;
- the admitted execution kind;
- the source control-plane state revision;
- an opaque workspace reference;
- typed effect classes and public-safe evidence references; and
- terminal status without raw transcript or tool output.

Child receipts must not invent an `agent_id`, peer claim, lease, or durable
session identity. The registered parent agent and each Todo remain
authoritative outside the receipt.

Before aggregate Todo completion or quota spend, the registered agent compares
the topology plan, host receipts, and current LoopX state through
`multi_agent_control_plane_reconciliation_v0`. Missing admission, stale
lineage, workspace mismatch, effect-boundary violations, missing worker
receipts, orphaned results, and aggregate settlement without lane evidence are
typed drift. The registered agent may independently verify and retain useful
output, but it cannot relabel the original topology as compliant.

The first implementation slice is observation-only. Settlement enforcement
belongs in the established typed control-plane transaction owner after the
receipt shape has a second real host consumer; host adapters and Python
facades remain bridges rather than a second source of truth. Registered-peer
session reconciliation is outside this child-worker contract.

## Enabling Bounded Orchestration

The feature remains opt-in:

```bash
loopx configure-goal \
  --goal-id example-peer-task-goal \
  --multi-subagent-feature enabled \
  --max-children 2 \
  --allowed-domain docs \
  --allowed-domain validation \
  --execute
```

`multi_subagent` remains the compatibility name for host child-worker capacity
and permission policy. It does not ask the user to select a run mode or agent
hierarchy. With observed host child capability, `quota should-run` may project
adaptive `task_orchestration_contract_v2`. Without that capability, it does not
fall back to coordinating registered peers: registration grants Todo ownership,
not cross-agent scheduling authority.

Use `--multi-subagent-feature off` to disable worker spawning. The low-level
`--orchestration-mode` and `--spawn-allowed` flags remain available for host
integrations.

## Explicit Registered-Peer Coordination

Registered peers are independent by default. LoopX never hashes the peer set or
open Todo bundle to auto-elect a coordinator. A host that can really activate
or resume durable peer runtimes may select one coordinator explicitly:

```bash
loopx configure-goal \
  --goal-id example-peer-task-goal \
  --peer-task-coordinator codex-alpha \
  --execute
```

The selected coordinator must then report the observed host capability on each
eligible turn:

```bash
loopx quota should-run \
  --goal-id example-peer-task-goal \
  --agent-id codex-alpha \
  --available-capability peer_agent_activation
```

The contract includes only peer lanes that are currently actionable. Dormant
registered agents and closed, blocked, or deferred todos are not coordinator
candidates. A dormant or non-resumable lane is projected under
`blocked_peer_lanes`; if no peer lane can run, the bundle has
`execution_state=blocked`,
`terminal_outcome=blocked`, and `retry_policy=material_peer_state_change_only`.
That blocked diagnostic does not replace the coordinator's own runnable lane or
re-arm an activation obligation on every heartbeat. If the coordinator also
has no in-scope runnable fallback, the final interaction mode is
`peer_coordination_blocked`: schedulers return the bundle to its owner and stop
the recurring heartbeat until peer capability/readiness, coordinator
configuration, or the coordinator's own work frontier materially changes.

Disable registered-peer coordination without changing peer registration or
child-worker policy:

```bash
loopx configure-goal \
  --goal-id example-peer-task-goal \
  --clear-peer-task-coordinator \
  --execute
```

This opt-in grants neither cross-owner Todo mutation nor broader repository,
publication, credential, or production authority. Read it back with
`loopx configure-goal --goal-id example-peer-task-goal` before relying on it.

## Run History And Observation

Run history should attribute task coordination without persisting rank:

```json
{
  "agent_model": "peer_v1",
  "task_coordinator": "codex-alpha",
  "control_plane_handoff_version": "subagent_control_plane_handoff_v0",
  "peer_lanes": [
    {"agent_id": "codex-beta", "todo_id": "todo_docs_map", "state": "completed"},
    {"agent_id": "codex-gamma", "todo_id": "todo_validation", "state": "running"}
  ],
  "accepted_evidence_count": 1,
  "next_action": "review the remaining validation evidence"
}
```

Useful observation surfaces include task bundle, participant peers, worker
context (`fresh`, `fork`, or `resume`), accepted or rejected evidence, leases,
worktrees, quota state, and typed continuation. They must not reconstruct a
durable leader from a temporary coordination event.

The operator view should also distinguish planned from observed topology. Four
visible child cards prove host activity, not four registered LoopX peers. A
compliant view joins each card to its admitted lane and shows whether the work
is `aligned`, `incomplete`, `rejected`, or `drifted`.

## Safety Rules

- Do not spawn when quota or the selected user gate blocks the task.
- Do not spawn without a current admitted child lane, even when the host tool
  itself is available.
- Do not infer permissions from an agent name, profile label, or old prompt.
- Do not launch a fresh worker without a complete task brief.
- Do not put credentials, private links, raw logs, or production material in a
  public handoff packet.
- Keep implementation scopes disjoint and use independent worktrees.
- Keep durable external effects with the registered parent agent unless a later
  reviewed child contract explicitly admits a narrower effect class.
- Reconcile every planned lane and observed worker before aggregate completion
  or spend.
- Let repository policy decide review and merge; peer identity grants neither.
- Let one temporary coordinator accept bundle evidence and write one spend
  event after validated progress.

The result is parallel execution without a permanent leader: durable agents
remain peers, while task coordination and host-child relationships stay bounded
to the work that requires them.
