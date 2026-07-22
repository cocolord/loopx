from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .reducer import _iso_date, _public_https_url, _reject_forbidden_material, _text


TURN_WINDOW_INPUT_SCHEMA_VERSION = "finance_turn_window_input_v0"
TURN_WINDOW_PACKET_SCHEMA_VERSION = "finance_turn_window_packet_v0"
REVERSAL_LEADERSHIP_INPUT_SCHEMA_VERSION = "finance_reversal_leadership_input_v0"
REVERSAL_LEADERSHIP_PACKET_SCHEMA_VERSION = "finance_reversal_leadership_packet_v0"
CHECKPOINTS = {1, 3, 5, 10, 20}
INVALIDATION_FLAGS = {
    "driver_evidence_refuted",
    "new_low_after_rebound",
    "relative_strength_lost",
    "sector_confirmation_failed",
}


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _ratio(value: object, *, field: str) -> float:
    result = _number(value, field=field)
    if not 0 <= result <= 1:
        raise ValueError(f"{field} must be between 0 and 1")
    return result


def _boolean(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _market(value: object) -> str:
    market = _text(value, field="market", limit=16)
    if market not in {"a_share", "us"}:
        raise ValueError("market must be a_share or us")
    return market


def _base(payload: Mapping[str, Any], *, schema_version: str) -> tuple[str, str]:
    _reject_forbidden_material(payload)
    if payload.get("schema_version") != schema_version:
        raise ValueError(f"schema_version must be {schema_version}")
    as_of = _iso_date(payload.get("as_of"), field="as_of")
    market = _market(payload.get("market"))
    if payload.get("point_in_time_data") is not True:
        raise ValueError("point_in_time_data must be true")
    if payload.get("lookahead_free") is not True:
        raise ValueError("lookahead_free must be true")
    return as_of, market


def _source_refs(value: object, *, as_of: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("source_refs must be a list")
    if not 1 <= len(value) <= 12:
        raise ValueError("source_refs must contain between 1 and 12 items")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        field = f"source_refs[{index}]"
        if not isinstance(item, Mapping):
            raise ValueError(f"{field} must be an object")
        allowed = {"source_id", "source_tier", "url", "provider_label", "observed_at"}
        if set(item) - allowed:
            raise ValueError(f"{field} has unsupported fields")
        tier = _text(item.get("source_tier"), field=f"{field}.source_tier", limit=32)
        if tier not in {"primary", "independent", "market_data"}:
            raise ValueError(f"{field}.source_tier is unsupported")
        url, provider = item.get("url"), item.get("provider_label")
        if bool(url) == bool(provider):
            raise ValueError(f"{field} requires exactly one of url or provider_label")
        observed_at = _iso_date(item.get("observed_at"), field=f"{field}.observed_at")
        if observed_at[:10] > as_of[:10]:
            raise ValueError(f"{field}.observed_at must not be after as_of")
        result.append(
            {
                "source_id": _text(
                    item.get("source_id"), field=f"{field}.source_id", limit=96
                ),
                "source_tier": tier,
                "url": _public_https_url(url, field=f"{field}.url") if url else None,
                "provider_label": _text(
                    provider, field=f"{field}.provider_label", limit=120
                )
                if provider
                else None,
                "observed_at": observed_at,
            }
        )
    ids = [item["source_id"] for item in result]
    if len(ids) != len(set(ids)):
        raise ValueError("source_refs must use unique source ids")
    return result


def _layer(layer_id: str, triggered: bool, evidence: str) -> dict[str, Any]:
    return {"layer_id": layer_id, "triggered": triggered, "evidence": evidence}


def _side(layers: list[dict[str, Any]], *, required: set[str]) -> dict[str, Any]:
    triggered = [item["layer_id"] for item in layers if item["triggered"]]
    observed = len(triggered) >= 3 and required <= set(triggered)
    return {
        "score": len(triggered),
        "triggered_layers": triggered,
        "clear_layers": [item["layer_id"] for item in layers if not item["triggered"]],
        "supporting_evidence": [
            item["evidence"] for item in layers if item["triggered"]
        ],
        "observed": observed,
        "confirmed": False,
        "layers": layers,
    }


def build_turn_window_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version",
        "as_of",
        "market",
        "point_in_time_data",
        "lookahead_free",
        "metrics",
        "source_refs",
    }
    if set(payload) != allowed:
        raise ValueError("turn-window input must match the frozen observation profile")
    as_of, market = _base(payload, schema_version=TURN_WINDOW_INPUT_SCHEMA_VERSION)
    raw = payload.get("metrics")
    fields = {
        "return_60d_pct",
        "distance_from_200d_pct",
        "days_since_20d_high",
        "from_20d_high_pct",
        "return_5d_pct",
        "participation_relative_5d_pct",
        "attention_5d_vs_20d_ratio",
        "drawdown_from_252d_high_pct",
        "days_since_20d_low",
        "bounce_from_20d_low_pct",
        "stress_unresolved",
    }
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise ValueError("metrics must match the frozen turn-window profile")
    metrics = {
        name: _number(raw[name], field=f"metrics.{name}")
        for name in fields - {"stress_unresolved"}
    }
    stress = _boolean(raw["stress_unresolved"], field="metrics.stress_unresolved")
    for name in ("days_since_20d_high", "days_since_20d_low"):
        if not metrics[name].is_integer() or not 0 <= metrics[name] <= 19:
            raise ValueError(f"metrics.{name} must be an integer from 0 to 19")
    if metrics["attention_5d_vs_20d_ratio"] < 0 or metrics["from_20d_high_pct"] > 0:
        raise ValueError(
            "attention ratio must be non-negative and from-high must be non-positive"
        )
    extension, distance, failed_high = (
        (8.0, 3.0, -2.0) if market == "a_share" else (10.0, 5.0, -1.5)
    )
    deep, bounce, rebound = (
        (-12.0, 3.5, 2.0) if market == "a_share" else (-10.0, 2.5, 1.5)
    )
    top = _side(
        [
            _layer(
                "prior_extension",
                metrics["return_60d_pct"] >= extension
                and metrics["distance_from_200d_pct"] >= distance,
                "Prior price extension is material.",
            ),
            _layer(
                "failed_upside_auction",
                metrics["days_since_20d_high"] <= 5
                and metrics["from_20d_high_pct"] <= failed_high
                and metrics["return_5d_pct"] < 0,
                "A recent high failed with negative five-session momentum.",
            ),
            _layer(
                "participation_rejection",
                metrics["participation_relative_5d_pct"] < 0,
                "Participation trails the primary index.",
            ),
            _layer(
                "attention_climax",
                metrics["attention_5d_vs_20d_ratio"] >= 1.2,
                "Attention or turnover expanded near the high.",
            ),
        ],
        required={"prior_extension", "failed_upside_auction"},
    )
    bottom = _side(
        [
            _layer(
                "deep_drawdown",
                metrics["drawdown_from_252d_high_pct"] <= deep,
                "The drawdown is material for this market.",
            ),
            _layer(
                "failed_downside_auction",
                metrics["days_since_20d_low"] <= 5
                and metrics["bounce_from_20d_low_pct"] >= bounce
                and metrics["return_5d_pct"] >= rebound,
                "A recent low failed to extend and price rebounded.",
            ),
            _layer(
                "participation_absorption",
                metrics["participation_relative_5d_pct"] > 0 and stress,
                "Participation improves while stress remains unresolved.",
            ),
            _layer(
                "attention_cooling",
                metrics["attention_5d_vs_20d_ratio"] <= 0.9,
                "Attention cooled after the selloff.",
            ),
        ],
        required={"deep_drawdown", "failed_downside_auction"},
    )
    if top["observed"] and bottom["observed"]:
        state, action = "conflicting_turn_windows", "quant_invalid"
    elif top["observed"]:
        state, action = (
            "top_window_observation",
            "validate_centered_five_session_window",
        )
    elif bottom["observed"]:
        state, action = (
            "bottom_window_observation",
            "validate_centered_five_session_window",
        )
    else:
        state, action = "no_turn_window", "close_or_replan"
    return {
        "ok": True,
        "schema_version": TURN_WINDOW_PACKET_SCHEMA_VERSION,
        "atom_id": "turn_window",
        "as_of": as_of,
        "market": market,
        "state": state,
        "top": top,
        "bottom": bottom,
        "research_next_action": action,
        "source_refs": _source_refs(payload.get("source_refs"), as_of=as_of),
        "validation_contract": {
            "signal_window_sessions": 5,
            "followthrough_sessions": 20,
            "matched_daily_base_rate_required": True,
            "future_data_is_validation_label_only": True,
        },
        "boundary": {"investment_advice": False, "trading_allowed": False},
    }


def _text_list(value: object, *, field: str, maximum: int) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a list")
    if len(value) > maximum:
        raise ValueError(f"{field} contains too many items")
    result = [
        _text(item, field=f"{field}[{index}]", limit=240)
        for index, item in enumerate(value)
    ]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} must contain unique items")
    return result


