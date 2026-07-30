# Extension-Gated Research Dashboard Implementation Plan

> **For agentic workers:** Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task.

**Goal:** Ship a revision-bound, extension-gated decision-research surface so LoopX Dashboard shows validated Finance research only while the owning extension is installed, enabled, doctor-ready, and matched to the published projection revision.

**Architecture:** The standalone Finance provider validates owner-supplied research and emits a generic `decision_research_dashboard_v0` view. A new generic extension-presentation module invokes the lifecycle-gated provider, validates and atomically persists an `extension_projection_surface_v0` envelope, and projects only active-revision surfaces into `loopx status`; the Dashboard derives navigation, summary cards, and the read-only research page exclusively from that status collection. Core never parses Finance source files, and the browser never receives raw provider input or private evidence bodies.

**Tech Stack:** Python 3.11+, stdlib JSON/TOML/hashlib/pathlib, pytest, React 19, TypeScript 6, Zod 4, TanStack Router, Tailwind CSS, Playwright browser smokes.

---

## File Map

### Generic extension presentation contract

- Modify `loopx/extensions/manifest.py`
  - Parse and strictly validate optional `[[presentation_surfaces]]` declarations.
  - Return normalized declarations in `manifest["presentation_surfaces"]`.
- Create `loopx/extensions/presentation.py`
  - Validate `decision_research_dashboard_v0`.
  - Publish and read back revision-bound projection envelopes.
  - Collect ready/empty/review-due/invalid surface projections without executing providers.
- Modify `loopx/cli_commands/extension.py`
  - Add `loopx extension publish-projection`.
- Modify `loopx/control_plane/status_collection.py`
  - Inject a presentation-surface collector callback and include its bounded result.
- Modify `loopx/status.py`
  - Wire the real extension presentation collector into status collection.
- Modify `tests/extensions/test_extension_runtime.py`
  - Cover manifest declaration, lifecycle gating, publication, persistence, revision mismatch, corruption, and CLI behavior.
- Modify `tests/control_plane/test_status_collection_material_capability_wiring.py`
  - Cover status callback wiring without coupling status collection to Finance.

### Finance provider mapping

- Modify `packages/loopx-finance-value-discovery/extension.toml`
  - Declare the owner-only `investment-research` presentation surface.
- Create `packages/loopx-finance-value-discovery/src/loopx_finance_value_discovery/dashboard.py`
  - Strictly validate `finance_research_dashboard_input_v0`.
  - Map Finance semantics to `decision_research_dashboard_v0`.
- Modify `packages/loopx-finance-value-discovery/src/loopx_finance_value_discovery/cli.py`
  - Dispatch by input schema while preserving the existing discovery reducer.
- Modify `packages/loopx-finance-value-discovery/src/loopx_finance_value_discovery/__init__.py`
  - Export the new packet builder.
- Add `packages/loopx-finance-value-discovery/examples/research-dashboard.json`
  - Provide a synthetic, public-safe fixture with no dated real-company research.
- Modify `packages/loopx-finance-value-discovery/README.md`
  - Document the owner-input and explicit publish flow.
- Modify `tests/extensions/test_finance_value_discovery_extension.py`
  - Cover the strict Finance contract and generic view mapping.

### Dashboard

- Modify `apps/presentation/dashboard/src/data/status.ts`
  - Add strict Zod schemas and exported types for presentation surfaces and decision-research views.
- Modify `apps/presentation/dashboard/src/router.tsx`
  - Add an optional generic `surfaceId` dashboard search parameter.
- Create `apps/presentation/dashboard/src/views/decision-research-surface.tsx`
  - Render ready, review-due, empty, invalid, and goal-unavailable states.
- Modify `apps/presentation/dashboard/src/views/dashboard-page.tsx`
  - Derive navigation and up to three homepage summaries from active surfaces.
  - Render the selected generic surface without hard-coding Finance or symbols.
