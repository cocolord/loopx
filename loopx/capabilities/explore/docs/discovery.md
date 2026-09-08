# Receipt-bound pre-universe discovery

`loopx explore discover` is an opt-in Explore adapter that captures public
observations before a research universe exists. It canonicalizes bounded
mechanism proposals, freezes at most 48 subjects, and records hypotheses in
the existing Explore result history. It does not admit research candidates or
settle domain lifecycle transitions.

## Ownership

The implementation belongs to Explore: `discovery_runtime.py` calls the
existing `extensions.capability_admission` prepare/invoke APIs, including
installed-provider revision admission and durable Goal capability bindings.
It uses `result_log.py` for idempotent hypothesis events and exact readback.
`discovery_contract.py` is the pure structural canonicalizer. Neither module
adds a public capability, scheduler, Goal state machine, or financial gate.

The evaluator owns its method vocabulary, horizon ceilings, and evaluation
operation. A managed read-only policy operation supplies those values; Core
does not copy an evaluator's strategy taxonomy or exchange calendar. The
current handoff supports US subjects and America/New_York only.

## Activation and commands

Discovery is off unless a local binding explicitly sets `enabled: true`.
Omitting the switch, or setting it to false, returns before provider resolution
or discovery-state access. Existing Explore commands do not invoke discovery.
`--execute` is separately required to call providers and persist Core receipts.
All downstream operations must remain read-only; Core writes only its own
capture journal and Explore history.

Example binding (provider names are illustrative, not bundled services):

```json
{
  "enabled": false,
  "public_origins": ["https://issuer.example"],
  "providers": {
    "policy": {"capability_id": "research-evaluator", "operation": "describe_discovery_policy"},
    "collector": {"capability_id": "public-observations", "operation": "collect"},
    "resolver": {"capability_id": "listed-entities", "operation": "resolve"},
    "proposer": {"capability_id": "mechanism-proposals", "operation": "propose"}
  }
}
```

Install and doctor the exact provider revisions, bind all four operations and
the policy-declared evaluation operation to the Goal through the existing
extension workflow, then explicitly enable the reviewed local binding.

```sh
loopx explore discover --goal-id example --binding-file discovery-binding.json \
  --trigger-id public-event-1 --cutoff-at 2026-08-28T20:00:00Z
loopx explore discover --goal-id example --binding-file discovery-binding.json \
  --trigger-id public-event-1 --cutoff-at 2026-08-28T20:00:00Z --execute
loopx explore discovery-readback --goal-id example --run-id discovery-RUN_ID
loopx explore discovery-evaluate --goal-id example --run-id discovery-RUN_ID \
  --binding-file discovery-binding.json --input-file evaluation-input.json --execute
```

Use the `run_id` returned by discovery. Preview validates configuration and
computes identity; it does not claim provider readiness. Disable the binding
to stop new discovery and evaluation calls. Readback remains available.
Manual, event, and existing LoopX scheduled callers can use the same commands;
their existing Goal/Todo/quota admission remains the caller's responsibility.
The adapter creates no schedule and does not consume or replenish quota.

## Managed role contracts

Every operation returns one observation packet inside the existing managed
read-only result envelope. Mutations, effects, and transition proposals are
rejected by existing Core admission. Packet validation adds strict fields,
bounded text, public-safety checks, and a 750 KB observation-packet ceiling.

| Role | Input supplied by Core | Observation schema |
| --- | --- | --- |
| Policy | `as_of` cutoff | `loopx_explore_discovery_policy_v0` |
| Collector | cutoff, max 96 observations, reviewed public HTTPS origins | `loopx_explore_public_observations_v0` |
| Resolver | cutoff, exact collected observations, collector receipt digest | `loopx_explore_subject_resolutions_v0` |
| Proposer | cutoff, policy, observations, resolutions, rotated lens order, limits, upstream receipt digests | `loopx_explore_mechanism_proposals_v0` |

The policy supplies method revision, market/timezone, caps no greater than 48,
five ordered causal lenses, three horizon-to-family mappings, corresponding
expiry ceilings, and the existing evaluation operation. Core allocates a
session ordinal under a lock and rotates the five lenses; neither model nor
caller can supply that ordinal.

