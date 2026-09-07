import type { JsonObject } from "../effect_program.ts";
import { EffectRuntimeRequestError } from "../effect_runtime_errors.ts";
import {
  optionalNonEmptyString,
  requireBoolean,
  requireJsonObject,
  requireNonEmptyString,
} from "../runtime_decode.ts";

export const FALLBACK_DISPOSITION_SCHEMA = "goal_fallback_disposition_v0";

function ids(value: unknown, label: string): Set<string> {
  if (!Array.isArray(value)) {
    throw new EffectRuntimeRequestError(`${label} must be an array`);
  }
  return new Set(value.map((item, index) => requireNonEmptyString(item, `${label}[${index}]`)));
}

/**
 * Qualify a declared alternate path before allowing a blocked frontier to wait.
 * Eligibility and resume-condition evaluation stay with their existing owners.
 * A vision todo_delta is planning intent, never proof of a persisted successor.
 */
export function projectFallbackDisposition(value: unknown): JsonObject {
  const request = requireJsonObject(value, "goal.fallback_disposition params");
  if (request.schema_version !== FALLBACK_DISPOSITION_SCHEMA) {
    throw new EffectRuntimeRequestError("fallback disposition schema mismatch");
  }
  const blocked = requireBoolean(request.primary_blocked, "primary_blocked");
  const terminal = requireBoolean(request.terminal, "terminal");
  const runnable = ids(request.runnable_todo_ids, "runnable_todo_ids");
  const waiting = ids(request.waiting_todo_ids, "waiting_todo_ids");
  if (!Array.isArray(request.declarations) || request.declarations.length > 4) {
    throw new EffectRuntimeRequestError("declarations must be an array of at most four entries");
  }
  const declarations = request.declarations.map((value, index) => {
    const item = requireJsonObject(value, `declarations[${index}]`);
    return {
      declarationId: requireNonEmptyString(item.declaration_id, "declaration_id"),
      targetId: optionalNonEmptyString(item.target_todo_id, "target_todo_id"),
      successorId: optionalNonEmptyString(item.successor_todo_id, "successor_todo_id"),
    };
  });
  const unresolved = new Set<string>();
  if (blocked && !terminal) {
    for (const declaration of declarations) {
      const candidates = [declaration.targetId, declaration.successorId].filter(
        (id): id is string => id !== null,
      );
      if (candidates.some((id) => runnable.has(id) || waiting.has(id))) continue;
      unresolved.add(declaration.targetId ?? declaration.successorId ?? declaration.declarationId);
    }
  }
  return {
    schema_version: FALLBACK_DISPOSITION_SCHEMA,
    disposition: unresolved.size > 0 ? "unresolved" : "resolved",
    unresolved_todo_ids: [...unresolved].sort(),
  };
}
