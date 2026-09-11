from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ...todos.contract import (
    TODO_STATUS_DEFERRED,
    TODO_STATUS_OPEN,
    TODO_TASK_CLASS_ADVANCEMENT,
    TODO_TASK_CLASS_MONITOR,
    normalize_todo_id,
    normalize_todo_resume_when,
    normalize_todo_status,
)
from ...todos.resume_planning import project_todo_resume_planning
from ...todos.projection import (
    agent_scoped_selectable_advancement_todo_ids,
    todo_item_claimed_by_agent_or_unclaimed,
    todo_item_is_actionable_open,
    todo_item_task_class,
)
from ...todos.resume_condition import evaluate_todo_resume_conditions
from ..goal_vision_read_model import (
    VISION_FRONTIER_TODO_DELTA_ACTIONS as VISION_FRONTIER_TODO_DELTA_ACTIONS,
    VISION_TODO_DELTA_ID_LIMIT as VISION_TODO_DELTA_ID_LIMIT,
    parse_vision_todo_delta_entries as parse_vision_todo_delta_entries,
)
from ..goal_vision_state import goal_vision_state_is_closed

# create/reopen entries are bounded successor declarations and resolve the
# fallback disposition on their own; activate/resume/retain entries only link
# the vision to existing Todos and still need a selectable frontier match.
VISION_TODO_DELTA_SUCCESSOR_ACTIONS = frozenset({"create", "reopen"})
VISION_TODO_DELTA_LINKAGE_ACTIONS = frozenset(
    VISION_FRONTIER_TODO_DELTA_ACTIONS - VISION_TODO_DELTA_SUCCESSOR_ACTIONS
)
VISION_FALLBACK_DECLARATION_ENTRY_LIMIT = 4
VISION_FALLBACK_DECLARATION_FIELDS = ("target_todo_id", "successor_todo_id")
VISION_FALLBACK_GAP_TRIGGER = "vision_fallback_unresolved"
VISION_FALLBACK_GAP_REASON_CODE = "declared_fallback_without_runnable_or_terminal"
VISION_FALLBACK_LOOKUP_UNCERTAIN_TRIGGER = "vision_fallback_lookup_uncertain"
VISION_FALLBACK_LOOKUP_UNCERTAIN_REASON_CODE = (
    "declared_fallback_authoritative_lookup_unavailable"
)
VISION_FALLBACK_TERMINAL_PATH_OUTCOME = "stop"
VISION_FALLBACK_RUNNABLE_ITEM_LIMIT = 3
VISION_FALLBACK_RECOMMENDED_ACTION = (
    "resolve the declared fallback direction: link or retain a runnable "
    "successor Todo referencing it, declare a bounded create/reopen "
    "successor, or record an explicit terminal no-follow-up disposition; "
    "do not invent a user gate"
)
VISION_FALLBACK_LOOKUP_UNCERTAIN_ACTION = (
    "retry the fallback disposition from the complete canonical Todo source; "
    "do not infer absence from a bounded presentation lane or invent a user gate"
)


class FallbackTodoReadState(Enum):
    UNAVAILABLE = "unavailable"


# None is an omitted source from a legacy caller; UNAVAILABLE is a failed
# authority read, which compact display evidence must not override.
FallbackTodoSource = list[dict[str, Any]] | FallbackTodoReadState | None


@dataclass(frozen=True)
class FallbackDeclaration:
    """Structured declaration of a fallback direction and its associated work."""

    declaration_id: str
    target_todo_id: str | None = None
    successor_todo_id: str | None = None

    @property
    def candidate_todo_ids(self) -> set[str]:
        return {
            todo_id
            for todo_id in (
                self.target_todo_id,
                self.successor_todo_id,
            )
            if todo_id
        }

    @property
    def unresolved_todo_id(self) -> str:
        return self.target_todo_id or self.successor_todo_id or self.declaration_id


