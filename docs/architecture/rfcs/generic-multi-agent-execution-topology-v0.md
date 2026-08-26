# Generic Multi-Agent Execution Topology v0

Status: Draft

## Decision

LoopX should strengthen one domain-neutral multi-agent control path instead of
adding product-specific coordinators for research, coding, review, or other
capabilities.

The control plane decides whether a task bundle stays serial, uses ephemeral
host child workers, activates durable peer sessions, or combines both. The host
executes that decision and returns compact receipts. LoopX then reconciles the
observed workers, sessions, workspaces, effects, and evidence against the
admitted topology before accepting completion or quota spend.

`spawn_agent`, a native Task tool, or any equivalent host primitive is execution
capacity. Its presence does not grant LoopX admission, authority, or proof that
the resulting work remains aligned with the control plane.

## Problem

LoopX already has most of the required parts:

- `task_orchestration_contract_v2` admits bounded ephemeral child lanes;
- `task_orchestration_contract_v1` describes explicitly coordinated registered
  peers;
- Todo claims and task leases own durable work;
- session-runtime projections identify visible runtime sessions;
- controlled writeback preserves LoopX as the durable authority;
- independent worktrees isolate repository-writing lanes.

The missing seam is end-to-end topology accountability. A host can still launch
children directly, assign broad work, and later let the coordinator summarize
all results under one aggregate Todo. The code changes may be valid and the
worktrees may be isolated, but LoopX cannot prove:

- that child execution was admitted by the current quota decision;
- which Todo and state revision each worker received;
- whether a worker was intentionally ephemeral or should have been a durable
  peer session;
- which workspace and external effects belong to each lane;
- whether every returned result was accepted, rejected, or left orphaned; or
- whether the aggregate completion describes the work that actually happened.

That is work/control-plane drift. It is not fixed by adding more agents, a
research-specific scheduler, or a second task store.

## Placement

- **Capability id:** none. This is a kernel execution contract, not a
  user-facing capability.
- **Control-plane owner:** `loopx/control_plane/agents/multi_agent/`, with
  settlement enforcement remaining in the established typed control-plane
  transaction boundary.
- **Provider owner:** each host adapter owns process/session lifecycle and emits
  observations; it does not own Goal, Todo, lease, quota, or acceptance truth.
- **Domain capabilities:** may supply task semantics, expected artifacts, and
  validation, but must not define their own coordinator, scheduler, worker
  lifecycle, or session authority.

The nearest existing owner is sufficient. No `auto-research`,
`deep-research`, issue-fix, or benchmark-specific orchestration module is
needed.

## Execution Topologies

The coordinator selects the least durable topology that can complete the work
without losing recovery, attribution, or authority.

| Topology | Use when | Control-plane identity | Allowed effects |
| --- | --- | --- | --- |
| `serial` | Fewer than two independent ready lanes exist, scopes overlap, or coordination cost exceeds the expected gain. | Current registered peer and selected Todo. | Existing Todo and Turn boundaries. |
| `ephemeral_children` | Work is bounded by the parent Turn, independently retryable, needs no later user interaction, and returns held evidence for coordinator review. | Coordinator identity plus one admitted child lane per Todo; the child is not a registered peer. | Read-only work and isolated local workspace changes. No remote or production effect in v0. |
| `durable_peer_sessions` | Work may outlive the parent Turn, needs resume or follow-up, owns a long-running lane, or performs durable external effects. | Registered `peer_v1` identity, claimed or leased Todo, and bound host session per lane. | Effects allowed by that peer's Goal, Todo, lease, and host contract. |
| `hybrid` | A bundle combines short evidence gathering with independently recoverable implementation or delivery. | Ephemeral child lanes and durable peer lanes remain distinct. | Each lane follows its own boundary; evidence does not transfer authority. |

Examples:

- repository mapping and an independent read-only review can use ephemeral
  children;
- a local patch may use an ephemeral child only while the result stays held in
  an isolated worktree and the coordinator owns validation and acceptance;
- pushing a branch, changing pull-request state, posting a review, deploying,
  monitoring for later feedback, or continuing across turns requires a durable
  peer session by default;
- an ephemeral child never becomes a durable peer merely because it ran for a
  long time or produced a useful result.

## Boundary Versus Strategy

Human or Goal policy defines the execution envelope:

- whether child spawning or durable peer activation is allowed;
- maximum concurrency and cost;
- allowed task domains, repositories, write scopes, and effect classes;
- whether a current-turn allowance expires with the Turn or persists on the
  Goal; and
- which actions still require a user gate.

Inside that envelope, the coordinator owns strategy:

- whether parallelism is useful now;
- how many lanes to run;
- which admitted lane remains local;
- whether an eligible lane uses fresh, resume, or a durable peer session; and
- when to stop, retry, reject, or reconcile.

A natural-language statement that multi-agent work is acceptable is not itself
a host launch receipt. The command or UI boundary should convert explicit user
intent into a typed current-Turn allowance or a reviewed Goal policy update.
Until that typed envelope exists, the host may advertise `subagent_spawn`, but
LoopX still admits no child lane.

