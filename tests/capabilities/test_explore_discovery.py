from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from loopx.capabilities.explore.discovery_contract import (
    canonicalize_proposals,
    digest,
    validate_observations,
    validate_resolutions,
)
from loopx.capabilities.explore.discovery_runtime import (
    evaluate_discovery,
    read_discovery,
    run_discovery,
)
from loopx.capabilities.explore.result_log import explore_result_log_path
from loopx.extensions.capability_admission import bind_external_capability_to_goal
from loopx.extensions.runtime import default_extension_state_file, install_extension

CUTOFF = "2026-08-28T20:00:00Z"
LENSES = [
    "lens-a",
    "lens-b",
    "lens-c",
    "lens-d",
    "lens-e",
]
POLICY = {
    "schema_version": "loopx_explore_discovery_policy_v0",
    "as_of": CUTOFF,
    "method_revision": "fixture-method-v1",
    "market": "US",
    "timezone": "America/New_York",
    "max_subjects": 48,
    "max_hypotheses": 48,
    "causal_lenses": LENSES,
    "families_by_horizon": {
        h: ["mechanism-a", "mechanism-b"]
        for h in ["intraday", "short_1_5_sessions", "medium_1_3_months"]
    },
    "expires_at_by_horizon": {
        "intraday": "2026-08-31T20:00:00Z",
        "short_1_5_sessions": "2026-09-04T20:00:00Z",
        "medium_1_3_months": "2026-11-27T18:00:00Z",
    },
    "evaluation_operation": "evaluate",
}


def observation(i=0):
    return {
        "source_id": f"source-{i}",
        "uri": f"https://issuer.example/filings/{i}",
        "entity_ids": [f"entity-{i}"],
        "as_of": CUTOFF,
        "available_at": CUTOFF,
        "content_digest": digest({"public_observation": i}),
        "summary": "Synthetic public operating observation.",
        "relation": None,
    }


def proposal(i=0):
    mechanism = f"Synthetic capacity change may shift the residual to entity {i}."
    return {
        "mechanism_id": f"mechanism-{i}",
        "mechanism": mechanism,
        "thesis_digest": digest({"mechanism": mechanism}),
        "family": "mechanism-a",
        "causal_lens": LENSES[i % 5],
        "entity_ids": [f"entity-{i}"],
        "industry_chain_id": "synthetic-chain",
        "proxies": [{"proxy_id": "capacity", "source_ids": [f"source-{i}"]}],
        "falsification_ids": ["capacity-declines"],
        "horizon": "medium_1_3_months",
        "expires_at": "2026-09-04T20:00:00Z",
        "supporting_source_ids": [f"source-{i}"],
        "counter_source_ids": [],
        "missing_evidence_ids": ["cash-conversion"],
        "conflict_source_ids": [],
        "adjacent_relation_source_id": None,
        "interaction_source_id": None,
    }


def packets(n=1):
    return {
        "policy": deepcopy(POLICY),
        "collect": {
            "schema_version": "loopx_explore_public_observations_v0",
            "observations": [observation(i) for i in range(n)],
            "overflow_count": 0,
        },
        "resolve": {
            "schema_version": "loopx_explore_subject_resolutions_v0",
            "resolutions": [
                {
                    "entity_id": f"entity-{i}",
                    "subject_id": f"US.EX{i}",
                    "source_ids": [f"source-{i}"],
                    "as_of": CUTOFF,
                    "available_at": CUTOFF,
                }
                for i in range(n)
            ],
        },
        "propose": {
            "schema_version": "loopx_explore_mechanism_proposals_v0",
            "proposals": [proposal(i) for i in range(n)],
            "unclassified_source_ids": [],
            "overflow_count": 0,
        },
    }


