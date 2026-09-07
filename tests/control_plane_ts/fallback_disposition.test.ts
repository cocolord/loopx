import assert from "node:assert/strict";
import test from "node:test";

import {
  FALLBACK_DISPOSITION_SCHEMA,
  projectFallbackDisposition,
} from "../../loopx/control_plane/goals/fallback_disposition.ts";

function request(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: FALLBACK_DISPOSITION_SCHEMA,
    primary_blocked: true,
    terminal: false,
    declarations: [{ declaration_id: "alternative", target_todo_id: "todo_b" }],
    runnable_todo_ids: [],
    waiting_todo_ids: [],
    ...overrides,
  };
}

test("a missing fallback remains unresolved even when creation was declared", () => {
  const result = projectFallbackDisposition(request({ todo_delta: ["create:todo_b"] }));
  assert.equal(result.disposition, "unresolved");
  assert.deepEqual(result.unresolved_todo_ids, ["todo_b"]);
});

test("real runnable or evaluated waiting fallback resolves the declaration", () => {
  for (const field of ["runnable_todo_ids", "waiting_todo_ids"]) {
    assert.equal(projectFallbackDisposition(request({ [field]: ["todo_b"] })).disposition, "resolved");
  }
});

test("an unrelated runnable task does not resolve the declared fallback", () => {
  assert.equal(projectFallbackDisposition(request({ runnable_todo_ids: ["todo_other"] })).disposition, "unresolved");
});

test("declaration identity is never inferred to be a Todo link", () => {
  assert.equal(projectFallbackDisposition(request({ runnable_todo_ids: ["alternative"] })).disposition, "unresolved");
});

test("no declaration, unblocked primary, and terminal disposition preserve existing behavior", () => {
  for (const change of [{ declarations: [] }, { primary_blocked: false }, { terminal: true }]) {
    assert.equal(projectFallbackDisposition(request(change)).disposition, "resolved");
  }
});

test("explicit successor links are evaluated against real frontier facts", () => {
  const declarations = [{ declaration_id: "alternative", successor_todo_id: "todo_successor" }];
  assert.deepEqual(projectFallbackDisposition(request({ declarations })).unresolved_todo_ids, ["todo_successor"]);
  assert.equal(projectFallbackDisposition(request({ declarations, runnable_todo_ids: ["todo_successor"] })).disposition, "resolved");
});

test("all declarations must be resolved and repeated reads are stable", () => {
  const input = request({
    declarations: [
      { declaration_id: "first", target_todo_id: "todo_b" },
      { declaration_id: "second", target_todo_id: "todo_c" },
    ],
    runnable_todo_ids: ["todo_b"],
  });
  assert.deepEqual(projectFallbackDisposition(input).unresolved_todo_ids, ["todo_c"]);
  assert.deepEqual(projectFallbackDisposition(input), projectFallbackDisposition(input));
});

test("malformed facts fail closed instead of looking like an empty frontier", () => {
  for (const change of [
    { schema_version: "unknown" }, { primary_blocked: "false" }, { terminal: 1 },
    { runnable_todo_ids: null }, { waiting_todo_ids: [null] },
    { declarations: null }, { declarations: [{}] },
    { declarations: Array(5).fill({ declaration_id: "alternative" }) },
  ]) {
    assert.throws(() => projectFallbackDisposition(request(change)));
  }
});
