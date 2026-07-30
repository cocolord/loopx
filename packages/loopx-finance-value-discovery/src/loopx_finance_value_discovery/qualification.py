from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .boundary import reject_forbidden_material
from .replay import canonical_json_bytes, canonical_sha256

FINANCE_SHADOW_QUALIFICATION_INPUT_SCHEMA_VERSION = (
    "finance_shadow_qualification_input_v1"
)
FINANCE_SHADOW_QUALIFICATION_SCHEMA_VERSION = "finance_shadow_qualification_v1"
FINANCE_METHOD_PROMOTION_REQUEST_SCHEMA_VERSION = (
    "finance_method_promotion_request_v1"
)
FINANCE_METHOD_ACTIVATION_RECEIPT_SCHEMA_VERSION = (
    "finance_method_activation_receipt_v1"
)
FINANCE_METHOD_ROLLBACK_REQUEST_SCHEMA_VERSION = "finance_method_rollback_request_v1"

FINANCE_SHADOW_QUALIFICATION_STAGE_IDS = (
    "point_in_time_integrity",
    "historical_positive_replay",
    "historical_negative_replay",
    "walk_forward",
    "prospective_shadow",
    "transaction_costs",
    "independent_evaluation",
)

_STAGE_STATES = frozenset({"passed", "failed", "missing", "conflict"})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _text(value: object, *, field: str, limit: int = 160) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    reject_forbidden_material(result, path=field)
    return result