- Modify `examples/dashboard-home-browser-smoke.mjs`
  - Add a synthetic extension surface fixture and desktop/mobile assertions.

### Public end-to-end validation

- Create `examples/extension-presentation-surface-smoke.py`
  - Exercise install, enable/readiness, publish/readback, status projection, disable, re-enable, and upgrade invalidation with a synthetic provider.
- Modify `docs/reference/extensions.md`
  - Document declaration, publication, lifecycle visibility, and privacy boundaries.

## Public Contracts

### Manifest declaration

`load_extension_manifest()` returns:

```python
{
    "provider": {...},
    "capabilities": [...],
    "implementations": [...],
    "runtime": {...},
    "presentation_surfaces": [
        {
            "id": "investment-research",
            "kind": "decision_research_dashboard",
            "title": "Investment Research",
            "view_schema": "decision_research_dashboard_v0",
            "visibility": "owner-only",
            "empty_state_title": "No validated research yet",
            "empty_state_detail": (
                "Publish a validated extension projection to populate this page."
            ),
        }
    ],
}
```

Surface ids match `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`, text is plain and bounded, visibility is `public-safe|owner-only`, and the only initially supported pair is `decision_research_dashboard` plus `decision_research_dashboard_v0`.

### Provider publication result

The generic publisher accepts a provider result containing:

```json
{
  "schema_version": "finance_research_dashboard_packet_v0",
  "presentation_projection": {
    "schema_version": "extension_presentation_projection_v0",
    "surface_id": "investment-research",
    "goal_id": "synthetic-research-goal",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "review_due_at": "2026-02-01T00:00:00+00:00",
    "lineage": {
      "source_id": "synthetic-research-2026-01-01",
      "version": 1,
      "row_lifecycle": "active",
      "supersedes": [],
      "superseded_by": null
    },
    "view_schema": "decision_research_dashboard_v0",
    "view": {}
  }
}
```

Core ignores any provider attempt to set extension id, extension revision, visibility, or payload hash. It takes those fields from the active manifest and lifecycle state.

### Persisted envelope

The publisher writes:

```json
{
  "schema_version": "extension_projection_surface_v0",
  "extension_id": "loopx-example",
  "extension_revision": "0123456789abcdef",
  "surface_id": "investment-research",
  "surface_kind": "decision_research_dashboard",
  "view_schema": "decision_research_dashboard_v0",
  "visibility": "owner-only",
  "goal_id": "synthetic-research-goal",
  "generated_at": "2026-01-01T00:00:00+00:00",
  "review_due_at": "2026-02-01T00:00:00+00:00",
  "payload_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "lineage": {...},
  "view": {...}
}
```

The canonical hash covers the complete envelope except `payload_sha256`. The
default path is
`Path(state_file).parent / "projections" / extension_id / f"{surface_id}.json"`.
Writes use a sibling temporary file, file `fsync`, `os.replace`, directory
`fsync` when available, and exact readback validation.

### Status projection

`collect_active_extension_presentation_surfaces()` returns:

```python
{
    "schema_version": "extension_presentation_surfaces_v0",
    "count": 1,
    "ready_count": 1,
    "review_due_count": 0,
    "empty_count": 0,
    "invalid_count": 0,
    "items": [
        {
            "extension_id": "loopx-example",
            "extension_revision": "0123456789abcdef",
            "surface_id": "investment-research",
            "surface_kind": "decision_research_dashboard",
            "title": "Investment Research",
            "view_schema": "decision_research_dashboard_v0",
            "visibility": "owner-only",
            "state": "ready",
            "goal_id": "synthetic-research-goal",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "review_due_at": "2026-02-01T00:00:00+00:00",
            "diagnostic": None,
            "empty_state_title": "No validated research yet",
            "empty_state_detail": "...",
            "view": {...},
        }
    ],
}
```

Absent, disabled, and doctor-stale extensions contribute no item. A ready declaration without a matching file contributes `empty`; a corrupt active file contributes `invalid` without `view`; a valid old-revision file contributes `empty`; a past `review_due_at` contributes `review_due`.

