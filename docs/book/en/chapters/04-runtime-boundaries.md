# Recovery, self-repair, and runtime boundaries

The hard part of a long-running system is not “continue forever.” It is deriving a legal next action after
the session, Host, Agent, workspace, or external facts have changed. This chapter separates continuation,
retry, replan, self-repair, and terminal closure, then places Agents, Providers, Capabilities, Extensions,
Hosts, and external systems behind explicit authority boundaries.

## What you should learn

After this chapter, you should be able to:

- explain which facts are replayable and which require fresh inspection;
- distinguish continuation, retry, replan, and self-repair;
- recognize projection gaps, stale evidence, and workspace drift;
- distinguish Agent, Provider, Capability, Kernel, and Extension;
- decide when a Goal is terminal rather than only seeing every current Todo checked;
- detect a broken public/private boundary.

## Recover action conditions, not old thoughts

Assume Codex CLI closes after local tests pass and Codex App takes over the next day. The new session does
not need a verbatim transcript. It does need to reconstruct:

- Goal, acceptance, and current per-Agent Vision;
- open Todos, dependencies, claims, and continuation;
- unresolved Gates and decision scopes;
- commands, revisions, and freshness attached to evidence;
- current worktree, Host capabilities, and write scope;
- external handles, readbacks, and monitor due state;
- current interaction contract and stop condition.

Some facts replay from durable project state. Others require a fresh read:

| Replayable facts | Facts to inspect again |
| --- | --- |
| Goal identity, Todo lineage, Gate resolution | Current checkout and uncommitted diff |
| Run and evidence references, old receipts | Current CI, PR, Issue, or cloud state |
| Registered Agents and policy | Current Host capability and login state |
| Previous scheduler proposal | Current time, monitor due state, and execution context |

An old receipt proves that an action succeeded for bound input and revision. It does not prove the external
world remains unchanged. An old claim does not prove the Agent is still running.

## Continuation, retry, replan, and self-repair

These actions solve different failures.

### Continuation

Goal, frontier, and protocol semantics are materially unchanged. A new turn performs another bounded
segment on the existing Todo. A resumable Host session still has to rerun current guards.

### Retry

The action remains legal, but transport, timeout, or temporary environment failure prevented a reliable
result. Retry needs an idempotency boundary, attempt identity, and readback so an already-successful effect
is not executed again after its response was lost.

### Replan

The work semantics must change. Examples include:

- Goal, acceptance, or per-Agent Vision drift;
- an exhausted frontier while acceptance remains open;
- a satisfied dependency whose old Todo needs a successor;
- new evidence that invalidates the plan;
- repeated surface activity without outcome progress;
- a peer whose role scope no longer covers the next step.

Replan produces an observable delta: Todo, Vision, acceptance, successor, supersession, or no-follow-up.
“Reconsidered and kept going” does not necessarily satisfy a replan obligation.

### Self-repair

The target work may still be correct while the control plane is inconsistent:

- an event source and status projection disagree;
- a User Todo count exists without a concrete Gate payload;
- Next Action points to a completed Todo;
- the wrong worktree remains configured as the delivery workspace;
- a monitor lacks target, cadence, or bounded observation handle;
- writeback and spend lineage is incomplete.

Self-repair fixes state, projection, or boundary. It does not weaken a Gate or invent permission.

## Long-horizon convergence: a Turn is not the unit of progress

Long-running work does not approach its Goal merely because it executes more Turns. A Turn may be a legal
wait, or it may produce a large diff without adding evidence that can change the next decision. To judge
convergence, separate four operating states:

| State | Observable property | Correct action |
| --- | --- | --- |
| Legal iteration | Input, revision, or evidence changed, making the next action distinguishable | Execute one new bounded Turn |
| External wait | No current action exists, but recovery condition, target, and next due time are explicit | Monitor, backoff, and quiet |
| Goal drift | A local metric or current Todo begins to replace Goal or Acceptance | Vision checkpoint, acceptance audit, and replan |
| Local loop | The same action family repeats without new information, state delta, or failure discrimination | Stop repeating; diagnose, replan, or self-repair |