def _compact_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def parse_fallback_declarations(
    agent_vision: dict[str, Any] | None,
) -> list[FallbackDeclaration]:
    """Parse typed fallback declarations written by the TS Vision contract.

    The only supported authoring path is ``agent_vision.fallback_declarations``
    as validated and persisted by the TS-owned ``goal.vision_checkpoint``
    prepare (and mirrored through the status/shared-runtime compact read
    model). Prose mentions, generic ``todo_delta`` actions, and legacy alias
    shapes are not declarations.
    """

    declarations: list[FallbackDeclaration] = []
    if not isinstance(agent_vision, dict):
        return declarations
    source = agent_vision.get("fallback_declarations")
    if not isinstance(source, list):
        return declarations

    seen: set[tuple[str, str | None, str | None]] = set()
    for raw in source[:VISION_FALLBACK_DECLARATION_ENTRY_LIMIT]:
        if not isinstance(raw, dict):
            continue
        declaration_id = _compact_text(
            raw.get("declaration_id"),
            limit=VISION_TODO_DELTA_ID_LIMIT,
        )
        if not declaration_id:
            continue
        target_todo_id = normalize_todo_id(raw.get("target_todo_id"))
        successor_todo_id = normalize_todo_id(raw.get("successor_todo_id"))
        key = (declaration_id, target_todo_id, successor_todo_id)
        if key in seen:
            continue
        seen.add(key)
        declarations.append(
            FallbackDeclaration(
                declaration_id=declaration_id,
                target_todo_id=target_todo_id,
                successor_todo_id=successor_todo_id,
            )
        )
    return declarations


def _blocked_successor_todo_ids(
    agent_todo_summary: dict[str, Any] | None,
    *,
    agent_id: str | None,
) -> set[str]:
    """Ids the blocked-successor wait state itself is waiting on."""

    if not isinstance(agent_todo_summary, dict):
        return set()
    return {
        todo_id
        for todo_id in (
            normalize_todo_id(item.get("todo_id"))
            for item in project_todo_resume_planning(
                agent_todo_summary,
                agent_id=agent_id,
            )["blocked_successor_items"]
            if isinstance(item, dict)
        )
        if todo_id
    }


def _blocked_primary_waiting(
    agent_todo_summary: dict[str, Any] | None,
    *,
    agent_id: str | None,
) -> bool:
    """Reuse the blocked-successor wait scope as the primary-blocked signal."""

    if not isinstance(agent_todo_summary, dict):
        return False
    blocker_items = agent_todo_summary.get("current_agent_blocker_items")
    if isinstance(blocker_items, list) and blocker_items:
        return True
    return bool(
        project_todo_resume_planning(
            agent_todo_summary,
            agent_id=agent_id,
        )["blocked_successor_items"]
    )


def _vision_has_terminal_disposition(agent_vision: dict[str, Any]) -> bool:
    """Terminal evidence: closed-family state or path_delta.outcome=stop."""

    if goal_vision_state_is_closed(agent_vision.get("state")):
        return True
    path_delta = agent_vision.get("path_delta")
    path_delta = path_delta if isinstance(path_delta, dict) else {}
    return (
        str(path_delta.get("outcome") or "").strip().lower()
        == VISION_FALLBACK_TERMINAL_PATH_OUTCOME
    )


