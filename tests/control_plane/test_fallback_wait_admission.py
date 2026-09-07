"""Declared alternate paths must survive local failure, wait, and replan writeback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loopx.cli import main as cli_main
from loopx.control_plane.goals.goal_vision import normalize_goal_vision_packet
from loopx.control_plane.scheduler.execution_context import (
    scheduler_execution_context_for_runtime_profile,
)
from loopx.control_plane.testing.quota_fixtures import quota_status_payload
from loopx.control_plane.todos.active_state_todo_parser import parse_active_state_todos
from loopx.control_plane.work_items.semantic_replan_writeback import (
    ReplanWritebackRejected,
    enforce_open_replan_writeback,
)
from loopx.quota import build_quota_should_run

GOAL = "fallback-wait-fixture"
AGENT = "worker"
COORDINATION = {"agent_model": "peer_v1", "registered_agents": [AGENT, "observer"]}
STATE = """# Active Goal State

## Agent Todo

- [ ] [P0] Observe recovery of source A.
  <!-- loopx:todo todo_id=todo_recovery status=open task_class=advancement_task claimed_by=observer -->
- [ ] [P0] Read source A after recovery.
  <!-- loopx:todo todo_id=todo_source_a status=deferred task_class=advancement_task claimed_by=worker resume_when=todo_done:todo_recovery -->
- [ ] [P2] Check source recovery on schedule.
  <!-- loopx:todo todo_id=todo_monitor status=open task_class=continuous_monitor claimed_by=worker cadence=1h next_due_at=2099-01-01T00:00:00+00:00 -->
"""


def vision_run(*, declared: bool = True) -> dict:
    vision = normalize_goal_vision_packet(
        {
            "state": "vision_drift_detected",
            "vision_patch": {
                "acceptance_summary": "Complete the bounded source check.",
                "replan_trigger_summary": "Source A is unavailable.",
            },
            "todo_delta": ["retain:todo_source_a"],
            "fallback_declarations": (
                [{"declaration_id": "source-b", "target_todo_id": "todo_source_b"}]
                if declared
                else []
            ),
        },
        goal_id=GOAL,
        agent_id=AGENT,
    )
    return {
        "classification": "source_path_checkpoint",
        "agent_id": AGENT,
        "generated_at": "2026-09-01T00:00:00+00:00",
        "agent_vision": vision,
    }


def decision(
    *,
    state: str = STATE,
    runs: list[dict] | None = None,
    profile: str = "outer_controller",
) -> dict:
    parsed = parse_active_state_todos(state, item_limit=None)
    payload = quota_status_payload(
        goal_id=GOAL,
        status="active",
        recommended_action="Wait for source A recovery.",
        agent_todos=parsed["agent_todos"],
        user_todos=parsed.get("user_todos"),
        coordination=COORDINATION,
        latest_runs=runs if runs is not None else [vision_run()],
    )
    return build_quota_should_run(
        payload,
        goal_id=GOAL,
        agent_id=AGENT,
        scheduler_execution_context=scheduler_execution_context_for_runtime_profile(
            profile
        ),
    )


def fallback_state(metadata: str) -> str:
    return (
        STATE
        + f"""
- [ ] [P1] Read authorized source B.
  <!-- loopx:todo todo_id=todo_source_b task_class=advancement_task {metadata} -->
