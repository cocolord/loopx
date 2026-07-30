# Extension-Gated Research Dashboard Design

## Status

Approved product design, ready for implementation planning.

## Summary

LoopX should expose an owner-facing research page only when the extension that
owns the page is installed, enabled, doctor-ready, and bound to the active
extension revision. The page must consume a validated, revision-bound
projection produced by the extension. It must not parse project-private files,
provider payloads, or domain-specific source documents in the browser.

The first provider is `loopx-finance-value-discovery`. It maps validated
finance research into a reusable decision-dashboard view that can show:

- the connected LoopX goal and method state;
- an executive adjudication;
- beta, cycle, company-value, and residual-alpha layers;
- entity research cards with observation ranges and scenario estimates;
- a selected, rejected, insufficient-evidence, and blocked research ledger;
- preregistered event-impact gates and thesis breakers;
- source lineage, evidence cutoff, confidence, and review freshness.

The page is a research aid. It must not emit investment advice, automatic trade
actions, position sizing, or an unqualified price target.

## User Outcome

An owner can open the local LoopX dashboard and answer, from the first screen:

1. Which goal and extension produced the research?
2. Is the extension currently ready, or is the page hidden?
3. What is the current adjudication and evidence cutoff?
4. Which conclusions are beta, cycle, company value, or residual alpha?
5. Which alpha claims passed or failed the full research gate?
6. Which event signals would support, reject, or invalidate the thesis?
7. Which results are current, review-due, blocked, or based on insufficient
   evidence?

## Placement Rationale

```text
capability_id: none for the standalone provider
provider_id: loopx-finance-value-discovery
origin: extension
provider_placement: packages/loopx-finance-value-discovery/
generic_lifecycle_placement: loopx/extensions/
generic_dashboard_placement: apps/presentation/dashboard/
reason: finance validation and mapping belong to the independently versioned
        provider; revision binding, projection persistence, status publication,
        and generic rendering are reusable LoopX extension mechanics.
```

The Finance package remains a standalone optional extension. Installing it does
not create a built-in `finance-value-discovery` capability. The dashboard does
not hard-code the extension id, tickers, finance routes, or finance gate
semantics.

The package owns:

- finance research input schemas and validation;
- finance-specific distinctions such as beta, cycle, company value, and
  residual alpha;
- constraints for scenario estimates, observation ranges, event gates, and
  thesis breakers;
- transformation from validated finance input to the generic dashboard view.

LoopX core owns:

- extension lifecycle and revision readiness;
- declarative presentation-surface registration;
- bounded provider execution;
- generic projection-envelope validation;
- atomic local persistence and readback;
- revision-bound status publication;
- generic diagnostics.

The dashboard owns:

- navigation derived from active presentation surfaces;
- a generic decision-research page renderer;
- goal-projection joins by stable `goal_id`;
- loading, empty, review-due, and safe-error states.

## Non-Goals

This change does not:

- install or enable an extension automatically;
- add finance logic to the built-in capability catalog;
- read arbitrary `.codex` files from the dashboard;
- expose raw provider bodies, credentials, account data, portfolio data, local
  paths, or private source documents;
- make projection state writable from the browser;
- activate, promote, or roll back a Finance method;
- run market-data collection from the status server;
- generate orders, position sizes, or trade recommendations;
- add a browser-loaded JavaScript plugin runtime.

## Architecture

```text
validated owner research input
        |
        v
loopx-finance-value-discovery
  validate domain semantics
  map to decision_research_dashboard_v0
        |
        v
LoopX extension projection publisher
  verify extension readiness
  validate declared surface + generic view
  bind active revision and payload hash
  atomically persist and read back
        |
        v
LoopX status projection
  include only ready, revision-matching surfaces
  join compact goal state by goal_id
        |
        v
Dashboard
  derive navigation
  render generic decision research view
```

The status path never executes the provider. Publication is an explicit command
that runs the provider once, validates the result, persists it, and verifies
readback. Status only reads already-validated local projection state.

## Declarative Surface Contract

An extension manifest may declare zero or more presentation surfaces:

```toml
[[presentation_surfaces]]
id = "investment-research"
kind = "decision_research_dashboard"
title = "Investment Research"
view_schema = "decision_research_dashboard_v0"
visibility = "owner-only"
empty_state_title = "No validated research yet"
empty_state_detail = "Publish a validated extension projection to populate this page."
```