---

### Task 1: Parse Declarative Presentation Surfaces

**Files:**
- Modify: `loopx/extensions/manifest.py`
- Test: `tests/extensions/test_extension_runtime.py`

- [ ] **Step 1: Write failing manifest tests**

Add tests that load a temporary standalone manifest and assert:

```python
assert manifest["presentation_surfaces"] == [{
    "id": "investment-research",
    "kind": "decision_research_dashboard",
    "title": "Investment Research",
    "view_schema": "decision_research_dashboard_v0",
    "visibility": "owner-only",
    "empty_state_title": "No validated research yet",
    "empty_state_detail": "Publish a validated projection.",
}]
```

Add parametrized rejection cases for duplicate ids, `Investment Research`, unsupported schema, unsupported visibility, markup such as `<script>`, URL text, absolute paths, and text over the documented bound.

- [ ] **Step 2: Verify the tests fail for the missing contract**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -k presentation_surface_manifest -q
```

Expected: failures show `presentation_surfaces` is absent or malformed declarations are accepted.

- [ ] **Step 3: Implement strict manifest parsing**

Add `_presentation_surfaces()` with explicit key allow-sets, duplicate detection, bounded plain-text validation, supported kind/schema validation, and normalized output. Include the normalized list in `load_extension_manifest()`'s return value without changing existing capability/runtime behavior.

- [ ] **Step 4: Verify green and existing manifest compatibility**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py \
  tests/extensions/test_extension_scaffold.py \
  tests/extensions/test_finance_value_discovery_extension.py -q
```

Expected: all tests pass; manifests without declarations return an empty list.

- [ ] **Step 5: Commit the manifest contract**

Stage only `loopx/extensions/manifest.py` and `tests/extensions/test_extension_runtime.py`, then commit with:

```text
feat(extensions): declare presentation surfaces

Co-authored-by: TRAE CLI <noreply@bytedance.com>
```

### Task 2: Validate and Persist Revision-Bound Projections

**Files:**
- Create: `loopx/extensions/presentation.py`
- Modify: `tests/extensions/test_extension_runtime.py`

- [ ] **Step 1: Write failing generic view validation tests**

Construct the smallest valid synthetic `decision_research_dashboard_v0` view containing identity, adjudication, one metric, one dashboard summary, one layer, one entity with distinct observation range and three scenario estimates, one ledger row, one event gate, method state, and boundary flags. Assert normalization preserves `validated alpha = 0`, rejected/insufficient decisions, scenario probability/horizon/assumptions, and thesis breakers.

Add focused rejection tests for:

- unknown top-level or nested keys;
- malformed ISO timestamps;
- arrays above their bounds and oversized text;
- scenario probabilities that do not sum to `1.0 ± 0.000001`;
- observation ranges without invalidation;
- scenario estimates without horizon, probability, or assumptions;
- HTML/script markup, absolute paths, home-relative paths, credential-like keys or values, account/order/position fields, and raw request/response bodies;
- unsupported evidence URLs.

- [ ] **Step 2: Verify validation tests fail**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -k decision_research_view -q
```

Expected: import or function-not-found failure for the new presentation module.

- [ ] **Step 3: Implement strict generic schemas**

In `loopx/extensions/presentation.py`, implement explicit allow-set validators and:

```python
def validate_decision_research_view(value: Mapping[str, Any]) -> dict[str, Any]:
    ...

