#!/usr/bin/env python3
"""Smoke-test the Codex sub-agent shared-control-plane contract."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "docs" / "integrations" / "codex-subagent-orchestration.md"
TOPOLOGY_RFC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "rfcs"
    / "generic-multi-agent-execution-topology-v0.md"
)
DRIFT_FIXTURE = (
    REPO_ROOT
    / "examples"
    / "fixtures"
    / "multi-agent-execution-topology-drift.public.json"
)

REQUIRED_PHRASES = (
    "shared control plane",
    "subagent_control_plane_handoff_v0",
    "`parent_goal_id`",
    "`authority_artifact`",
    "`latest_state_ref`",
    "`quota_gate_snapshot`",
    "`evidence_boundary`",
    "`writeback_spend_contract`",
    "`child_decision`",
    "`continue`, `wait`, or `reuse_existing_evidence`",
    "temporary task coordinator",
    "child worker reports evidence only; task coordinator writes accepted state and spends",
    "control_plane_handoff_version",
    "It does not own durable goal authority",
    "one pending lease for `(goal_id, todo_id)`",
    "`goal_id` is the shared control-plane lane",
    "`todo_id` is the work item being claimed",
    '"agent_model": "peer_v1"',
    "independent worktrees",
    "subagents that parallelize multiple Todos inside one registered agent lane",
    "does not describe orchestration among multiple registered LoopX agents",
    "Multiple registered LoopX agents remain equal peers",
    "Subagent cards or host workers must never be reclassified as peer agents",
    "Review remains `action_kind=review`",
    "Dormant registered agents and closed, blocked, or deferred todos are not coordinator candidates.",
    "multi_agent_execution_topology_v0",
    "multi_agent_host_execution_receipt_v0",
    "multi_agent_control_plane_reconciliation_v0",
    "worktree proves filesystem isolation",
    "Do not spawn without a current admitted child lane",
)

TOPOLOGY_REQUIRED_PHRASES = (
    "Status: Draft",
    "`serial`",
    "`ephemeral_children`",
    "`task_orchestration_contract_v2`",
    "`task_orchestration_contract_v1`",
    "`multi_agent_execution_topology_v0`",
    "`multi_agent_host_execution_receipt_v0`",
    "`multi_agent_control_plane_reconciliation_v0`",
    "`unadmitted_child_spawn`",
    "`aggregate_todo_not_decomposed`",
    "`child_capacity_exceeded`",
    "`side_effect_boundary_exceeded`",
    "`aggregate_settlement_without_lane_evidence`",
    "`loopx/control_plane/turn_driver/` host observation code",
    "`control_plane/turn_driver/child_execution_topology.py`",
    "`demo/multi_agent/` package is a source-checkout",
    "No runtime behavior changes in this slice.",
    "a research-specific coordinator or worker protocol",
    "This contract does not coordinate",
    "multiple registered LoopX agents",
    "The correction is not to call the children LoopX agents",
)

FORBIDDEN_PHRASES = (
    "PRIVATE_HOME/",
    "lark" + "office.com",
    "~/.codex/sessions",
    "raw_thread",
    "session_history",
    "coordination.primary_agent",
    "primary-agent review todo",
    "side agents",
    "main controller",
    '"role": "controller"',
    '"role": "subagent"',
    "controller owns",
    "parent writes and spends",
    "/Users/",
)


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    topology = TOPOLOGY_RFC.read_text(encoding="utf-8")
    drift_fixture = json.loads(DRIFT_FIXTURE.read_text(encoding="utf-8"))
    compact = " ".join(text.split())
    for phrase in REQUIRED_PHRASES:
        assert phrase in compact, phrase
    for phrase in TOPOLOGY_REQUIRED_PHRASES:
        assert phrase in topology, phrase
    for source in (text, topology):
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in source, phrase
    assert text.count("subagent_control_plane_handoff_v0") >= 2, text
    assert text.count("## ") >= 7, text
    planned = drift_fixture["planned_control_plane"]
    observed = drift_fixture["observed_host_execution"]
    expected = drift_fixture["expected_reconciliation"]
    orchestration = drift_fixture["goal"]["orchestration"]
    assert orchestration["spawn_allowed"] is False
    assert planned["task_orchestration_contract"] is None
    assert planned["admitted_lane_count"] == 0
    assert planned["materialized_child_todo_count"] == 0
    assert observed["worker_count"] == len(observed["workers"]) == 4
    assert observed["worker_count"] > orchestration["max_children"]
    assert all(worker["receipt_present"] is False for worker in observed["workers"])
    observed_effects = {
        effect
        for worker in observed["workers"]
        for effect in worker["observed_effect_classes"]
    }
    requested_effects = {
        effect
        for worker in observed["workers"]
        for effect in worker["requested_effect_classes"]
    }
    allowed_effects = set(orchestration["allowed_effect_classes"])
    assert requested_effects == observed_effects
    assert observed_effects - allowed_effects == {
        "remote_branch_write",
        "remote_pull_request_write",
    }
    assert expected["status"] == "drifted"
    assert expected["required_topology"] == "ephemeral_children"
    assert set(expected["reason_codes"]) == {
        "unadmitted_child_spawn",
        "aggregate_todo_not_decomposed",
        "child_capacity_exceeded",
        "missing_todo_lineage",
        "side_effect_boundary_exceeded",
        "worker_receipt_missing",
        "aggregate_settlement_without_lane_evidence",
    }
    negative_cases = {
        case["case_id"]: case
        for case in drift_fixture["otherwise_aligned_negative_cases"]
    }
    assert set(negative_cases) == {
        "child_capacity_exceeded_only",
        "side_effect_boundary_exceeded_only",
    }
    for case in negative_cases.values():
        assert case["all_lanes_admitted"] is True
        assert case["all_todo_lineage_current"] is True
        assert case["all_workspaces_match"] is True
        assert case["all_receipts_terminal"] is True
    capacity_case = negative_cases["child_capacity_exceeded_only"]
    assert (
        capacity_case["observed_worker_count"]
        == capacity_case["planned_lane_count"]
        > capacity_case["execution_envelope"]["max_children"]
    )
    assert set(capacity_case["observed_effect_classes"]) <= set(
        capacity_case["execution_envelope"]["allowed_effect_classes"]
    )
    assert (
        capacity_case["requested_effect_classes"]
        == capacity_case["observed_effect_classes"]
    )
    assert capacity_case["expected_reason_codes"] == ["child_capacity_exceeded"]
    effect_case = negative_cases["side_effect_boundary_exceeded_only"]
    assert (
        effect_case["observed_worker_count"]
        == effect_case["planned_lane_count"]
        <= effect_case["execution_envelope"]["max_children"]
    )
    assert set(effect_case["observed_effect_classes"]) - set(
        effect_case["execution_envelope"]["allowed_effect_classes"]
    ) == {"remote_branch_write"}
    assert (
        effect_case["requested_effect_classes"]
        == effect_case["observed_effect_classes"]
    )
    assert effect_case["expected_reason_codes"] == ["side_effect_boundary_exceeded"]
    assert all(value is False for value in drift_fixture["boundary"].values())
    print("codex-subagent-orchestration-contract-smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