Repetition alone is not a loop. Processing a PR again after checks move from pending to failed is legal
iteration. Observing an external training task at its due time is legal waiting. Work is spinning only when
input facts, attributable evidence, and the next plan all remain materially unchanged while the same class
of Turn continues to consume resources.

### Material evidence delta

A Turn that deserves more resource consumption should advance at least one of these:

- a new observation changes the current domain judgment;
- new evidence supports or excludes a testable explanation;
- a validated artifact satisfies an acceptance condition;
- a successor, Gate, blocker, Vision, or no-follow-up changes the machine-visible frontier;
- a Provider effect receives a receipt bound to proposal identity, revision, and readback;
- the system proves that it can only wait and writes the target, cadence, and recovery condition.

More logs, rewritten summaries, a refresh of the same projection, another unchanged poll, or a test result
that cannot bind to the current revision are not material progress. They may be diagnostic steps, but they
must not impersonate Goal advancement.

### Six convergence invariants

Review a long-running chain with six questions:

1. **Direction:** Can the current Todo still be traced to Vision, Goal, and Acceptance?
2. **Authority:** Does the transition affect the correct object under the correct Agent, Gate, or Host
   capability?
3. **Evidence:** Is the observation fresh, and is evidence bound to revision, scope, and evaluator?
4. **Delta:** Did this Turn change replayable facts, the frontier, or a wait condition?
5. **Liveness:** If acceptance remains open and the frontier is empty, did the system create a wait, replan,
   repair, or explicit stop?
6. **Closure:** Does terminal state close Todos, Monitors, Gates, successors, receipts, and acceptance gaps?

These invariants combine Safety and Liveness. Safety prevents an invalid transition. Liveness prevents a
system from remaining cautiously stuck forever. A successor reconnects local completion to the Goal;
Monitor backoff avoids hot polling; Replan changes a failed route; Self-Repair fixes control-plane gaps;
and terminal audit prevents “all current Todos are checked” from becoming a false completion claim.

For the complete paired-Showcase replay, evidence-delta criteria, independent oracle, and convergence
experiments, use
[Long-horizon convergence](/loopx/docs/development/control-plane-course/topic-long-horizon-convergence/).
[Control-Plane Course Lesson 6](/loopx/docs/development/control-plane-course/06-evidence-refresh-and-self-repair/)
continues into source paths for evidence, refresh, spend, and repair deltas.

## Handle a projection gap in order

When two surfaces disagree:

```text
detect mismatch
  -> identify authoritative source
  -> classify source-write / projection / migration / freshness failure
  -> repair through the owning protocol
  -> recompute and validate
  -> rerun quota
```

If active-state Markdown marks a Todo complete while the event projection remains open:

1. check whether completion passed through a lifecycle command and formed an event;
2. if only Markdown changed, normalize valid evidence into the canonical transition;
3. if the event exists, repair the projection head or sequence;
4. rerun status and quota;
5. do not execute a dependent successor until the state is consistent.

Do not hand-edit Markdown, a dashboard fixture, and a status cache until they merely look consistent.

## Vision checkpoint and acceptance gaps