## Topology Plan

`multi_agent_execution_topology_v0` is a proposed read model over existing
admission contracts. It does not replace them or create new authority.

```json
{
  "schema_version": "multi_agent_execution_topology_v0",
  "goal_id": "example-goal",
  "bundle_id": "bundle_7d2f",
  "coordinator_agent_id": "codex-coordinator",
  "source_state_ref": "sha256:current-control-plane-state",
  "topology": "hybrid",
  "execution_envelope": {
    "source": "goal_policy_or_current_turn_authorization",
    "expires_with_turn": true,
    "max_children": 2,
    "allowed_effect_classes": ["local_read", "held_workspace_write"]
  },
  "rationale_codes": [
    "parallel_independent_lanes",
    "durable_external_effect_requires_peer_session"
  ],
  "lanes": [
    {
      "lane_id": "lane-review",
      "todo_id": "todo_review",
      "execution_kind": "ephemeral_child",
      "admission_ref": "task_orchestration_contract_v2:todo_review",
      "effect_boundary": "held_evidence_only"
    },
    {
      "lane_id": "lane-repair",
      "todo_id": "todo_repair",
      "execution_kind": "durable_peer_session",
      "agent_id": "codex-repair-peer",
      "admission_ref": "task_orchestration_contract_v1:todo_repair",
      "effect_boundary": "todo_lease_and_goal_authority"
    }
  ]
}
```

The plan must reference, not copy, the authoritative admission:

- an aggregate Todo must first materialize one existing Todo per executable
  lane; free-form decomposition inside the host is not an admitted bundle;
- an ephemeral lane references an admitted
  `task_orchestration_contract_v2` child;
- a durable lane references an actionable
  `task_orchestration_contract_v1` peer lane and its Todo claim or lease;
- a serial lane references the selected Turn Todo;
- the execution envelope references typed user/Goal policy rather than inferred
  chat permission; and
- absence of the required admission makes the lane non-executable.

The coordinator may choose a more conservative topology than the plan permits.
It may not choose a more powerful one.

## Host Execution Receipt

Every launched child or activated session returns one
`multi_agent_host_execution_receipt_v0`:

```json
{
  "schema_version": "multi_agent_host_execution_receipt_v0",
  "bundle_id": "bundle_7d2f",
  "lane_id": "lane-review",
  "goal_id": "example-goal",
  "todo_id": "todo_review",
  "execution_kind": "ephemeral_child",
  "runtime_id": "codex_app",
  "worker_ref": "opaque-host-worker-ref",
  "session_ref": null,
  "source_state_ref": "sha256:current-control-plane-state",
  "workspace_ref": "opaque-workspace-ref",
  "status": "completed",
  "effect_classes": ["local_read"],
  "evidence_refs": ["artifact:review-summary"],
  "raw_transcript_copied": false
}
```

For a durable peer session, `agent_id`, `session_ref`, and the active Todo lease
reference are required. For an ephemeral child, `agent_id` and durable
`session_ref` are absent; `worker_ref` is only a host observation and grants no
LoopX identity.

Receipts contain compact refs and typed effect classes, never raw prompts,
transcripts, tool output, credentials, private links, or local absolute paths.

## Reconciliation

Before the coordinator completes the bundle or spends quota,
`multi_agent_control_plane_reconciliation_v0` compares the topology plan with
host receipts and current LoopX state.

The read model classifies each lane as:

- `aligned`: admitted execution, current lineage, expected workspace/effects,
  and accepted evidence;
- `incomplete`: admitted work is still running or has no terminal receipt;
- `rejected`: the coordinator inspected the result and did not accept it;
- `drifted`: observed execution contradicts the admitted topology or authority.

Required drift reason codes:

- `unadmitted_child_spawn`;
- `aggregate_todo_not_decomposed`;
- `execution_kind_mismatch`;
- `missing_todo_lineage`;
- `durable_session_unbound`;
- `task_lease_missing_or_stale`;
- `source_state_stale`;
- `workspace_mismatch`;
- `side_effect_boundary_exceeded`;
- `worker_receipt_missing`;
- `orphaned_worker_result`;
- `aggregate_settlement_without_lane_evidence`.

The reconciliation result is evidence for settlement, not a second work
ledger. Existing Todos, leases, sessions, and Turn settlement remain
authoritative.

## Existing Owner Map

The first runtime implementation should extend these owners rather than create
a parallel orchestration stack:

| Concern | Existing owner | Required change |
| --- | --- | --- |
| Child admission | `control_plane/quota/task_orchestration_admission.py` | Add the bounded effect and durability facts needed by topology selection; keep domain names out. |
| Peer activation | `control_plane/quota/task_orchestration.py` | Reuse explicit coordinator, peer liveness, Todo ownership, and `peer_agent_activation`. |
| Host operation planning | `control_plane/turn_driver/driver.py` | Emit only operations admitted by the selected topology and carry a stable bundle/lane correlation id. |
| Durable work ownership | Existing Todo claim, task lease, workspace guard, and continuation contracts | Require these unchanged for durable peer sessions; do not recreate them in host adapters. |
| Session observation | `session_runtime_loopx_projection_v0` and host adapters | Return opaque worker/session/workspace facts and typed effect classes without raw traces. |
| Reconciliation projection | `control_plane/agents/multi_agent/` | Join planned lanes and observed receipts as a read model; do not mutate Todo or session state here. |
| Completion and spend | Existing typed Turn/Todo settlement boundary | After observation-only qualification, enforce that every lane has a legal terminal disposition before aggregate settlement. |
| Operator display | `agent_management_projection_v0` and the local Agent workspace | Render planned versus observed topology and drift; never become a dispatcher or source of truth. |

The deterministic final gate belongs in TypeScript when settlement enforcement
lands because TypeScript already owns the migrated Turn and Todo transaction
semantics. The initial topology and reconciliation read models may remain in
Python while they are observational. This is a bounded Strangler Fig step, not
a reason to rewrite the multi-agent kernel.

## Failure And Repair

When drift is detected:

1. stop launching additional lanes from the stale bundle;
2. do not retroactively register an ephemeral child as a peer;
3. retain only compact host receipts and public-safe evidence refs;
4. independently read back any durable external effect before accepting it;
5. reject or quarantine results that exceeded their effect or workspace
   boundary;
6. create a durable peer Todo/session only for remaining work that still needs
   recovery or follow-up;
7. block aggregate completion and spend until every planned lane is aligned,
   rejected, or explicitly cancelled.

An already-valid repository result may remain useful after independent
readback. That does not make the original execution topology compliant.

## Generalized Four-Lane Case

A coordinator owns one aggregate pull-request repair Todo. It launches four
host children in separate worktrees:

- two children are described as exact-head validation, but their briefs also
  permit branch updates and review requests;
- two children explicitly rebase branches and perform remote pull-request
  effects;
- the coordinator later completes one aggregate Todo with all four outcomes.

The worktree isolation is real, and the code outcomes may be valid. The
topology is still drifted when:

- the Goal projects `spawn_allowed=false` or no
  `task_orchestration_contract_v2`;
- the aggregate Todo was not decomposed into four LoopX Todo lanes before
  launch;
- no child lane is bound to an admitted Todo;
- the two side-effecting lanes have no registered peer identity, lease, or
  session binding; and
- only the coordinator's aggregate completion appears in LoopX.

Because every lane's brief permits durable external effects and later review
follow-up, the correct topology is four durable peer sessions. A validation
lane may use an ephemeral child only after its brief is narrowed to read-only
evidence with no branch update, review request, monitor, or later continuation.
Every lane returns a receipt, and the coordinator settles only accepted bundle
evidence.

## Implementation Slices

### Slice 0: contract and characterization

- document topology selection and reconciliation;
- add a public synthetic four-lane fixture or contract smoke;
- record the real incident only in ignored/local LoopX evidence.

No runtime behavior changes in this slice.

### Slice 1: observation-only reconciliation

- let host adapters emit compact worker/session execution receipts;
- join receipts to the current topology, Todo, workspace, and state revision;
- expose drift in status and the local Agent workspace;
- do not block existing execution yet.

### Slice 2: settlement enforcement

- require aligned lane receipts before aggregate completion or quota spend;
- put the final deterministic gate in the established typed settlement owner;
- keep Python and host adapters as input/output bridges rather than a second
  authority.

### Slice 3: durable session activation

- implement only for hosts that can create or resume a session and return a
  stable binding;
- require registered peer identity, claim or lease, independent workspace, and
  controlled writeback;
- keep unsupported hosts fail-closed or serial.

### Slice 4: operator experience

- show planned versus observed lanes, execution kind, owner, workspace, status,
  effects, and accepted evidence;
- allow the operator to inspect or cancel through existing typed actions;
- keep the UI a projection, never a dispatcher or second source of truth.

## Non-Goals

- a research-specific coordinator or worker protocol;
- automatic conversion of every sub-agent into a durable session;
- a second scheduler, task store, evidence store, or Agent hierarchy;
- automatic coordinator election for registered peers;
- raw host transcript ingestion;
- direct UI mutation of claims, leases, sessions, or settlement;
- a broad TypeScript rewrite before a second runtime consumer exists.

## Acceptance

The design is ready for runtime implementation only when:

1. a host cannot claim compliant child execution without a current admitted
   child lane;
2. durable side-effecting work is attributable to a registered peer, Todo
   claim or lease, host session, and workspace;
3. every observed worker or session maps to exactly one planned lane;
4. every planned lane is aligned, rejected, cancelled, or explicitly
   incomplete before aggregate settlement;
5. stale state, missing receipts, workspace mismatch, and effect-boundary
   violations produce typed drift instead of optimistic completion;
6. Auto Research, Deep Research, Issue Fix, and future products can supply
   domain work without importing or forking orchestration mechanics; and
7. the public projection remains compact and contains no raw transcript,
   credential, private link, or local absolute path.