Rules:

- `id` is unique within the extension and uses a bounded lower-kebab token.
- `kind` and `view_schema` are versioned contracts recognized by LoopX.
- `visibility` is `public-safe` or `owner-only`.
- Text fields are bounded plain text and cannot contain paths, markup, or URLs.
- A manifest declaration makes the surface discoverable only while the
  extension is ready.
- A declaration does not imply that a data projection exists.
- Duplicate surface ids or unsupported view schemas fail manifest validation.

The Finance manifest declares one owner-only
`decision_research_dashboard_v0` surface. The generic contract permits future
extensions to render the same view without copying Finance logic into core.

## Projection Envelope

LoopX persists a generic envelope:

```json
{
  "schema_version": "extension_projection_surface_v0",
  "extension_id": "loopx-finance-value-discovery",
  "extension_revision": "<active-revision>",
  "surface_id": "investment-research",
  "surface_kind": "decision_research_dashboard",
  "view_schema": "decision_research_dashboard_v0",
  "visibility": "owner-only",
  "goal_id": "<stable-goal-id>",
  "generated_at": "<ISO-8601 timestamp>",
  "review_due_at": "<ISO-8601 timestamp or null>",
  "payload_sha256": "<sha256>",
  "lineage": {
    "source_id": "<stable-source-id>",
    "version": 1,
    "row_lifecycle": "active",
    "supersedes": [],
    "superseded_by": null
  },
  "view": {}
}
```

Core sets `extension_id`, `extension_revision`, and `payload_sha256`; it does
not trust provider-supplied values for those fields. The provider supplies the
surface id, goal id, timestamps, lineage, and view. Core validates them against
the active manifest and the generic view schema.

Projection persistence is local runtime state. The default location is under
the LoopX runtime root, grouped by extension and surface id. The state contains
only the validated envelope and compact diagnostics, not raw input evidence.

## Generic Decision Research View

`decision_research_dashboard_v0` is presentation-oriented and domain-neutral.
It contains bounded arrays and text fields:

```text
identity
  title
  subtitle
  as_of
  evidence_cutoff

adjudication
  status
  label
  summary
  confidence

metrics[]
  id
  label
  value
  detail
  tone

dashboard_summaries[]
  id
  label
  title
  summary
  tone
  destination_anchor

layers[]
  id
  order
  label
  status
  summary
  evidence_points[]

entities[]
  entity_id
  symbol
  display_name
  classification
  status
  confidence
  inference
  observations[]
  scenario_estimates[]
  counterevidence[]
  thesis_breakers[]
  next_events[]

research_ledger[]
  case_id
  label
  gate_states[]
  decision
  summary
  evidence_refs[]

event_gates[]
  event_id
  label
  status
  observation_window
  frozen_hypothesis
  observables[]
  current_evidence[]
  supports[]
  refutes[]
  thesis_breakers[]
  next_review

method_state
  revision
  lifecycle_state
  active_method_changed
  summary

boundary
  research_aid_only
  investment_advice
  trading_allowed
  raw_provider_payload_recorded
  private_source_content_read
```

The schema does not define finance calculations. It defines how already
validated conclusions are displayed. `dashboard_summaries` is bounded to three
items and is the only source for main-dashboard research summaries.

## Finance Domain Contract

The Finance package adds a separate input and result path alongside the
existing discovery reducer:

- input: `finance_research_dashboard_input_v0`
- result: `finance_research_dashboard_packet_v0`
- embedded generic view: `decision_research_dashboard_v0`

The existing `finance_value_discovery_input_v0` and
`finance_value_discovery_packet_v0` remain backward compatible.

Finance validation enforces:

- a single point-in-time cutoff in valid ISO-8601 form;
- bounded, explicit fact, inference, guidance, and estimate classifications;
- support and counterevidence for every material conclusion;
- confidence and `as_of` values for current observations;
- assumptions, horizon, and probability for scenario estimates;
- scenario probabilities summing to one per entity;
- the term `scenario estimate` rather than an unsupported target price;
- an invalidation condition for observation ranges;
- explicit `selected`, `rejected`, `insufficient_evidence`, `blocked`, or
  `superseded` research decisions;