def _evidence_refs(value: object, *, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list")
    if len(value) > 12:
        raise ValueError(f"{field} must contain at most 12 items")
    refs = [
        _text(item, field=f"{field}[{index}]", limit=120)
        for index, item in enumerate(value)
    ]
    if len(refs) != len(set(refs)):
        raise ValueError(f"{field} must use unique evidence refs")
    return refs


def _stage(value: object, *, index: int) -> dict[str, Any]:
    field = f"stages[{index}]"
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    allowed = {"stage_id", "state", "evidence_refs", "reason"}
    if set(value) - allowed:
        raise ValueError(f"{field} has unsupported fields")
    state = _text(value.get("state"), field=f"{field}.state", limit=24)
    if state not in _STAGE_STATES:
        raise ValueError(f"{field}.state must be one of {sorted(_STAGE_STATES)}")
    refs = _evidence_refs(value.get("evidence_refs"), field=f"{field}.evidence_refs")
    if state in {"passed", "failed"} and not refs:
        raise ValueError(f"{field} {state} requires evidence_refs")
    if state == "conflict" and len(refs) < 2:
        raise ValueError(f"{field} conflict requires at least two evidence_refs")
    if state == "missing" and refs:
        raise ValueError(f"{field} missing cannot include evidence_refs")
    return {
        "stage_id": _text(
            value.get("stage_id"),
            field=f"{field}.stage_id",
            limit=80,
        ),
        "state": state,
        "evidence_refs": refs,
        "reason": _text(value.get("reason"), field=f"{field}.reason"),
    }


def _qualification_input(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("shadow qualification input must be an object")
    reject_forbidden_material(value)
    allowed = {
        "schema_version",
        "qualification_id",
        "method_id",
        "current_active_revision",
        "candidate_revision",
        "point_in_time",
        "executor_id",
        "evaluator_id",
        "stages",
    }
    if set(value) - allowed:
        raise ValueError("shadow qualification input has unsupported fields")
    if value.get("schema_version") != FINANCE_SHADOW_QUALIFICATION_INPUT_SCHEMA_VERSION:
        raise ValueError(
            "schema_version must be "
            f"{FINANCE_SHADOW_QUALIFICATION_INPUT_SCHEMA_VERSION}"
        )
    stages_value = value.get("stages")
    if not isinstance(stages_value, Sequence) or isinstance(
        stages_value, (str, bytes, bytearray)
    ):
        raise ValueError("stages must be a list")
    stages = [_stage(item, index=index) for index, item in enumerate(stages_value)]
    if tuple(stage["stage_id"] for stage in stages) != (
        FINANCE_SHADOW_QUALIFICATION_STAGE_IDS
    ):
        raise ValueError(
            "stages must exactly match the frozen finance qualification order"
        )
    executor_id = _text(value.get("executor_id"), field="executor_id", limit=80)
    evaluator_id = _text(value.get("evaluator_id"), field="evaluator_id", limit=80)
    if executor_id == evaluator_id:
        raise ValueError("executor_id and evaluator_id must differ")
    current_revision = _text(
        value.get("current_active_revision"),
        field="current_active_revision",
        limit=100,
    )
    candidate_revision = _text(
        value.get("candidate_revision"),
        field="candidate_revision",
        limit=100,
    )
    if current_revision == candidate_revision:
        raise ValueError("candidate_revision must differ from current_active_revision")
    return {
        "schema_version": FINANCE_SHADOW_QUALIFICATION_INPUT_SCHEMA_VERSION,
        "qualification_id": _text(
            value.get("qualification_id"),
            field="qualification_id",
            limit=100,
        ),
        "method_id": _text(value.get("method_id"), field="method_id", limit=100),
        "current_active_revision": current_revision,
        "candidate_revision": candidate_revision,
        "point_in_time": _text(
            value.get("point_in_time"),
            field="point_in_time",
            limit=40,
        ),
        "executor_id": executor_id,
        "evaluator_id": evaluator_id,
        "stages": stages,
    }


def build_finance_shadow_qualification(value: object) -> dict[str, Any]:
    payload = _qualification_input(value)
    failed_stage = next(
        (stage for stage in payload["stages"] if stage["state"] == "failed"),
        None,
    )
    first_blocking = next(
        (stage for stage in payload["stages"] if stage["state"] != "passed"),
        None,
    )
    if failed_stage is not None:
        disposition = "rejected"
    elif first_blocking is None:
        disposition = "ready_for_owner_review"
    else:
        disposition = "insufficient_evidence"
    qualification = {
        "schema_version": FINANCE_SHADOW_QUALIFICATION_SCHEMA_VERSION,
        "qualification_id": payload["qualification_id"],
        "method_id": payload["method_id"],
        "current_active_revision": payload["current_active_revision"],
        "candidate_revision": payload["candidate_revision"],
        "point_in_time": payload["point_in_time"],
        "executor_id": payload["executor_id"],
        "evaluator_id": payload["evaluator_id"],
        "stages": payload["stages"],
        "disposition": disposition,
        "first_blocking_stage": (
            {
                "stage_id": first_blocking["stage_id"],
                "state": first_blocking["state"],
                "reason": first_blocking["reason"],
            }
            if first_blocking is not None
            else None
        ),
        "boundary": {
            "active_revision_changed": False,
            "automatic_promotion_allowed": False,
            "automatic_rollback_allowed": False,
            "human_decision_required": True,
            "investment_advice": False,
            "trading_allowed": False,
        },
    }
    return {
        **qualification,
        "replay": {
            "input_sha256": canonical_sha256(payload),
            "qualification_sha256": canonical_sha256(qualification),
            "canonicalization": "json_sort_keys_compact_ascii_v1",
        },
    }


def replay_finance_shadow_qualification(
    value: object,
    expected: object,
) -> dict[str, Any]:
    if not isinstance(expected, Mapping):
        raise ValueError("expected qualification must be an object")
    replayed = build_finance_shadow_qualification(value)
    expected_replay = expected.get("replay")
    if not isinstance(expected_replay, Mapping):
        raise ValueError("expected qualification requires a replay receipt")
    for field in ("input_sha256", "qualification_sha256"):
        if expected_replay.get(field) != replayed["replay"][field]:
            raise ValueError(f"replay {field} mismatch")
    if canonical_json_bytes(expected) != canonical_json_bytes(replayed):
        raise ValueError("replay qualification bytes mismatch")
    return {
        "ok": True,
        "schema_version": FINANCE_SHADOW_QUALIFICATION_SCHEMA_VERSION,
        "replay_verified": True,
        "input_sha256": replayed["replay"]["input_sha256"],
        "qualification_sha256": replayed["replay"]["qualification_sha256"],
    }


def _validated_qualification(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("qualification must be an object")
    replay = value.get("replay")
    if not isinstance(replay, Mapping):
        raise ValueError("qualification requires a replay receipt")
    if set(replay) != {
        "input_sha256",
        "qualification_sha256",
        "canonicalization",
    }:
        raise ValueError("qualification replay receipt fields do not match")
    if replay.get("canonicalization") != "json_sort_keys_compact_ascii_v1":
        raise ValueError("qualification replay receipt canonicalization mismatch")
    qualification = dict(value)
    qualification.pop("replay", None)
    expected_sha256 = replay.get("qualification_sha256")
    if (
        not isinstance(expected_sha256, str)
        or canonical_sha256(qualification) != expected_sha256
    ):
        raise ValueError("qualification_sha256 mismatch")
    if value.get("schema_version") != FINANCE_SHADOW_QUALIFICATION_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {FINANCE_SHADOW_QUALIFICATION_SCHEMA_VERSION}"
        )
    if value.get("disposition") != "ready_for_owner_review":
        raise ValueError("qualification must be ready_for_owner_review")
    boundary = value.get("boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("qualification boundary is required")
    if boundary.get("active_revision_changed") is not False:
        raise ValueError("qualification cannot change the active revision")
    if boundary.get("automatic_promotion_allowed") is not False:
        raise ValueError("qualification cannot allow automatic promotion")
    replay_input = {
        "schema_version": FINANCE_SHADOW_QUALIFICATION_INPUT_SCHEMA_VERSION,
        "qualification_id": value.get("qualification_id"),
        "method_id": value.get("method_id"),
        "current_active_revision": value.get("current_active_revision"),
        "candidate_revision": value.get("candidate_revision"),
        "point_in_time": value.get("point_in_time"),
        "executor_id": value.get("executor_id"),
        "evaluator_id": value.get("evaluator_id"),
        "stages": value.get("stages"),
    }
    replayed = build_finance_shadow_qualification(replay_input)
    if replay.get("input_sha256") != replayed["replay"]["input_sha256"]:
        raise ValueError("qualification does not exactly match a valid replay")
    replayed_qualification = dict(replayed)
    replayed_qualification.pop("replay")
    if canonical_json_bytes(qualification) != canonical_json_bytes(
        replayed_qualification
    ):
        raise ValueError("qualification does not exactly match a valid replay")
    return dict(value)


def build_finance_promotion_request(
    qualification: object,
    *,
    requested_by: str,
) -> dict[str, Any]:
    payload = _validated_qualification(qualification)
    requester = _text(requested_by, field="requested_by", limit=80)
    candidate_revision = _text(
        payload.get("candidate_revision"),
        field="candidate_revision",
        limit=100,
    )
    current_revision = _text(
        payload.get("current_active_revision"),
        field="current_active_revision",
        limit=100,
    )
    return {
        "schema_version": FINANCE_METHOD_PROMOTION_REQUEST_SCHEMA_VERSION,
        "request_id": f"promote-{payload['qualification_id']}",
        "status": "awaiting_owner_decision",
        "requested_by": requester,
        "method_id": payload["method_id"],
        "current_active_revision": current_revision,
        "candidate_revision": candidate_revision,
        "rollback_target_revision": current_revision,
        "qualification_sha256": payload["replay"]["qualification_sha256"],
        "decision_scope": (
            f"direction:action:promote_finance_method:{candidate_revision}"
        ),
        "activation_performed": False,
        "automatic_promotion_allowed": False,
    }


def build_finance_rollback_request(
    activation_receipt: object,
    *,
    requested_by: str,
) -> dict[str, Any]:
    if not isinstance(activation_receipt, Mapping):
        raise ValueError("activation receipt must be an object")
    reject_forbidden_material(activation_receipt)
    allowed = {
        "schema_version",
        "activation_id",
        "method_id",
        "decision_authority",
        "decision_outcome",
        "previous_revision",
        "active_revision",
        "qualification_sha256",
    }
    if set(activation_receipt) != allowed:
        raise ValueError("activation receipt fields do not match the frozen contract")
    if (
        activation_receipt.get("schema_version")
        != FINANCE_METHOD_ACTIVATION_RECEIPT_SCHEMA_VERSION
    ):
        raise ValueError(
            f"schema_version must be {FINANCE_METHOD_ACTIVATION_RECEIPT_SCHEMA_VERSION}"
        )
    if activation_receipt.get("decision_authority") != "human_owner":
        raise ValueError("activation receipt requires human_owner authority")
    if activation_receipt.get("decision_outcome") != "approve":
        raise ValueError("activation receipt requires an approved decision")
    qualification_sha256 = activation_receipt.get("qualification_sha256")
    if not isinstance(qualification_sha256, str) or not _SHA256_PATTERN.fullmatch(
        qualification_sha256
    ):
        raise ValueError("qualification_sha256 must be a lowercase SHA-256")
    active_revision = _text(
        activation_receipt.get("active_revision"),
        field="active_revision",
        limit=100,
    )
    previous_revision = _text(
        activation_receipt.get("previous_revision"),
        field="previous_revision",
        limit=100,
    )
    if active_revision == previous_revision:
        raise ValueError("rollback target must differ from the active revision")
    activation_id = _text(
        activation_receipt.get("activation_id"),
        field="activation_id",
        limit=100,
    )
    method_id = _text(
        activation_receipt.get("method_id"),
        field="method_id",
        limit=100,
    )
    requester = _text(requested_by, field="requested_by", limit=80)
    return {
        "schema_version": FINANCE_METHOD_ROLLBACK_REQUEST_SCHEMA_VERSION,
        "request_id": f"rollback-{activation_id}",
        "status": "awaiting_owner_decision",
        "requested_by": requester,
        "method_id": method_id,
        "current_active_revision": active_revision,
        "rollback_target_revision": previous_revision,
        "activation_receipt_sha256": canonical_sha256(activation_receipt),
        "qualification_sha256": qualification_sha256,
        "decision_scope": (
            f"direction:action:rollback_finance_method:{active_revision}"
        ),
        "rollback_performed": False,
        "automatic_rollback_allowed": False,
    }