def installed(tmp_path: Path, data=None):
    """Real installed subprocess provider; no mocked invocation or ledger."""
    data = data or packets()
    (tmp_path / "data.json").write_text(json.dumps(data))
    provider = tmp_path / "provider"
    provider.write_text(f"""#!{sys.executable}
import json, sys
from pathlib import Path
if "--doctor" in sys.argv: raise SystemExit(0)
r = json.load(sys.stdin)
data = json.loads(Path(__file__).with_name("data.json").read_text())
with Path(__file__).with_name("calls.jsonl").open("a") as f:
    f.write(json.dumps(r) + "\\n")
op = r["operation"]
observation = data[op] if op != "evaluate" else {{"evaluated_universe": r["input"]["universe"]}}
if op == "propose":
    policy = r["input"]["policy"]
    for i, proposal in enumerate(observation["proposals"]):
        proposal["family"] = policy["families_by_horizon"][proposal["horizon"]][0]
        proposal["causal_lens"] = policy["causal_lenses"][i % 5]
json.dump({{"schema_version": "fixture_result_v0", "invocation_id": r["invocation_id"],
    "status": data.get("result_status", "succeeded"), "observations": [observation], "domain_state_mutations": [],
    "domain_transition_receipts": [], "transition_proposals": [], "effect_receipt": None,
    "follow_up": {{"kind": "none"}}}}, sys.stdout)
""")
    provider.chmod(0o755)
    profile = {
        "schema_version": "loopx_external_domain_capability_profile_v0",
        "capability_id": "fixture-discovery-data",
        "protocol": "fixture_discovery_v0",
        "operations": [
            {
                "id": op,
                "effect_class": "read_only",
                "required_permission": "public_data.read",
                "request_schema": "fixture_request_v0",
                "result_schema": "fixture_result_v0",
            }
            for op in ["policy", "collect", "resolve", "propose", "evaluate"]
        ],
    }
    (tmp_path / "profile.json").write_text(json.dumps(profile))
    manifest = tmp_path / "extension.toml"
    manifest.write_text(f"""schema_version = "loopx_extension_manifest_v0"
id = "fixture-discovery-provider"
version = "0.1.0"
requires_loopx_api = ">=1,<2"
permissions = ["public_data.read"]
[runtime]
protocol = "fixture_discovery_v0"
entrypoint = {json.dumps(str(provider))}
doctor_args = ["--doctor"]
required_permissions = ["public_data.read"]
timeout_seconds = 10
[[provides]]
id = "fixture-discovery-data"
kind = "public_observations"
title = "Synthetic public observations"
status = "active-preview"
user_value = "Exercise the receipt-bound discovery contract."
next_real_step = "Run isolated contract validation."
real_world_anchor = "Synthetic public source fixtures."
entry_command = "loopx capability invoke"
visibility = "public"
integration_profile = "profile.json"
""")
    runtime = tmp_path / "runtime"
    state = default_extension_state_file(runtime)
    install_extension(manifest, state_file=state, execute=True)
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "loopx_registry_v1",
                "common_runtime_root": str(runtime),
                "goals": [{"id": "discovery-test", "repo": str(tmp_path)}],
            }
        )
    )
    bind_external_capability_to_goal(
        registry_path=registry,
        goal_id="discovery-test",
        state_file=state,
        capability_id="fixture-discovery-data",
        operations=["policy", "collect", "resolve", "propose", "evaluate"],
        execute=True,
    )
    binding = {
        "enabled": True,
        "public_origins": ["https://issuer.example"],
        "providers": {
            role: {"capability_id": "fixture-discovery-data", "operation": op}
            for role, op in [
                ("policy", "policy"),
                ("collector", "collect"),
                ("resolver", "resolve"),
                ("proposer", "propose"),
            ]
        },
    }
    return dict(
        registry_path=registry,
        runtime_root=runtime,
        goal_id="discovery-test",
        binding=binding,
        trigger_id="public-event-1",
        cutoff_at=CUTOFF,
    )


def test_disabled_and_preview_do_not_resolve_providers_or_write(tmp_path):
    args = dict(
        registry_path=tmp_path / "absent",
        runtime_root=tmp_path / "runtime",
        goal_id="test",
        binding={},
        trigger_id="event",
        cutoff_at=CUTOFF,
    )
    assert run_discovery(**args, execute=True)["status"] == "disabled"
    assert list(tmp_path.iterdir()) == []
    args["binding"] = {
        "enabled": True,
        "public_origins": ["https://issuer.example"],
        "providers": {
            role: {"capability_id": "absent", "operation": role}
            for role in ["policy", "collector", "resolver", "proposer"]
        },
    }
    assert run_discovery(**args)["status"] == "preview"
    assert list(tmp_path.iterdir()) == []


