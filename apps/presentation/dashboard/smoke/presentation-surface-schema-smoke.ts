import {
  decisionResearchViewSchema,
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

function validView() {
  return {
    identity: {
      title: "Synthetic Technology Research",
      subtitle: "Evidence-gated decision review",
      as_of: "2026-01-15T12:00:00+00:00",
      evidence_cutoff: "2026-01-15",
    },
    adjudication: {
      status: "insufficient_evidence",
      label: "Insufficient Evidence",
      summary: "The frozen gates do not yet support a selected conclusion.",
      confidence: "medium",
    },
    metrics: [
      {
        id: "validated-alpha",
        label: "Validated company alpha",
        value: "0",
        detail: "No company-specific residual passed every frozen gate.",
        tone: "warning",
      },
      {
        id: "method-state",
        label: "Active method",
        value: "unchanged",
        detail: "The active method was not promoted or replaced.",
        tone: "neutral",
      },
    ],
    dashboard_summaries: [
      {
        id: "adjudication-summary",
        label: "Current adjudication",
        title: "Evidence remains insufficient",
        summary: "Continue monitoring the frozen event gates.",
        tone: "warning",
        destination_anchor: "executive-adjudication",
      },
    ],
    layers: [
      {
        id: "beta",
        order: 1,
        label: "Beta",
        status: "supported",
        summary: "Discount-rate exposure explains part of the move.",
        evidence_points: ["Support: broad synthetic peers moved together."],
      },
    ],
    entities: [
      {
        entity_id: "synthetic-cloud",
        symbol: "SYN",
        display_name: "Synthetic Cloud",
        classification: "Watchlist",
        status: "insufficient_evidence",
        confidence: "medium",
        inference: "A quality business is not yet a validated mispricing.",
        observations: [
          {
            id: "observation-range",
            label: "Observation range",
            kind: "observation_range",
            value: "90-100 synthetic units",
            as_of: "2026-01-15T12:00:00+00:00",
            source_ref: "filing:syn-q4",
            source_type: "company_filing",
            confidence: "high",
            invalidation: "A verified close below 90 with weaker fundamentals.",
          },
        ],
        scenario_estimates: [
          {
            scenario: "bull",
            label: "Bull scenario estimate",
            value: "140 synthetic units",
            horizon: "24 months",
            probability: 0.25,
            assumptions: ["Growth reaccelerates."],
          },
          {
            scenario: "base",
            label: "Base scenario estimate",
            value: "112 synthetic units",
            horizon: "24 months",
            probability: 0.5,
            assumptions: ["Growth remains durable."],
          },
          {
            scenario: "bear",
            label: "Bear scenario estimate",
            value: "72 synthetic units",
            horizon: "24 months",
            probability: 0.25,
            assumptions: ["Growth slows."],
          },
        ],
        counterevidence: ["Capital intensity may remain elevated."],
        thesis_breakers: ["Growth and cash conversion weaken together."],
        next_events: ["Next official earnings release."],
      },
    ],
    research_ledger: [
      {
        case_id: "case-synthetic-cloud",
        label: "Synthetic residual-alpha case",
        gate_states: [
          {
            gate_id: "persistence",
            label: "Persistence",
            status: "failed",
            summary: "The residual did not persist.",
          },
        ],
        decision: "rejected",
        summary: "The company-specific alpha claim was rejected.",
        evidence_refs: ["market:synthetic-peer-control"],
      },
    ],
    event_gates: [
      {
        event_id: "E1",
        label: "Synthetic cloud earnings",
        status: "pending",
        observation_window: "Next official reporting window",
        frozen_hypothesis: "Returns depend on monetization, not capex alone.",
        observables: ["Cloud growth versus frozen guidance."],
        current_evidence: [],
        supports: ["Growth above the frozen range."],
        refutes: ["Higher capex without measurable return."],
        thesis_breakers: ["Official guidance shows deteriorating returns."],
        next_review: "After the official filing is available.",
      },
    ],
    method_state: {
      revision: "candidate-v1",
      lifecycle_state: "active_method_unchanged",
      active_method_changed: false,
      summary: "Active method unchanged.",
    },
    boundary: {
      research_aid_only: true,
      investment_advice: false,
      trading_allowed: false,
      raw_provider_payload_recorded: false,
      private_source_content_read: false,
    },
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
    visibility: "owner-only",
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

const view = decisionResearchViewSchema.parse(validView());
assert(view.metrics[0]?.value === "0", "validated company alpha must remain zero");
assert(
  view.method_state.active_method_changed === false,
  "active method must remain unchanged",
);

for (const state of ["empty", "ready", "review_due", "invalid"] as const) {
  const candidate = baseSurface(state);
  const parsed = presentationSurfaceSchema.parse(
    state === "ready" || state === "review_due"
      ? { ...candidate, view: validView() }
      : candidate,
  );
  assert(parsed.state === state, `surface state drifted: ${state}`);
}

const collection = presentationSurfaceCollectionSchema.parse({
  schema_version: "extension_presentation_surfaces_v0",
  count: 2,
  ready_count: 1,
  review_due_count: 1,
  empty_count: 0,
  invalid_count: 0,
  items: [
    { ...baseSurface("ready"), view: validView() },
    { ...baseSurface("review_due"), view: validView() },
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

const invalidSurface = {
  ...baseSurface("invalid"),
  view: validView(),
};
assert(
  !presentationSurfaceSchema.safeParse(invalidSurface).success,
  "invalid surface with view must fail closed",
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

const invalidProbability = {
  ...baseSurface("ready"),
  view: {
    ...validView(),
    entities: [
      {
        ...validView().entities[0],
        scenario_estimates: [
          {
            ...validView().entities[0].scenario_estimates[0],
            probability: "0.25",
          },
          ...validView().entities[0].scenario_estimates.slice(1),
        ],
      },
    ],
  },
};
assert(
  !presentationSurfaceSchema.safeParse(invalidProbability).success,
  "invalid scenario probability type must fail closed",
);

console.log("presentation surface schema smoke ok");
