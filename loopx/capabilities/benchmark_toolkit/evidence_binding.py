"""Bind runner-collected evidence to the existing external-agent v1 launch.

The runner pins a launch before execution and seals evidence after observing
containment cleanup. These hashes detect mismatched inputs; they neither perform
nor authenticate the runner's observations. No process or file lifecycle is owned
here, and the legacy request/result and integrity paths remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .external_agent import (
    EXTERNAL_AGENT_RESULT_SCHEMA_VERSION,
    LOOPX_EXTERNAL_AGENT_PHASE_RECEIPT_SCHEMA_VERSION,
    _validate_request,
)
from .integrity import _validated_policy, build_benchmark_integrity_qualification
from .traex_evidence import BENCHMARK_MODEL_ROUTE_RECEIPT_SCHEMA_VERSION

BENCHMARK_EVIDENCE_BINDING_SCHEMA_VERSION = "benchmark_evidence_binding_v0"
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError("benchmark_evidence_digest_invalid")
    return value


def _route_sha256(model: object, provider: object) -> str:
    if any(not isinstance(item, str) or not item.strip() for item in (model, provider)):
        raise ValueError("benchmark_evidence_route_invalid")
    return _sha256([str(model).strip().casefold(), str(provider).strip().casefold()])


@dataclass(frozen=True, slots=True)
class BenchmarkEvidenceLaunch:
    """Immutable input pin; persist its digest before invoking the solver.

    A fresh runner verification receipt reference is required for each launch,
    including retries and comparison arms that use the same instruction.
    """

    instruction_sha256: str
    containment_ref_sha256: str
    route_sha256: str
    policy_sha256: str

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            _digest(value)

    @property
    def sha256(self) -> str:
        return _sha256(asdict(self))


def prepare_benchmark_evidence_launch(
    request: Mapping[str, Any],
    *,
    expected_model: str,
    expected_provider: str,
    policy: Mapping[str, Any] | None = None,
) -> BenchmarkEvidenceLaunch:
    """Pin an admitted v1 request in the runner's current task workspace."""

    instruction, _workspace, _timeout, _kind, receipt_ref = _validate_request(request)
    return BenchmarkEvidenceLaunch(
        instruction_sha256=_text_sha256(instruction),
        containment_ref_sha256=_text_sha256(receipt_ref),
        route_sha256=_route_sha256(expected_model, expected_provider),
        policy_sha256=_sha256(_validated_policy(policy)),
    )


def build_benchmark_evidence_binding(
    *,
    launch: BenchmarkEvidenceLaunch,
    external_agent_result: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    runtime_attestation: Mapping[str, Any],
    route_receipt: Mapping[str, Any],
    containment_drained: bool,
    containment_evidence_sha256: str,
) -> dict[str, Any]:
    """Seal final artifacts collected by the trusted runner for this launch.

    Call only after the runner independently observes that the exact containment
    is empty. A successful parent process or a pre-launch containment declaration
    is insufficient. Retain the underlying cleanup observation privately.
    """

    if containment_drained is not True:
        raise ValueError("benchmark_evidence_containment_not_drained")
    cleanup_digest = _digest(containment_evidence_sha256)
    receipt = external_agent_result.get("receipt")
    if (
        external_agent_result.get("schema_version")
        != EXTERNAL_AGENT_RESULT_SCHEMA_VERSION
        or external_agent_result.get("status") != "succeeded"
        or type(external_agent_result.get("exit_code")) is not int
        or external_agent_result.get("exit_code") != 0
        or not isinstance(receipt, Mapping)
        or receipt.get("schema_version")
        != LOOPX_EXTERNAL_AGENT_PHASE_RECEIPT_SCHEMA_VERSION
        or receipt.get("classification") != "solver_completed"
        or receipt.get("instruction_sha256") != launch.instruction_sha256
        or receipt.get("containment_verification_ref_sha256")
        != launch.containment_ref_sha256
    ):
        raise ValueError("benchmark_evidence_result_launch_mismatch")
    if (
        route_receipt.get("schema_version")
        != BENCHMARK_MODEL_ROUTE_RECEIPT_SCHEMA_VERSION
        or route_receipt.get("runtime_audited") is not True
        or type(route_receipt.get("observed_route_count")) is not int
        or route_receipt.get("observed_route_count") != 1
        or route_receipt.get("matched") is not True
        or route_receipt.get("status") != "runtime_route_verified"
        or _route_sha256(
            route_receipt.get("requested_model"),
            route_receipt.get("requested_provider"),
        )
        != launch.route_sha256
        or _route_sha256(
            route_receipt.get("observed_model"), route_receipt.get("observed_provider")
        )
        != launch.route_sha256
    ):
        raise ValueError("benchmark_evidence_route_mismatch")
    return {
        "schema_version": BENCHMARK_EVIDENCE_BINDING_SCHEMA_VERSION,
        "launch": asdict(launch),
        "artifacts": {
            "external_agent_result_sha256": _sha256(external_agent_result),
            "trajectory_sha256": _sha256(trajectory),
            "runtime_attestation_sha256": _sha256(runtime_attestation),
            "route_receipt_sha256": _sha256(route_receipt),
        },
        "containment_absence": {"verified": True, "evidence_sha256": cleanup_digest},
    }