def test_managed_capture_core_settlement_and_evaluation_replay(tmp_path):
    args = installed(tmp_path)
    result = run_discovery(**args, execute=True)
    assert result["readback_verified"] is True
    assert result["freeze"]["universe"]["subject_ids"] == ["US.EX0"]
    assert result["settlement_receipt"]["research_admission"] is False
    assert result["settlement_receipt"]["lifecycle_promotion"] is False
    log = explore_result_log_path(args["runtime_root"], args["goal_id"])
    original = log.read_bytes()
    assert run_discovery(**args, execute=True) == result
    assert log.read_bytes() == original
    calls = [
        json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()
    ]
    assert [row["operation"] for row in calls] == [
        "policy",
        "collect",
        "resolve",
        "propose",
    ]
    assert "subject_ids" not in calls[1]["input"]  # Discovery precedes any watchlist.
    assert calls[3]["input"]["lens_order"] == LENSES
    evaluate = dict(
        registry_path=args["registry_path"],
        runtime_root=args["runtime_root"],
        goal_id=args["goal_id"],
        run_id=result["run_id"],
        binding=args["binding"],
        provider_input={
            "context_refs": [],
            "input": {
                "universe": result["freeze"]["universe"],
                "cutoff_at": CUTOFF,
                "market": "US",
                "timezone": "America/New_York",
                "trading_date": "2026-08-28",
                "method_revision": "fixture-method-v1",
            },
        },
    )
    receipt = evaluate_discovery(**evaluate, execute=True)
    assert receipt["effects"]["provider_invoked"] is True
    assert evaluate_discovery(**evaluate, execute=True) == receipt
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 5
    evaluate["provider_input"]["input"]["universe"] = {
        **result["freeze"]["universe"],
        "subject_ids": ["US.INJECTED"],
    }
    with pytest.raises(ValueError, match="exactly match"):
        evaluate_discovery(**evaluate, execute=True)
    log.write_text("")
    with pytest.raises(ValueError, match="absent from Core"):
        read_discovery(
            runtime_root=args["runtime_root"],
            goal_id=args["goal_id"],
            run_id=result["run_id"],
        )


def test_core_ordinal_rotates_and_retry_cannot_change_cutoff(tmp_path):
    args = installed(tmp_path)
    first = run_discovery(**args, execute=True)
    second = run_discovery(**{**args, "trigger_id": "public-event-2"}, execute=True)
    assert first["freeze"]["canonical"]["lens_order"] == LENSES
    assert second["freeze"]["canonical"]["lens_order"] == LENSES[1:] + LENSES[:1]
    with pytest.raises(ValueError, match="another cutoff"):
        run_discovery(**{**args, "cutoff_at": "2026-08-28T21:00:00Z"}, execute=True)


def reduce(data):
    return canonicalize_proposals(
        data["propose"],
        policy=data["policy"],
        observations=data["collect"],
        resolutions=data["resolve"],
        cutoff_at=CUTOFF,
        session_ordinal=0,
    )


def test_bounded_diverse_universe_and_explicit_overflow():
    data = packets(60)
    reduced = reduce(data)
    assert len(reduced["subject_ids"]) == 48
    assert reduced["coverage"]["canonical_overflow_count"] == 12
    assert set(reduced["coverage"]["lens_counts"].values()) <= {9, 10}
    assert reduce(data) == reduced


@pytest.mark.parametrize(
    "field,value",
    [
        ("score", 100),
        ("disposition", "research_candidate"),
        ("receipt", {"verified": True}),
        ("transition_proposals", []),
        ("session_ordinal", 7),
    ],
)
def test_model_cannot_supply_authority(field, value):
    data = packets()
    data["propose"]["proposals"][0][field] = value
    with pytest.raises(ValueError, match="authoritative fields"):
        reduce(data)


@pytest.mark.parametrize(
    "mutation", ["falsification", "source", "expiry", "entity", "digest", "relation"]
)
def test_invalid_proposals_drop_without_permanent_rejection(mutation):
    data = packets()
    p = data["propose"]["proposals"][0]
    if mutation == "falsification":
        p["falsification_ids"] = []
    if mutation == "source":
        p["supporting_source_ids"] = ["unreceipted-source"]
    if mutation == "expiry":
        p["expires_at"] = "2027-01-01T00:00:00Z"
    if mutation == "entity":
        p["entity_ids"] = ["unknown-entity"]
    if mutation == "digest":
        p["thesis_digest"] = "sha256:" + "0" * 64
    if mutation == "relation":
        p["adjacent_relation_source_id"] = "source-0"
    result = reduce(data)
    assert result["hypotheses"] == []
    assert len(result["coverage"]["dropped_proposals"]) == 1
    assert "tombstones" not in result


def test_point_in_time_and_entity_binding_are_receipt_requirements():
    data = packets(2)
    data["collect"]["observations"][0]["available_at"] = "2026-08-29T00:00:00Z"
    with pytest.raises(ValueError, match="not available"):
        validate_observations(
            data["collect"], cutoff_at=CUTOFF, public_origins=["https://issuer.example"]
        )
    data = packets(2)
    data["resolve"]["resolutions"][0]["source_ids"] = ["source-1"]
    with pytest.raises(ValueError, match="entity-bound"):
        validate_resolutions(
            data["resolve"], observations=data["collect"], cutoff_at=CUTOFF
        )


def test_all_dropped_is_a_settled_no_candidate_run(tmp_path):
    data = packets()
    data["propose"]["proposals"][0]["falsification_ids"] = []
    args = installed(tmp_path, data)
    result = run_discovery(**args, execute=True)
    assert result["status"] == "no_candidates"
    assert result["readback_verified"] is True
    assert result["freeze"]["universe"]["subject_ids"] == []
    assert not explore_result_log_path(args["runtime_root"], args["goal_id"]).exists()