Each observation binds `source_id`, `uri`, `entity_ids`, `as_of`, `available_at`,
`content_digest`, `summary`, and an optional relation. Both timestamps must be
no later than cutoff, with observation time no later than availability. Source
URLs must match the reviewed HTTPS origins and carry no credentials, query,
or fragment. Relations bind two observed entities and a
producer/customer/substitute edge. The packet includes `overflow_count`.

The resolver explicitly returns every observed entity, including unresolved
entities with null `subject_id`. Each listed US subject resolution must bind
entity-specific observed sources and point-in-time availability. This
identity is owned by the resolver; the model cannot propose a ticker directly.

The proposer returns at most 96 proposals, bounded
`unclassified_source_ids`, and `overflow_count`. Each proposal has exactly:

```text
mechanism_id mechanism thesis_digest family causal_lens entity_ids
industry_chain_id proxies falsification_ids horizon expires_at
supporting_source_ids counter_source_ids missing_evidence_ids conflict_source_ids
adjacent_relation_source_id interaction_source_id
```

`thesis_digest` is SHA-256 over the canonical JSON object containing the
whitespace-normalized `mechanism`; JSON is sorted, compact, and UTF-8 encoded.
Proxy rows contain `proxy_id` and `source_ids`. Source labels and proxies must
refer to receipt-bound observations. At least one falsification and one public
proxy are required. Missing/invalid fields drop that proposal with an explicit
reason; unknown fields such as score, confidence, disposition, factor judgment,
or model-authored receipts fail the invocation.

Multi-entity proposals require one observed interaction covering all affected
entities. An adjacent-industry transfer additionally requires an explicit
public edge; at most one transfer can enter the frozen scope. No pairwise
combinations are generated by Core.

## Canonicalization and settlement

Core derives mechanism and hypothesis ids from normalized content, ignoring
model identity labels. It preserves family/lens buckets using deterministic
round-robin selection and canonical identity as the tie-breaker, admitting a
proposal's complete subject set or none of it. The freeze contains coverage
counts by lens and family, unclassified and unrepresented source references,
drop reasons, duplicates, and collector/proposer/canonical overflow counts.
The universe always declares `bounded_research_pool` and `partial` coverage.

The Goal-local `explore-discovery` journal retains exact managed requests,
successful executed receipts, provider revisions, request/result digests,
capture times, canonical freeze, and the scope settlement. There is no receipt
import API. Receipt binding establishes which admitted provider produced an
observation; it is not independent verification of that observation's truth.
Core runtime storage remains the trusted local authority, not a cryptographic
attestation against an operator who can rewrite the entire runtime.

Accepted proposals become `hypothesis/open` events in the existing Explore
history. Readback revalidates the request/receipt chain, rederives the freeze,
and requires exact event presence. Empty results settle as `no_candidates`.
Neither path writes active-pool rows, tombstones, or research findings.

The same Goal and trigger id resume the same run; changing its binding or
cutoff fails. Captures are checkpointed, event writes are idempotent, and a
crash after append can finish settlement on retry. A crash before a capture
checkpoint can repeat that read-only invocation with the same identity. A new
trigger advances the ordinal even when an earlier attempt failed.

## Evaluator handoff and limits

`discovery-evaluate` requires an existing evaluator input whose universe,
cutoff, method, market, timezone, and trading date exactly match the freeze.
It adds the scope settlement digest as managed context, admits the exact
policy-provider revision, and invokes its read-only evaluation operation.
Successful evaluation receipts are persisted and replayed only for the same
request digest.

This is a subject-scope handoff: discovered mechanism proposals remain in Core
history. It does not convert their support/counter labels into research claims,
factor evidence, or an assertion that those specific mechanisms were tested.
The evaluator still requires its existing typed evidence input. Empty evidence
may legitimately produce no actionable research result. Domain lifecycle
settlement, reviewed thesis promotion, source truth verification, live source
providers, and whole-market coverage remain separate integrations.

Validation lives in `tests/capabilities/test_explore_discovery.py`: real
installed subprocess providers and Goal bindings exercise capture, discovery
outside a supplied watchlist, bounded selection, Core history readback,
interrupted settlement, tamper rejection, and repeat evaluation. Domain
providers should additionally run these seams against their production CLI
and existing packet schemas before activation.
