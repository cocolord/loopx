"""Core-owned capture, canonicalization, settlement and evaluator handoff.

There is deliberately no JSON receipt-import API. Each provenance receipt is
captured from a Goal-bound managed read-only invocation. The generator sees
that evidence but owns neither the receipt journal nor Explore event writes.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from ...extensions.capability_admission import (
    invoke_external_capability,
    prepare_external_capability_invocation,
    validate_external_capability_result,
)
from ...extensions.runtime import default_extension_state_file
from ...file_lock import exclusive_file_lock
from ...registry import atomic_write_json
from .discovery_contract import (
    MAX_BYTES,
    canonicalize_proposals,
    digest,
    exact,
    rows,
    timestamp,
    token,
    validate_observations,
    validate_policy,
    validate_resolutions,
)
from .result_log import (
    append_explore_result_events,
    build_explore_node_event,
    explore_result_log_path,
    load_explore_result_events_strict,
)

ROLES = ("policy", "collector", "resolver", "proposer")
JOURNAL_SCHEMA = "loopx_explore_discovery_run_v0"


def load_json(path: Path) -> dict:
    if path.stat().st_size > 5_000_000:
        raise ValueError("discovery local artifact exceeds its size envelope")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("discovery artifact must be an object")
    return value


def validate_binding(value: object) -> dict:
    binding = exact(value, "enabled public_origins providers", "discovery binding")
    if type(binding["enabled"]) is not bool:
        raise ValueError("discovery enabled must be a boolean")
    origins = rows(binding["public_origins"], 32, "public origins")
    if not origins:
        raise ValueError("discovery requires owner-reviewed public origins")
    for origin in origins:
        url = urlsplit(origin)
        if (
            url.scheme != "https"
            or url.path
            or url.query
            or url.fragment
            or url.username
            or url.password
            or not url.hostname
            or "." not in url.hostname
            or url.port
            or url.hostname.endswith((".local", ".internal", ".localhost"))
        ):
            raise ValueError("discovery requires exact public HTTPS origins")
        import ipaddress

        try:
            address = ipaddress.ip_address(url.hostname)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("private origins are not public research sources")
    providers = exact(binding["providers"], " ".join(ROLES), "discovery providers")
    for role, provider in providers.items():
        ref = exact(provider, "capability_id operation", f"{role} binding")
        token(ref["capability_id"])
        token(ref["operation"])
    return binding


def _root(runtime_root: Path, goal_id: str) -> Path:
    return runtime_root / "goals" / token(goal_id) / "explore-discovery"


def _save(path: Path, journal: dict) -> None:
    payload = deepcopy(journal)
    payload.pop("journal_digest", None)
    payload["journal_digest"] = digest(payload)
    atomic_write_json(path, payload)


def _load(path: Path) -> dict:
    journal = load_json(path)
    supplied_digest = journal.pop("journal_digest", None)
    if (
        supplied_digest != digest(journal)
        or journal.get("schema_version") != JOURNAL_SCHEMA
    ):
        raise ValueError("discovery journal integrity failure")
    if journal.get("run_id") != path.stem:
        raise ValueError("discovery journal identity mismatch")
    return journal


def _context(journal: dict) -> list[dict]:
    return [
        {
            "kind": "explore-discovery",
            "ref": journal["run_id"],
            "digest": digest(journal["session"]),
        }
    ]


def _capture(
    *, journal: dict, role: str, payload: dict, registry_path: Path, runtime_root: Path
) -> dict:
    if role in journal["captures"]:
        capture = journal["captures"][role]
        if capture["input"] != payload:
            raise ValueError("discovery retry changed a frozen provider input")
        return capture
    provider = journal["binding"]["providers"][role]
    args = dict(
        state_file=default_extension_state_file(runtime_root),
        registry_path=registry_path,
        goal_id=journal["goal_id"],
        capability_id=provider["capability_id"],
        operation=provider["operation"],
        provider_input={"context_refs": _context(journal), "input": payload},
    )
    prepared = prepare_external_capability_invocation(**args)
    if prepared["operation_profile"]["effect_class"] != "read_only":
        raise ValueError("discovery providers must be read-only")
    receipt = invoke_external_capability(**args, execute=True)
    if (
        receipt["request_digest"] != prepared["request_digest"]
        or receipt["invocation_id"] != prepared["invocation_id"]
    ):
        raise ValueError("discovery provider binding changed during capture")
    capture = {
        "input": payload,
        "request": prepared["request"],
        "operation_profile": prepared["operation_profile"],
        "receipt": receipt,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    _capture_observation(capture, journal=journal)
    journal["captures"][role] = capture
    return capture


def _validate_receipt(receipt: dict, *, request: dict, operation: dict) -> dict:
    result = validate_external_capability_result(
        receipt["provider_result"],
        invocation_id=request["invocation_id"],
        operation=operation,
    )
    if (
        operation["effect_class"] != "read_only"
        or receipt.get("executed") is not True
        or receipt.get("effect_class") != "read_only"
        or receipt.get("status") != result["status"]
        or receipt.get("effects", {}).get("provider_invoked") is not True
        or any(
            receipt.get("effects", {}).get(key) is not False
            for key in (
                "external_write_performed",
                "loopx_state_written",
                "quota_spent",
            )
        )
        or receipt.get("invocation_id") != request["invocation_id"]
        or receipt.get("capability_id") != request["capability_id"]
        or receipt.get("operation") != request["operation"]
        or receipt["request_digest"] != digest(request)
        or receipt["provider_result_digest"] != digest(result)
        or receipt["provider"] != request["provider"]
        or receipt["goal_binding"]["goal_id"] != request["goal"]["goal_id"]
        or receipt["goal_binding"]["binding_digest"]
        != request["goal"]["capability_binding_digest"]
    ):
        raise ValueError("discovery requires a successful managed read-only receipt")
    return result


def _capture_observation(capture: dict, *, journal: dict) -> dict:
    request = capture["request"]
    result = _validate_receipt(
        capture["receipt"], request=request, operation=capture["operation_profile"]
    )
    if (
        request["goal"]["goal_id"] != journal["goal_id"]
        or request["context_refs"] != _context(journal)
        or request["input"] != capture["input"]
    ):
        raise ValueError(
            "discovery capture is not bound to a successful managed invocation"
        )
    observations = rows(result["observations"], 1, "provider observations")
    if len(observations) != 1 or len(json.dumps(observations).encode()) > MAX_BYTES:
        raise ValueError("discovery provider requires one bounded observation packet")
    if timestamp(capture["captured_at"]) < timestamp(journal["session"]["started_at"]):
        raise ValueError("discovery capture predates its Core session")
    return observations[0]


def _reduce(journal: dict) -> dict:
    cutoff = journal["session"]["cutoff_at"]
    captures = journal["captures"]
    for role in ROLES:
        request = captures[role]["request"]
        bound = journal["binding"]["providers"][role]
        if (
            request["capability_id"] != bound["capability_id"]
            or request["operation"] != bound["operation"]
        ):
            raise ValueError(
                "discovery capture differs from the Core provider-role binding"
            )
    if captures["policy"]["input"] != {"as_of": cutoff}:
        raise ValueError("policy receipt does not bind the Core cutoff")
    policy = validate_policy(
        _capture_observation(captures["policy"], journal=journal), cutoff
    )
    observations = validate_observations(
        _capture_observation(captures["collector"], journal=journal),
        cutoff_at=cutoff,
        public_origins=journal["binding"]["public_origins"],
    )
    resolutions = validate_resolutions(
        _capture_observation(captures["resolver"], journal=journal),
        observations=observations,
        cutoff_at=cutoff,
    )
    ordinal = journal["session"]["ordinal"]
    if type(ordinal) is not int or ordinal < 0:
        raise ValueError("invalid Core discovery session ordinal")
    lenses = policy["causal_lenses"]
    offset = ordinal % len(lenses)
    expected_inputs = {
        "collector": {
            "cutoff_at": cutoff,
            "max_observations": 96,
            "public_origins": journal["binding"]["public_origins"],
        },
        "resolver": {
            "cutoff_at": cutoff,
            "observations": observations,
            "collector_receipt_digest": digest(captures["collector"]),
        },
        "proposer": {
            "cutoff_at": cutoff,
            "policy": policy,
            "observations": observations,
            "resolutions": resolutions,
            "lens_order": lenses[offset:] + lenses[:offset],
            "max_proposals": 96,
            "max_adjacent_transfers": 1,
            "receipt_digests": {role: digest(captures[role]) for role in ROLES[:-1]},
        },
    }
    if any(
        captures[role]["input"] != expected
        for role, expected in expected_inputs.items()
    ):
        raise ValueError(
            "discovery receipt chain does not bind exact upstream observations"
        )
    canonical = canonicalize_proposals(
        _capture_observation(captures["proposer"], journal=journal),
        policy=policy,
        observations=observations,
        resolutions=resolutions,
        cutoff_at=cutoff,
        session_ordinal=journal["session"]["ordinal"],
    )
    universe = {
        "universe_id": journal["run_id"],
        "source_id": journal["run_id"],
        "frozen_at": cutoff,
        "coverage_claim": "bounded_research_pool",
        "completeness": "partial",
        "subject_ids": canonical["subject_ids"],
    }
    return {
        "schema_version": "loopx_explore_discovery_freeze_v0",
        "goal_id": journal["goal_id"],
        "run_id": journal["run_id"],
        "captured_at": captures["proposer"]["captured_at"],
        "session_receipt_digest": digest(journal["session"]),
        "capture_receipt_digests": {role: digest(captures[role]) for role in ROLES},
        "policy": policy,
        "canonical": canonical,
        "universe": universe,
        "authority": "evaluation_scope_only",
    }


def _events(freeze: dict) -> list[dict]:
    return [
        build_explore_node_event(
            goal_id=freeze["goal_id"],
            node_id=p["canonical_id"],
            title=p["mechanism"],
            node_kind="hypothesis",
            status="open",
            summary="Canonical proposal for bounded evaluation; no research finding or lifecycle promotion.",
            run_id=freeze["run_id"],
            recorded_at=freeze["captured_at"],
            evidence_refs=[
                freeze["run_id"],
                p["thesis_digest"],
                *p["supporting_source_ids"][:12],
            ],
            tags=["discovery-proposal", p["family"], p["causal_lens"]],
        )
        for p in freeze["canonical"]["hypotheses"]
    ]


def run_discovery(
    *,
    registry_path: Path,
    runtime_root: Path,
    goal_id: str,
    binding: dict,
    trigger_id: str,
    cutoff_at: str,
    execute: bool = False,
) -> dict:
    # Feature-off returns before provider resolution, journal reads, or writes.
    if binding.get("enabled", False) is False:
        return {"ok": True, "status": "disabled", "executed": False}
    binding = validate_binding(binding)
    token(goal_id)
    token(trigger_id)
    cutoff = timestamp(cutoff_at)
    now = datetime.now(timezone.utc)
    if cutoff > now:
        raise ValueError("discovery cutoff cannot be in the future")
    run_id = "discovery-" + digest({"goal_id": goal_id, "trigger_id": trigger_id})[7:31]
    if not execute:
        return {"ok": True, "status": "preview", "run_id": run_id, "executed": False}
    root = _root(runtime_root, goal_id)
    path = root / f"{run_id}.json"
    with exclusive_file_lock(root / "sessions"):
        if path.exists():
            journal = _load(path)
            if (
                journal["binding"] != binding
                or journal["session"]["cutoff_at"] != cutoff_at
            ):
                raise ValueError(
                    "discovery trigger already binds another cutoff or configuration"
                )
        else:
            prior = [
                _load(p)["session"]["ordinal"] for p in root.glob("discovery-*.json")
            ]
            journal = {
                "schema_version": JOURNAL_SCHEMA,
                "goal_id": goal_id,
                "run_id": run_id,
                "binding": deepcopy(binding),
                "captures": {},
                "session": {
                    "trigger_id": trigger_id,
                    "cutoff_at": cutoff_at,
                    "started_at": now.isoformat(),
                    "ordinal": max(prior, default=-1) + 1,
                },
                "freeze": None,
                "settlement": None,
            }
            _save(path, journal)
        if journal["settlement"] is not None:
            return read_discovery(
                runtime_root=runtime_root, goal_id=goal_id, run_id=run_id
            )
        policy_capture = _capture(
            journal=journal,
            role="policy",
            payload={"as_of": cutoff_at},
            registry_path=registry_path,
            runtime_root=runtime_root,
        )
        policy = validate_policy(
            _capture_observation(policy_capture, journal=journal), cutoff_at
        )
        _save(path, journal)
        collector = _capture(
            journal=journal,
            role="collector",
            payload={
                "cutoff_at": cutoff_at,
                "max_observations": 96,
                "public_origins": binding["public_origins"],
            },
            registry_path=registry_path,
            runtime_root=runtime_root,
        )
        observations = validate_observations(
            _capture_observation(collector, journal=journal),
            cutoff_at=cutoff_at,
            public_origins=binding["public_origins"],
        )
        _save(path, journal)
        resolver = _capture(
            journal=journal,
            role="resolver",
            payload={
                "cutoff_at": cutoff_at,
                "observations": observations,
                "collector_receipt_digest": digest(collector),
            },
            registry_path=registry_path,
            runtime_root=runtime_root,
        )
        resolutions = validate_resolutions(
            _capture_observation(resolver, journal=journal),
            observations=observations,
            cutoff_at=cutoff_at,
        )
        _save(path, journal)
        ordinal = journal["session"]["ordinal"]
        lenses = policy["causal_lenses"]
        offset = ordinal % len(lenses)
        _capture(
            journal=journal,
            role="proposer",
            payload={
                "cutoff_at": cutoff_at,
                "policy": policy,
                "observations": observations,
                "resolutions": resolutions,
                "lens_order": lenses[offset:] + lenses[:offset],
                "max_proposals": 96,
                "max_adjacent_transfers": 1,
                "receipt_digests": {
                    role: digest(journal["captures"][role]) for role in ROLES[:-1]
                },
            },
            registry_path=registry_path,
            runtime_root=runtime_root,
        )
        freeze = _reduce(journal)
        journal["freeze"] = freeze
        _save(path, journal)
        events = _events(freeze)
        log = explore_result_log_path(runtime_root, goal_id)
        # Validate the existing ledger strictly before using its idempotent writer.
        load_explore_result_events_strict(log, goal_id=goal_id)
        if events:
            append_explore_result_events(log, events, expected_goal_id=goal_id)
        existing = {
            e["event_id"]: e
            for e in load_explore_result_events_strict(log, goal_id=goal_id)
        }
        if any(existing.get(e["event_id"]) != e for e in events):
            raise ValueError("discovery Explore settlement readback failed")
        journal["settlement"] = {
            "schema_version": "loopx_explore_discovery_settlement_v0",
            "freeze_digest": digest(freeze),
            "event_ids": [e["event_id"] for e in events],
            "status": "scope_frozen" if events else "no_candidates",
            "research_admission": False,
            "lifecycle_promotion": False,
        }
        _save(path, journal)
    return read_discovery(runtime_root=runtime_root, goal_id=goal_id, run_id=run_id)


def read_discovery(*, runtime_root: Path, goal_id: str, run_id: str) -> dict:
    journal = _load(_root(runtime_root, goal_id) / f"{token(run_id)}.json")
    if journal["goal_id"] != goal_id or journal["settlement"] is None:
        raise ValueError("discovery has no settled Core scope receipt")
    freeze = _reduce(journal)
    if journal["freeze"] != freeze or journal["settlement"]["freeze_digest"] != digest(
        freeze
    ):
        raise ValueError("discovery frozen scope drifted from its receipts")
    events = _events(freeze)
    if journal["settlement"]["event_ids"] != [e["event_id"] for e in events]:
        raise ValueError("discovery settlement event identity mismatch")
    existing = {
        e["event_id"]: e
        for e in load_explore_result_events_strict(
            explore_result_log_path(runtime_root, goal_id), goal_id=goal_id
        )
    }
    if any(existing.get(e["event_id"]) != e for e in events):
        raise ValueError("discovery settlement is absent from Core Explore history")
    return {
        "ok": True,
        "status": journal["settlement"]["status"],
        "run_id": run_id,
        "freeze": freeze,
        "settlement_receipt": journal["settlement"],
        "readback_verified": True,
    }


def evaluate_discovery(
    *,
    registry_path: Path,
    runtime_root: Path,
    goal_id: str,
    run_id: str,
    provider_input: dict,
    binding: dict,
    execute: bool = False,
) -> dict:
    if binding.get("enabled", False) is False:
        return {"ok": True, "status": "disabled", "provider_invoked": False}
    binding = validate_binding(binding)
    result = read_discovery(runtime_root=runtime_root, goal_id=goal_id, run_id=run_id)
    freeze = result["freeze"]
    if not freeze["universe"]["subject_ids"]:
        return {"ok": True, "status": "no_candidates", "provider_invoked": False}
    journal_path = _root(runtime_root, goal_id) / f"{run_id}.json"
    journal = _load(journal_path)
    if journal["binding"] != binding:
        raise ValueError(
            "evaluation binding differs from the settled discovery configuration"
        )
    request = deepcopy(exact(provider_input, "context_refs input", "evaluation input"))
    policy, cutoff = freeze["policy"], freeze["universe"]["frozen_at"]
    payload = request["input"]
    if (
        payload.get("universe") != freeze["universe"]
        or payload.get("cutoff_at") != cutoff
        or payload.get("method_revision") != policy["method_revision"]
        or payload.get("market") != policy["market"]
        or payload.get("timezone") != policy["timezone"]
        or payload.get("trading_date")
        != timestamp(cutoff).astimezone(ZoneInfo(policy["timezone"])).date().isoformat()
    ):
        raise ValueError(
            "evaluation input must exactly match the Core-frozen universe and method"
        )
    ref = {
        "kind": "explore-discovery",
        "ref": run_id,
        "digest": digest(result["settlement_receipt"]),
    }
    if ref not in request["context_refs"]:
        request["context_refs"].append(ref)
    evaluator_binding = journal["binding"]["providers"]["policy"]
    args = dict(
        state_file=default_extension_state_file(runtime_root),
        registry_path=registry_path,
        goal_id=goal_id,
        capability_id=evaluator_binding["capability_id"],
        operation=policy["evaluation_operation"],
        provider_input=request,
    )
    prepared = prepare_external_capability_invocation(**args)
    if prepared["operation_profile"]["effect_class"] != "read_only":
        raise ValueError("discovery evaluation must remain read-only")
    if (
        prepared["request"]["provider"]
        != journal["captures"]["policy"]["request"]["provider"]
    ):
        raise ValueError("evaluation provider revision differs from frozen policy")
    if not execute:
        return invoke_external_capability(**args, execute=False)
    with exclusive_file_lock(journal_path):
        journal = _load(journal_path)
        prior = journal.get("evaluation")
        if prior is not None:
            if prior["request_digest"] != prepared["request_digest"]:
                raise ValueError(
                    "settled discovery already binds another evaluation input"
                )
            _validate_receipt(
                prior,
                request=prepared["request"],
                operation=prepared["operation_profile"],
            )
            return prior
        receipt = invoke_external_capability(**args, execute=True)
        if receipt["request_digest"] != prepared["request_digest"]:
            raise ValueError("evaluation invocation changed after Core admission")
        _validate_receipt(
            receipt,
            request=prepared["request"],
            operation=prepared["operation_profile"],
        )
        journal["evaluation"] = receipt
        _save(journal_path, journal)
        if _load(journal_path)["evaluation"] != receipt:
            raise ValueError("evaluation receipt readback failed")
        return receipt
