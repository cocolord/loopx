from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlparse

from ..file_lock import exclusive_file_lock
from .runtime import (
    _resolved_active_extension,
    extension_catalog_entries,
    run_standalone_extension,
)


DECISION_RESEARCH_VIEW_SCHEMA_VERSION = "decision_research_dashboard_v0"
EXTENSION_PRESENTATION_PROJECTION_SCHEMA_VERSION = (
    "extension_presentation_projection_v0"
)
EXTENSION_PROJECTION_SURFACE_SCHEMA_VERSION = "extension_projection_surface_v0"
EXTENSION_PRESENTATION_SURFACES_SCHEMA_VERSION = (
    "extension_presentation_surfaces_v0"
)
EXTENSION_PROJECTION_PUBLISH_RECEIPT_SCHEMA_VERSION = (
    "extension_projection_publish_receipt_v0"
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ANCHOR_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MARKUP_RE = re.compile(r"<[^>]*>|javascript:", re.IGNORECASE)
_LOCAL_PATH_RE = re.compile(
    r"(?:^|[\s(])(?:~[/\\]|/+(?:Users|home|tmp|private|var|etc|opt)/|"
    r"[A-Za-z]:[\\/])"
)
_CREDENTIAL_RE = re.compile(
    r"(?:bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:api[_ -]?key|access[_ -]?token|secret|password)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_FORBIDDEN_KEY_TOKENS = {
    "account_id",
    "account_number",
    "access_token",
    "api_key",
    "credential",
    "cookie",
    "order_id",
    "order_request",
    "portfolio",
    "portfolio_holdings",
    "position_size",
    "raw_provider",
    "raw_request",
    "raw_response",
    "secret",
    "token",
}
_DECISIONS = {
    "selected",
    "rejected",
    "insufficient_evidence",
    "blocked",
    "superseded",
}
_CONFIDENCE = {"high", "medium", "low"}
_TONES = {"neutral", "success", "warning", "info", "danger"}
_LAYER_STATES = {
    "supported",
    "partial",
    "rejected",
    "insufficient_evidence",
    "blocked",
    "pending",
}
_GATE_STATES = {
    "passed",
    "failed",
    "pending",
    "blocked",
    "insufficient_evidence",
    "partial",
}
_EVENT_STATES = {
    "pending",
    "partially_adjudicated",
    "selected",
    "rejected",
    "insufficient_evidence",
    "blocked",
    "superseded",
}


def _record(
    value: Any,
    *,
    context: str,
    allowed: set[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    unsupported = sorted(set(value) - allowed)
    if unsupported:
        raise ValueError(f"{context} contains unsupported keys {unsupported}")
    return value


def _plain_text(
    value: Any,
    *,
    context: str,
    max_length: int = 600,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be plain text")
    text = value.strip()
    if not text and not allow_empty:
        raise ValueError(f"{context} must be non-empty plain text")
    if len(text) > max_length:
        raise ValueError(f"{context} must contain at most {max_length} characters")
    if "\x00" in text or _MARKUP_RE.search(text):
        raise ValueError(f"{context} must be plain text without markup")
    if _LOCAL_PATH_RE.search(text):
        raise ValueError(f"{context} must not contain a local path")
    if _CREDENTIAL_RE.search(text):
        raise ValueError(f"{context} must not contain credential material")
    return text


def _required_text(
    record: Mapping[str, Any],
    key: str,
    *,
    context: str,
    max_length: int = 600,
) -> str:
    return _plain_text(
        record.get(key),
        context=f"{context}.{key}",
        max_length=max_length,
    )


def _identifier(value: Any, *, context: str) -> str:
    text = _plain_text(value, context=context, max_length=128)
    if not _ID_RE.fullmatch(text):
        raise ValueError(f"{context} must be a stable identifier")
    return text


def _enum(value: Any, allowed: set[str], *, context: str) -> str:
    text = _plain_text(value, context=context, max_length=64)
    if text not in allowed:
        raise ValueError(f"{context} must be one of {sorted(allowed)}")
    return text


def _boolean(value: Any, *, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value


def _number(value: Any, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric")
    return float(value)


def _iso_value(value: Any, *, context: str, date_only_allowed: bool = True) -> str:
    text = _plain_text(value, context=context, max_length=40)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        if "T" in normalized:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                raise ValueError
        elif date_only_allowed:
            date.fromisoformat(normalized)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"{context} must be a valid ISO-8601 value") from exc
    return text


def _bounded_list(
    value: Any,
    *,
    context: str,
    minimum: int = 0,
    maximum: int,
) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    if len(value) < minimum:
        raise ValueError(f"{context} requires at least {minimum} items")
    if len(value) > maximum:
        raise ValueError(f"{context} must contain at most {maximum} items")
    return value


def _text_list(
    value: Any,
    *,
    context: str,
    minimum: int = 0,
    maximum: int,
    item_limit: int = 600,
) -> list[str]:
    return [
        _plain_text(
            item,
            context=f"{context}[{index}]",
            max_length=item_limit,
        )
        for index, item in enumerate(
            _bounded_list(
                value,
                context=context,
                minimum=minimum,
                maximum=maximum,
            )
        )
    ]


def _assert_allowed_keys_recursively(value: Any, *, context: str = "view") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(
                normalized == token or normalized.startswith(f"{token}_")
                for token in _FORBIDDEN_KEY_TOKENS
            ):
                if normalized not in {
                    "raw_provider_payload_recorded",
                    "private_source_content_read",
                }:
                    raise ValueError(f"{context} contains forbidden key `{key}`")
            _assert_allowed_keys_recursively(child, context=f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_allowed_keys_recursively(child, context=f"{context}[{index}]")
    elif isinstance(value, str):
        _plain_text(value, context=context, max_length=2_000, allow_empty=True)


def _evidence_reference(value: Any, *, context: str) -> str:
    reference = _plain_text(value, context=context, max_length=500)
    if "://" not in reference:
        if not _ID_RE.fullmatch(reference):
            raise ValueError(f"{context} must be a compact evidence reference")
        return reference
    parsed = urlparse(reference)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname
        or hostname in {"localhost", "127.0.0.1", "::1"}
        or hostname.endswith((".internal", ".local"))
        or hostname.startswith(("private.", "internal."))
        or parsed.username
        or parsed.password
    ):
        raise ValueError(f"{context} contains an unsafe evidence reference")
    return reference


def _identity(value: Any) -> dict[str, Any]:
    record = _record(
        value,
        context="view.identity",
        allowed={"title", "subtitle", "as_of", "evidence_cutoff"},
    )
    return {
        "title": _required_text(record, "title", context="view.identity", max_length=160),
        "subtitle": _required_text(
            record,
            "subtitle",
            context="view.identity",
            max_length=240,
        ),
        "as_of": _iso_value(
            record.get("as_of"),
            context="view.identity.as_of",
            date_only_allowed=False,
        ),
        "evidence_cutoff": _iso_value(
            record.get("evidence_cutoff"),
            context="view.identity.evidence_cutoff",
        ),
    }


def _adjudication(value: Any) -> dict[str, Any]:
    record = _record(
        value,
        context="view.adjudication",
        allowed={"status", "label", "summary", "confidence"},
    )
    return {
        "status": _enum(
            record.get("status"),
            _DECISIONS,
            context="view.adjudication.status",
        ),
        "label": _required_text(
            record,
            "label",
            context="view.adjudication",
            max_length=120,
        ),
        "summary": _required_text(
            record,
            "summary",
            context="view.adjudication",
            max_length=800,
        ),
        "confidence": _enum(
            record.get("confidence"),
            _CONFIDENCE,
            context="view.adjudication.confidence",
        ),
    }


def _metrics(value: Any) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for index, item in enumerate(
        _bounded_list(value, context="view.metrics", minimum=1, maximum=12)
    ):
        context = f"view.metrics[{index}]"
        record = _record(
            item,
            context=context,
            allowed={"id", "label", "value", "detail", "tone"},
        )
        metrics.append(
            {
                "id": _identifier(record.get("id"), context=f"{context}.id"),
                "label": _required_text(record, "label", context=context, max_length=80),
                "value": _required_text(record, "value", context=context, max_length=120),
                "detail": _required_text(
                    record,
                    "detail",
                    context=context,
                    max_length=400,
                ),
                "tone": _enum(record.get("tone"), _TONES, context=f"{context}.tone"),
            }
        )
    return metrics


def _dashboard_summaries(value: Any) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, item in enumerate(
        _bounded_list(value, context="view.dashboard_summaries", maximum=3)
    ):
        context = f"view.dashboard_summaries[{index}]"
        record = _record(
            item,
            context=context,
            allowed={
                "id",
                "label",
                "title",
                "summary",
                "tone",
                "destination_anchor",
            },
        )
        destination_anchor = _required_text(
            record,
            "destination_anchor",
            context=context,
            max_length=80,
        )
        if not _ANCHOR_RE.fullmatch(destination_anchor):
            raise ValueError(
                f"{context}.destination_anchor must be a lower-kebab anchor"
            )
        summaries.append(
            {
                "id": _identifier(record.get("id"), context=f"{context}.id"),
                "label": _required_text(record, "label", context=context, max_length=80),
                "title": _required_text(record, "title", context=context, max_length=160),
                "summary": _required_text(
                    record,
                    "summary",
                    context=context,
                    max_length=500,
                ),
                "tone": _enum(record.get("tone"), _TONES, context=f"{context}.tone"),
                "destination_anchor": destination_anchor,
            }
        )
    return summaries


def _layers(value: Any) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    seen_orders: set[int] = set()
    for index, item in enumerate(
        _bounded_list(value, context="view.layers", minimum=1, maximum=12)
    ):
        context = f"view.layers[{index}]"
        record = _record(
            item,
            context=context,
            allowed={"id", "order", "label", "status", "summary", "evidence_points"},
        )
        order = record.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise ValueError(f"{context}.order must be a positive integer")
        if order in seen_orders:
            raise ValueError("view.layers order values must be unique")
        seen_orders.add(order)
        layers.append(
            {
                "id": _identifier(record.get("id"), context=f"{context}.id"),
                "order": order,
                "label": _required_text(record, "label", context=context, max_length=100),
                "status": _enum(
                    record.get("status"),
                    _LAYER_STATES,
                    context=f"{context}.status",
                ),
                "summary": _required_text(
                    record,
                    "summary",
                    context=context,
                    max_length=600,
                ),
                "evidence_points": _text_list(
                    record.get("evidence_points"),
                    context=f"{context}.evidence_points",
                    minimum=1,
                    maximum=12,
                ),
            }
        )
    return sorted(layers, key=lambda item: item["order"])


def _observations(value: Any, *, entity_context: str) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for index, item in enumerate(
        _bounded_list(
            value,
            context=f"{entity_context}.observations",
            minimum=1,
            maximum=20,
        )
    ):
        context = f"{entity_context}.observations[{index}]"
        record = _record(
            item,
            context=context,
            allowed={
                "id",
                "label",
                "kind",
                "value",
                "as_of",
                "source_ref",
                "source_type",
                "confidence",
                "invalidation",
            },
        )
        kind = _enum(
            record.get("kind"),
            {
                "observation_range",
                "current_fact",
                "historical_fact",
                "management_guidance",
                "analyst_estimate",
                "agent_inference",
            },
            context=f"{context}.kind",
        )
        invalidation = _required_text(
            record,
            "invalidation",
            context=context,
            max_length=500,
        )
        observations.append(
            {
                "id": _identifier(record.get("id"), context=f"{context}.id"),
                "label": _required_text(record, "label", context=context, max_length=100),
                "kind": kind,
                "value": _required_text(record, "value", context=context, max_length=200),
                "as_of": _iso_value(record.get("as_of"), context=f"{context}.as_of"),
                "source_ref": _evidence_reference(
                    record.get("source_ref"),
                    context=f"{context}.source_ref",
                ),
                "source_type": _enum(
                    record.get("source_type"),
                    {
                        "company_filing",
                        "company_guidance",
                        "regulator",
                        "exchange",
                        "market_data",
                        "industry_source",
                        "high_quality_media",
                        "community_signal",
                        "agent_analysis",
                    },
                    context=f"{context}.source_type",
                ),
                "confidence": _enum(
                    record.get("confidence"),
                    _CONFIDENCE,
                    context=f"{context}.confidence",
                ),
                "invalidation": invalidation,
            }
        )
    return observations


def _scenario_estimates(
    value: Any,
    *,
    entity_context: str,
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(
        _bounded_list(
            value,
            context=f"{entity_context}.scenario_estimates",
            minimum=3,
            maximum=3,
        )
    ):
        context = f"{entity_context}.scenario_estimates[{index}]"
        record = _record(
            item,
            context=context,
            allowed={
                "scenario",
                "label",
                "value",
                "horizon",
                "probability",
                "assumptions",
            },
        )
        scenario = _enum(
            record.get("scenario"),
            {"bull", "base", "bear"},
            context=f"{context}.scenario",
        )
        if scenario in seen:
            raise ValueError(f"{entity_context}.scenario_estimates must be unique")
        seen.add(scenario)
        probability = _number(
            record.get("probability"),
            context=f"{context}.probability",
        )
        if probability < 0 or probability > 1:
            raise ValueError(f"{context}.probability must be between 0 and 1")
        scenarios.append(
            {
                "scenario": scenario,
                "label": _required_text(record, "label", context=context, max_length=100),
                "value": _required_text(record, "value", context=context, max_length=160),
                "horizon": _required_text(
                    record,
                    "horizon",
                    context=context,
                    max_length=100,
                ),
                "probability": probability,
                "assumptions": _text_list(
                    record.get("assumptions"),
                    context=f"{context}.assumptions",
                    minimum=1,
                    maximum=8,
                ),
            }
        )
    if seen != {"bull", "base", "bear"}:
        raise ValueError(
            f"{entity_context}.scenario_estimates must contain bull, base and bear"
        )
    if abs(sum(item["probability"] for item in scenarios) - 1.0) > 0.000001:
        raise ValueError(
            f"{entity_context}.scenario_estimates probabilities must sum to 1"
        )
    return scenarios


def _entities(value: Any) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for index, item in enumerate(
        _bounded_list(value, context="view.entities", maximum=24)
    ):
        context = f"view.entities[{index}]"
        record = _record(
            item,
            context=context,
            allowed={
                "entity_id",
                "symbol",
                "display_name",
                "classification",
                "status",
                "confidence",
                "inference",
                "observations",
                "scenario_estimates",
                "counterevidence",
                "thesis_breakers",
                "next_events",
            },
        )
        entities.append(
            {
                "entity_id": _identifier(
                    record.get("entity_id"),
                    context=f"{context}.entity_id",
                ),
                "symbol": _required_text(
                    record,
                    "symbol",
                    context=context,
                    max_length=24,
                ),
                "display_name": _required_text(
                    record,
                    "display_name",
                    context=context,
                    max_length=160,
                ),
                "classification": _required_text(
                    record,
                    "classification",
                    context=context,
                    max_length=80,
                ),
                "status": _enum(
                    record.get("status"),
                    _DECISIONS,
                    context=f"{context}.status",
                ),
                "confidence": _enum(
                    record.get("confidence"),
                    _CONFIDENCE,
                    context=f"{context}.confidence",
                ),
                "inference": _required_text(
                    record,
                    "inference",
                    context=context,
                    max_length=700,
                ),
                "observations": _observations(
                    record.get("observations"),
                    entity_context=context,
                ),
                "scenario_estimates": _scenario_estimates(
                    record.get("scenario_estimates"),
                    entity_context=context,
                ),
                "counterevidence": _text_list(
                    record.get("counterevidence"),
                    context=f"{context}.counterevidence",
                    minimum=1,
                    maximum=12,
                ),
                "thesis_breakers": _text_list(
                    record.get("thesis_breakers"),
                    context=f"{context}.thesis_breakers",
                    minimum=1,
                    maximum=12,
                ),
                "next_events": _text_list(
                    record.get("next_events"),
                    context=f"{context}.next_events",
                    maximum=12,
                ),
            }
        )
    return entities


def _research_ledger(value: Any) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for index, item in enumerate(
        _bounded_list(value, context="view.research_ledger", maximum=40)
    ):
        context = f"view.research_ledger[{index}]"
        record = _record(
            item,
            context=context,
            allowed={
                "case_id",
                "label",
                "gate_states",
                "decision",
                "summary",
                "evidence_refs",
            },
        )
        gate_states: list[dict[str, Any]] = []
        for gate_index, gate in enumerate(
            _bounded_list(
                record.get("gate_states"),
                context=f"{context}.gate_states",
                minimum=1,
                maximum=16,
            )
        ):
            gate_context = f"{context}.gate_states[{gate_index}]"
            gate_record = _record(
                gate,
                context=gate_context,
                allowed={"gate_id", "label", "status", "summary"},
            )
            gate_states.append(
                {
                    "gate_id": _identifier(
                        gate_record.get("gate_id"),
                        context=f"{gate_context}.gate_id",
                    ),
                    "label": _required_text(
                        gate_record,
                        "label",
                        context=gate_context,
                        max_length=100,
                    ),
                    "status": _enum(
                        gate_record.get("status"),
                        _GATE_STATES,
                        context=f"{gate_context}.status",
                    ),
                    "summary": _required_text(
                        gate_record,
                        "summary",
                        context=gate_context,
                        max_length=500,
                    ),
                }
            )
        evidence_refs = [
            _evidence_reference(
                reference,
                context=f"{context}.evidence_refs[{reference_index}]",
            )
            for reference_index, reference in enumerate(
                _bounded_list(
                    record.get("evidence_refs"),
                    context=f"{context}.evidence_refs",
                    minimum=1,
                    maximum=20,
                )
            )
        ]
        ledger.append(
            {
                "case_id": _identifier(
                    record.get("case_id"),
                    context=f"{context}.case_id",
                ),
                "label": _required_text(record, "label", context=context, max_length=180),
                "gate_states": gate_states,
                "decision": _enum(
                    record.get("decision"),
                    _DECISIONS,
                    context=f"{context}.decision",
                ),
                "summary": _required_text(
                    record,
                    "summary",
                    context=context,
                    max_length=700,
                ),
                "evidence_refs": evidence_refs,
            }
        )
    return ledger


def _event_gates(value: Any) -> list[dict[str, Any]]:
    event_gates: list[dict[str, Any]] = []
    for index, item in enumerate(
        _bounded_list(value, context="view.event_gates", maximum=32)
    ):
        context = f"view.event_gates[{index}]"
        record = _record(
            item,
            context=context,
            allowed={
                "event_id",
                "label",
                "status",
                "observation_window",
                "frozen_hypothesis",
                "observables",
                "current_evidence",
                "supports",
                "refutes",
                "thesis_breakers",
                "next_review",
            },
        )
        event_gates.append(
            {
                "event_id": _identifier(
                    record.get("event_id"),
                    context=f"{context}.event_id",
                ),
                "label": _required_text(record, "label", context=context, max_length=180),
                "status": _enum(
                    record.get("status"),
                    _EVENT_STATES,
                    context=f"{context}.status",
                ),
                "observation_window": _required_text(
                    record,
                    "observation_window",
                    context=context,
                    max_length=240,
                ),
                "frozen_hypothesis": _required_text(
                    record,
                    "frozen_hypothesis",
                    context=context,
                    max_length=700,
                ),
                "observables": _text_list(
                    record.get("observables"),
                    context=f"{context}.observables",
                    minimum=1,
                    maximum=16,
                ),
                "current_evidence": _text_list(
                    record.get("current_evidence"),
                    context=f"{context}.current_evidence",
                    maximum=16,
                ),
                "supports": _text_list(
                    record.get("supports"),
                    context=f"{context}.supports",
                    minimum=1,
                    maximum=12,
                ),
                "refutes": _text_list(
                    record.get("refutes"),
                    context=f"{context}.refutes",
                    minimum=1,
                    maximum=12,
                ),
                "thesis_breakers": _text_list(
                    record.get("thesis_breakers"),
                    context=f"{context}.thesis_breakers",
                    minimum=1,
                    maximum=12,
                ),
                "next_review": _required_text(
                    record,
                    "next_review",
                    context=context,
                    max_length=240,
                ),
            }
        )
    return event_gates


def _method_state(value: Any) -> dict[str, Any]:
    record = _record(
        value,
        context="view.method_state",
        allowed={"revision", "lifecycle_state", "active_method_changed", "summary"},
    )
    return {
        "revision": _identifier(
            record.get("revision"),
            context="view.method_state.revision",
        ),
        "lifecycle_state": _identifier(
            record.get("lifecycle_state"),
            context="view.method_state.lifecycle_state",
        ),
        "active_method_changed": _boolean(
            record.get("active_method_changed"),
            context="view.method_state.active_method_changed",
        ),
        "summary": _required_text(
            record,
            "summary",
            context="view.method_state",
            max_length=500,
        ),
    }


def _boundary(value: Any) -> dict[str, Any]:
    record = _record(
        value,
        context="view.boundary",
        allowed={
            "research_aid_only",
            "investment_advice",
            "trading_allowed",
            "raw_provider_payload_recorded",
            "private_source_content_read",
        },
    )
    result = {
        key: _boolean(record.get(key), context=f"view.boundary.{key}")
        for key in (
            "research_aid_only",
            "investment_advice",
            "trading_allowed",
            "raw_provider_payload_recorded",
            "private_source_content_read",
        )
    }
    if result != {
        "research_aid_only": True,
        "investment_advice": False,
        "trading_allowed": False,
        "raw_provider_payload_recorded": False,
        "private_source_content_read": False,
    }:
        raise ValueError("view.boundary violates the research boundary")
    return result


def validate_decision_research_view(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one domain-neutral, presentation-oriented research view."""

    _assert_allowed_keys_recursively(value)
    record = _record(
        value,
        context="view",
        allowed={
            "identity",
            "adjudication",
            "metrics",
            "dashboard_summaries",
            "layers",
            "entities",
            "research_ledger",
            "event_gates",
            "method_state",
            "boundary",
        },
    )
    return {
        "identity": _identity(record.get("identity")),
        "adjudication": _adjudication(record.get("adjudication")),
        "metrics": _metrics(record.get("metrics")),
        "dashboard_summaries": _dashboard_summaries(
            record.get("dashboard_summaries")
        ),
        "layers": _layers(record.get("layers")),
        "entities": _entities(record.get("entities")),
        "research_ledger": _research_ledger(record.get("research_ledger")),
        "event_gates": _event_gates(record.get("event_gates")),
        "method_state": _method_state(record.get("method_state")),
        "boundary": _boundary(record.get("boundary")),
    }


def _sha256(value: Any, *, context: str) -> str:
    text = _plain_text(value, context=context, max_length=64)
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{context} must be a lowercase SHA-256")
    return text


def validate_provider_presentation_projection(
    value: Mapping[str, Any],
    *,
    declared_surface: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate provider-owned fields before Core binds lifecycle identity."""

    record = _record(
        value,
        context="presentation_projection",
        allowed={
            "schema_version",
            "surface_id",
            "goal_id",
            "generated_at",
            "review_due_at",
            "lineage",
            "view_schema",
            "view",
        },
    )
    if (
        record.get("schema_version")
        != EXTENSION_PRESENTATION_PROJECTION_SCHEMA_VERSION
    ):
        raise ValueError(
            "presentation_projection has unsupported schema_version"
        )
    surface_id = _identifier(
        record.get("surface_id"),
        context="presentation_projection.surface_id",
    )
    if surface_id != declared_surface.get("id"):
        raise ValueError("presentation_projection surface_id is not declared")
    view_schema = _plain_text(
        record.get("view_schema"),
        context="presentation_projection.view_schema",
        max_length=80,
    )
    if view_schema != declared_surface.get("view_schema"):
        raise ValueError("presentation_projection view_schema does not match manifest")
    review_due_raw = record.get("review_due_at")
    review_due_at = (
        None
        if review_due_raw is None
        else _iso_value(
            review_due_raw,
            context="presentation_projection.review_due_at",
            date_only_allowed=False,
        )
    )
    lineage = _record(
        record.get("lineage"),
        context="presentation_projection.lineage",
        allowed={
            "source_id",
            "version",
            "row_lifecycle",
            "supersedes",
            "superseded_by",
        },
    )
    version = lineage.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("presentation_projection.lineage.version must be positive")
    row_lifecycle = _enum(
        lineage.get("row_lifecycle"),
        {"active"},
        context="presentation_projection.lineage.row_lifecycle",
    )
    supersedes = [
        _identifier(
            item,
            context=f"presentation_projection.lineage.supersedes[{index}]",
        )
        for index, item in enumerate(
            _bounded_list(
                lineage.get("supersedes"),
                context="presentation_projection.lineage.supersedes",
                maximum=20,
            )
        )
    ]
    superseded_by_raw = lineage.get("superseded_by")
    superseded_by = (
        None
        if superseded_by_raw is None
        else _identifier(
            superseded_by_raw,
            context="presentation_projection.lineage.superseded_by",
        )
    )
    return {
        "schema_version": EXTENSION_PRESENTATION_PROJECTION_SCHEMA_VERSION,
        "surface_id": surface_id,
        "goal_id": _identifier(
            record.get("goal_id"),
            context="presentation_projection.goal_id",
        ),
        "generated_at": _iso_value(
            record.get("generated_at"),
            context="presentation_projection.generated_at",
            date_only_allowed=False,
        ),
        "review_due_at": review_due_at,
        "lineage": {
            "source_id": _identifier(
                lineage.get("source_id"),
                context="presentation_projection.lineage.source_id",
            ),
            "version": version,
            "row_lifecycle": row_lifecycle,
            "supersedes": supersedes,
            "superseded_by": superseded_by,
        },
        "view_schema": view_schema,
        "view": validate_decision_research_view(record.get("view")),
    }


def validate_projection_hash(value: Any, *, context: str) -> str:
    return _sha256(value, context=context)


def default_extension_projection_root(state_file: str | Path) -> Path:
    return Path(state_file).expanduser().parent / "projections"


def _declared_surface(
    manifest: Mapping[str, Any],
    *,
    extension_id: str,
    surface_id: str,
) -> Mapping[str, Any]:
    surfaces = manifest.get("presentation_surfaces")
    if not isinstance(surfaces, list):
        raise ValueError("extension active manifest has invalid presentation surfaces")
    matching = [
        item
        for item in surfaces
        if isinstance(item, Mapping) and item.get("id") == surface_id
    ]
    if not matching:
        raise ValueError(
            f"extension `{extension_id}` does not declare presentation surface "
            f"`{surface_id}`"
        )
    if len(matching) != 1:
        raise ValueError("extension active manifest has duplicate presentation surfaces")
    return matching[0]


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _envelope_hash(value: Mapping[str, Any]) -> str:
    payload = {key: child for key, child in value.items() if key != "payload_sha256"}
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _validate_persisted_envelope(
    value: Any,
    *,
    extension_id: str,
    revision: str,
    declared_surface: Mapping[str, Any],
) -> dict[str, Any]:
    record = _record(
        value,
        context="projection_envelope",
        allowed={
            "schema_version",
            "extension_id",
            "extension_revision",
            "surface_id",
            "surface_kind",
            "view_schema",
            "visibility",
            "goal_id",
            "generated_at",
            "review_due_at",
            "payload_sha256",
            "lineage",
            "view",
        },
    )
    if record.get("schema_version") != EXTENSION_PROJECTION_SURFACE_SCHEMA_VERSION:
        raise ValueError("projection_envelope has unsupported schema_version")
    expected = {
        "extension_id": extension_id,
        "extension_revision": revision,
        "surface_id": declared_surface.get("id"),
        "surface_kind": declared_surface.get("kind"),
        "view_schema": declared_surface.get("view_schema"),
        "visibility": declared_surface.get("visibility"),
    }
    for key, expected_value in expected.items():
        if record.get(key) != expected_value:
            raise ValueError(f"projection_envelope.{key} does not match active state")
    provider_projection = validate_provider_presentation_projection(
        {
            "schema_version": EXTENSION_PRESENTATION_PROJECTION_SCHEMA_VERSION,
            "surface_id": record.get("surface_id"),
            "goal_id": record.get("goal_id"),
            "generated_at": record.get("generated_at"),
            "review_due_at": record.get("review_due_at"),
            "lineage": record.get("lineage"),
            "view_schema": record.get("view_schema"),
            "view": record.get("view"),
        },
        declared_surface=declared_surface,
    )
    envelope = {
        "schema_version": EXTENSION_PROJECTION_SURFACE_SCHEMA_VERSION,
        **expected,
        "goal_id": provider_projection["goal_id"],
        "generated_at": provider_projection["generated_at"],
        "review_due_at": provider_projection["review_due_at"],
        "lineage": provider_projection["lineage"],
        "view": provider_projection["view"],
    }
    payload_sha256 = validate_projection_hash(
        record.get("payload_sha256"),
        context="projection_envelope.payload_sha256",
    )
    if _envelope_hash(envelope) != payload_sha256:
        raise ValueError("projection_envelope payload_sha256 does not match content")
    envelope["payload_sha256"] = payload_sha256
    return envelope


def _atomic_write_projection(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                dict(payload),
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def publish_extension_projection(
    extension_id: str,
    surface_id: str,
    *,
    state_file: str | Path,
    request: Mapping[str, Any],
    execute: bool = False,
) -> dict[str, Any]:
    """Run one ready standalone provider and atomically publish its declared view."""

    state_path = Path(state_file).expanduser()
    active_revision, verified_entrypoint, manifest = _resolved_active_extension(
        extension_id,
        state_file=state_path,
    )
    surface = _declared_surface(
        manifest,
        extension_id=extension_id,
        surface_id=surface_id,
    )
    receipt: dict[str, Any] = {
        "ok": True,
        "schema_version": EXTENSION_PROJECTION_PUBLISH_RECEIPT_SCHEMA_VERSION,
        "operation": "publish_projection",
        "extension_id": extension_id,
        "surface_id": surface_id,
        "revision": active_revision,
        "dry_run": not execute,
        "executed": False,
        "status": "ready" if not execute else "running",
    }
    if not execute:
        return receipt

    runtime_receipt = run_standalone_extension(
        extension_id,
        state_file=state_path,
        request=request,
        execute=True,
    )
    if not runtime_receipt.get("ok") or runtime_receipt.get("status") != "succeeded":
        raise ValueError(
            f"extension `{extension_id}` provider did not produce a successful result"
        )
    provider_result = runtime_receipt.get("provider_result")
    if not isinstance(provider_result, Mapping):
        raise ValueError("extension provider result must be an object")
    provider_projection = validate_provider_presentation_projection(
        provider_result.get("presentation_projection"),
        declared_surface=surface,
    )

    confirmed_revision, confirmed_entrypoint, confirmed_manifest = (
        _resolved_active_extension(extension_id, state_file=state_path)
    )
    if (
        confirmed_revision != active_revision
        or confirmed_entrypoint.identity != verified_entrypoint.identity
    ):
        raise ValueError(
            f"extension `{extension_id}` lifecycle changed during projection publication"
        )
    confirmed_surface = _declared_surface(
        confirmed_manifest,
        extension_id=extension_id,
        surface_id=surface_id,
    )
    if dict(confirmed_surface) != dict(surface):
        raise ValueError(
            f"extension `{extension_id}` surface changed during projection publication"
        )

    envelope: dict[str, Any] = {
        "schema_version": EXTENSION_PROJECTION_SURFACE_SCHEMA_VERSION,
        "extension_id": extension_id,
        "extension_revision": active_revision,
        "surface_id": surface_id,
        "surface_kind": surface["kind"],
        "view_schema": surface["view_schema"],
        "visibility": surface["visibility"],
        "goal_id": provider_projection["goal_id"],
        "generated_at": provider_projection["generated_at"],
        "review_due_at": provider_projection["review_due_at"],
        "lineage": provider_projection["lineage"],
        "view": provider_projection["view"],
    }
    envelope["payload_sha256"] = _envelope_hash(envelope)
    projection_path = (
        default_extension_projection_root(state_path)
        / extension_id
        / f"{surface_id}.json"
    )
    with exclusive_file_lock(projection_path):
        final_revision, final_entrypoint, final_manifest = _resolved_active_extension(
            extension_id,
            state_file=state_path,
        )
        if (
            final_revision != active_revision
            or final_entrypoint.identity != verified_entrypoint.identity
            or dict(
                _declared_surface(
                    final_manifest,
                    extension_id=extension_id,
                    surface_id=surface_id,
                )
            )
            != dict(surface)
        ):
            raise ValueError(
                f"extension `{extension_id}` lifecycle changed before projection write"
            )
        _atomic_write_projection(projection_path, envelope)
        try:
            readback_raw = json.loads(projection_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("published projection readback is unreadable") from exc
        readback = _validate_persisted_envelope(
            readback_raw,
            extension_id=extension_id,
            revision=active_revision,
            declared_surface=surface,
        )
        if readback != envelope:
            raise ValueError("published projection readback does not match exact payload")

    return {
        **receipt,
        "executed": True,
        "status": "published",
        "payload_sha256": envelope["payload_sha256"],
        "readback_verified": True,
        "entity_count": len(envelope["view"]["entities"]),
        "event_gate_count": len(envelope["view"]["event_gates"]),
        "ledger_count": len(envelope["view"]["research_ledger"]),
    }


def _surface_status_item(
    *,
    extension_id: str,
    revision: str,
    surface: Mapping[str, Any],
    state: str,
    diagnostic: str | None = None,
    envelope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "extension_id": extension_id,
        "extension_revision": revision,
        "surface_id": surface["id"],
        "surface_kind": surface["kind"],
        "title": surface["title"],
        "view_schema": surface["view_schema"],
        "visibility": surface["visibility"],
        "state": state,
        "goal_id": envelope.get("goal_id") if envelope else None,
        "generated_at": envelope.get("generated_at") if envelope else None,
        "review_due_at": envelope.get("review_due_at") if envelope else None,
        "diagnostic": diagnostic,
        "empty_state_title": surface["empty_state_title"],
        "empty_state_detail": surface["empty_state_detail"],
    }
    if envelope is not None and state in {"ready", "review_due"}:
        item["view"] = envelope["view"]
    return item


def _review_due(
    review_due_at: str | None,
    *,
    now: datetime,
) -> bool:
    if review_due_at is None:
        return False
    normalized = (
        review_due_at[:-1] + "+00:00"
        if review_due_at.endswith("Z")
        else review_due_at
    )
    deadline = datetime.fromisoformat(normalized)
    return deadline <= now


def _projection_diagnostic(exc: ValueError) -> str:
    message = str(exc)
    if "payload_sha256" in message:
        return "projection_hash_invalid"
    if "schema_version" in message:
        return "projection_schema_invalid"
    if "local path" in message or "credential" in message or "forbidden key" in message:
        return "projection_boundary_invalid"
    return "projection_content_invalid"


def collect_active_extension_presentation_surfaces(
    *,
    state_file: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read active, doctor-ready surface declarations and revision-bound data."""

    state_path = Path(state_file).expanduser()
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        raise ValueError("presentation surface collection `now` must be timezone-aware")
    items: list[dict[str, Any]] = []
    for manifest in extension_catalog_entries(state_file=state_path):
        provider = manifest.get("provider")
        if not isinstance(provider, Mapping) or provider.get("ready") is not True:
            continue
        extension_id = str(provider.get("id") or "")
        revision = str(provider.get("active_revision") or "")
        surfaces = manifest.get("presentation_surfaces")
        if not isinstance(surfaces, list):
            continue
        for surface in surfaces:
            if not isinstance(surface, Mapping):
                continue
            projection_path = (
                default_extension_projection_root(state_path)
                / extension_id
                / f"{surface['id']}.json"
            )
            if not projection_path.exists():
                items.append(
                    _surface_status_item(
                        extension_id=extension_id,
                        revision=revision,
                        surface=surface,
                        state="empty",
                    )
                )
                continue
            try:
                raw = json.loads(projection_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                items.append(
                    _surface_status_item(
                        extension_id=extension_id,
                        revision=revision,
                        surface=surface,
                        state="invalid",
                        diagnostic="projection_unreadable",
                    )
                )
                continue
            if (
                isinstance(raw, Mapping)
                and raw.get("extension_revision") != revision
            ):
                items.append(
                    _surface_status_item(
                        extension_id=extension_id,
                        revision=revision,
                        surface=surface,
                        state="empty",
                    )
                )
                continue
            try:
                envelope = _validate_persisted_envelope(
                    raw,
                    extension_id=extension_id,
                    revision=revision,
                    declared_surface=surface,
                )
            except ValueError as exc:
                items.append(
                    _surface_status_item(
                        extension_id=extension_id,
                        revision=revision,
                        surface=surface,
                        state="invalid",
                        diagnostic=_projection_diagnostic(exc),
                    )
                )
                continue
            state = (
                "review_due"
                if _review_due(envelope["review_due_at"], now=observed_at)
                else "ready"
            )
            items.append(
                _surface_status_item(
                    extension_id=extension_id,
                    revision=revision,
                    surface=surface,
                    state=state,
                    envelope=envelope,
                )
            )

    counts = {
        state: sum(item["state"] == state for item in items)
        for state in ("ready", "review_due", "empty", "invalid")
    }
    return {
        "schema_version": EXTENSION_PRESENTATION_SURFACES_SCHEMA_VERSION,
        "count": len(items),
        "ready_count": counts["ready"],
        "review_due_count": counts["review_due"],
        "empty_count": counts["empty"],
        "invalid_count": counts["invalid"],
        "items": items,
    }
