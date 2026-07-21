from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any

from .execution_envelope import (
    build_extension_execution_envelope,
    extension_request_digest,
)


EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION = "loopx_extension_authority_decision_v0"
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_AUTHORITY_FIELDS = {
    "schema_version",
    "decision",
    "extension_id",
    "extension_revision",
    "protocol",
    "action",
    "scope",
    "permissions",
    "subject",
    "nonce",
    "expires_at",
    "request_digest",
}
_SUBJECT_FIELDS = {"agent_id", "goal_id"}
_RESERVED_REQUEST_FIELDS = {"authority_decision", "execution_envelope"}


def _token(value: object, label: str) -> str:
    token = str(value or "").strip()
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError(f"{label} must be a bounded execution token")
    return token


def _expiry(value: object) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("extension authority expires_at must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise ValueError("extension authority expires_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def extension_authority_request_digest(request: Mapping[str, Any]) -> str:
    if not isinstance(request, Mapping):
        raise ValueError("extension authority request must be an object")
    payload = {
        str(key): deepcopy(value)
        for key, value in request.items()
        if str(key) not in _RESERVED_REQUEST_FIELDS
    }
    return extension_request_digest(payload)


def validate_extension_authority_decision(
    raw: Mapping[str, Any],
    *,
    extension_id: str,
    extension_revision: str,
    protocol: str,
    required_permissions: Sequence[str],
    available_capabilities: Sequence[str],
    request: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("extension authority decision must be an object")
    authority = {str(key): deepcopy(value) for key, value in raw.items()}
    if set(authority) != _AUTHORITY_FIELDS:
        raise ValueError("extension authority decision fields do not match the schema")
    if authority.get("schema_version") != EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION:
        raise ValueError(
            "extension authority decision must use "
            f"{EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION}"
        )
    if authority.get("decision") != "allow":
        raise ValueError("extension authority decision must explicitly allow")
    if authority.get("extension_id") != extension_id:
        raise ValueError("extension authority extension_id does not match")
    if authority.get("extension_revision") != extension_revision:
        raise ValueError("extension authority extension_revision does not match")
    if authority.get("protocol") != protocol:
        raise ValueError("extension authority protocol does not match")
    _token(authority.get("action"), "extension authority action")
    scope = authority.get("scope")
    if not isinstance(scope, Mapping) or not scope:
        raise ValueError("extension authority scope must be a non-empty object")
    permissions = authority.get("permissions")
    expected_permissions = sorted({str(value) for value in required_permissions})
    if not isinstance(permissions, list) or permissions != expected_permissions:
        raise ValueError("extension authority permissions do not match the runtime")
    observed = {str(value).strip() for value in available_capabilities}
    missing = sorted(set(expected_permissions) - observed)
    if missing:
        raise ValueError(f"extension authority requires observed capabilities {missing}")
    subject = authority.get("subject")
    if not isinstance(subject, Mapping) or set(subject) != _SUBJECT_FIELDS:
        raise ValueError("extension authority subject fields do not match the schema")
    _token(subject.get("agent_id"), "extension authority subject.agent_id")
    _token(subject.get("goal_id"), "extension authority subject.goal_id")
    _token(authority.get("nonce"), "extension authority nonce")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if _expiry(authority.get("expires_at")) <= current:
        raise ValueError("extension authority decision has expired")
    if authority.get("request_digest") != extension_authority_request_digest(request):
        raise ValueError("extension authority request_digest does not match")
    return authority


def build_authorized_extension_request(
    request: Mapping[str, Any],
    *,
    authority_decision: Mapping[str, Any],
    extension_id: str,
    extension_revision: str,
) -> dict[str, Any]:
    if any(field in request for field in _RESERVED_REQUEST_FIELDS):
        raise ValueError("extension run input contains reserved authority fields")
    authorized = deepcopy(dict(request))
    authorized["authority_decision"] = deepcopy(dict(authority_decision))
    authorized["execution_envelope"] = build_extension_execution_envelope(
        action=str(authority_decision["action"]),
        scope=authority_decision["scope"],
        extension_id=extension_id,
        extension_revision=extension_revision,
        request=authorized,
    )
    return authorized