- gate-by-gate outcomes for alpha claims;
- event hypotheses and observables frozen before result ingestion;
- no automatic conclusion change based only on an event date;
- no raw source body, credential, local path, account, portfolio, or order
  material;
- no unsupported top-level or nested fields.

The Finance mapper may label domain layers as beta, cycle, company value, and
residual alpha. These labels are content, not renderer logic. The approved
initial owner projection explicitly preserves `validated company alpha = 0`
and `active method unchanged` as first-screen facts; zero validated alpha is a
research adjudication, not a missing-data fallback.

## Publication Flow

The CLI gains a generic extension projection operation. The exact parser shape
will be finalized in the implementation plan, but the user-visible behavior is:

1. Resolve the installed extension and require:
   - installed;
   - enabled;
   - active revision selected;
   - doctor proof bound to that revision and current entrypoint identity.
2. Require the requested surface to be declared by the active manifest.
3. Invoke the provider with bounded JSON input.
4. Require a successful provider result containing one generic presentation
   view for that surface.
5. Validate the generic envelope fields and view schema.
6. Scan the projection for forbidden local/private material.
7. Bind the active extension revision and canonical payload hash.
8. Write a temporary file, fsync, atomically replace the current surface file,
   and read it back.
9. Return a receipt containing the surface id, revision, hash, row counts, and
   readback result.

Dry-run is the default. Persistence requires `--execute`.

No quota is spent merely for displaying or reading a projection. The
projection command does not change goals, todos, methods, extension activation,
or external systems.

## Lifecycle and Visibility Rules

The dashboard surface state is derived from two sources:

- active extension manifest and readiness;
- persisted projection for the active extension revision.

| Extension state | Projection state | Dashboard behavior |
| --- | --- | --- |
| absent | any | hide navigation and summaries |
| installed but disabled | any | hide navigation and summaries |
| enabled but doctor-stale | any | hide navigation and summaries |
| ready | none | show navigation with declared empty state |
| ready | valid and revision-matching | show page and dashboard summaries |
| ready | corrupt or schema-invalid | show safe error state and diagnostics |
| ready | valid but review-due | show historical result with prominent review-due label |
| upgraded or rolled back | old revision only | show empty state; do not reuse old projection |

Disable and upgrade operations do not delete projection files. Revision
matching makes stale data unavailable without destructive cleanup. Re-enabling
the same ready revision can make its matching projection visible again.

Core must not silently fall back to an older revision, superseded row, or
invalid payload.

## Status Projection

The status contract adds a bounded collection of active presentation surfaces.
Each item contains:

- manifest-derived navigation metadata;
- extension id, active revision, and readiness state;
- surface state: `empty`, `ready`, `review_due`, or `invalid`;
- compact diagnostics;
- the validated view only for `ready` or `review_due`;
- a stable `goal_id` for joining live goal state.

Normal status rendering remains compact. It reports surface counts and
diagnostics but does not dump the complete owner-only view into Markdown.
`serve-status` may expose the validated JSON to the local dashboard because the
projection has already passed the public/private boundary scan.

If a projection references an unknown goal, the research page remains
available but the goal panel shows an unavailable join. Core does not invent a
goal state or copy stale goal metadata into the research payload.

## Dashboard Experience

### Navigation

The dashboard derives one navigation item per active manifest surface.
Navigation metadata comes from the manifest, not from a hard-coded Finance
entry.

The investment-research item is therefore absent when the Finance extension is
not ready. It appears when the extension is ready, including the empty state.

### Main Dashboard Summary

When a ready projection exists, the main dashboard may show up to three
provider-selected summary cards. They link to the full research surface. The
summary area disappears with the extension surface.

The main dashboard does not independently compute research conclusions.

### Decision Research Page

The generic page renders:

1. connected goal and extension identity;
2. executive adjudication and key metrics;
3. ordered explanatory layers;
4. entity research cards;
5. the research gate ledger;
6. event-impact gates;
7. method state, evidence cutoff, freshness, and boundary notes.

Observation ranges are visually distinct from scenario estimates. Scenario
estimates show horizon, probability, and assumptions. Thesis breakers are
visually prominent.

`validated alpha = 0` is a legitimate research result, not an error state.
Rejected and insufficient-evidence cases remain visible.

