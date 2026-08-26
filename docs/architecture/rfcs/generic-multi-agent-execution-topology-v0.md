# Agent-Lane Subagent Execution Topology v0

Status: Draft

## Decision

LoopX should strengthen one domain-neutral subagent control path for parallel
work inside one registered agent lane. This contract does not coordinate
multiple registered LoopX agents.

The control plane decides whether one agent lane stays serial or uses
ephemeral host child workers to advance multiple admitted Todos in parallel.
The host executes that decision and returns compact receipts. LoopX then
reconciles the observed workers, workspaces, effects, and evidence against the
admitted child lanes before the registered agent accepts completion or spends
quota.

`spawn_agent`, a native Task tool, or any equivalent host primitive is execution
capacity. Its presence does not grant LoopX admission, authority, or proof that
the resulting work remains aligned with the control plane.

## Problem

LoopX already has the two distinct orchestration layers:

- `task_orchestration_contract_v2` admits bounded ephemeral child lanes;
- `task_orchestration_contract_v1` describes explicitly coordinated registered
  peers;
- Todo claims and task leases own durable work;
- session-runtime projections identify visible runtime sessions;
- controlled writeback preserves LoopX as the durable authority;
- independent worktrees isolate repository-writing lanes.

This RFC concerns only the first layer. The missing seam is end-to-end
accountability for child workers inside one agent lane. A host can still launch
children directly, assign broad work, and later let the registered agent
summarize all results under one aggregate Todo. The code changes may be valid
and the worktrees may be isolated, but LoopX cannot prove:

- that child execution was admitted by the current quota decision;
- which Todo and state revision each worker received;
- which workspace and external effects belong to each lane;
- whether every returned result was accepted, rejected, or left orphaned; or
- whether the aggregate completion describes the work that actually happened.

That is work/control-plane drift. It is not fixed by adding more agents, a
research-specific scheduler, or a second task store.

Registered-peer coordination is a separate concern. It uses
`task_orchestration_contract_v1`, registered `peer_v1` identities, Todo
ownership, session liveness, and explicit peer activation. A host child never
becomes a LoopX peer merely because it appears as another card or process.

## Placement

- **Capability id:** none. This is a kernel execution contract, not a
  user-facing capability.
- **Control-plane owner:** existing child admission and
  `loopx/control_plane/agents/multi_agent/` observation code, with settlement
  enforcement remaining in the established typed control-plane transaction
  boundary.
- **Provider owner:** each host adapter owns child lifecycle and emits
  observations; it does not own Goal, Todo, quota, or acceptance truth.
- **Domain capabilities:** may supply task semantics, expected artifacts, and
  validation, but must not define their own coordinator, scheduler, or child
  lifecycle.

The nearest existing owner is sufficient. No `auto-research`,
`deep-research`, issue-fix, or benchmark-specific orchestration module is
needed.

## Agent-Lane Execution Topologies

The registered agent selects the least complex topology that can advance its
current Todo frontier without losing attribution or authority.

| Topology | Use when | Control-plane identity | Allowed effects |
| --- | --- | --- | --- |
| `serial` | Fewer than two independent ready lanes exist, scopes overlap, or coordination cost exceeds the expected gain. | Current registered peer and selected Todo. | Existing Todo and Turn boundaries. |
| `ephemeral_children` | At least two independent Todos belong to the same agent lane and can finish inside the parent Turn or return held work for parent acceptance. | One registered agent identity plus one admitted child lane per Todo; children are not LoopX agents. | Effects admitted by the child contract. In v0, durable remote effects stay with the registered agent after child result acceptance. |

Examples:

- repository mapping and an independent validation Todo in the same agent lane
  can use ephemeral children;
- two disjoint implementation Todos can use separate child worktrees while the
  registered agent retains final validation, push, review-request, and
  writeback ownership;
- a child that cannot finish returns held evidence or a held patch; the
  registered agent resumes the Todo or performs the authorized durable effect;
- multiple registered LoopX agents cooperating on separate long-lived lanes
  use the peer orchestration contract, not this topology.

## Boundary Versus Strategy

Human or Goal policy defines the execution envelope:

- whether child spawning is allowed;
- maximum concurrency and cost;
- allowed task domains, repositories, write scopes, and effect classes;
- whether a current-turn allowance expires with the Turn or persists on the
  Goal; and
- which actions still require a user gate.

Inside that envelope, the coordinator owns strategy:

- whether parallelism is useful now;
- how many lanes to run;
- which admitted lane remains local;
- whether an eligible child uses fresh or resume; and
- when to stop, retry, reject, or reconcile.

A natural-language statement that multi-agent work is acceptable is not itself
a host launch receipt. The command or UI boundary should convert explicit user
intent into a typed current-Turn allowance or a reviewed Goal policy update.
Until that typed envelope exists, the host may advertise `subagent_spawn`, but
LoopX still admits no child lane.

## Topology Plan

`multi_agent_execution_topology_v0` is the compatibility schema name used by
the current host observation slice. Semantically it is a read model for
subagent execution inside one registered agent lane. It does not model
registered-peer orchestration, replace admission, or create new authority.

```json
{
  "schema_version": "multi_agent_execution_topology_v0",
  "goal_id": "example-goal",
  "bundle_id": "bundle_7d2f",
  "agent_id": "codex-maintainer",
  "source_state_ref": "sha256:current-control-plane-state",
  "topology": "ephemeral_children",
  "execution_envelope": {
    "source": "goal_policy_or_current_turn_authorization",
    "expires_with_turn": true,
    "max_children": 2,
    "allowed_effect_classes": ["local_read", "held_workspace_write"]
  },
  "rationale_codes": [
    "parallel_independent_todos"
  ],
  "lanes": [
    {
      "lane_id": "lane-review",
      "todo_id": "todo_review",
      "execution_kind": "ephemeral_child",
      "admission_ref": "task_orchestration_contract_v2:todo_review",
      "effect_boundary": "held_evidence_only"
    }
  ]
}
```

The plan must reference, not copy, the authoritative admission:

- an aggregate Todo must first materialize one existing Todo per executable
  lane; free-form decomposition inside the host is not an admitted bundle;
- an ephemeral lane references an admitted
  `task_orchestration_contract_v2` child;
- a serial lane references the selected Turn Todo;
- the execution envelope references typed user/Goal policy rather than inferred
  chat permission; and
- absence of the required admission makes the lane non-executable.

`task_orchestration_contract_v1` remains the separate contract for registered
peer agents. Its lanes must not be inserted into this child topology.

The coordinator may choose a more conservative topology than the plan permits.
It may not choose a more powerful one.

## Host Execution Receipt

Every launched child returns one
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

The registered parent agent is identified by the topology plan and current
Turn. The child receipt has no `agent_id` or durable `session_ref`;
`worker_ref` is only a host observation and grants no LoopX identity.

Receipts contain compact refs and typed effect classes, never raw prompts,
transcripts, tool output, credentials, private links, or local absolute paths.

## Reconciliation

Before the registered agent completes the bundle or spends quota,
`multi_agent_control_plane_reconciliation_v0` compares the topology plan with
host receipts and current LoopX state.

The read model classifies each lane as:

- `aligned`: admitted execution, current lineage, expected workspace/effects,
  and accepted evidence;
- `incomplete`: admitted work is still running or has no terminal receipt;
- `rejected`: the registered agent inspected the result and did not accept it;
- `drifted`: observed execution contradicts the admitted topology or authority.

Required drift reason codes:

- `unadmitted_child_spawn`;
- `aggregate_todo_not_decomposed`;
- `execution_kind_mismatch`;
- `missing_todo_lineage`;
- `source_state_stale`;
- `workspace_mismatch`;
- `side_effect_boundary_exceeded`;
- `worker_receipt_missing`;
- `orphaned_worker_result`;
- `aggregate_settlement_without_lane_evidence`.

The reconciliation result is evidence for settlement, not a second work
ledger. Existing Todos and Turn settlement remain
authoritative.

## Existing Owner Map

The first runtime implementation should extend these owners rather than create
a parallel orchestration stack:

| Concern | Existing owner | Required change |
| --- | --- | --- |
| Child admission | `control_plane/quota/task_orchestration_admission.py` | Add the bounded effect and durability facts needed by topology selection; keep domain names out. |
| Host operation planning | `control_plane/turn_driver/driver.py` | Emit only operations admitted by the selected topology and carry a stable bundle/lane correlation id. |
| Parent work ownership | Existing Todo, workspace guard, and continuation contracts | Keep final acceptance and durable effects with the registered agent; do not recreate ownership in child adapters. |
| Child observation | Host adapters | Return opaque worker/workspace facts and typed effect classes without raw traces. |
| Reconciliation projection | `control_plane/agents/multi_agent/` | Join planned lanes and observed receipts as a read model; do not mutate Todo state here. |
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
6. return unfinished work to the registered agent's Todo frontier for resume or
   explicit peer handoff through the separate peer contract;
7. block aggregate completion and spend until every planned lane is aligned,
   rejected, or explicitly cancelled.

An already-valid repository result may remain useful after independent
readback. That does not make the original execution topology compliant.

## Generalized Four-Lane Case

A registered agent owns one aggregate pull-request repair Todo and should first
materialize four child-eligible Todos. It then launches four host children in
separate worktrees:

- two children validate exact heads and return evidence;
- two children rebase and repair branches but leave the resulting commits held
  in their worktrees;
- the registered agent validates the returned evidence and commits, performs
  any authorized remote branch or pull-request effects, and settles each Todo.

The worktree isolation is real, and the code outcomes may be valid. The
topology is still drifted when:

- the Goal projects `spawn_allowed=false` or no
  `task_orchestration_contract_v2`;
- the aggregate Todo was not decomposed into four LoopX Todo lanes before
  launch;
- no child lane is bound to an admitted Todo;
- child briefs permit durable remote effects outside the admitted child
  boundary; and
- only the aggregate completion appears in LoopX.

The correction is not to call the children LoopX agents. The aggregate work
must become four Todos in the same agent lane, each child must reference one
admitted Todo and return a receipt, and durable remote effects remain with the
registered agent. If a Todo truly needs an independent long-lived LoopX agent,
that Todo leaves this subagent topology and enters the separate peer
orchestration contract.

## Implementation Slices

### Slice 0: contract and characterization

- document topology selection and reconciliation;
- add a public synthetic four-lane fixture or contract smoke;
- record the real incident only in ignored/local LoopX evidence.

No runtime behavior changes in this slice.

### Slice 1: observation-only reconciliation

- let host adapters emit compact child execution receipts;
- join receipts to the current topology, Todo, workspace, and state revision;
- expose drift in status and the local Agent workspace;
- do not block existing execution yet.

### Slice 2: settlement enforcement

- require aligned lane receipts before aggregate completion or quota spend;
- put the final deterministic gate in the established typed settlement owner;
- keep Python and host adapters as input/output bridges rather than a second
  authority.

### Slice 3: operator experience

- show planned versus observed child lanes, workspace, status,
  effects, and accepted evidence;
- allow the operator to inspect or cancel through existing typed actions;
- keep the UI a projection, never a dispatcher or second source of truth.

## Non-Goals

- a research-specific coordinator or worker protocol;
- registered-peer orchestration, session activation, or peer recovery;
- a second scheduler, task store, evidence store, or Agent hierarchy;
- automatic coordinator election for registered peers;
- raw host transcript ingestion;
- direct UI mutation of Todos or settlement;
- a broad TypeScript rewrite before a second runtime consumer exists.

## Acceptance

The design is ready for runtime implementation only when:

1. a host cannot claim compliant child execution without a current admitted
   child lane;
2. every child lane belongs to one registered agent lane and one admitted Todo;
3. every observed worker maps to exactly one planned child lane;
4. every planned lane is aligned, rejected, cancelled, or explicitly
   incomplete before aggregate settlement;
5. stale state, missing receipts, workspace mismatch, and effect-boundary
   violations produce typed drift instead of optimistic completion;
6. Auto Research, Deep Research, Issue Fix, and future products can supply
   domain Todos without importing or forking child orchestration mechanics;
   registered-peer coordination remains separately owned; and
7. the public projection remains compact and contains no raw transcript,
   credential, private link, or local absolute path.