def test_managed_no_change_receipts_can_carry_observations(tmp_path):
    data = packets()
    data["result_status"] = "no_change"
    result = run_discovery(**installed(tmp_path, data), execute=True)
    assert result["status"] == "scope_frozen"
    assert result["readback_verified"] is True


def test_cli_is_a_real_discovery_entrypoint(tmp_path, capsys):
    from loopx.cli import main

    args = installed(tmp_path)
    config = tmp_path / "binding.json"
    config.write_text(json.dumps(args["binding"]))
    assert (
        main(
            [
                "--registry",
                str(args["registry_path"]),
                "--runtime-root",
                str(args["runtime_root"]),
                "--format",
                "json",
                "explore",
                "discover",
                "--goal-id",
                args["goal_id"],
                "--binding-file",
                str(config),
                "--trigger-id",
                "cli-event",
                "--cutoff-at",
                CUTOFF,
                "--execute",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["readback_verified"] is True


def test_scope_settlement_resumes_after_interrupted_journal_write(
    tmp_path, monkeypatch
):
    from loopx.capabilities.explore import discovery_runtime as runtime

    args = installed(tmp_path)
    save = runtime._save

    def interrupted(path, journal):
        if journal["settlement"] is not None:
            raise OSError("simulated interruption after Explore append")
        save(path, journal)

    with monkeypatch.context() as scoped:
        scoped.setattr(runtime, "_save", interrupted)
        with pytest.raises(OSError, match="simulated interruption"):
            run_discovery(**args, execute=True)
    log = explore_result_log_path(args["runtime_root"], args["goal_id"])
    original = log.read_bytes()
    resumed = run_discovery(**args, execute=True)
    assert resumed["readback_verified"] is True
    assert log.read_bytes() == original
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 4


def test_capture_result_tampering_fails_even_with_rehashed_journal(tmp_path):
    from loopx.capabilities.explore import discovery_runtime as runtime

    args = installed(tmp_path)
    result = run_discovery(**args, execute=True)
    path = (
        runtime._root(args["runtime_root"], args["goal_id"])
        / f"{result['run_id']}.json"
    )
    journal = runtime._load(path)
    receipt = journal["captures"]["collector"]["receipt"]
    receipt["provider_result"]["observations"][0]["observations"][0]["summary"] = (
        "Altered observation"
    )
    runtime._save(path, journal)
    with pytest.raises(ValueError, match="successful managed read-only receipt"):
        read_discovery(
            runtime_root=args["runtime_root"],
            goal_id=args["goal_id"],
            run_id=result["run_id"],
        )


def test_disabled_evaluation_does_not_read_frozen_state(tmp_path):
    result = evaluate_discovery(
        registry_path=tmp_path / "absent",
        runtime_root=tmp_path / "runtime",
        goal_id="test",
        run_id="absent",
        binding={},
        provider_input={},
        execute=True,
    )
    assert result["status"] == "disabled"
    assert list(tmp_path.iterdir()) == []


def test_core_identity_ignores_model_labels_and_preserves_original_packet():
    data = packets()
    duplicate = deepcopy(data["propose"]["proposals"][0])
    duplicate["mechanism_id"] = "arbitrary-model-label"
    data["propose"]["proposals"].append(duplicate)
    original = deepcopy(data)
    result = reduce(data)
    assert data == original
    assert result["coverage"]["duplicate_proposal_count"] == 1
    assert len(result["hypotheses"]) == 1
    assert result["hypotheses"][0]["mechanism_id"] != proposal()["mechanism_id"]


def test_only_one_evidenced_adjacent_transfer_enters_scope():
    data = packets(4)
    proposals = []
    for i in (0, 2):
        entities = [f"entity-{i}", f"entity-{i + 1}"]
        source = data["collect"]["observations"][i]
        source["entity_ids"] = entities
        source["relation"] = {
            "from_entity": entities[0],
            "to_entity": entities[1],
            "kind": "customer",
        }
        p = proposal(i)
        p["entity_ids"] = entities
        p["adjacent_relation_source_id"] = p["interaction_source_id"] = source[
            "source_id"
        ]
        proposals.append(p)
    data["propose"]["proposals"] = proposals
    result = reduce(data)
    assert len(result["hypotheses"]) == 1
    assert len(result["subject_ids"]) == 2
    assert result["coverage"]["canonical_overflow_count"] == 1
    data["propose"]["proposals"][0]["interaction_source_id"] = None
    assert len(reduce(data)["coverage"]["dropped_proposals"]) == 1