### Empty and Error States

- Empty: the extension is ready but no matching projection has been published.
- Review due: data remains readable, but freshness is prominent and current
  observations are not represented as fresh.
- Invalid: show manifest identity and a safe diagnostic. Do not render partial
  provider data.
- Goal unavailable: show research content and a bounded goal-join warning.

The page remains read-only.

## Error Handling

Failures are explicit and fail closed:

- invalid manifest surface declaration blocks installation or upgrade;
- provider failure does not replace the previous valid projection;
- invalid provider output does not persist;
- failed boundary scan does not persist and reports only safe diagnostics;
- write or readback failure leaves the prior file unchanged when possible;
- revision drift during publication aborts before replacement;
- status treats a missing or revision-mismatching file as empty; for a file that
  targets the active extension and surface but fails schema or hash validation,
  it emits safe `invalid` metadata without rendering the payload;
- dashboard schema errors render a safe state rather than accepting unknown
  fields or guessing defaults.

## Security and Privacy

The projection contract rejects:

- absolute and home-relative local paths;
- credentials, cookies, tokens, account ids, and order ids;
- portfolio holdings and position sizes;
- raw provider request or response bodies;
- private document URLs or source bodies;
- script, HTML, or executable markup in text fields;
- unsupported external links.

Evidence references are compact stable ids or explicitly allowed public URLs.
The browser never receives the source document body.

Owner-only means local operator visibility, not permission to store secrets.
Owner-only projections still pass the same credential, path, and raw-evidence
boundary scan.

## Validation Strategy

### Extension Manifest and Runtime

- accept a valid declared surface;
- reject duplicate, unsupported, or malformed surface declarations;
- hide surfaces for absent, disabled, or stale-doctor extensions;
- invalidate projections after upgrade or rollback revision changes;
- preserve old files without making them visible;
- abort publication if extension state changes during execution;
- verify atomic write and exact hash readback;
- ensure failed provider output preserves the prior projection.

### Generic Projection Contract

- reject unsupported keys and oversized arrays or text;
- reject malformed timestamps, hashes, lineage, and goal ids;
- reject forbidden paths, credentials, markup, and raw bodies;
- validate empty, ready, review-due, invalid, and goal-unavailable states;
- verify owner-only Markdown output remains compact.

### Finance Package

- preserve existing discovery packet behavior;
- validate scenario probabilities and assumptions;
- reject unsupported target-price semantics;
- require support, counterevidence, and thesis breakers;
- require frozen event hypotheses and observables;
- preserve rejected and insufficient-evidence cases;
- map finance layers and gate outcomes into the generic view;
- prove deterministic output for equivalent canonical input.

### Dashboard

- hide navigation and summary when no ready surface exists;
- show declared empty state for a ready extension without data;
- render ready and review-due projections;
- render safe invalid and missing-goal states;
- render zero validated alpha as an ordinary adjudication;
- verify observation ranges and scenario estimates are labeled differently;
- test desktop and mobile first viewports;
- verify no write controls or trading actions are introduced.

### End-to-End Smoke

A focused public-safe fixture will:

1. install a synthetic standalone extension with one declared research surface;
2. publish a synthetic validated decision view;
3. verify revision-bound persistence and status readback;
4. verify dashboard navigation and key sections;
5. disable the extension and verify the surface disappears;
6. re-enable and doctor the same revision and verify the surface returns;
7. upgrade to a new revision and verify the old projection is not reused.

The smoke uses synthetic entities and contains no dated market research,
private project state, raw source evidence, credentials, or local paths.

## Delivery Boundaries

Implementation should be split by reviewer logic:

1. generic manifest, runtime projection persistence, status projection, and
   focused backend tests;
2. Finance input validation and generic view mapping with package tests;
3. dashboard generic renderer, navigation, fixtures, and visual tests;
4. public documentation and a focused end-to-end smoke if not already covered
   by the preceding batches.

The implementation plan may combine adjacent parts when a split would leave an
unusable half-contract. It must avoid adding a generic frontend plugin runtime,
new capability registration, or unrelated dashboard refactoring.

Before merge, run focused package, extension-runtime, status, and dashboard
tests; build the dashboard; inspect desktop and mobile first viewports; run
private-boundary scans; and execute the risk-based LoopX premerge canary.