def _authoritative_fallback_disposition_ids(
    declarations: list[FallbackDeclaration],
    *,
    agent_todo_source_items: list[dict[str, Any]],
    agent_id: str | None,
    rollout_events: list[dict[str, Any]] | None,
    available_capabilities: Any,
) -> tuple[set[str], set[str], set[str]]:
    """Return exact declared Todo ids that are runnable or validly waiting.

    The planning source is complete canonical state, not a presentation lane.
    Existing Todo predicates retain ownership, exclusion, task-class, and
    lifecycle semantics; the TS resume evaluator remains the authority for a
    linked external wait.
    """

    declared_ids = {
        todo_id
        for declaration in declarations
        for todo_id in declaration.candidate_todo_ids
    }
    matched_items = [
        item
        for item in agent_todo_source_items
        if isinstance(item, dict)
        and normalize_todo_id(item.get("todo_id")) in declared_ids
    ]
    resume_items = [
        item
        for item in matched_items
        if normalize_todo_resume_when(item.get("resume_when"))
    ]
    resume_conditions = (
        evaluate_todo_resume_conditions(
            resume_items,
            source_items=agent_todo_source_items,
            rollout_events=rollout_events,
            available_capabilities=available_capabilities,
        )
        if resume_items
        else {}
    )
    evaluated_source_items: list[dict[str, Any]] = []
    for source_item in agent_todo_source_items:
        evaluated_item = dict(source_item)
        source_todo_id = normalize_todo_id(source_item.get("todo_id"))
        condition = resume_conditions.get(source_todo_id or "")
        if isinstance(condition, dict):
            evaluated_item["resume_condition"] = condition
            evaluated_item["resume_ready"] = condition.get("satisfied") is True
        evaluated_source_items.append(evaluated_item)
    ordinary_waiting_ids = {
        todo_id
        for todo_id in (
            normalize_todo_id(item.get("todo_id"))
            for item in project_todo_resume_planning(
                {"items": evaluated_source_items},
                agent_id=agent_id,
            )["blocked_successor_items"]
            if isinstance(item, dict)
        )
        if todo_id
    }

    runnable_ids: set[str] = set()
    waiting_ids: set[str] = set()
    uncertain_ids: set[str] = set()
    for item in matched_items:
        todo_id = normalize_todo_id(item.get("todo_id"))
        if not todo_id:
            continue
        if todo_item_task_class(item) != TODO_TASK_CLASS_ADVANCEMENT:
            continue
        if not todo_item_claimed_by_agent_or_unclaimed(item, agent_id=agent_id):
            continue

        resume_when = normalize_todo_resume_when(item.get("resume_when"))
        if resume_when:
            status = normalize_todo_status(item.get("status")) or TODO_STATUS_OPEN
            if status not in {TODO_STATUS_OPEN, TODO_STATUS_DEFERRED}:
                continue
            condition = resume_conditions.get(todo_id)
            if not isinstance(condition, dict):
                uncertain_ids.add(todo_id)
                continue
            if condition.get("invalid_target") is True or condition.get(
                "invalid_state"
            ):
                continue
            if condition.get("provider_required") is True:
                # Capability evidence was unavailable, so this lookup is
                # uncertain rather than proof that the fallback is absent.
                uncertain_ids.add(todo_id)
                continue
            if condition.get("satisfied") is True:
                runnable_ids.add(todo_id)
            elif condition.get("satisfied") is False:
                if condition.get("kind") == "monitor_changed":
                    # An unchanged generation is a durable wait only while
                    # its continuous-monitor target remains open.  A terminal
                    # monitor cannot produce another generation, so accepting
                    # that condition as pending would hide the fallback gap
                    # forever.  A changed generation is handled above and
                    # remains runnable even if the monitor closed concurrently.
                    target_status = normalize_todo_status(
                        condition.get("target_status")
                    )
                    if (
                        target_status == TODO_STATUS_OPEN
                        and condition.get("target_task_class")
                        == TODO_TASK_CLASS_MONITOR
                    ):
                        waiting_ids.add(todo_id)
                elif todo_id in ordinary_waiting_ids:
                    waiting_ids.add(todo_id)
            continue

        if todo_item_is_actionable_open(item):
            runnable_ids.add(todo_id)

    return runnable_ids, waiting_ids, uncertain_ids


