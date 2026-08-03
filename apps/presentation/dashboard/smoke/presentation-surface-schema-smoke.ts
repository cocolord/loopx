import {
  exampleStatusPayload,
  parseStatusPayload,
  presentationSurfaceCollectionSchema,
  presentationSurfaceSchema,
} from "../src/data/status.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const PAYLOAD_SHA256 =
  "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

function detailRef() {
  return {
    extension_id: "test-research-extension",
    surface_id: "investment-research",
    extension_revision: "0123456789abcdef",
    payload_sha256: PAYLOAD_SHA256,
  };
}

function baseSurface(state: "empty" | "ready" | "review_due" | "invalid") {
  return {
    extension_id: "test-research-extension",
    extension_revision: "0123456789abcdef",
    surface_id: "investment-research",
    surface_kind: "decision_research_dashboard",
    title: "Investment Research",
    view_schema: "decision_research_dashboard_v0",
    visibility: "public-safe",
    state,
    goal_id: state === "empty" || state === "invalid" ? null : "synthetic-research-goal",
    generated_at:
      state === "empty" || state === "invalid"
        ? null
        : "2026-01-15T12:00:00+00:00",
    review_due_at:
      state === "empty" || state === "invalid"
        ? null
        : "2026-02-15T12:00:00+00:00",
    diagnostic: state === "invalid" ? "projection validation failed" : null,
    empty_state_title: "No validated research yet",
    empty_state_detail: "Publish a validated projection.",
  };
}

// The Core status contract is provider-neutral: ready/review_due carry a compact
// detail_ref pointer, not an inline domain view.
for (const state of ["empty", "ready", "review_due", "invalid"] as const) {
  const candidate = baseSurface(state);
  const parsed = presentationSurfaceSchema.parse(
    state === "ready" || state === "review_due"
      ? { ...candidate, detail_ref: detailRef() }
      : candidate,
  );
  assert(parsed.state === state, `surface state drifted: ${state}`);
}

const readySurface = presentationSurfaceSchema.parse({
  ...baseSurface("ready"),
  detail_ref: detailRef(),
});
assert(
  readySurface.state === "ready" && "detail_ref" in readySurface,
  "ready surface must carry a detail_ref",
);
assert(
  !("view" in readySurface),
  "ready surface must not carry an inline view",
);

// A generic view_schema token (a different domain) must still parse: Core does
// not freeze any one domain's schema.
const genericSurface = presentationSurfaceSchema.safeParse({
  ...baseSurface("ready"),
  surface_kind: "release_dashboard",
  view_schema: "release_dashboard_v0",
  detail_ref: detailRef(),
});
assert(genericSurface.success, "generic provider view_schema must parse");

const collection = presentationSurfaceCollectionSchema.parse({
  schema_version: "extension_presentation_surfaces_v0",
  count: 2,
  ready_count: 1,
  review_due_count: 1,
  empty_count: 0,
  invalid_count: 0,
  items: [
    { ...baseSurface("ready"), detail_ref: detailRef() },
    { ...baseSurface("review_due"), detail_ref: detailRef() },
  ],
});
assert(collection.items.length === 2, "ready and review-due surfaces must parse");

const legacyPayload = structuredClone(exampleStatusPayload) as Record<string, unknown>;
delete legacyPayload.presentation_surfaces;
const legacyParsed = parseStatusPayload(legacyPayload);
assert(
  legacyParsed.presentation_surfaces.count === 0,
  "missing presentation surfaces must default to an empty collection",
);

// An inline `view` on a ready surface must fail closed: status is index-only.
const readyWithInlineView = {
  ...baseSurface("ready"),
  detail_ref: detailRef(),
  view: { headline: "should not be here" },
};
assert(
  !presentationSurfaceSchema.safeParse(readyWithInlineView).success,
  "ready surface with an inline view must fail closed",
);

// A ready surface without a detail_ref must fail closed.
const readyWithoutDetailRef = baseSurface("ready");
assert(
  !presentationSurfaceSchema.safeParse(readyWithoutDetailRef).success,
  "ready surface without a detail_ref must fail closed",
);

const invalidSurface = {
  ...baseSurface("invalid"),
  detail_ref: detailRef(),
};
assert(
  !presentationSurfaceSchema.safeParse(invalidSurface).success,
  "invalid surface with a detail_ref must fail closed",
);

const malformedDetailRef = {
  ...baseSurface("ready"),
  detail_ref: { ...detailRef(), payload_sha256: "not-a-hash" },
};
assert(
  !presentationSurfaceSchema.safeParse(malformedDetailRef).success,
  "malformed detail_ref payload hash must fail closed",
);

const unknownCollection = {
  schema_version: "extension_presentation_surfaces_v99",
  count: 0,
  ready_count: 0,
  review_due_count: 0,
  empty_count: 0,
  invalid_count: 0,
  items: [],
};
assert(
  !presentationSurfaceCollectionSchema.safeParse(unknownCollection).success,
  "unknown collection schema must fail closed",
);

console.log("presentation surface schema smoke ok");