[`goal_vision_replan_contract_v0`](https://github.com/huangruiteng/loopx/blob/main/docs/reference/protocols/goal-vision-replan-contract-v0.md)
requires an Agent that uses Vision to record one of these outcomes after material refresh:

- Vision was patched;
- Vision remains unchanged, with a reason;
- Vision is satisfied and retired;
- a successor supersedes it;
- the current role does not require Vision.

A missing required checkpoint can produce a `vision_checkpoint_missing` acceptance gap. The purpose is not
to make an Agent write more visionary prose. It is to prove that local delivery did not move the Agent's
lane away from the Goal.

Goal-level replan takes precedence over monitor quiet or agent-scope wait. Otherwise the system can remain
quiet because no current Todo is runnable while acceptance still has an open gap.

## Terminal closure

Every current Todo being done proves only that the list ended. A terminal audit also checks:

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

If acceptance is satisfied and no follow-up is needed, record structured no-follow-up. If work remains,
create a successor. If an external result is still pending, preserve a monitor or blocker. Do not delete
open state to make the Goal look complete.

## Four runtime responsibilities

Long-running systems often call every integration a tool or plugin. LoopX keeps four runtime
responsibilities distinct:

| Responsibility | Contract |
| --- | --- |
| Agent / Executor | Plans and executes one allowed bounded action in a Host |
| Provider | Calls an external system and returns an observation, effect result, or readback |
| Capability | Defines a caller outcome, normalizes Provider output, and applies domain policy |
| LoopX Kernel | Accepts or rejects a proposal and owns generic Goal, Todo, Gate, quota, and recovery state |

The normal flow is not “the Agent called a tool, therefore the Todo is done”:

```text
Agent -> Capability -> Provider -> external system
Provider readback -> Capability validation/proposal -> LoopX transition
```

A Capability is the outcome contract a caller can depend on. A Provider implements that contract or
accesses an external system. The Kernel owns cross-domain lifecycle. Domain packs such as Issue-Fix or
Explore can own domain results, but they must not become a second owner for generic quota, Gates, or
permission.

## Extension is a delivery and lifecycle boundary

An **Extension** has independent:

- packaging;
- installation;
- enable and disable;
- upgrade and rollback;
- compatibility;
- provider ownership.

It is not a fifth runtime responsibility and does not automatically gain domain authority:

```text
Extension package
└── delivers Provider
      └── participates in Agent -> Capability -> Provider -> Kernel flow
```

A deterministic, zero-permission standalone Extension can expose a bounded request/response command
through the managed runtime. As soon as an operation needs read, write, send, publish, or manage authority,
it must enter a Capability or domain command that can enforce permission, decision scope, and domain
policy.

“Installed,” “doctor-ready,” and “authorized for this effect” are three different states.

## Who owns each fact

### LoopX canonical state

LoopX owns work-lifecycle facts:

- Goal, Todo, and Gate;
- claim, lease, dependency, and successor;
- quota, monitor, and scheduler hint;
- accepted evidence pointer and receipt;
- event lineage, Vision checkpoint, and projection inputs.

### External systems

External systems remain authoritative for their facts:

- Git owns commits and branches;
- GitHub owns current PR, Issue, and check state;
- CI owns job results;
- a cloud service owns actual resource state.
- the Host owns its session and actual wake-up effect.

LoopX may retain bounded observations, readbacks, and evidence pointers. A stale copy must not replace the
external authority.

### Host and Agent

The Host owns sessions, model turns, tools, and wake-up mechanisms. The Agent owns current reasoning and a
temporary plan. Neither can be the sole owner of project Goal state.

The Host follows the current `interaction_contract` and `scheduler_hint`. It must not preserve
project-specific control logic indefinitely in a heartbeat prompt. The Agent cannot infer current
authority merely because a similar action was legal in a previous turn.

## Public/private boundary

Project control state commonly contains material that must not be committed publicly:

- local registry and active Goal state;
- task leases and Host session handles;
- raw transcripts, trajectories, and verifier tails;
- credentials and private Provider configuration;
- machine paths, internal links, and private organizational narrative;
- unredacted external evidence.

The project-onboarding chapter requires these directories to stay outside Git:

```text
.loopx/
.codex/goals/
.local/
```

Ignore rules are only one defense. Before publication, still scan for credentials, absolute paths, raw
logs, private links, and runtime artifacts. Durable public conclusions should first become public-safe
behavior, schema, fixtures, or evidence pointers.

A handoff must not copy private material into a public packet. It transfers stable ids, bounded references,
freshness, omission notes, and legal routes for reacquiring material.

## What LoopX does not replace

LoopX does not replace:

- the agent runtime that performs reasoning;
- the Host scheduler that actually wakes work;
- Git history and branches;
- CI execution and check state;
- external service authentication;
- a domain system's own resource facts;
- an independent validator.

A TurnEnvelope or receipt is not a service credential. An executor's own completion claim is not sufficient
proof.

These boundaries support two later paths:

1. **Project onboarding** reuses the protocols without modifying LoopX source.
2. **Developer contributions** locate the owning contract and bounded context before changing the Control
   Plane, a Capability, a Provider, Host or Runner integration, a projection, documentation or fixture, or
   an Extension package.

The paths share the same control-plane model and do not require one another. Extension lifecycle remains a
specialized contribution path for optional or independently versioned delivery. The next part starts with
the most common job: onboarding an existing project.
