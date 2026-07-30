# Unified Finance Gate Contract

`finance_case_contract_v1` is the common, provider-neutral contract for
research cases evaluated by this extension. It does not collect market data or
calculate a finance metric. Collectors and metric providers produce frozen
typed observations; the gate engine compares those values with contract-owned
rules and thresholds.

## Ownership

| Surface | Owner | Responsibility |
| --- | --- | --- |
| Contract | Finance extension | Revision, cutoff, frozen identities and thresholds, gate order, safety boundaries |
| Observation | Collector or metric provider | Public evidence references and a typed value, missing marker, or conflict marker |
| Gate engine | Finance extension | Typed comparison, deterministic short-circuiting, and disposition |
| Replay harness | Finance extension | Canonical hashes and byte-identical re-evaluation |
| Revision promotion | Human owner | Approval after historical, walk-forward, and shadow review |

The contract is intentionally smaller than any individual method. A de-beta,
quality, valuation, or market-regime method may choose different gate ids, but
all must use the same typed comparisons and transition rules. Boolean and
string gates support equality. Numeric gates support equality and ordered
comparisons. Providers cannot declare their own pass or fail result.

## Attribution And Industry Overlays

Layered beta attribution is deterministic arithmetic over caller-supplied,
point-in-time observations. The explained order is frozen as market, rate,
sector, narrow peer, cycle, and event. Residual is computed as total move minus
all six explained components only when every component is observed. Attribution
does not estimate a factor, select a source, or execute a gate.

Industry metric packs are semantic overlays on the same case contract. A pack
may require metric ids, value types, and allowed operator directions. It cannot
provide a threshold, reorder common source or cutoff gates, reinterpret missing
or conflicting evidence, or alter promotion authority. Thresholds remain
inside the frozen case contract, and observations still pass through the common
gate engine.

## Gate States

| Result state | Meaning | Disposition |
| --- | --- | --- |
| `passed` | Evidence satisfies the frozen gate | Continue |
| `failed` | Evidence falsifies the frozen gate | `rejected` |
| `missing` | Required evidence is absent | `insufficient_evidence` |
| `conflict` | Valid evidence disagrees | `insufficient_evidence` |
| `not_run` | An earlier gate already blocked evaluation | No new conclusion |

Observations must exactly match the ordered `gates` list. An `observed` value is
typed and compared with the frozen rule to produce `passed` or `failed`.
Providers may instead report `missing` or `conflict`. The first `failed`,
`missing`, or `conflict` result blocks the case, and every later observation
must be `not_run`.
Running a later gate after a blocker is rejected as an invalid input rather
than silently accepted.

Passing every gate means only `eligible_for_research_successor`. It never means
method promotion, investment advice, or permission to trade.

## Shadow Qualification And Human Decisions

`finance_shadow_qualification_input_v1` evaluates a complete candidate method,
not an individual stock case. Its ordered stages are fixed:

1. point-in-time integrity;
2. historical positive replay;
3. historical negative and counterexample replay;
4. walk-forward evaluation;
5. prospective shadow evaluation;
6. transaction cost, turnover, and slippage evaluation;
7. independent evaluation by an identity distinct from the executor.

Every stage is explicit `passed`, `failed`, `missing`, or `conflict`.
`failed` produces `rejected`; `missing` and `conflict` produce
`insufficient_evidence`. Only seven passed stages produce
`ready_for_owner_review`. The result carries canonical input and qualification
hashes and still reports `active_revision_changed=false`.

The promotion helper accepts only a byte-replayable ready qualification. It
emits `finance_method_promotion_request_v1` with a typed owner decision scope,
the current and candidate revisions, a rollback target, and
`activation_performed=false`. It has no activation operation.

The rollback helper accepts only an explicit
`finance_method_activation_receipt_v1` whose authority is `human_owner` and
whose outcome is `approve`. It emits a separate owner decision request bound
to the exact active and previous revisions. It has no rollback operation.
Agents therefore may qualify and request review, but cannot activate a
candidate or roll back an active method.

## Replay

The replay receipt binds three SHA-256 values:

- the normalized contract;
- the complete input, including evidence references;
- the evaluation before the receipt is attached.

Canonicalization uses compact ASCII JSON with sorted keys. Replay recomputes
the evaluation and requires matching hashes plus byte-identical canonical
output. Changing a threshold, cutoff, observation, reason, or result fails
closed.

## Compatibility

The existing `finance_value_discovery_input_v0` reducer and
`finance_value_discovery_extension_v0` provider protocol remain supported.
`finance_case_gate_input_v1` is an additive input schema. Existing packets are
not reclassified and gain no new fields.
