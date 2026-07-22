from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from loopx_finance_value_discovery.reducer import (
    _iso_date,
    _public_https_url,
    _reject_forbidden_material,
    _text,
    build_finance_value_discovery_packet,
)
from loopx_finance_value_discovery.signals import (
    build_reversal_leadership_packet,
    build_turn_window_packet,
)


MARKET_JUDGMENT_INPUT_SCHEMA_VERSION = "market_judgment_case_v0"
MARKET_JUDGMENT_PACKET_SCHEMA_VERSION = "market_judgment_packet_v0"
MARKET_JUDGMENT_PROTOCOL = "market_judgment_extension_v0"
ATOM_IDS = {"value_discovery", "turn_window", "reversal_leadership"}
STATES = {
    "hypothesis_frozen",
    "quant_running",
    "quant_invalid",
    "quant_inconclusive",
    "quant_validated",
    "replan",
    "judgment_revised",
    "paper_gate",
    "paper_active",
    "observation_due",
    "closed",
}
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _token(value: object, *, field: str) -> str:
    result = _text(value, field=field, limit=128)
    if not _TOKEN.fullmatch(result):
        raise ValueError(f"{field} must be a bounded token")
    return result


def _text_list(
    value: object, *, field: str, maximum: int, limit: int = 240
) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list")
    if not 1 <= len(value) <= maximum:
        raise ValueError(f"{field} must contain between 1 and {maximum} items")
    result = [
        _text(item, field=f"{field}[{index}]", limit=limit)
        for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must contain unique items")
    return result


def _hypothesis(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("hypothesis must be an object")
    allowed = {
        "hypothesis_id",
        "as_of",
        "market",
        "claim",
        "falsifiers",
        "evaluation_horizon_sessions",
    }
    if set(value) != allowed:
        raise ValueError("hypothesis must match the frozen hypothesis profile")
    market = _text(value.get("market"), field="hypothesis.market", limit=16)
    if market not in {"a_share", "us"}:
        raise ValueError("hypothesis.market must be a_share or us")
    horizon = value.get("evaluation_horizon_sessions")
    if (
        not isinstance(horizon, int)
        or isinstance(horizon, bool)
        or not 1 <= horizon <= 252
    ):
        raise ValueError("hypothesis.evaluation_horizon_sessions must be from 1 to 252")
    return {
        "hypothesis_id": _token(
            value.get("hypothesis_id"), field="hypothesis.hypothesis_id"
        ),
        "as_of": _iso_date(value.get("as_of"), field="hypothesis.as_of"),
        "market": market,
        "claim": _text(value.get("claim"), field="hypothesis.claim", limit=500),
        "falsifiers": _text_list(
            value.get("falsifiers"), field="hypothesis.falsifiers", maximum=8
        ),
        "evaluation_horizon_sessions": horizon,
    }


def _atom(
    value: object, *, hypothesis: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"atom_id", "input"}:
        raise ValueError("atom must contain exactly atom_id and input")
    atom_id = _text(value.get("atom_id"), field="atom.atom_id", limit=48)
    if atom_id not in ATOM_IDS:
        raise ValueError(f"atom.atom_id must be one of {sorted(ATOM_IDS)}")
    raw = value.get("input")
    if not isinstance(raw, Mapping):
        raise ValueError("atom.input must be an object")
    if raw.get("as_of") != hypothesis["as_of"]:
        raise ValueError("atom.input.as_of must match the frozen hypothesis")
    if raw.get("market") not in {None, hypothesis["market"]}:
        raise ValueError("atom.input.market must match the frozen hypothesis")
    if atom_id == "value_discovery":
        packet = build_finance_value_discovery_packet(raw)
    elif atom_id == "turn_window":
        packet = build_turn_window_packet(raw)
    else:
        packet = build_reversal_leadership_packet(raw)
    return atom_id, packet


def _evidence_refs(value: object, *, field: str) -> list[str]:
    refs = _text_list(value, field=field, maximum=12, limit=500)
    return [
        _public_https_url(item, field=f"{field}[{index}]")
        for index, item in enumerate(refs)
    ]


def _event(value: object, *, index: int, revision: str) -> dict[str, Any]:
    field = f"events[{index}]"
    if not isinstance(value, Mapping) or set(value) != {
        "event_id",
        "revision",
        "type",
        "observed_at",
        "detail",
    }:
        raise ValueError(f"{field} must match the event envelope")
    if value.get("revision") != revision:
        raise ValueError(f"{field}.revision must match the frozen case revision")
    event_type = _text(value.get("type"), field=f"{field}.type", limit=48)
    detail = value.get("detail")
    if not isinstance(detail, Mapping):
        raise ValueError(f"{field}.detail must be an object")
    return {
        "event_id": _token(value.get("event_id"), field=f"{field}.event_id"),
        "revision": revision,
        "type": event_type,
        "observed_at": _iso_date(
            value.get("observed_at"), field=f"{field}.observed_at"
        ),
        "detail": dict(detail),
    }


def _exact(detail: Mapping[str, Any], fields: set[str], *, event_type: str) -> None:
    if set(detail) != fields:
        raise ValueError(f"{event_type} detail must contain exactly {sorted(fields)}")


def _reduce_events(
    events: list[dict[str, Any]], *, hypothesis_as_of: str
) -> dict[str, Any]:
    state = "hypothesis_frozen"
    history = [{"state": state, "event_id": None}]
    quant_result: dict[str, Any] | None = None
    judgment: dict[str, Any] | None = None
    paper_authority: dict[str, Any] | None = None
    last_time = hypothesis_as_of
    for event in events:
        if event["observed_at"] < last_time:
            raise ValueError("events must be ordered by observed_at")
        last_time = event["observed_at"]
        event_type, detail = event["type"], event["detail"]
        if event_type == "quant_requested":
            _exact(detail, set(), event_type=event_type)
            if state != "hypothesis_frozen":
                raise ValueError("quant_requested requires hypothesis_frozen")
            state = "quant_running"
        elif event_type == "quant_result_recorded":
            _exact(
                detail,
                {
                    "status",
                    "point_in_time",
                    "lookahead_free",
                    "held_out",
                    "evidence_refs",
                    "rationale",
                },
                event_type=event_type,
            )
            if state != "quant_running":
                raise ValueError("quant_result_recorded requires quant_running")
            status = _text(
                detail.get("status"), field="quant_result_recorded.status", limit=24
            )
            if status not in {"invalid", "inconclusive", "validated"}:
                raise ValueError(
                    "quant result status must be invalid, inconclusive, or validated"
                )
            for flag in ("point_in_time", "lookahead_free", "held_out"):
                if not isinstance(detail.get(flag), bool):
                    raise ValueError(f"quant_result_recorded.{flag} must be boolean")
            refs = _evidence_refs(
                detail.get("evidence_refs"), field="quant_result_recorded.evidence_refs"
            )
            if status == "validated" and not all(
                detail.get(flag) is True
                for flag in ("point_in_time", "lookahead_free", "held_out")
            ):
                raise ValueError(
                    "validated quant result requires point-in-time, lookahead-free, held-out evidence"
                )
            quant_result = {
                "status": status,
                "point_in_time": detail["point_in_time"],
                "lookahead_free": detail["lookahead_free"],
                "held_out": detail["held_out"],
                "evidence_refs": refs,
                "rationale": _text(
                    detail.get("rationale"),
                    field="quant_result_recorded.rationale",
                    limit=500,
                ),
            }
            state = f"quant_{status}"
        elif event_type == "replan_requested":
            _exact(detail, {"rationale"}, event_type=event_type)
            if state not in {"quant_invalid", "quant_inconclusive"}:
                raise ValueError(
                    "replan_requested requires an invalid or inconclusive quant result"
                )
            _text(
                detail.get("rationale"), field="replan_requested.rationale", limit=500
            )
            state = "replan"
        elif event_type == "hypothesis_refrozen":
            _exact(detail, {"revision_note"}, event_type=event_type)
            if state != "replan":
                raise ValueError("hypothesis_refrozen requires replan")
            _text(
                detail.get("revision_note"),
                field="hypothesis_refrozen.revision_note",
                limit=500,
            )
            quant_result, judgment = None, None
            state = "hypothesis_frozen"
        elif event_type == "judgment_revised":
            _exact(detail, {"disposition", "rationale"}, event_type=event_type)
            if state not in {"quant_validated", "observation_due"}:
                raise ValueError(
                    "judgment_revised requires quant_validated or observation_due"
                )
            disposition = _text(
                detail.get("disposition"),
                field="judgment_revised.disposition",
                limit=32,
            )
            if disposition not in {"paper_candidate", "continue_research", "close"}:
                raise ValueError("judgment disposition is unsupported")
            judgment = {
                "disposition": disposition,
                "rationale": _text(
                    detail.get("rationale"),
                    field="judgment_revised.rationale",
                    limit=500,
                ),
            }
            state = "judgment_revised"
        elif event_type == "paper_gate_opened":
            _exact(detail, {"provider_id", "permission"}, event_type=event_type)
            if (
                state != "judgment_revised"
                or not judgment
                or judgment["disposition"] != "paper_candidate"
            ):
                raise ValueError(
                    "paper_gate_opened requires a paper_candidate judgment"
                )
            if (
                not quant_result
                or quant_result["status"] != "validated"
                or not quant_result["held_out"]
            ):
                raise ValueError("paper gate requires held-out quant validation")
            provider = _text(
                detail.get("provider_id"),
                field="paper_gate_opened.provider_id",
                limit=96,
            )
            permission = _text(
                detail.get("permission"), field="paper_gate_opened.permission", limit=96
            )
            if (
                provider != "loopx-futu-paper-trade"
                or permission != "broker.order.submit.simulated"
            ):
                raise ValueError(
                    "paper gate only supports the typed Futu simulated provider contract"
                )
            state = "paper_gate"
        elif event_type == "paper_activated":
            _exact(
                detail,
                {"provider_id", "permission", "authority_status", "authority_ref"},
                event_type=event_type,
            )
            if state != "paper_gate":
                raise ValueError("paper_activated requires paper_gate")
            if (
                detail.get("provider_id") != "loopx-futu-paper-trade"
                or detail.get("permission") != "broker.order.submit.simulated"
                or detail.get("authority_status") != "approved"
            ):
                raise ValueError(
                    "paper_activated requires an approved typed Futu simulated authority"
                )
            paper_authority = {
                "provider_id": detail["provider_id"],
                "permission": detail["permission"],
                "authority_status": "approved",
                "authority_ref": _token(
                    detail.get("authority_ref"), field="paper_activated.authority_ref"
                ),
            }
            state = "paper_active"
        elif event_type == "observation_scheduled":
            _exact(detail, {"due_at", "metrics"}, event_type=event_type)
            if state != "paper_active":
                raise ValueError("observation_scheduled requires paper_active")
            due_at = _iso_date(
                detail.get("due_at"), field="observation_scheduled.due_at"
            )
            if due_at <= event["observed_at"]:
                raise ValueError("observation due_at must be after the event")
            _text_list(
                detail.get("metrics"), field="observation_scheduled.metrics", maximum=8
            )
            state = "observation_due"
        elif event_type == "oos_result_recorded":
            _exact(
                detail, {"status", "evidence_refs", "rationale"}, event_type=event_type
            )
            if state != "observation_due":
                raise ValueError("oos_result_recorded requires observation_due")
            status = _text(
                detail.get("status"), field="oos_result_recorded.status", limit=24
            )
            if status not in {"supports", "revises", "invalidates"}:
                raise ValueError("OOS status must be supports, revises, or invalidates")
            _evidence_refs(
                detail.get("evidence_refs"), field="oos_result_recorded.evidence_refs"
            )
            _text(
                detail.get("rationale"),
                field="oos_result_recorded.rationale",
                limit=500,
            )
            state = "closed" if status == "invalidates" else "judgment_revised"
            if state == "judgment_revised":
                judgment = {
                    "disposition": "continue_research",
                    "rationale": detail["rationale"],
                }
        elif event_type == "closed":
            _exact(detail, {"reason"}, event_type=event_type)
            if state not in {"replan", "judgment_revised", "observation_due"}:
                raise ValueError(
                    "closed requires replan, judgment_revised, or observation_due"
                )
            _text(detail.get("reason"), field="closed.reason", limit=500)
            state = "closed"
        else:
            raise ValueError(f"unsupported market-judgment event type: {event_type}")
        history.append({"state": state, "event_id": event["event_id"]})
        if state not in STATES:
            raise AssertionError("unreachable market-judgment state")
    return {
        "state": state,
        "history": history,
        "quant_result": quant_result,
        "judgment": judgment,
        "paper_authority": paper_authority,
    }


def build_market_judgment_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    _reject_forbidden_material(payload)
    allowed = {
        "schema_version",
        "case_id",
        "revision",
        "hypothesis",
        "atom",
        "events",
    }
    if set(payload) != allowed:
        raise ValueError("market-judgment input must match the case profile")
    if payload.get("schema_version") != MARKET_JUDGMENT_INPUT_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version must be {MARKET_JUDGMENT_INPUT_SCHEMA_VERSION}"
        )
    case_id = _token(payload.get("case_id"), field="case_id")
    revision = _token(payload.get("revision"), field="revision")
    hypothesis = _hypothesis(payload.get("hypothesis"))
    atom_id, atom_packet = _atom(payload.get("atom"), hypothesis=hypothesis)
    raw_events = payload.get("events")
    if (
        not isinstance(raw_events, Sequence)
        or isinstance(raw_events, (str, bytes, bytearray))
        or len(raw_events) > 64
    ):
        raise ValueError("events must be a list with at most 64 items")
    events = [
        _event(item, index=index, revision=revision)
        for index, item in enumerate(raw_events)
    ]
    ids = [item["event_id"] for item in events]
    if len(ids) != len(set(ids)):
        raise ValueError("events must use unique event ids")
    projection = _reduce_events(events, hypothesis_as_of=hypothesis["as_of"])
    paper_ready = projection["state"] == "paper_gate"
    return {
        "ok": True,
        "schema_version": MARKET_JUDGMENT_PACKET_SCHEMA_VERSION,
        "protocol": MARKET_JUDGMENT_PROTOCOL,
        "case_id": case_id,
        "revision": revision,
        "hypothesis": hypothesis,
        "atom": {"atom_id": atom_id, "result": atom_packet},
        "projection": projection,
        "paper_handoff": {
            "ready_for_external_authority": paper_ready,
            "provider_id": "loopx-futu-paper-trade" if paper_ready else None,
            "permission": "broker.order.submit.simulated" if paper_ready else None,
            "order_request": None,
            "account_ref": None,
        },
        "boundary": {
            "canonical_judgment_owner": True,
            "external_reads_performed": False,
            "external_writes_performed": False,
            "account_or_position_accessed": False,
            "order_submitted": False,
            "investment_advice": False,
            "human_decision_owner": True,
        },
        "truth_contract": {
            "atom_result_is_not_quant_validation": True,
            "validated_requires_point_in_time_lookahead_free_held_out_evidence": True,
            "paper_gate_does_not_grant_execution_authority": True,
            "paper_provider_never_chooses_investments": True,
            "invalid_or_inconclusive_results_cannot_enter_paper": True,
            "out_of_sample_invalidation_closes_the_case": True,
        },
    }
