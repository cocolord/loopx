"""One source snapshot, bounded transport, no fallback-specific state authority."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ....history import load_registry
from ....state_refresh import resolve_goal_state
from ...coordination.local_authority import (
    LocalCoordinationAuthorityUnavailable,
    read_canonical_todos_if_promoted,
)
from ...effect_runtime import EffectRuntimeRemoteError
from ...todos.active_state_todo_parser import parse_todo_source
from ...todos.contract import normalize_todo_id, normalize_todo_resume_when
from .fallback_disposition import (
    FallbackTodoReadState, FallbackTodoSource, parse_fallback_declarations,
)
from .semantic_history import latest_agent_vision_from_status_payload


def read_fallback_source_snapshot(
    *, registry_path: Path, runtime_root: Path, goal_id: str,
) -> list[dict[str, Any]]:
    canonical = read_canonical_todos_if_promoted(runtime_root=runtime_root, goal_id=goal_id)
    if canonical is not None:
        # Failure after promotion must not consult the Markdown projection.
        return canonical["todos"]
    goal, _, state_file = resolve_goal_state(
        registry=load_registry(registry_path), goal_id=goal_id,
        project_override=None, state_file_override=None,
    )
    if goal is None:
        raise ValueError("fallback source goal is absent")
    groups, archived, _ = parse_todo_source(state_file.read_text(encoding="utf-8"))
    return [*groups["user"], *groups["agent"], *archived]


def live_fallback_authority_items(
    status_payload: dict[str, Any], *, registry_path: Path, runtime_root: Path,
    goal_id: str, agent_id: str | None,
) -> FallbackTodoSource:
    vision = latest_agent_vision_from_status_payload(
        status_payload, goal_id=goal_id, agent_id=agent_id,
    )
    requested = {
        todo_id for declaration in parse_fallback_declarations(vision)
        for todo_id in declaration.candidate_todo_ids
    }
    if not requested:
        return None
    try:
        source = read_fallback_source_snapshot(
            registry_path=registry_path, runtime_root=runtime_root, goal_id=goal_id,
        )
    except (EffectRuntimeRemoteError, LocalCoordinationAuthorityUnavailable, OSError, ValueError):
        return FallbackTodoReadState.UNAVAILABLE
    if not isinstance(source, list) or any(not isinstance(item, dict) for item in source):
        return FallbackTodoReadState.UNAVAILABLE
    by_id: dict[str, list[dict[str, Any]]] = {}
    for item in source:
        todo_id = normalize_todo_id(item.get("todo_id"))
        if todo_id:
            by_id.setdefault(todo_id, []).append(item)
    selected = set(requested)
    for todo_id in requested:
        for item in by_id.get(todo_id, []):
            resume = normalize_todo_resume_when(item.get("resume_when"))
            kind, _, target = (resume or "").partition(":")
            if kind in {"todo_done", "monitor_changed"}:
                dependency = normalize_todo_id(target)
                if dependency:
                    selected.add(dependency)
    # Four declarations name at most eight alternatives and eight direct
    # dependencies. Do not follow dependency chains or re-read another revision.
    if any(len(by_id.get(todo_id, [])) > 1 for todo_id in selected):
        return FallbackTodoReadState.UNAVAILABLE
    return [by_id[todo_id][0] for todo_id in sorted(selected) if todo_id in by_id]
