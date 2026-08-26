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
    "`durable_peer_sessions`",
    "`hybrid`",
    "`task_orchestration_contract_v2`",
    "`task_orchestration_contract_v1`",
    "`multi_agent_execution_topology_v0`",
    "`multi_agent_host_execution_receipt_v0`",
    "`multi_agent_control_plane_reconciliation_v0`",
    "`unadmitted_child_spawn`",
    "`aggregate_todo_not_decomposed`",
    "`durable_session_unbound`",
    "`side_effect_boundary_exceeded`",
    "`aggregate_settlement_without_lane_evidence`",
    "No runtime behavior changes in this slice.",
    "a research-specific coordinator or worker protocol",
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
    assert drift_fixture["goal"]["orchestration"]["spawn_allowed"] is False
    assert planned["task_orchestration_contract"] is None
    assert planned["admitted_lane_count"] == 0
    assert observed["worker_count"] == len(observed["workers"]) == 4
    assert all(worker["receipt_present"] is False for worker in observed["workers"])
    assert any(
        "remote_pull_request_write" in worker["permitted_effect_classes"]
        for worker in observed["workers"]
    )
    assert expected["status"] == "drifted"
    assert expected["required_topology"] == "durable_peer_sessions"
    assert set(expected["reason_codes"]) == {
        "unadmitted_child_spawn",
        "aggregate_todo_not_decomposed",
        "missing_todo_lineage",
        "durable_session_unbound",
        "worker_receipt_missing",
        "aggregate_settlement_without_lane_evidence",
    }
    assert all(value is False for value in drift_fixture["boundary"].values())
    print("codex-subagent-orchestration-contract-smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
