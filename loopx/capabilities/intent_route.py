from __future__ import annotations

import re
import shlex
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


CAPABILITY_INTENT_ROUTE_SCHEMA_VERSION = "loopx_capability_intent_route_v0"
CAPABILITY_INTENT_GOAL_TEXT_TOKEN = "{goal_text}"
CAPABILITY_INTENT_ROUTE_FIELDS = frozenset(
    {
        "route_id",
        "match_kind",
        "aliases",
        "command_argv",
        "effect_class",
    }
)
CAPABILITY_INTENT_MATCH_KINDS = frozenset(
    {"normalized_prefix", "normalized_clause_prefix"}
)


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def normalize_capability_intent_routes(
    value: object,
    *,
    context: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a list")
    normalized_routes: list[dict[str, Any]] = []
    seen_route_ids: set[str] = set()
    for index, route_value in enumerate(value):
        route_context = f"{context}[{index}]"
        if not isinstance(route_value, Mapping):
            raise ValueError(f"{route_context} must be a mapping")
        unknown_fields = set(route_value) - CAPABILITY_INTENT_ROUTE_FIELDS
        if unknown_fields:
            raise ValueError(
                f"{route_context} has unsupported fields: "
                + ", ".join(sorted(str(field) for field in unknown_fields))
            )
        route_id = _required_string(
            route_value.get("route_id"),
            field=f"{route_context} route_id",
        )
        if route_id in seen_route_ids:
            raise ValueError(f"{context} has duplicate route_id `{route_id}`")
        seen_route_ids.add(route_id)
        match_kind = _required_string(
            route_value.get("match_kind"),
            field=f"{route_context} match_kind",
        )
        if match_kind not in CAPABILITY_INTENT_MATCH_KINDS:
            raise ValueError(
                f"{route_context} has unsupported match_kind `{match_kind}`"
            )
        aliases = route_value.get("aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"{route_context} requires non-empty aliases")
        normalized_aliases = [
            _required_string(alias, field=f"{route_context} alias")
            for alias in aliases
        ]
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise ValueError(f"{route_context} has duplicate aliases")
        command_argv = route_value.get("command_argv")
        if not isinstance(command_argv, list) or not command_argv:
            raise ValueError(f"{route_context} requires non-empty command_argv")
        normalized_argv = [
            _required_string(argument, field=f"{route_context} argument")
            for argument in command_argv
        ]
        if normalized_argv[0] != "{cli_bin}":
            raise ValueError(
                f"{route_context} command_argv must begin with `{{cli_bin}}`"
            )
        if normalized_argv.count(CAPABILITY_INTENT_GOAL_TEXT_TOKEN) != 1:
            raise ValueError(
                f"{route_context} command_argv must contain exactly one "
                f"`{CAPABILITY_INTENT_GOAL_TEXT_TOKEN}`"
            )
        normalized_routes.append(
            {
                "route_id": route_id,
                "match_kind": match_kind,
                "aliases": normalized_aliases,
                "command_argv": normalized_argv,
                "effect_class": _required_string(
                    route_value.get("effect_class") or "capability_entry",
                    field=f"{route_context} effect_class",
                ),
            }
        )
    return normalized_routes


def _normalized_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "\n".join(" ".join(line.split()) for line in normalized.splitlines()).strip()


def _matches(text: str, *, alias: str, match_kind: str) -> bool:
    if match_kind == "normalized_prefix":
        return text.startswith(alias)
    return any(
        clause.strip().startswith(alias)
        for clause in re.split(r"[。！？!?；;，,\n]+", text)
    )


def resolve_capability_intent_route_from_records(
    goal_text: str,
    *,
    records: Iterable[Mapping[str, Any]],
    cli_bin: str,
    runtime_root: str | None = None,
) -> dict[str, Any] | None:
    original_text = str(goal_text or "").strip()
    normalized_text = _normalized_text(original_text)
    if not normalized_text:
        return None
    normalized_runtime_root = (
        _required_string(runtime_root, field="runtime_root")
        if runtime_root is not None
        else None
    )

    matches: list[dict[str, Any]] = []
    for record in records:
        provider_state = record.get("provider_state")
        if not isinstance(provider_state, Mapping) or provider_state.get("ready") is not True:
            continue
        for route in record.get("intent_routes") or []:
            for raw_alias in route["aliases"]:
                alias = _normalized_text(raw_alias)
                if _matches(
                    normalized_text,
                    alias=alias,
                    match_kind=route["match_kind"],
                ):
                    matches.append(
                        {
                            "capability_id": record["id"],
                            "route_id": route["route_id"],
                            "matched_alias": raw_alias,
                            "normalized_alias": alias,
                            "match_kind": route["match_kind"],
                            "command_argv": route["command_argv"],
                            "effect_class": route["effect_class"],
                        }
                    )
    if not matches:
        return None
    capability_ids = sorted({str(match["capability_id"]) for match in matches})
    if len(capability_ids) != 1:
        raise ValueError(
            "ambiguous capability intent route; matched capabilities: "
            + ", ".join(capability_ids)
        )
    selected = max(matches, key=lambda match: len(str(match["normalized_alias"])))
    command_argv: list[str] = []
    for argument in selected["command_argv"]:
        if argument == "{cli_bin}":
            command_argv.append(str(cli_bin))
            if normalized_runtime_root is not None:
                command_argv.extend(["--runtime-root", normalized_runtime_root])
        elif argument == CAPABILITY_INTENT_GOAL_TEXT_TOKEN:
            command_argv.append(original_text)
        else:
            command_argv.append(str(argument))
    return {
        "schema_version": CAPABILITY_INTENT_ROUTE_SCHEMA_VERSION,
        "capability_id": selected["capability_id"],
        "route_id": selected["route_id"],
        "selection_source": "capability_catalog_intent_alias",
        "selection_reason_code": "explicit_capability_alias",
        "match_kind": selected["match_kind"],
        "matched_alias": selected["matched_alias"],
        "entry_command": shlex.join(command_argv),
        "effect_class": selected["effect_class"],
        "bypasses_generic_goal_start": True,
    }
