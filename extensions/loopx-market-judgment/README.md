# LoopX market judgment extension

`loopx-market-judgment` is the canonical owner of an investment-research case
from a frozen hypothesis to validation, revision, simulated-observation gating,
and closure. It does not collect market data, choose broker orders, or hold
trading authority.

The v0 workflow is deliberately small:

```text
hypothesis_frozen -> quant_running
  -> quant_invalid|quant_inconclusive -> replan -> hypothesis_frozen|closed
  -> quant_validated -> judgment_revised -> paper_gate -> paper_active
  -> observation_due -> judgment_revised|closed
```

Illegal transitions fail closed. `quant_validated` requires point-in-time,
lookahead-free, held-out evidence. Every event is bound to the frozen case
revision, so stale quant or observation results cannot cross revisions.
`paper_gate` only emits the typed provider id
and permission expected by `loopx-futu-paper-trade`; it never creates an order,
account reference, or authority decision.

## Judgment atoms

The workflow dispatches three independently testable atoms from
`loopx-finance-value-discovery`:

- `value_discovery`: cross-sectional, de-beta value discovery, including the
  frozen PayPal case;
- `turn_window`: a five-session top/bottom observation that must beat matched
  daily base rates before validation;
- `reversal_leadership`: session 1/3/5 A-share early candidates followed by
  session 10/20 leadership checks. The early layer separates oversold response
  from pre-rebound resilience, and durable leadership cannot be observed before
  session 20.

Atoms produce evidence packets, not a validation verdict. The case event log
records whether a separate quant run invalidated, could not resolve, or
validated the hypothesis.

## Run

Install `loopx-finance-value-discovery` first, then this package. Direct use is
side-effect free:

```bash
loopx-market-judgment reduce \
  --input-json examples/a-share-turn-window.json \
  --format json
```

Extension-runtime execution likewise needs no permission because this provider
cannot trade. A later Futu invocation requires its own revision-bound authority
decision and the `broker.order.submit.simulated` capability.
