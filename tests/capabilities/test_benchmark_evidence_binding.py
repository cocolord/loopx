"""Runner integration with synthetic observations and real CLI/filesystem IO.

No model, benchmark task, container, or verifier is launched. The fake solver
emits synthetic TraeX events; containment and isolation observations are fixture
inputs, not claims that this test establishes a real isolation boundary.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from loopx.capabilities.benchmark_toolkit import (
    BENCHMARK_RUNTIME_INTEGRITY_ATTESTATION_SCHEMA_VERSION,
    REQUIRED_RUNTIME_ATTESTATIONS,
    BenchmarkEvidenceLaunch,
    build_benchmark_evidence_binding,
    build_benchmark_integrity_qualification,
    build_bound_benchmark_integrity_qualification,
    prepare_benchmark_evidence_launch,
)
from loopx.capabilities.benchmark_toolkit.external_agent import (
    execute_external_agent_request,
)
from loopx.cli import main
from loopx.registry import atomic_write_json


@pytest.fixture
def run_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request = {
        "schema_version": "external_agent_request_v1",
        "instruction": "synthetic private instruction",
        "workspace": str(workspace),
        "timeout_seconds": 10,
        "containment": {
            "schema_version": "external_agent_containment_v1",
            "kind": "container",
            "timeout_owner": "runner",
            "termination_postcondition": "drained_before_result_consumption",
            "verification": {
                "schema_version": "external_agent_containment_verification_v1",
                "authority": "runner",
                "status": "verified",
                "receipt_ref": "synthetic-run-a",
            },
        },
    }
    launch = prepare_benchmark_evidence_launch(
        request, expected_model="model-a", expected_provider="trae"
    )
    # The runner persists the independent pin before any execution or artifact.
    pin_path = tmp_path / "launch.sha256"
    pin_path.write_text(launch.sha256, encoding="utf-8")
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    atomic_write_json(request_path, request)
    program = """
import json, sys
from pathlib import Path
instruction = sys.stdin.read()
events = [
    {"type": "item.completed", "item": {
        "type": "agent_message", "text": instruction}},
    {"type": "event_msg", "payload": {"type": "token_count", "context": {
        "model": "model-a", "modelProviderId": "trae"}}},
]
Path("events.jsonl").write_text(
    "\\n".join(json.dumps(event) for event in events), encoding="utf-8")