"""
    )


@pytest.mark.parametrize(
    "profile", ["outer_controller", "ark_managed_agent_goal", "codex_app_heartbeat"]
)
def test_unhandled_fallback_cannot_become_host_defer(profile: str) -> None:
    result = decision(profile=profile)
    assert result["effective_action"] == "autonomous_replan_required"
    assert result["should_run"] is True
    assert result["execution_obligation"]["must_attempt_work"] is True
    assert (
        result["interaction_contract"]["agent_channel"]["quiet_noop_allowed"] is False
    )
    assert result["scheduler_hint"]["action"] == "run_now"
    if profile == "ark_managed_agent_goal":
        assert (
            result["scheduler_hint"]["goal_runtime_continuation"]["disposition"]
            == "continue_now"
        )


def test_real_fallback_runs_while_source_a_stays_deferred() -> None:
    state = fallback_state("status=open claimed_by=worker")
    result = decision(state=state)
    assert result["selected_todo"]["todo_id"] == "todo_source_b"
    assert result["execution_obligation"]["must_attempt_work"] is True
    assert "status=deferred" in state


@pytest.mark.parametrize(
    "declared", [False, True], ids=["no-authorized-alternative", "both-paths-waiting"]
)
def test_real_external_wait_is_preserved_without_replan_spin(declared: bool) -> None:
    state = (
        fallback_state(
            "status=deferred claimed_by=worker resume_when=todo_done:todo_recovery"
        )
        if declared
        else STATE
    )
    runs = [vision_run(declared=declared)]
    for _ in range(2):
        result = decision(state=state, runs=runs, profile="ark_managed_agent_goal")
        assert result["should_run"] is False
        assert result["execution_obligation"]["must_attempt_work"] is False
        assert (
            result["scheduler_hint"]["goal_runtime_continuation"]["disposition"]
            == "defer"
        )


@pytest.mark.parametrize(
    "metadata",
    [
        "status=open claimed_by=observer",
        "status=open claimed_by=worker excluded_agents=worker",
        "status=deferred claimed_by=worker",
    ],
)
def test_unselectable_or_unexplained_fallback_is_never_executed(metadata: str) -> None:
    result = decision(state=fallback_state(metadata))
    assert (result.get("selected_todo") or {}).get("todo_id") != "todo_source_b"
    assert result["effective_action"] == "autonomous_replan_required"


def test_repeated_reads_keep_one_obligation_and_generic_ack_cannot_hide_gap() -> None:
    run = vision_run()
    first = decision(runs=[run])["autonomous_replan_obligation"]
    assert (
        decision(runs=[run])["autonomous_replan_obligation"]["obligation_id"]
        == first["obligation_id"]
    )
    ack = {
        "classification": "state_refreshed",
        "agent_id": AGENT,
        "generated_at": "2026-09-01T00:01:00+00:00",
        "autonomous_replan_ack": {
            "schema_version": "autonomous_replan_ack_v0",
            "recorded": True,
            "semantic_delta": {
                "schema_version": "replan_semantic_delta_v0",
                "accepted": True,
                "outcomes": ["new_concrete_blocker"],
                "satisfying_outcomes": ["new_concrete_blocker"],
                "obligation_id": first["obligation_id"],
            },
        },
    }
    later = decision(runs=[ack, run])
    assert later["effective_action"] == "autonomous_replan_required"
    assert (
        later["autonomous_replan_obligation"]["obligation_id"] == first["obligation_id"]
    )


@pytest.mark.parametrize("new_vision", [False, True])
def test_new_blocker_cannot_settle_an_unresolved_declared_fallback(
    new_vision: bool,
) -> None:
    run = vision_run()
    with pytest.raises(ReplanWritebackRejected) as error:
        enforce_open_replan_writeback(
            newest_first_runs=[run],
            state_text=STATE,
            agent_id=AGENT,
            goal_id=GOAL,
            registry_goal={"coordination": COORDINATION},
            agent_vision=run["agent_vision"] if new_vision else None,
            progress_observation={
                "result_class": "blocked",
                "blocker_id": "source-a-unavailable",
                "evidence_ids": ["source-a-failure"],
            },
        )
    assert error.value.semantic_delta["reason_code"] == "declared_fallback_unresolved"


@pytest.mark.parametrize(
    "metadata",
    [
        "status=open claimed_by=worker",
        "status=deferred claimed_by=worker resume_when=todo_done:todo_recovery",
    ],
)
def test_materialized_fallback_clears_the_writeback_obligation(metadata: str) -> None:
    assert (
        enforce_open_replan_writeback(
            newest_first_runs=[vision_run()],
            state_text=fallback_state(metadata),
            agent_id=AGENT,
            goal_id=GOAL,
            registry_goal={"coordination": COORDINATION},
        )
        is None
    )


def test_cli_reads_real_state_and_history_before_admitting_wait(
    tmp_path: Path, capsys
) -> None:
    state_file = tmp_path / "ACTIVE_GOAL_STATE.md"
    state_file.write_text(STATE)
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "goals": [
                    {
                        "id": GOAL,
                        "status": "active",
                        "domain": "engineering",
                        "waiting_on": "codex",
                        "state_file": str(state_file),
                        "repo": str(tmp_path),
                        "adapter": {
                            "kind": "fixture_connected_delivery_v0",
                            "status": "connected-delivery",
                        },
                        "quota": {
                            "compute": 1.0,
                            "window_hours": 24,
                            "slot_minutes": 1,
                        },
                        "coordination": COORDINATION,
                    }
                ]
            }
        )
    )
    runtime = tmp_path / "runtime"
    runs = runtime / "goals" / GOAL / "runs"
    runs.mkdir(parents=True)
    run = vision_run()
    json_path = runs / "source-checkpoint.json"
    markdown_path = runs / "source-checkpoint.md"
    json_path.write_text(json.dumps(run) + "\n")
    markdown_path.write_text("# Source checkpoint\n")
    (runs / "index.jsonl").write_text(
        json.dumps(
            {
                **run,
                "json_path": str(json_path),
                "markdown_path": str(markdown_path),
            }
        )
        + "\n"
    )
    args = [
        "--format",
        "json",
        "--registry",
        str(registry),
        "--runtime-root",
        str(runtime),
        "quota",
        "should-run",
        "--verbose",
        "--goal-id",
        GOAL,
        "--agent-id",
        AGENT,
        "--runtime-profile",
        "ark_managed_agent_goal",
    ]
    result = cli_main(args)
    output = json.loads(capsys.readouterr().out)
    assert result == 0, {
        key: output.get(key)
        for key in (
            "status",
            "reason",
            "status_health_ok",
            "recommended_action",
            "contract",
        )
    }
    assert output["effective_action"] == "autonomous_replan_required"
    assert (
        output["scheduler_hint"]["goal_runtime_continuation"]["disposition"]
        == "continue_now"
    )

    state_file.write_text(fallback_state("status=open claimed_by=worker"))
    assert cli_main(args) == 0
    continued = json.loads(capsys.readouterr().out)
    assert continued["selected_todo"]["todo_id"] == "todo_source_b"
    assert continued["execution_obligation"]["must_attempt_work"] is True

    state_file.write_text(
        fallback_state(
            "status=deferred claimed_by=worker resume_when=todo_done:todo_recovery"
        )
    )
    assert cli_main(args) == 0
    waiting = json.loads(capsys.readouterr().out)
    assert waiting["execution_obligation"]["must_attempt_work"] is False
    assert (
        waiting["scheduler_hint"]["goal_runtime_continuation"]["disposition"] == "defer"
    )