def build_reversal_leadership_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version",
        "as_of",
        "market",
        "point_in_time_data",
        "lookahead_free",
        "checkpoint_session",
        "market_whipsaw_observed",
        "candidates",
        "source_refs",
    }
    if set(payload) != allowed:
        raise ValueError(
            "reversal-leadership input must match the frozen observation profile"
        )
    as_of, market = _base(
        payload, schema_version=REVERSAL_LEADERSHIP_INPUT_SCHEMA_VERSION
    )
    checkpoint = _number(payload.get("checkpoint_session"), field="checkpoint_session")
    if not checkpoint.is_integer() or int(checkpoint) not in CHECKPOINTS:
        raise ValueError("checkpoint_session must be 1, 3, 5, 10, or 20")
    session = int(checkpoint)
    whipsaw = _boolean(
        payload.get("market_whipsaw_observed"), field="market_whipsaw_observed"
    )
    raw_candidates = payload.get("candidates")
    if (
        not isinstance(raw_candidates, Sequence)
        or isinstance(raw_candidates, (str, bytes, bytearray))
        or not 1 <= len(raw_candidates) <= 12
    ):
        raise ValueError("candidates must contain between 1 and 12 items")
    candidates: list[dict[str, Any]] = []
    fields = {
        "symbol",
        "sector",
        "relative_strength_percentile",
        "early_response_percentile",
        "pre_rebound_resilience_percentile",
        "sector_confirmation_count",
        "driver_evidence",
        "counterevidence",
        "invalidation_flags",
    }
    for index, raw in enumerate(raw_candidates):
        field = f"candidates[{index}]"
        if not isinstance(raw, Mapping) or set(raw) != fields:
            raise ValueError(f"{field} must match the frozen candidate profile")
        relative = _ratio(
            raw["relative_strength_percentile"],
            field=f"{field}.relative_strength_percentile",
        )
        early = _ratio(
            raw["early_response_percentile"], field=f"{field}.early_response_percentile"
        )
        resilience = _ratio(
            raw["pre_rebound_resilience_percentile"],
            field=f"{field}.pre_rebound_resilience_percentile",
        )
        count = _number(
            raw["sector_confirmation_count"], field=f"{field}.sector_confirmation_count"
        )
        if not count.is_integer() or not 0 <= count <= 20:
            raise ValueError(
                f"{field}.sector_confirmation_count must be an integer from 0 to 20"
            )
        evidence = _text_list(
            raw["driver_evidence"], field=f"{field}.driver_evidence", maximum=4
        )
        counter = _text_list(
            raw["counterevidence"], field=f"{field}.counterevidence", maximum=4
        )
        flags = _text_list(
            raw["invalidation_flags"], field=f"{field}.invalidation_flags", maximum=4
        )
        if set(flags) - INVALIDATION_FLAGS:
            raise ValueError(f"{field}.invalidation_flags contains unsupported values")
        price_leader = relative >= 0.75
        story_supported = len(evidence) >= 2
        seed_supported = len(evidence) >= 1
        sector_supported = count >= 2
        early_routes: list[str] = []
        if early >= 0.65 and relative >= 0.60:
            early_routes.append("shock_responder")
        if resilience >= 0.75 and relative >= 0.65:
            early_routes.append("structural_resilience")
        if flags:
            classification = "invalidated"
        elif session == 20 and price_leader and story_supported and sector_supported:
            classification = "second_phase_leader"
        elif (
            market == "a_share"
            and session == 10
            and price_leader
            and (early >= 0.75 or resilience >= 0.75)
            and story_supported
            and sector_supported
        ):
            classification = "emerging_driver"
        elif (
            market == "a_share"
            and session in {1, 3, 5}
            and early_routes
            and seed_supported
            and sector_supported
        ):
            classification = "early_strong_candidate"
        elif early >= 0.75 and (
            (market == "us" and session < 20 and whipsaw)
            or (session == 20 and not price_leader)
        ):
            classification = "shock_beta"
        else:
            classification = "unproven_rebound"
        candidates.append(
            {
                "symbol": _text(raw["symbol"], field=f"{field}.symbol", limit=32),
                "sector": _text(raw["sector"], field=f"{field}.sector", limit=96),
                "relative_strength_percentile": relative,
                "early_response_percentile": early,
                "pre_rebound_resilience_percentile": resilience,
                "sector_confirmation_count": int(count),
                "driver_evidence": evidence,
                "counterevidence": counter,
                "invalidation_flags": flags,
                "early_candidate_routes": early_routes,
                "classification": classification,
                "durable_leadership_observed": classification == "second_phase_leader",
                "confirmed": False,
            }
        )
    symbols = [item["symbol"] for item in candidates]
    if len(symbols) != len(set(symbols)):
        raise ValueError("candidates must use unique symbols")
    durable = [
        item["symbol"]
        for item in candidates
        if item["classification"] == "second_phase_leader"
    ]
    emerging = [
        item["symbol"]
        for item in candidates
        if item["classification"] == "emerging_driver"
    ]
    early_candidates = [
        item["symbol"]
        for item in candidates
        if item["classification"] == "early_strong_candidate"
    ]
    if durable:
        state = "second_phase_leader_observation"
    elif emerging:
        state = "driver_hypothesis"
    elif early_candidates:
        state = "early_strong_candidate_observation"
    elif any(item["classification"] == "shock_beta" for item in candidates):
        state = "shock_beta_observation"
    else:
        state = "no_durable_driver"
    return {
        "ok": True,
        "schema_version": REVERSAL_LEADERSHIP_PACKET_SCHEMA_VERSION,
        "atom_id": "reversal_leadership",
        "as_of": as_of,
        "market": market,
        "state": state,
        "checkpoint_session": session,
        "candidates": candidates,
        "early_strong_candidate_symbols": early_candidates,
        "emerging_driver_symbols": emerging,
        "second_phase_leader_symbols": durable,
        "source_refs": _source_refs(payload.get("source_refs"), as_of=as_of),
        "validation_contract": {
            "checkpoints": [1, 3, 5, 10, 20],
            "early_candidate_checkpoints": [1, 3, 5],
            "durable_leadership_checkpoint": 20,
            "early_candidate_is_not_durable_leadership": True,
            "held_out_forward_sessions": 60,
            "session_20_price_baseline_required": True,
            "future_returns_are_validation_labels_only": True,
        },
        "boundary": {"investment_advice": False, "trading_allowed": False},
    }