"""
    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command=[sys.executable, "-c", program],
        execute=True,
    )
    assert result["status"] == "succeeded"
    # Exercise the existing, unbound TraeX CLI on the native filesystem. This
    # test is also selected by the native Windows job.
    assert (
        main(
            [
                "benchmark",
                "traex-evidence",
                "--source-jsonl",
                str(workspace / "events.jsonl"),
                "--atif-output",
                str(tmp_path / "atif.json"),
                "--route-receipt-output",
                str(tmp_path / "route.json"),
                "--requested-model",
                "model-a",
                "--execute",
                "--format",
                "json",
            ]
        )
        == 0
    )
    capture = json.loads(capsys.readouterr().out)
    assert capture["private_atif_written"] and capture["route_receipt_written"]
    attestation = {
        "schema_version": BENCHMARK_RUNTIME_INTEGRITY_ATTESTATION_SCHEMA_VERSION,
        "authority": "runner",
        "benchmark_id": "synthetic",
        "case_id": "case-a",
        **{field: True for field in REQUIRED_RUNTIME_ATTESTATIONS},
    }
    atomic_write_json(tmp_path / "attestation.json", attestation)
    artifacts = {
        "external_agent_result": json.loads(result_path.read_text(encoding="utf-8")),
        "trajectory": json.loads((tmp_path / "atif.json").read_text(encoding="utf-8")),
        "runtime_attestation": attestation,
        "route_receipt": json.loads(
            (tmp_path / "route.json").read_text(encoding="utf-8")
        ),
    }
    cleanup_sha256 = hashlib.sha256(b"synthetic runner cleanup observation").hexdigest()
    binding = build_benchmark_evidence_binding(
        launch=launch,
        **artifacts,
        containment_drained=True,
        containment_evidence_sha256=cleanup_sha256,
    )
    # A single final seal is published only after both artifact files exist.
    atomic_write_json(tmp_path / "binding.json", binding)
    return dict(
        artifacts=artifacts,
        binding=binding,
        launch=launch,
        request=request,
        expected_launch_sha256=pin_path.read_text(encoding="utf-8"),
        cleanup_sha256=cleanup_sha256,
        root=tmp_path,
    )


def _qualify(evidence, **overrides):
    arguments = {
        **evidence["artifacts"],
        "evidence_binding": evidence["binding"],
        "expected_launch_sha256": evidence["expected_launch_sha256"],
        **overrides,
    }
    return build_bound_benchmark_integrity_qualification(**arguments)


def _cli(evidence):
    root = evidence["root"]
    return [
        "benchmark",
        "integrity-qualification",
        "--format",
        "json",
        "--require-qualified",
        "--trajectory-json",
        str(root / "atif.json"),
        "--runtime-attestation-json",
        str(root / "attestation.json"),
        "--evidence-binding-json",
        str(root / "binding.json"),
        "--external-agent-result-json",
        str(root / "result.json"),
        "--route-receipt-json",
        str(root / "route.json"),
        "--expected-launch-sha256",
        evidence["expected_launch_sha256"],
    ]


def test_runner_produces_binding_consumed_by_real_cli(run_evidence, capsys):
    assert main(_cli(run_evidence)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["integrity_qualified"] is True
    assert result["evidence_binding_verified"] is True
    assert result["score_claim_countable"] is False
    text = json.dumps([run_evidence["binding"], result])
    assert "synthetic private instruction" not in text
    assert "synthetic-run-a" not in text
    assert str(run_evidence["root"]) not in text


def test_binding_does_not_change_successful_legacy_audit(run_evidence):
    artifacts = run_evidence["artifacts"]
    legacy = build_benchmark_integrity_qualification(
        trajectory=artifacts["trajectory"],
        runtime_attestation=artifacts["runtime_attestation"],
    )
    assert _qualify(run_evidence) == {**legacy, "evidence_binding_verified": True}


@pytest.mark.parametrize(
    "artifact",
    ["trajectory", "runtime_attestation", "route_receipt", "external_agent_result"],
)
def test_swapped_artifact_cannot_pass_existing_seal(run_evidence, artifact):
    changed = copy.deepcopy(run_evidence["artifacts"][artifact])
    changed["other_run_evidence"] = True
    result = _qualify(run_evidence, **{artifact: changed})
    assert result["integrity_qualified"] is False
    assert result["integrity_countable"] is False
    assert result["score_claim_eligible"] is False
    assert "benchmark_evidence_artifacts_mismatch" in result["blockers"]


def test_other_launch_cannot_reuse_valid_artifacts_and_seal(run_evidence):
    result = _qualify(run_evidence, expected_launch_sha256="a" * 64)
    assert result["integrity_qualified"] is False
    assert "benchmark_evidence_launch_mismatch" in result["blockers"]


def test_same_prompt_with_fresh_runner_reference_has_different_pin(run_evidence):
    request = copy.deepcopy(run_evidence["request"])
    request["containment"]["verification"]["receipt_ref"] = "synthetic-run-b"
    other = prepare_benchmark_evidence_launch(
        request, expected_model="model-a", expected_provider="trae"
    )
    assert other.sha256 != run_evidence["launch"].sha256
    with pytest.raises(ValueError, match="result_launch_mismatch"):
        build_benchmark_evidence_binding(
            launch=other,
            **run_evidence["artifacts"],
            containment_drained=True,
            containment_evidence_sha256=run_evidence["cleanup_sha256"],
        )


def test_policy_cannot_be_loosened_after_launch(run_evidence):
    result = _qualify(
        run_evidence,
        policy={
            "schema_version": "benchmark_integrity_policy_v0",
            "policy_id": "different",
            "network_access": "permitted_solving",
        },
    )
    assert result["integrity_qualified"] is False
    assert "benchmark_evidence_policy_mismatch" in result["blockers"]


@pytest.mark.parametrize("drained", [False, None, 1, "true"])
def test_cleanup_requires_explicit_observation(run_evidence, drained):
    with pytest.raises(ValueError, match="containment_not_drained"):
        build_benchmark_evidence_binding(
            launch=run_evidence["launch"],
            **run_evidence["artifacts"],
            containment_drained=drained,
            containment_evidence_sha256=run_evidence["cleanup_sha256"],
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("observed_model", "different"),
        ("observed_provider", "different"),
        ("requested_model", "different"),
        ("runtime_audited", False),
        ("observed_route_count", 2),
        ("observed_route_count", True),
        ("status", "route_requested_not_runtime_audited"),
        ("matched", False),
    ],
)
def test_route_requires_actual_matching_observation(run_evidence, field, value):
    artifacts = copy.deepcopy(run_evidence["artifacts"])
    artifacts["route_receipt"][field] = value
    with pytest.raises(ValueError, match="route_mismatch"):
        build_benchmark_evidence_binding(
            launch=run_evidence["launch"],
            **artifacts,
            containment_drained=True,
            containment_evidence_sha256=run_evidence["cleanup_sha256"],
        )


@pytest.mark.parametrize("change", ["preview", "failed", "instruction", "boolean_exit"])
def test_nonterminal_or_different_result_cannot_be_sealed(run_evidence, change):
    artifacts = copy.deepcopy(run_evidence["artifacts"])
    result = artifacts["external_agent_result"]
    if change == "preview":
        result["receipt"]["classification"] = "request_validated_not_executed"
    elif change == "failed":
        result["status"] = "failed"
    elif change == "boolean_exit":
        result["exit_code"] = False
    else:
        result["receipt"]["instruction_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="result_launch_mismatch"):
        build_benchmark_evidence_binding(
            launch=run_evidence["launch"],
            **artifacts,
            containment_drained=True,
            containment_evidence_sha256=run_evidence["cleanup_sha256"],
        )


def test_valid_binding_never_upgrades_failed_isolation_audit(run_evidence):
    artifacts = copy.deepcopy(run_evidence["artifacts"])
    artifacts["runtime_attestation"]["agent_phase_isolated"] = False
    binding = build_benchmark_evidence_binding(
        launch=run_evidence["launch"],
        **artifacts,
        containment_drained=True,
        containment_evidence_sha256=run_evidence["cleanup_sha256"],
    )
    result = _qualify(run_evidence, **artifacts, evidence_binding=binding)
    assert result["evidence_binding_verified"] is True
    assert result["integrity_qualified"] is False
    assert "runtime_attestation_agent_phase_isolated_missing" in result["blockers"]


@pytest.mark.parametrize(
    "mutation", ["unknown", "missing", "unverified", "digest", "launch"]
)
def test_malformed_seal_fails_closed_in_cli(run_evidence, capsys, mutation):
    binding = copy.deepcopy(run_evidence["binding"])
    if mutation == "unknown":
        binding["untrusted"] = "private-value"
    elif mutation == "missing":
        del binding["artifacts"]
    elif mutation == "unverified":
        binding["containment_absence"]["verified"] = False
    elif mutation == "digest":
        binding["containment_absence"]["evidence_sha256"] = "invalid"
    else:
        binding["launch"]["instruction_sha256"] = None
    atomic_write_json(run_evidence["root"] / "binding.json", binding)
    assert main(_cli(run_evidence)) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["integrity_qualified"] is False
    assert "private-value" not in json.dumps(result)


@pytest.mark.parametrize(
    "option",
    [
        "--evidence-binding-json",
        "--expected-launch-sha256",
        "--external-agent-result-json",
        "--route-receipt-json",
    ],
)
def test_partial_opt_in_cannot_fall_back_to_legacy_audit(run_evidence, capsys, option):
    argv = _cli(run_evidence)
    index = argv.index(option)
    del argv[index : index + 2]
    assert main(argv) == 1
    assert json.loads(capsys.readouterr().out)["integrity_qualified"] is False


@pytest.mark.parametrize(
    "filename", ["route.json", "atif.json", "result.json", "binding.json"]
)
def test_missing_artifact_is_not_successful_publication(run_evidence, capsys, filename):
    (run_evidence["root"] / filename).unlink()
    assert main(_cli(run_evidence)) == 1
    assert json.loads(capsys.readouterr().out)["integrity_qualified"] is False


def test_launch_roundtrips_without_raw_request(run_evidence):
    launch = run_evidence["launch"]
    assert BenchmarkEvidenceLaunch(**json.loads(json.dumps(asdict(launch)))) == launch
