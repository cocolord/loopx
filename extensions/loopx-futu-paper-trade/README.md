# Futu paper-trade extension

`loopx-futu-paper-trade` is an independently installed LoopX Extension for Futu
OpenD Hong Kong, US, and China A-share simulated stock orders. It is not a built-in capability and it does not
declare `[[provides]]` or `[[implements]]`. LoopX owns lifecycle management,
typed authority validation, revision-bound invocation, and process limits; the
Extension owns Futu request validation, simulated execution, and order readback.

The v0 package accepts only `HK.*`, `US.*`, `SH.*`, and `SZ.*` symbols with
`TrdEnv.SIMULATE`, connects only to a loopback OpenD endpoint, stores no
credentials, and never chooses investments. Real trading is intentionally not
represented by the request schema or runtime permission.

Market routing is explicit: `HK.*` uses `TrdMarket.HK`, `US.*` uses
`TrdMarket.US`, and `SH.*`/`SZ.*` use `TrdMarket.CN`. The latter is an A-share
paper-trading market; this Extension never routes A shares through the live-only
China Connect market.

## Install

Run these commands in the same Python environment:

```bash
python3 -m pip install .
loopx extension install --manifest extension.toml --execute --format json
loopx extension enable loopx-futu-paper-trade --execute --format json
loopx extension doctor loopx-futu-paper-trade --execute --format json
```

OpenD defaults to `127.0.0.1:11111`. Override the loopback endpoint with
`LOOPX_FUTU_OPEND_HOST` and `LOOPX_FUTU_OPEND_PORT`. Account discovery compares
only redacted references of the form `futu-hk-sim-<digest>`.

## Invoke

`loopx extension run` resolves the installed revision. A dry run performs no
provider invocation:

```bash
loopx extension run loopx-futu-paper-trade \
  --input-json examples/order.json \
  --format json
```

Execution additionally requires a fresh `loopx_extension_authority_decision_v0`
that binds the active revision, protocol, exact request digest, effect scope,
and `broker.order.submit.simulated` permission:

```bash
loopx extension run loopx-futu-paper-trade \
  --input-json /private/path/order.json \
  --authority-json /private/path/authority.json \
  --available-capability broker.order.submit.simulated \
  --execute \
  --format json
```

Keep account aliases and authority decisions outside the repository. The
Extension revalidates the typed decision and LoopX execution envelope before it
creates a broker connection.
