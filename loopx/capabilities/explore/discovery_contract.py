"""Pure admission of receipt-backed discovery proposals, without effects.

Source facts arrive from Core-captured collector/resolver results. Mechanism
semantics remain model proposals even after canonical identity is assigned.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from urllib.parse import urlsplit

from ...control_plane.runtime.public_safety import validate_public_safe_value

MAX_OBSERVATIONS = 96
MAX_PROPOSALS = 96
MAX_SUBJECTS = 48
MAX_BYTES = 750_000
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def digest(value: object) -> str:
    data = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(data.encode()).hexdigest()


def exact(value: object, keys: str, label: str) -> dict:
    if not isinstance(value, Mapping) or set(value) != set(keys.split()):
        raise ValueError(f"{label} has missing or unknown fields")
    validate_public_safe_value(value, path=label)
    return dict(value)


def token(value: object) -> str:
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ValueError("discovery identity must be a bounded token")
    return value


def timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValueError("discovery time must be RFC3339 with an offset")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def rows(value: object, limit: int, label: str) -> list:
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{label} exceeds the bounded envelope")
    return value


def tokens(value: object, limit: int, *, nonempty: bool = False) -> list[str]:
    values = [token(item) for item in rows(value, limit, "identities")]
    if len(values) != len(set(values)) or (nonempty and not values):
        raise ValueError(
            "discovery identities must be unique and nonempty when required"
        )
    return sorted(values)


def count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValueError("invalid bounded discovery count")
    return value


def text(value: object, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("invalid bounded discovery statement")
    return " ".join(value.split())


def validate_policy(value: object, cutoff_at: str) -> dict:
    policy = exact(
        value,
        "schema_version as_of method_revision market timezone max_subjects max_hypotheses causal_lenses families_by_horizon expires_at_by_horizon evaluation_operation",
        "discovery policy",
    )
    if policy["schema_version"] != "loopx_explore_discovery_policy_v0" or timestamp(
        policy["as_of"]
    ) != timestamp(cutoff_at):
        raise ValueError("discovery policy cutoff or schema mismatch")
    for field in ("max_subjects", "max_hypotheses"):
        if type(policy[field]) is not int or not 1 <= policy[field] <= MAX_SUBJECTS:
            raise ValueError(
                "discovery policy exceeds the 48-subject/hypothesis ceiling"
            )
    for field in ("method_revision", "market", "evaluation_operation"):
        token(policy[field])
    if policy["market"] != "US" or policy["timezone"] != "America/New_York":
        raise ValueError("only the bounded US evaluator handoff is supported")
    lenses = tokens(policy["causal_lenses"], 5, nonempty=True)
    if len(lenses) != 5:
        raise ValueError("discovery requires five ordered causal lenses")
    families = policy["families_by_horizon"]
    ceilings = policy["expires_at_by_horizon"]
    if (
        not isinstance(families, dict)
        or not isinstance(ceilings, dict)
        or set(families) != set(ceilings)
        or len(families) != 3
    ):
        raise ValueError("discovery policy horizon/expiry mismatch")
    for horizon, values in families.items():
        token(horizon)
        tokens(values, 8, nonempty=True)
        if timestamp(ceilings[horizon]) <= timestamp(cutoff_at):
            raise ValueError("discovery policy expiry must follow cutoff")
    return policy


def validate_observations(
    value: object, *, cutoff_at: str, public_origins: list[str]
) -> dict:
    packet = exact(
        value,
        "schema_version observations overflow_count",
        "collector observation packet",
    )
    if packet["schema_version"] != "loopx_explore_public_observations_v0":
        raise ValueError("unsupported collector observation schema")
    count(packet["overflow_count"])
    cutoff = timestamp(cutoff_at)
    seen = set()
    for observation in rows(packet["observations"], MAX_OBSERVATIONS, "observations"):
        row = exact(
            observation,
            "source_id uri entity_ids as_of available_at content_digest summary relation",
            "public observation",
        )
        source_id = token(row["source_id"])
        if source_id in seen:
            raise ValueError("duplicate observation identity")
        seen.add(source_id)
        tokens(row["entity_ids"], 8, nonempty=True)
        if not timestamp(row["as_of"]) <= timestamp(row["available_at"]) <= cutoff:
            raise ValueError("observation was not available at the frozen cutoff")
        if not isinstance(row["content_digest"], str) or not DIGEST.fullmatch(
            row["content_digest"]
        ):
            raise ValueError("observation requires a content digest")
        text(row["summary"])
        url = urlsplit(row["uri"])
        if (
            url.scheme != "https"
            or url.username
            or url.password
            or url.query
            or url.fragment
            or f"https://{url.netloc}" not in public_origins
        ):
            raise ValueError("observation URL is outside the reviewed public origins")
        if row["relation"] is not None:
            relation = exact(
                row["relation"], "from_entity to_entity kind", "public relation"
            )
            if relation["kind"] not in {"producer", "customer", "substitute"}:
                raise ValueError("unsupported public relation")
            if relation["from_entity"] == relation["to_entity"] or not {
                relation["from_entity"],
                relation["to_entity"],
            } <= set(row["entity_ids"]):
                raise ValueError("public relation does not bind its entities")
    return packet


def validate_resolutions(value: object, *, observations: dict, cutoff_at: str) -> dict:
    packet = exact(value, "schema_version resolutions", "resolver packet")
    if packet["schema_version"] != "loopx_explore_subject_resolutions_v0":
        raise ValueError("unsupported resolver schema")
    sources = {row["source_id"]: row for row in observations["observations"]}
    entities = {entity for row in sources.values() for entity in row["entity_ids"]}
    resolved = set()
    for item in rows(packet["resolutions"], MAX_OBSERVATIONS * 8, "resolutions"):
        row = exact(
            item,
            "entity_id subject_id source_ids as_of available_at",
            "subject resolution",
        )
        entity = token(row["entity_id"])
        if entity not in entities or entity in resolved:
            raise ValueError("resolution has an unknown or duplicate entity")
        resolved.add(entity)
        refs = tokens(row["source_ids"], 8, nonempty=row["subject_id"] is not None)
        if any(
            ref not in sources or entity not in sources[ref]["entity_ids"]
            for ref in refs
        ):
            raise ValueError("resolution lacks entity-bound source evidence")
        if (
            not timestamp(row["as_of"])
            <= timestamp(row["available_at"])
            <= timestamp(cutoff_at)
        ):
            raise ValueError("resolution was not available at cutoff")
        if any(
            timestamp(sources[ref]["available_at"]) > timestamp(row["available_at"])
            for ref in refs
        ):
            raise ValueError("resolution predates its supporting public sources")
        subject = row["subject_id"]
        if subject is not None and (
            not isinstance(subject, str)
            or not re.fullmatch(r"US\.[A-Z0-9][A-Z0-9.-]{0,24}", subject)
        ):
            raise ValueError("resolution is not a listed US subject identity")
    if resolved != entities:
        raise ValueError("resolver must preserve explicit unresolved entities")
    return packet


PROPOSAL_FIELDS = "mechanism_id mechanism thesis_digest family causal_lens entity_ids industry_chain_id proxies falsification_ids horizon expires_at supporting_source_ids counter_source_ids missing_evidence_ids conflict_source_ids adjacent_relation_source_id interaction_source_id"


def _proposal(
    value: object, *, policy: dict, sources: dict, resolutions: dict, cutoff_at: str
) -> dict:
    p = deepcopy(exact(value, PROPOSAL_FIELDS, "mechanism proposal"))
    token(p["mechanism_id"])
    p["mechanism"] = text(p["mechanism"])
    if p["thesis_digest"] != digest({"mechanism": p["mechanism"]}):
        raise ValueError("thesis digest does not bind the proposed mechanism")
    token(p["industry_chain_id"])
    entities = tokens(p["entity_ids"], 8, nonempty=True)
    if any(
        entity not in resolutions or resolutions[entity] is None for entity in entities
    ):
        raise ValueError("unresolved proposal entity")
    if p["causal_lens"] not in policy["causal_lenses"] or p["family"] not in policy[
        "families_by_horizon"
    ].get(p["horizon"], []):
        raise ValueError("unsupported hypothesis family, horizon, or causal lens")
    if (
        not timestamp(cutoff_at)
        < timestamp(p["expires_at"])
        <= timestamp(policy["expires_at_by_horizon"][p["horizon"]])
    ):
        raise ValueError("proposal exceeds provider-owned expiry")
    p["falsification_ids"] = tokens(p["falsification_ids"], 4, nonempty=True)
    p["missing_evidence_ids"] = tokens(p["missing_evidence_ids"], 16)
    bound = set()
    for field in ("supporting_source_ids", "counter_source_ids", "conflict_source_ids"):
        p[field] = tokens(p[field], 12)
        for ref in p[field]:
            if ref not in sources or not set(sources[ref]["entity_ids"]) & set(
                entities
            ):
                raise ValueError("proposal source is not receipt-bound to its entities")
            bound.add(ref)
    if not p["supporting_source_ids"]:
        raise ValueError("proposal requires an observable supporting source")
    proxies = rows(p["proxies"], 8, "proxies")
    if not proxies:
        raise ValueError("proposal requires an observable public proxy")
    for proxy in proxies:
        exact(proxy, "proxy_id source_ids", "proxy")
        token(proxy["proxy_id"])
        proxy["source_ids"] = tokens(proxy["source_ids"], 8, nonempty=True)
        if not set(proxy["source_ids"]) <= bound:
            raise ValueError("proxy is not bound to proposal sources")
    relation_ref = p["adjacent_relation_source_id"]
    interaction_ref = p["interaction_source_id"]
    if relation_ref is not None:
        if relation_ref not in bound or sources[relation_ref]["relation"] is None:
            raise ValueError("adjacent transfer requires an explicit public relation")
        relation = sources[relation_ref]["relation"]
        if {relation["from_entity"], relation["to_entity"]} != set(entities):
            raise ValueError("adjacent transfer is limited to one evidenced edge")
    if len(entities) > 1:
        if interaction_ref not in bound or not set(entities) <= set(
            sources[interaction_ref]["entity_ids"]
        ):
            raise ValueError(
                "combination requires a receipt-bound interaction observation"
            )
    elif interaction_ref is not None:
        raise ValueError("single-entity proposal cannot claim an interaction")
    p["entity_ids"] = entities
    p["subject_ids"] = sorted({resolutions[entity] for entity in entities})
    p["proxies"] = sorted(proxies, key=lambda row: row["proxy_id"])
    # Caller/model ids are labels. Core owns the canonical hypothesis identity.
    identity = {key: val for key, val in p.items() if key != "mechanism_id"}
    p["canonical_id"] = "hyp-" + digest(identity)[7:31]
    p["mechanism_id"] = (
        "mechanism-"
        + digest(
            {"mechanism": p["mechanism"], "industry_chain_id": p["industry_chain_id"]}
        )[7:31]
    )
    return p


def canonicalize_proposals(
    value: object,
    *,
    policy: dict,
    observations: dict,
    resolutions: dict,
    cutoff_at: str,
    session_ordinal: int,
) -> dict:
    packet = exact(
        value,
        "schema_version proposals unclassified_source_ids overflow_count",
        "proposal packet",
    )
    if packet["schema_version"] != "loopx_explore_mechanism_proposals_v0":
        raise ValueError("unsupported mechanism proposal schema")
    count(packet["overflow_count"])
    proposals = rows(packet["proposals"], MAX_PROPOSALS, "proposals")
    sources = {row["source_id"]: row for row in observations["observations"]}
    resolved = {
        row["entity_id"]: row["subject_id"] for row in resolutions["resolutions"]
    }
    unclassified = tokens(packet["unclassified_source_ids"], MAX_OBSERVATIONS)
    if not set(unclassified) <= set(sources):
        raise ValueError("unclassified observations require receipt-bound references")
    accepted, dropped = {}, []
    for index, raw in enumerate(proposals):
        # Unknown fields are an invocation-level structural boundary (including
        # scores, dispositions, mutations, and caller-authored receipt fields).
        if not isinstance(raw, dict) or set(raw) - set(PROPOSAL_FIELDS.split()):
            raise ValueError("proposal contains unknown or authoritative fields")
        try:
            p = _proposal(
                raw,
                policy=policy,
                sources=sources,
                resolutions=resolved,
                cutoff_at=cutoff_at,
            )
        except (ValueError, TypeError, KeyError) as exc:
            dropped.append({"proposal_index": index, "reason": str(exc)})
            continue
        accepted.setdefault(p["canonical_id"], p)
    lenses = policy["causal_lenses"]
    offset = session_ordinal % len(lenses)
    order = lenses[offset:] + lenses[:offset]
    families = sorted(
        {
            family
            for values in policy["families_by_horizon"].values()
            for family in values
        }
    )
    buckets = [
        [
            p
            for p in sorted(accepted.values(), key=lambda row: row["canonical_id"])
            if p["causal_lens"] == lens and p["family"] == family
        ]
        for lens in order
        for family in families
    ]
    selected, subjects, transfer_count, overflow = [], set(), 0, 0
    while any(buckets):
        for bucket in buckets:
            if not bucket:
                continue
            p = bucket.pop(0)
            transfer = int(p["adjacent_relation_source_id"] is not None)
            if (
                len(subjects | set(p["subject_ids"])) > policy["max_subjects"]
                or len(selected) >= policy["max_hypotheses"]
                or transfer_count + transfer > 1
            ):
                overflow += 1
                continue
            subjects.update(p["subject_ids"])
            selected.append(p)
            transfer_count += transfer
    represented = {
        ref
        for p in selected
        for field in (
            "supporting_source_ids",
            "counter_source_ids",
            "conflict_source_ids",
        )
        for ref in p[field]
    }
    unrepresented = sorted(set(sources) - represented - set(unclassified))
    return {
        "schema_version": "loopx_explore_discovery_canonical_v0",
        "hypotheses": selected,
        "subject_ids": sorted(subjects),
        "lens_order": order,
        "coverage": {
            "observation_count": len(sources),
            "input_proposal_count": len(proposals),
            "accepted_hypothesis_count": len(selected),
            "dropped_proposals": dropped,
            "unclassified_source_ids": unclassified,
            "unclassified_count": len(unclassified),
            "unrepresented_source_ids": unrepresented,
            "duplicate_proposal_count": len(proposals) - len(dropped) - len(accepted),
            "collector_overflow_count": observations["overflow_count"],
            "proposer_overflow_count": packet["overflow_count"],
            "canonical_overflow_count": overflow,
            "lens_counts": {
                lens: sum(p["causal_lens"] == lens for p in selected) for lens in lenses
            },
            "family_counts": {
                family: sum(p["family"] == family for p in selected)
                for family in families
            },
        },
        "semantic_authority": "model_proposal",
    }