def build_bound_benchmark_integrity_qualification(
    *,
    evidence_binding: Mapping[str, Any],
    expected_launch_sha256: str,
    external_agent_result: Mapping[str, Any],
    route_receipt: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    runtime_attestation: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
    restricted_access_adjudication: Mapping[str, Any] | None = None,
    sensitive_values: Iterable[str] = (),
) -> dict[str, Any]:
    """Qualify only the artifacts sealed under the independently pinned launch.

    The caller must obtain the pin and seal from trusted runner state. A complete
    replacement of both the trusted seal and its inputs cannot be detected by
    unkeyed hashes. This API never upgrades a failed legacy integrity audit.
    """

    if (
        not isinstance(evidence_binding, Mapping)
        or set(evidence_binding)
        != {"schema_version", "launch", "artifacts", "containment_absence"}
        or evidence_binding.get("schema_version")
        != BENCHMARK_EVIDENCE_BINDING_SCHEMA_VERSION
    ):
        raise ValueError("benchmark_evidence_binding_invalid")
    launch_data = evidence_binding["launch"]
    absence = evidence_binding["containment_absence"]
    if (
        not isinstance(launch_data, dict)
        or not isinstance(absence, Mapping)
        or set(absence) != {"verified", "evidence_sha256"}
    ):
        raise ValueError("benchmark_evidence_binding_invalid")
    launch = BenchmarkEvidenceLaunch(**launch_data)
    rebuilt = build_benchmark_evidence_binding(
        launch=launch,
        external_agent_result=external_agent_result,
        trajectory=trajectory,
        runtime_attestation=runtime_attestation,
        route_receipt=route_receipt,
        containment_drained=absence["verified"],
        containment_evidence_sha256=absence["evidence_sha256"],
    )
    failures = []
    if launch.sha256 != _digest(expected_launch_sha256):
        failures.append("benchmark_evidence_launch_mismatch")
    if launch.policy_sha256 != _sha256(_validated_policy(policy)):
        failures.append("benchmark_evidence_policy_mismatch")
    if rebuilt != evidence_binding:
        failures.append("benchmark_evidence_artifacts_mismatch")
    result = build_benchmark_integrity_qualification(
        trajectory=trajectory,
        runtime_attestation=runtime_attestation,
        policy=policy,
        restricted_access_adjudication=restricted_access_adjudication,
        sensitive_values=sensitive_values,
    )
    if failures:
        result["classification"] = "evidence_binding_not_qualified"
        result["blockers"] = [*result["blockers"], *failures]
        result["integrity_qualified"] = False
        result["integrity_countable"] = False
        result["score_claim_eligible"] = False
    result["evidence_binding_verified"] = not failures
    return result