def validate_provider_presentation_projection(
    value: Mapping[str, Any],
    *,
    declared_surface: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

Use timezone-aware ISO parsing, compact bounded text, exact enums, deterministic ordering, and recursive public/private boundary checks. Do not import Finance modules.

- [ ] **Step 4: Write failing publication and readback tests**

Install and enable a synthetic standalone provider with a declared surface. Assert dry-run returns readiness without invoking or writing. Assert execute:

- runs through `run_standalone_extension`;
- binds the active revision and manifest visibility;
- writes mode `0600`;
- returns a SHA-256 and `readback_verified=True`;
- leaves no temporary file;
- preserves the previous valid file when provider output, validation, write, or readback fails;
- aborts when active revision changes between provider execution and replacement.

- [ ] **Step 5: Verify publication tests fail**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -k projection_publication -q
```

Expected: publication API is missing.

- [ ] **Step 6: Implement publication**

Add:

```python
def default_extension_projection_root(state_file: str | Path) -> Path:
    ...

def publish_extension_projection(
    extension_id: str,
    surface_id: str,
    *,
    state_file: str | Path,
    request: Mapping[str, Any],
    execute: bool = False,
) -> dict[str, Any]:
    ...
```

Resolve active lifecycle state before execution, invoke the existing bounded standalone runtime, validate the provider projection, resolve lifecycle state again, require the same revision and entrypoint identity, hash canonical JSON, atomically replace, read back, and compare the normalized envelope and hash.

- [ ] **Step 7: Verify green**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -k \
  'decision_research_view or projection_publication' -q
```

Expected: all focused tests pass.

### Task 3: Project Active Surfaces into Status

**Files:**
- Modify: `loopx/extensions/presentation.py`
- Modify: `loopx/control_plane/status_collection.py`
- Modify: `loopx/status.py`
- Modify: `tests/extensions/test_extension_runtime.py`
- Modify: `tests/control_plane/test_status_collection_material_capability_wiring.py`

- [ ] **Step 1: Write failing lifecycle collection tests**

Cover:

- absent/disabled/doctor-stale extension -> no item;
- ready/no file -> `empty`;
- ready/current valid file -> `ready`;
- review deadline before injected `now` -> `review_due`;
- malformed JSON, bad current-revision hash, or invalid current schema -> `invalid` with safe diagnostic and no view;
- valid old-revision file after upgrade/rollback -> `empty`;
- disable then re-enable and doctor the same revision -> matching projection visible again.

- [ ] **Step 2: Verify lifecycle tests fail**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -k active_presentation_surfaces -q
```

- [ ] **Step 3: Implement read-only collection**

Add:

```python
def collect_active_extension_presentation_surfaces(
    *,
    state_file: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    ...
```

Read state and files only. Never execute provider code. Return only ready extension declarations and bounded safe diagnostics.

- [ ] **Step 4: Write failing status callback tests**

Extend the fixture context with `collect_extension_presentation_surfaces`. Assert `collect_status()` calls it with `default_extension_state_file(runtime_root)` semantics and places the result at `presentation_surfaces`. Assert an empty result remains a compact zero-count collection.

- [ ] **Step 5: Verify callback tests fail**

Run:

```bash
uv run --extra test python -m pytest \
  tests/control_plane/test_status_collection_material_capability_wiring.py -q
```

- [ ] **Step 6: Wire status collection**

Add the callback to `StatusCollectionContext`, invoke it after runtime root resolution, and wire the real collector in `build_status_collection_context()`. Do not add Finance imports or parse project-local research files.

- [ ] **Step 7: Verify backend status green**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py \
  tests/control_plane/test_status_collection_material_capability_wiring.py -q
```

- [ ] **Step 8: Commit generic runtime/status behavior**

Stage only the generic module, status wiring, and related tests. Commit:

```text
feat(extensions): publish research projections

Co-authored-by: TRAE CLI <noreply@bytedance.com>
```

### Task 4: Add the Projection Publication CLI

**Files:**
- Modify: `loopx/cli_commands/extension.py`
- Modify: `tests/extensions/test_extension_runtime.py`

- [ ] **Step 1: Write failing CLI tests**

Exercise:

```bash
loopx extension publish-projection loopx-example investment-research \
  --input-json request.json --format json
```

and the same command with `--execute`. Assert dry-run does not invoke/write, execute returns the published hash and readback receipt, stdin `-` works, oversized input is rejected before runtime resolution, and disabled/stale extensions fail closed.

- [ ] **Step 2: Verify CLI tests fail**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -k publish_projection_cli -q
```

- [ ] **Step 3: Implement parser and handler**

Reuse `_add_common()` and `_load_json_object()`. Add positional `extension_id`, positional `surface_id`, required `--input-json`, and optional `--execute`. Delegate to `publish_extension_projection()` and preserve JSON/Markdown output behavior.

- [ ] **Step 4: Verify CLI green**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py -q
```

### Task 5: Build the Strict Finance Research Mapper

**Files:**
- Create: `packages/loopx-finance-value-discovery/src/loopx_finance_value_discovery/dashboard.py`
- Modify: `packages/loopx-finance-value-discovery/src/loopx_finance_value_discovery/cli.py`
- Modify: `packages/loopx-finance-value-discovery/src/loopx_finance_value_discovery/__init__.py`
- Modify: `tests/extensions/test_finance_value_discovery_extension.py`

- [ ] **Step 1: Write failing positive mapping test**

Build a synthetic input with:

- `schema_version=finance_research_dashboard_input_v0`;
- one stable goal and source id;
- valid point-in-time/evidence cutoff and review deadline;
- `insufficient_evidence` adjudication;
- first-screen metrics `validated company alpha = 0` and `active method unchanged`;
- beta, cycle, company-value, and residual-alpha layers;
- one entity with observation ranges and Bull/Base/Bear scenario estimates;
- support, counterevidence, and thesis breakers;
- an event gate whose hypothesis and observables are frozen;
- a rejected ledger case and an insufficient-evidence case;
- safe boundary flags.

Assert `build_finance_research_dashboard_packet()` emits deterministic canonical content under `presentation_projection` and never emits raw input evidence.

- [ ] **Step 2: Verify positive test fails**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_finance_value_discovery_extension.py \
  -k finance_research_dashboard_mapping -q
```

- [ ] **Step 3: Implement minimum strict mapper**

Add:

```python
def build_finance_research_dashboard_packet(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

Use explicit allow-sets at every level. Validate ISO-8601 timestamps rather than accepting arbitrary point-in-time text. Preserve fact/guidance/inference/estimate classification, support and counterevidence, confidence, event freeze state, and method-state truth. Output only the generic presentation projection.

- [ ] **Step 4: Write failing negative contract tests**

Parametrize rejections for:

- malformed `point_in_time` or `evidence_cutoff`;
- unknown top-level/nested fields;
- missing support, counterevidence, or thesis breaker;
- scenario probability sum mismatch;
- target-price wording or missing scenario assumptions/horizon;
- observation range without invalidation;
- event evidence dated before freeze but represented as post-event adjudication;
- unsupported decision or gate state;
- raw payload/body, local path, credential, account, portfolio, position, or order material.

- [ ] **Step 5: Verify negative tests fail for the intended reasons**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_finance_value_discovery_extension.py \
  -k finance_research_dashboard -q
```

- [ ] **Step 6: Complete validation and deterministic mapping**

Implement only the fields exercised by the public contract. Reuse small helpers inside `dashboard.py`; do not add a generic Finance framework or change the active method.

- [ ] **Step 7: Dispatch the new schema through the provider CLI**

Make `cli.run()` parse stdin once and route:

```python
if payload["schema_version"] == "finance_research_dashboard_input_v0":
    result = build_finance_research_dashboard_packet(payload)
else:
    result = build_finance_value_discovery_packet(payload)
```

Keep `--doctor` side-effect free and preserve existing discovery output byte-for-byte.

- [ ] **Step 8: Verify Finance package green**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_finance_value_discovery_extension.py -q
```

### Task 6: Declare and Document the Finance Surface

**Files:**
- Modify: `packages/loopx-finance-value-discovery/extension.toml`
- Add: `packages/loopx-finance-value-discovery/examples/research-dashboard.json`
- Modify: `packages/loopx-finance-value-discovery/README.md`
- Modify: `tests/extensions/test_finance_value_discovery_extension.py`

- [ ] **Step 1: Add failing manifest and fixture test**

Assert the Finance manifest declares exactly one owner-only research surface and the synthetic example maps successfully while containing none of the repository's private goal names, real symbols, local paths, credentials, or dated owner research.

- [ ] **Step 2: Verify red**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_finance_value_discovery_extension.py \
  -k finance_presentation_surface -q
```

- [ ] **Step 3: Add declaration, fixture, and owner workflow docs**

Document:

```bash
loopx extension publish-projection \
  loopx-finance-value-discovery investment-research \
  --input-json owner-research.json --execute --format json
```

State explicitly that installation/enablement is separate, publication is local and read-only, old revisions are hidden, and the command does not activate methods, spend quota, or create trades.

- [ ] **Step 4: Verify package and boundary scans**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_finance_value_discovery_extension.py -q
rg -n '/Users/|bytedance|Bearer |api[_-]?key|account_id|order_id|position_size' \
  packages/loopx-finance-value-discovery
```

Expected: tests pass and the scan returns no private leaks; schema examples may mention forbidden key names only in explicit documentation if necessary.

- [ ] **Step 5: Commit Finance provider behavior**

Stage only the Finance package and Finance tests. Commit:

```text
feat(finance): project validated research views

Co-authored-by: TRAE CLI <noreply@bytedance.com>
```

### Task 7: Parse Presentation Surfaces in Dashboard

**Files:**
- Modify: `apps/presentation/dashboard/src/data/status.ts`
- Modify: `apps/presentation/dashboard/src/router.tsx`
- Add: `apps/presentation/dashboard/smoke/presentation-surface-schema-smoke.ts`
- Modify: `apps/presentation/dashboard/package.json`

- [ ] **Step 1: Write failing TypeScript schema smoke**

Compile and run a smoke that:

- parses empty/ready/review-due/invalid surfaces;
- preserves `validated company alpha = 0`;
- rejects an invalid surface with a partial view;
- rejects unknown schema versions and invalid scenario probability types;
- defaults missing `presentation_surfaces` to an empty collection for backward compatibility.

- [ ] **Step 2: Verify red**

Run:

```bash
cd apps/presentation/dashboard
npm run smoke:presentation-surface-schema
```

Expected: the script is missing or TypeScript symbols are undefined.

- [ ] **Step 3: Add strict Zod schemas and exports**

Define `decisionResearchViewSchema`, `presentationSurfaceSchema`, and `presentationSurfaceCollectionSchema`. Add `presentation_surfaces` to `statusPayloadSchema`. Export inferred types. Use `.strict()` on the new contracts so browser rendering fails closed.

- [ ] **Step 4: Add generic surface selection to router search**

Add:

```typescript
surfaceId: z.string().regex(/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/).optional()
```

Do not add a Finance-specific route or extension id.

- [ ] **Step 5: Verify green and build**

Run:

```bash
cd apps/presentation/dashboard
npm run smoke:presentation-surface-schema
npm run build
```

### Task 8: Render Generic Research Navigation, Summary, and Page

**Files:**
- Add: `apps/presentation/dashboard/src/views/decision-research-surface.tsx`
- Modify: `apps/presentation/dashboard/src/views/dashboard-page.tsx`
- Modify: `examples/dashboard-home-browser-smoke.mjs`

- [ ] **Step 1: Add failing browser fixture assertions**

Extend the synthetic status fixture with one ready research surface. Assert:

- the left navigation shows the manifest title;
- the home shows at most three `dashboard_summaries`;
- selecting the item sets `surfaceId` and shows adjudication, metrics, layers, entities, ledger, event gates, method state, evidence cutoff, and boundary;
- observation ranges and scenario estimates use distinct headings;
- rejected and insufficient-evidence states remain visible;
- `validated company alpha = 0` and `active method unchanged` appear in the first viewport;
- no Buy/Sell/order/position/trade controls exist;
- desktop 1440×1000 and mobile 390×844 screenshots are written.

Add a second reload fixture/state that removes surfaces and assert both navigation and summaries disappear.

- [ ] **Step 2: Verify browser smoke red**

Run:

```bash
cd apps/presentation/dashboard
npm run smoke:home-browser
```

Expected: research navigation or renderer assertions fail.

- [ ] **Step 3: Implement the generic renderer**

`DecisionResearchSurface` accepts one `PresentationSurface` plus the existing goal list. It renders:

- safe invalid diagnostics without `view`;
- manifest-owned empty state;
- review-due banner;
- goal-join warning when `goal_id` is unknown;
- generic ready content in the approved visual hierarchy.

It must not test extension ids, symbols, or Finance layer ids.

- [ ] **Step 4: Integrate dynamic navigation and homepage summaries**

In `DashboardPage`, derive active items from `payload.presentation_surfaces.items`. Keep the Dashboard nav item first. Use only each view's `dashboard_summaries.slice(0, 3)` for home cards. Link cards and nav through the existing dashboard route search while preserving status source/search settings.

- [ ] **Step 5: Verify browser and build green**

Run:

```bash
cd apps/presentation/dashboard
npm run build
npm run smoke:home-browser
```

Inspect both generated screenshots for clipping, overlap, and first-viewport truth.

- [ ] **Step 6: Commit Dashboard rendering**

Stage only Dashboard source, package script metadata, and the browser smoke. Commit:

```text
feat(dashboard): render extension research surfaces

Co-authored-by: TRAE CLI <noreply@bytedance.com>
```

### Task 9: Add the Public End-to-End Lifecycle Smoke

**Files:**
- Add: `examples/extension-presentation-surface-smoke.py`
- Modify: `docs/reference/extensions.md`

- [ ] **Step 1: Write the smoke against public APIs**

The smoke creates a temporary executable provider and two manifest revisions. It must:

1. install revision A with one declared synthetic surface;
2. verify disabled/stale states are absent;
3. enable and doctor revision A;
4. verify ready/no projection is empty;
5. publish a synthetic projection and verify exact hash/readback;
6. collect ready status;
7. disable and verify hidden;
8. re-enable/doctor A and verify the same matching projection returns;
9. upgrade to revision B and verify A's file remains on disk but status is empty;
10. corrupt B's active file and verify safe invalid status without provider view.

- [ ] **Step 2: Run smoke and expect failure before docs/final fixes**

Run:

```bash
uv run --extra test python examples/extension-presentation-surface-smoke.py
```

Expected before final integration: any missing public API or lifecycle mismatch fails with a direct assertion.

- [ ] **Step 3: Complete the documented extension workflow**

Add `Presentation surfaces` to `docs/reference/extensions.md`, including provider ownership, manifest declaration, dry-run/execute publication, revision visibility table, privacy scan, and status-only read behavior. Keep examples synthetic and public-safe.

- [ ] **Step 4: Run focused full validation**

Run:

```bash
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py \
  tests/extensions/test_finance_value_discovery_extension.py \
  tests/control_plane/test_status_collection_material_capability_wiring.py -q
uv run --extra test python examples/extension-presentation-surface-smoke.py
cd apps/presentation/dashboard
npm run build
npm run smoke:presentation-surface-schema
npm run smoke:home-browser
```

- [ ] **Step 5: Commit docs and lifecycle smoke**

Stage only `examples/extension-presentation-surface-smoke.py` and `docs/reference/extensions.md`. Commit:

```text
docs(extensions): document research surfaces

Co-authored-by: TRAE CLI <noreply@bytedance.com>
```

### Task 10: Validate, Publish Owner Projection, and Prepare PR

**Files:**
- No additional tracked files unless validation exposes a defect.
- Local-only owner input under the ignored goal/runtime state.

- [ ] **Step 1: Establish final repository ground truth**

Run:

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
git ls-files --others --exclude-standard
```

Classify every path as product code, public docs, durable smoke, local/private state, or obsolete artifact. Do not stage `uv.lock`, output screenshots, `.codex` owner research, or runtime projection files.

- [ ] **Step 2: Run private/public boundary scans**

Run targeted scans for local absolute paths, credentials, private organizational names, raw evidence bodies, benchmark logs, account/order/portfolio terms, and internal links across changed tracked files. Review each match semantically; forbidden examples may appear only as generalized rejection rules.

- [ ] **Step 3: Run risk-based premerge validation**

Run:

```bash
loopx canary premerge --from-git-diff
uv run --extra test python -m pytest \
  tests/extensions/test_extension_runtime.py \
  tests/extensions/test_finance_value_discovery_extension.py \
  tests/control_plane/test_status_collection_material_capability_wiring.py -q
uv run --extra test python examples/extension-presentation-surface-smoke.py
cd apps/presentation/dashboard
npm run build
npm run smoke:presentation-surface-schema
npm run smoke:home-browser
```

Record failures and skips exactly; do not hide unrelated baseline failures.

- [ ] **Step 4: Publish the approved owner-only Finance projection locally**

Create an ignored owner input by mapping the validated tracker, finding, and
active-goal records named in the design spec into
`finance_research_dashboard_input_v0`. Export its absolute path through the
required local-only environment variable
`LOOPX_FINANCE_RESEARCH_DASHBOARD_INPUT`, validate it locally, then explicitly
install/enable/doctor the Finance extension because the owner has authorized
this workstation to show it. Execute:

```bash
test -f "${LOOPX_FINANCE_RESEARCH_DASHBOARD_INPUT:?set the ignored owner input path}"
loopx extension publish-projection \
  loopx-finance-value-discovery investment-research \
  --input-json "$LOOPX_FINANCE_RESEARCH_DASHBOARD_INPUT" \
  --execute --format json
```

Read back `loopx status --format json` and verify:

- extension and active revision match;
- `surface_id=investment-research`;
- state is `ready` or `review_due`;
- goal id joins the expected goal;
- first-screen facts remain `validated company alpha = 0`, `active method unchanged`, and `Insufficient Evidence`;
- no raw owner evidence or local source path appears.

This local publication is runtime state, not a tracked repository fixture.

- [ ] **Step 5: Capture acceptance screenshots**

Start the local status server and Dashboard, then capture:

- home desktop 1440×1000 with research summaries;
- research desktop 1440×1000;
- research mobile 390×844;
- disabled-extension home proving the tab and summaries disappear.

Keep screenshots local unless they are explicitly generalized and approved for public documentation.

- [ ] **Step 6: Inspect commit hygiene**

Verify each commit has exactly one final trailer:

```bash
git log --format='%H%n%B%n---' origin/main..HEAD
```

No commit may combine private state with public code.

- [ ] **Step 7: Push and open the PR**

Push `codex/finance-research-dashboard-extension-gate-20260730` and open a PR describing:

- generic extension presentation contract;
- Finance mapper boundary;
- Dashboard lifecycle behavior;
- exact tests/smokes and screenshots;
- any skipped checks;
- why no Finance logic or private evidence entered Core/browser.

- [ ] **Step 8: Request independent review**

Review the exact pushed head for lifecycle bypass, revision/hash attacks, schema fail-open behavior, private-data leakage, dashboard partial rendering, and preservation of rejected/insufficient-evidence conclusions. Resolve actionable findings with new failing tests before code changes.

- [ ] **Step 9: Present acceptance evidence**

Provide the PR URL, local acceptance URL, screenshot paths, command results, visible lifecycle matrix, and any remaining owner-only runtime setup. Do not claim acceptance until the pushed head and local projection readback both match the evidence.