def declared_fallback_gap_from_agent_vision(
    agent_vision: dict[str, Any] | None,
    *,
    agent_todo_summary: dict[str, Any] | None,
    agent_id: str | None,
    agent_todo_source_items: FallbackTodoSource = None,
    rollout_events: list[dict[str, Any]] | None = None,
    available_capabilities: Any = None,
) -> dict[str, Any] | None:
    """Project one advisory gap for an unresolved declared fallback.

    A fallback direction is declared structurally via the agent vision's
    typed ``fallback_declarations`` contract, which the TS-owned Vision
    prepare validates and persists. Prose mentions never declare a
    fallback, and generic ``todo_delta`` actions are not fallback
    declarations on their own.

    The declared direction is resolved when one of:
    1. A linked Todo sits on the authoritative agent-scoped selectable
       advancement frontier (peer-claimed primary-path Todos do not);
    2. A bounded successor Todo is created or reopened specifically for
       this fallback direction; or
    3. The vision records an explicit terminal disposition (closed-family state
       or path_delta.outcome=stop).

    When the primary path is blocked and none of the resolutions holds, the
    declared fallback would otherwise disappear silently behind the
    blocked-successor wait state, which clears the ordinary acceptance gaps.
    This advisory gap stays in the independent ``fallback_gaps`` projection
    field and never enters the acceptance-gap replan stream.
    """

    if not isinstance(agent_vision, dict):
        return None
    if _vision_has_terminal_disposition(agent_vision):
        return None
    if not _blocked_primary_waiting(
        agent_todo_summary,
        agent_id=agent_id,
    ):
        return None

    declarations = parse_fallback_declarations(agent_vision)
    if not declarations:
        return None

    source_is_authoritative = isinstance(agent_todo_source_items, list)
    uncertain_todo_ids: set[str] = set()
    if isinstance(agent_todo_source_items, list):
        (
            selectable_ids,
            waiting_todo_ids,
            uncertain_todo_ids,
        ) = _authoritative_fallback_disposition_ids(
            declarations,
            agent_todo_source_items=agent_todo_source_items or [],
            agent_id=agent_id,
            rollout_events=rollout_events,
            available_capabilities=available_capabilities,
        )
    elif agent_todo_source_items is FallbackTodoReadState.UNAVAILABLE:
        selectable_ids = set()
        waiting_todo_ids = set()
    else:
        # Legacy direct callers may only have a compact display summary. It
        # remains valid positive evidence, but omission from a bounded lane is
        # uncertainty and must not be projected as authoritative absence.
        selectable_ids = agent_scoped_selectable_advancement_todo_ids(
            agent_todo_summary,
            agent_id=agent_id,
        )
        waiting_todo_ids = _blocked_successor_todo_ids(
            agent_todo_summary,
            agent_id=agent_id,
        )
    todo_delta = parse_vision_todo_delta_entries(agent_vision.get("todo_delta"))
    created_or_reopened_ids = {
        todo_id
        for action, todo_id in todo_delta
        if action in VISION_TODO_DELTA_SUCCESSOR_ACTIONS
    }

    unresolved_ids: set[str] = set()
    lookup_uncertain_ids: set[str] = set(uncertain_todo_ids)
    for declaration in declarations:
        candidate_ids = declaration.candidate_todo_ids - waiting_todo_ids
        if not candidate_ids:
            if not declaration.candidate_todo_ids:
                unresolved_ids.add(declaration.unresolved_todo_id)
            continue
        # Disposition 1: Runnable on authoritative selectable advancement frontier
        if candidate_ids & selectable_ids:
            continue
        # Disposition 2: Bounded successor created/reopened specifically for this fallback
        if candidate_ids & created_or_reopened_ids:
            continue
        if candidate_ids & lookup_uncertain_ids:
            continue
        if (
            declaration.successor_todo_id
            and declaration.successor_todo_id in created_or_reopened_ids
        ):
            continue
        if not source_is_authoritative:
            lookup_uncertain_ids.update(candidate_ids)
            continue

        unresolved_id = declaration.unresolved_todo_id
        if unresolved_id not in waiting_todo_ids:
            unresolved_ids.add(unresolved_id)

    if not unresolved_ids and not lookup_uncertain_ids:
        return None

    lookup_uncertain_only = not unresolved_ids

    gap: dict[str, Any] = {
        "kind": (
            VISION_FALLBACK_LOOKUP_UNCERTAIN_TRIGGER
            if lookup_uncertain_only
            else VISION_FALLBACK_GAP_TRIGGER
        ),
        "source": "latest_agent_vision",
        "agent_id": agent_vision.get("agent_id"),
        "state": agent_vision.get("state"),
        "reason_code": (
            VISION_FALLBACK_LOOKUP_UNCERTAIN_REASON_CODE
            if lookup_uncertain_only
            else VISION_FALLBACK_GAP_REASON_CODE
        ),
        "recommended_action": (
            VISION_FALLBACK_LOOKUP_UNCERTAIN_ACTION
            if lookup_uncertain_only
            else VISION_FALLBACK_RECOMMENDED_ACTION
        ),
    }
    unresolved_todo_ids = [todo_id for todo_id in sorted(unresolved_ids) if todo_id][
        :VISION_FALLBACK_RUNNABLE_ITEM_LIMIT
    ]
    if unresolved_todo_ids:
        gap["unresolved_todo_ids"] = unresolved_todo_ids
    uncertain_todo_ids = [
        todo_id for todo_id in sorted(lookup_uncertain_ids) if todo_id
    ][:VISION_FALLBACK_RUNNABLE_ITEM_LIMIT]
    if uncertain_todo_ids:
        gap["lookup_uncertain_todo_ids"] = uncertain_todo_ids
    generated_at = _compact_text(agent_vision.get("generated_at"), limit=80)
    if generated_at:
        gap["generated_at"] = generated_at
    return {key: value for key, value in gap.items() if value is not None}
