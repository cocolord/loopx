from __future__ import annotations

import io
import json
import sys
import tomllib
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXTENSION_ROOT = ROOT / "packages" / "loopx-finance-value-discovery"
EXTENSION_SRC = EXTENSION_ROOT / "src"
EXAMPLE = EXTENSION_ROOT / "examples" / "shadow-qualification-v1.json"
sys.path.insert(0, str(EXTENSION_SRC))

import loopx_finance_value_discovery as finance_extension  # noqa: E402
from loopx_finance_value_discovery.qualification import (  # noqa: E402
    FINANCE_SHADOW_QUALIFICATION_STAGE_IDS,
    build_finance_promotion_request,
    build_finance_rollback_request,
    build_finance_shadow_qualification,
    replay_finance_shadow_qualification,
)
from loopx_finance_value_discovery.cli import run  # noqa: E402
from loopx_finance_value_discovery.replay import canonical_sha256  # noqa: E402

from loopx.control_plane.todos.contract import (  # noqa: E402
    normalize_todo_decision_scope,
)


def _example() -> dict[str, object]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_shadow_contract_is_a_versioned_public_extension_surface() -> None:
    manifest = tomllib.loads(
        (EXTENSION_ROOT / "extension.toml").read_text(encoding="utf-8")
    )
    project = tomllib.loads(
        (EXTENSION_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    assert manifest["version"] == "0.5.0"
    assert project["version"] == "0.5.0"
    assert (
        finance_extension.FINANCE_SHADOW_QUALIFICATION_SCHEMA_VERSION
        == "finance_shadow_qualification_v1"
    )
    assert callable(finance_extension.build_finance_shadow_qualification)
    assert callable(finance_extension.replay_finance_shadow_qualification)
    assert callable(finance_extension.build_finance_promotion_request)
    assert callable(finance_extension.build_finance_rollback_request)


def test_complete_shadow_evidence_only_becomes_ready_for_owner_review() -> None:
    result = build_finance_shadow_qualification(_example())

    assert result["schema_version"] == "finance_shadow_qualification_v1"
    assert result["disposition"] == "ready_for_owner_review"
    assert [stage["stage_id"] for stage in result["stages"]] == list(
        FINANCE_SHADOW_QUALIFICATION_STAGE_IDS
    )
    assert result["boundary"] == {
        "active_revision_changed": False,
        "automatic_promotion_allowed": False,
        "automatic_rollback_allowed": False,
        "human_decision_required": True,
        "investment_advice": False,
        "trading_allowed": False,
    }
    assert result["replay"]["qualification_sha256"]


@pytest.mark.parametrize(
    ("stage_id", "state", "expected"),
    [
        ("point_in_time_integrity", "missing", "insufficient_evidence"),
        ("historical_negative_replay", "conflict", "insufficient_evidence"),
        ("transaction_costs", "failed", "rejected"),
        ("prospective_shadow", "failed", "rejected"),
    ],
)
def test_any_unqualified_stage_fails_closed(
    stage_id: str,
    state: str,
    expected: str,
) -> None:
    payload = _example()
    stage = next(item for item in payload["stages"] if item["stage_id"] == stage_id)
    stage["state"] = state
    stage["evidence_refs"] = (
        []
        if state == "missing"
        else ["first-evaluator-result", "second-evaluator-result"]
        if state == "conflict"
        else ["falsifying-result"]
    )
    stage["reason"] = "Frozen qualification evidence does not pass this stage."

    result = build_finance_shadow_qualification(payload)

    assert result["disposition"] == expected
    assert result["first_blocking_stage"]["stage_id"] == stage_id
    assert result["first_blocking_stage"]["state"] == state
    assert result["boundary"]["active_revision_changed"] is False


def test_any_failed_stage_rejects_even_after_missing_evidence() -> None:
    payload = _example()
    payload["stages"][0]["state"] = "missing"
    payload["stages"][0]["evidence_refs"] = []
    payload["stages"][0]["reason"] = "Point-in-time evidence is missing."
    payload["stages"][5]["state"] = "failed"
    payload["stages"][5]["evidence_refs"] = ["cost-falsification"]
    payload["stages"][5]["reason"] = "Transaction costs invalidate the candidate."

    result = build_finance_shadow_qualification(payload)

    assert result["disposition"] == "rejected"
    assert result["first_blocking_stage"]["stage_id"] == "point_in_time_integrity"
    assert result["first_blocking_stage"]["state"] == "missing"
    assert any(stage["state"] == "failed" for stage in result["stages"])


def test_stage_set_and_order_are_frozen() -> None:
    missing = _example()
    missing["stages"].pop()
    with pytest.raises(ValueError, match="exactly match"):
        build_finance_shadow_qualification(missing)

    reordered = _example()
    reordered["stages"][0], reordered["stages"][1] = (
        reordered["stages"][1],
        reordered["stages"][0],
    )
    with pytest.raises(ValueError, match="exactly match"):
        build_finance_shadow_qualification(reordered)

    extra = _example()
    extra["stages"].append(deepcopy(extra["stages"][-1]))
    with pytest.raises(ValueError, match="exactly match"):
        build_finance_shadow_qualification(extra)


def test_independent_evaluator_cannot_be_the_executor() -> None:
    payload = _example()
    payload["evaluator_id"] = payload["executor_id"]

    with pytest.raises(ValueError, match="must differ"):
        build_finance_shadow_qualification(payload)


def test_point_in_time_requires_an_iso_date_or_datetime() -> None:
    payload = _example()
    payload["point_in_time"] = "not-an-iso-cutoff"

    with pytest.raises(ValueError, match="ISO-8601"):
        build_finance_shadow_qualification(payload)


def test_ready_qualification_builds_a_request_not_an_activation() -> None:
    qualification = build_finance_shadow_qualification(_example())

    request = build_finance_promotion_request(
        qualification,
        requested_by="finance-method-maintainer",
    )

    assert request["schema_version"] == "finance_method_promotion_request_v1"
    assert request["status"] == "awaiting_owner_decision"
    assert request["current_active_revision"] == "finance-method-v0"
    assert request["candidate_revision"] == "finance-method-v1-candidate"
    assert request["rollback_target_revision"] == "finance-method-v0"
    assert request["qualification_sha256"] == qualification["replay"][
        "qualification_sha256"
    ]
    assert request["decision_scope"] == (
        "direction:action:promote_finance_method:finance-method-v1-candidate"
    )
    assert normalize_todo_decision_scope(request["decision_scope"]) is not None
    assert request["activation_performed"] is False
    assert request["automatic_promotion_allowed"] is False


def test_normalized_input_can_still_build_a_promotion_request() -> None:
    payload = _example()
    payload["qualification_id"] = "  finance-method-v1-shadow-qualification  "
    qualification = build_finance_shadow_qualification(payload)
    request = build_finance_promotion_request(
        qualification,
        requested_by="finance-method-maintainer",
    )
    canonical_request = build_finance_promotion_request(
        build_finance_shadow_qualification(_example()),
        requested_by="finance-method-maintainer",
    )

    assert request["request_id"].startswith(
        "promote-finance-method-v1-shadow-qualification-"
    )
    assert request["request_id"] == canonical_request["request_id"]


def test_promotion_request_rejects_unqualified_or_mutated_evidence() -> None:
    incomplete = _example()
    incomplete["stages"][0]["state"] = "missing"
    incomplete["stages"][0]["evidence_refs"] = []
    incomplete["stages"][0]["reason"] = "PIT evidence is missing."
    qualification = build_finance_shadow_qualification(incomplete)
    with pytest.raises(ValueError, match="ready_for_owner_review"):
        build_finance_promotion_request(
            qualification,
            requested_by="finance-method-maintainer",
        )

    ready = build_finance_shadow_qualification(_example())
    mutated = deepcopy(ready)
    mutated["candidate_revision"] = "finance-method-v2-unreviewed"
    with pytest.raises(ValueError, match="qualification_sha256"):
        build_finance_promotion_request(
            mutated,
            requested_by="finance-method-maintainer",
        )

    forged_input_hash = deepcopy(ready)
    forged_input_hash["replay"]["input_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="valid replay"):
        build_finance_promotion_request(
            forged_input_hash,
            requested_by="finance-method-maintainer",
        )

    extended_replay = deepcopy(ready)
    extended_replay["replay"]["unreviewed_note"] = "extra replay metadata"
    with pytest.raises(ValueError, match="replay receipt"):
        build_finance_promotion_request(
            extended_replay,
            requested_by="finance-method-maintainer",
        )

    forged = deepcopy(ready)
    forged["stages"] = []
    forged_without_replay = deepcopy(forged)
    forged_without_replay.pop("replay")
    forged["replay"]["qualification_sha256"] = canonical_sha256(
        forged_without_replay
    )
    with pytest.raises(ValueError, match="exactly match"):
        build_finance_promotion_request(
            forged,
            requested_by="finance-method-maintainer",
        )


def test_promotion_request_rejects_unsupported_qualification_fields() -> None:
    qualification = build_finance_shadow_qualification(_example())
    qualification["unreviewed_note"] = "extra qualification metadata"
    qualification_without_replay = deepcopy(qualification)
    qualification_without_replay.pop("replay")
    qualification["replay"]["qualification_sha256"] = canonical_sha256(
        qualification_without_replay
    )

    with pytest.raises(ValueError, match="unsupported fields"):
        build_finance_promotion_request(
            qualification,
            requested_by="finance-method-maintainer",
        )


def test_owner_requests_require_canonical_decision_scope_revisions() -> None:
    promotion_input = _example()
    promotion_input["candidate_revision"] = "finance method v1"
    qualification = build_finance_shadow_qualification(promotion_input)

    with pytest.raises(ValueError, match="canonical decision scope"):
        build_finance_promotion_request(
            qualification,
            requested_by="finance-method-maintainer",
        )

    receipt = {
        "schema_version": "finance_method_activation_receipt_v1",
        "activation_id": "activation-finance-method-v1",
        "method_id": "finance-value-discovery",
        "decision_authority": "human_owner",
        "decision_outcome": "approve",
        "previous_revision": "finance-method-v0",
        "active_revision": "finance method v1",
        "qualification_sha256": "a" * 64,
    }
    with pytest.raises(ValueError, match="canonical decision scope"):
        build_finance_rollback_request(
            receipt,
            requested_by="finance-method-maintainer",
        )


def test_owner_request_ids_bind_the_complete_request_source() -> None:
    first_input = _example()
    first = build_finance_promotion_request(
        build_finance_shadow_qualification(first_input),
        requested_by="finance-method-maintainer",
    )
    second_input = _example()
    second_input["candidate_revision"] = "finance-method-v2-candidate"
    second = build_finance_promotion_request(
        build_finance_shadow_qualification(second_input),
        requested_by="finance-method-maintainer",
    )

    assert first["request_id"] != second["request_id"]

    first_receipt = {
        "schema_version": "finance_method_activation_receipt_v1",
        "activation_id": "activation-finance-method-v1",
        "method_id": "finance-value-discovery",
        "decision_authority": "human_owner",
        "decision_outcome": "approve",
        "previous_revision": "finance-method-v0",
        "active_revision": "finance-method-v1-candidate",
        "qualification_sha256": "a" * 64,
    }
    first_rollback = build_finance_rollback_request(
        first_receipt,
        requested_by="finance-method-maintainer",
    )
    second_receipt = deepcopy(first_receipt)
    second_receipt["previous_revision"] = "finance-method-v0.1"
    second_rollback = build_finance_rollback_request(
        second_receipt,
        requested_by="finance-method-maintainer",
    )

    assert first_rollback["request_id"] != second_rollback["request_id"]


def test_qualification_replay_and_cli_are_deterministic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qualification = build_finance_shadow_qualification(_example())
    assert replay_finance_shadow_qualification(
        _example(), qualification
    )["replay_verified"]

    mutated = _example()
    mutated["stages"][4]["reason"] = "The sealed prospective result was changed."
    with pytest.raises(ValueError, match="replay"):
        replay_finance_shadow_qualification(mutated, qualification)

    assert run(["qualify-shadow", "--input-json", str(EXAMPLE)]) == 0
    direct = json.loads(capsys.readouterr().out)
    assert direct == qualification

    expected = tmp_path / "qualification.json"
    expected.write_text(json.dumps(qualification), encoding="utf-8")
    assert (
        run(
            [
                "replay-qualification",
                "--input-json",
                str(EXAMPLE),
                "--expected-json",
                str(expected),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["replay_verified"] is True

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_example())))
    assert run([]) == 0
    managed = json.loads(capsys.readouterr().out)
    assert managed == qualification


def test_direct_cli_builds_owner_requests_without_applying_them(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    qualification = build_finance_shadow_qualification(_example())
    qualification_path = tmp_path / "qualification.json"
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")

    assert (
        run(
            [
                "request-promotion",
                "--qualification-json",
                str(qualification_path),
                "--requested-by",
                "finance-method-maintainer",
            ]
        )
        == 0
    )
    promotion = json.loads(capsys.readouterr().out)
    assert promotion["status"] == "awaiting_owner_decision"
    assert promotion["activation_performed"] is False

    receipt = {
        "schema_version": "finance_method_activation_receipt_v1",
        "activation_id": "activation-finance-method-v1",
        "method_id": "finance-value-discovery",
        "decision_authority": "human_owner",
        "decision_outcome": "approve",
        "previous_revision": "finance-method-v0",
        "active_revision": "finance-method-v1-candidate",
        "qualification_sha256": qualification["replay"]["qualification_sha256"],
    }
    receipt_path = tmp_path / "activation.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert (
        run(
            [
                "request-rollback",
                "--activation-receipt-json",
                str(receipt_path),
                "--requested-by",
                "finance-method-maintainer",
            ]
        )
        == 0
    )
    rollback = json.loads(capsys.readouterr().out)
    assert rollback["status"] == "awaiting_owner_decision"
    assert rollback["method_id"] == "finance-value-discovery"
    assert rollback["rollback_performed"] is False


def test_rollback_request_requires_an_explicit_human_activation_receipt() -> None:
    receipt = {
        "schema_version": "finance_method_activation_receipt_v1",
        "activation_id": "activation-finance-method-v1",
        "method_id": "finance-value-discovery",
        "decision_authority": "human_owner",
        "decision_outcome": "approve",
        "previous_revision": "finance-method-v0",
        "active_revision": "finance-method-v1-candidate",
        "qualification_sha256": "a" * 64,
    }

    request = build_finance_rollback_request(
        receipt,
        requested_by="finance-method-maintainer",
    )

    assert request["schema_version"] == "finance_method_rollback_request_v1"
    assert request["status"] == "awaiting_owner_decision"
    assert request["method_id"] == "finance-value-discovery"
    assert request["current_active_revision"] == "finance-method-v1-candidate"
    assert request["rollback_target_revision"] == "finance-method-v0"
    assert request["decision_scope"] == (
        "direction:action:rollback_finance_method:finance-method-v1-candidate"
    )
    assert normalize_todo_decision_scope(request["decision_scope"]) is not None
    assert request["rollback_performed"] is False
    assert request["automatic_rollback_allowed"] is False

    for field, value in (
        ("activation_id", ""),
        ("method_id", ""),
        ("decision_authority", "agent"),
        ("decision_outcome", "reject"),
    ):
        invalid = deepcopy(receipt)
        invalid[field] = value
        with pytest.raises(ValueError):
            build_finance_rollback_request(
                invalid,
                requested_by="finance-method-maintainer",
            )
