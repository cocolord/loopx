from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from loopx.cli import main
from loopx.extensions.manifest import load_extension_manifest
from loopx.extensions.runtime import default_extension_state_file, install_extension


ROOT = Path(__file__).resolve().parents[2]
EXTENSION_ROOT = ROOT / "extensions" / "loopx-market-judgment"
FINANCE_ROOT = ROOT / "extensions" / "loopx-finance-value-discovery"
EXTENSION_SRC = EXTENSION_ROOT / "src"
FINANCE_SRC = FINANCE_ROOT / "src"
MANIFEST = EXTENSION_ROOT / "extension.toml"
EXAMPLE = EXTENSION_ROOT / "examples" / "a-share-turn-window.json"
PAYPAL_EXAMPLE = FINANCE_ROOT / "examples" / "paypal-debeta-discovery.json"
sys.path[:0] = [str(EXTENSION_SRC), str(FINANCE_SRC)]

from loopx_market_judgment.cli import run  # noqa: E402
from loopx_market_judgment.reducer import build_market_judgment_packet  # noqa: E402


def _example() -> dict[str, object]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _quant_result(status: str = "validated") -> dict[str, object]:
    return {
        "event_id": "event-2",
        "revision": "revision-1",
        "type": "quant_result_recorded",
        "observed_at": "2026-07-21",
        "detail": {
            "status": status,
            "point_in_time": True,
            "lookahead_free": True,
            "held_out": status == "validated",
            "evidence_refs": ["https://example.com/held-out-result"],
            "rationale": "Frozen evaluation result.",
        },
    }


def _paper_gate_case() -> dict[str, object]:
    payload = _example()
    payload["events"].extend(
        [
            _quant_result(),
            {
                "event_id": "event-3",
                "revision": "revision-1",
                "type": "judgment_revised",
                "observed_at": "2026-07-21",
                "detail": {
                    "disposition": "paper_candidate",
                    "rationale": "Held-out evidence cleared the research gate.",
                },
            },
            {
                "event_id": "event-4",
                "revision": "revision-1",
                "type": "paper_gate_opened",
                "observed_at": "2026-07-21",
                "detail": {
                    "provider_id": "loopx-futu-paper-trade",
                    "permission": "broker.order.submit.simulated",
                },
            },
        ]
    )
    return payload


def test_manifest_is_permissionless_canonical_judgment_provider() -> None:
    manifest = load_extension_manifest(MANIFEST)
    assert manifest["capabilities"] == []
    assert manifest["implementations"] == []
    assert manifest["provider"]["permissions"] == []
    assert manifest["runtime"]["required_permissions"] == []
    assert manifest["runtime"]["protocol"] == "market_judgment_extension_v0"


def test_example_freezes_hypothesis_before_quant_result() -> None:
    packet = build_market_judgment_packet(_example())
    assert packet["projection"]["state"] == "quant_running"
    assert packet["atom"]["result"]["state"] == "top_window_observation"
    assert packet["boundary"]["canonical_judgment_owner"] is True
    assert packet["boundary"]["order_submitted"] is False


def test_held_out_validation_can_open_but_not_execute_paper_gate() -> None:
    packet = build_market_judgment_packet(_paper_gate_case())
    assert packet["projection"]["state"] == "paper_gate"
    assert packet["paper_handoff"] == {
        "ready_for_external_authority": True,
        "provider_id": "loopx-futu-paper-trade",
        "permission": "broker.order.submit.simulated",
        "order_request": None,
        "account_ref": None,
    }
    assert packet["projection"]["paper_authority"] is None


def test_paper_activation_requires_external_typed_authority_receipt() -> None:
    payload = _paper_gate_case()
    payload["events"].append(
        {
            "event_id": "event-5",
            "revision": "revision-1",
            "type": "paper_activated",
            "observed_at": "2026-07-21",
            "detail": {
                "provider_id": "loopx-futu-paper-trade",
                "permission": "broker.order.submit.simulated",
                "authority_status": "approved",
                "authority_ref": "authority-receipt-1",
            },
        }
    )
    packet = build_market_judgment_packet(payload)
    assert packet["projection"]["state"] == "paper_active"
    assert packet["boundary"]["order_submitted"] is False

    payload["events"][-1]["detail"]["authority_status"] = "pending"
    with pytest.raises(ValueError, match="approved typed Futu"):
        build_market_judgment_packet(payload)


def test_invalid_or_inconclusive_quant_result_cannot_reach_paper() -> None:
    for status in ("invalid", "inconclusive"):
        payload = _example()
        payload["events"].append(_quant_result(status))
        payload["events"].append(
            {
                "event_id": "event-3",
                "revision": "revision-1",
                "type": "paper_gate_opened",
                "observed_at": "2026-07-21",
                "detail": {
                    "provider_id": "loopx-futu-paper-trade",
                    "permission": "broker.order.submit.simulated",
                },
            }
        )
        with pytest.raises(ValueError, match="paper_gate_opened requires"):
            build_market_judgment_packet(payload)


def test_validation_and_transitions_fail_closed() -> None:
    payload = _example()
    result = _quant_result()
    result["detail"]["held_out"] = False
    payload["events"].append(result)
    with pytest.raises(ValueError, match="held-out evidence"):
        build_market_judgment_packet(payload)

    payload = _example()
    payload["events"] = [
        {
            "event_id": "event-1",
            "revision": "revision-1",
            "type": "paper_gate_opened",
            "observed_at": "2026-07-21",
            "detail": {
                "provider_id": "loopx-futu-paper-trade",
                "permission": "broker.order.submit.simulated",
            },
        }
    ]
    with pytest.raises(ValueError, match="paper_gate_opened requires"):
        build_market_judgment_packet(payload)

    payload = _example()
    payload["events"][0]["revision"] = "stale-revision"
    with pytest.raises(ValueError, match="frozen case revision"):
        build_market_judgment_packet(payload)


def test_reversal_atom_cannot_promote_session_10_to_durable_leader() -> None:
    payload = _example()
    payload["case_id"] = "a-share-reversal-example"
    payload["hypothesis"]["hypothesis_id"] = "a-share-reversal-v0"
    payload["atom"] = {
        "atom_id": "reversal_leadership",
        "input": {
            "schema_version": "finance_reversal_leadership_input_v0",
            "as_of": "2026-07-21",
            "market": "a_share",
            "point_in_time_data": True,
            "lookahead_free": True,
            "checkpoint_session": 10,
            "market_whipsaw_observed": False,
            "candidates": [
                {
                    "symbol": "SZ.000001",
                    "sector": "example-sector",
                    "relative_strength_percentile": 0.9,
                    "early_response_percentile": 0.9,
                    "pre_rebound_resilience_percentile": 0.8,
                    "sector_confirmation_count": 3,
                    "driver_evidence": ["evidence one", "evidence two"],
                    "counterevidence": ["counterevidence remains"],
                    "invalidation_flags": [],
                }
            ],
            "source_refs": [
                {
                    "source_id": "public-example",
                    "source_tier": "market_data",
                    "provider_label": "point-in-time public market data",
                    "observed_at": "2026-07-21",
                }
            ],
        },
    }
    packet = build_market_judgment_packet(payload)
    result = packet["atom"]["result"]
    assert result["state"] == "driver_hypothesis"
    assert result["second_phase_leader_symbols"] == []
    assert result["candidates"][0]["durable_leadership_observed"] is False

    payload["atom"]["input"]["checkpoint_session"] = 20
    result = build_market_judgment_packet(payload)["atom"]["result"]
    assert result["state"] == "second_phase_leader_observation"
    assert result["second_phase_leader_symbols"] == ["SZ.000001"]


@pytest.mark.parametrize(
    ("symbol", "early", "resilience", "expected_routes"),
    [
        ("SZ.300308", 0.82, 0.40, ["shock_responder"]),
        ("SZ.300502", 0.58, 0.86, ["structural_resilience"]),
    ],
)
def test_a_share_early_strong_candidate_supports_two_routes_without_promotion(
    symbol: str,
    early: float,
    resilience: float,
    expected_routes: list[str],
) -> None:
    payload = _example()
    payload["case_id"] = f"early-strong-{symbol}"
    payload["hypothesis"]["hypothesis_id"] = f"early-strong-{symbol}-v0"
    payload["atom"] = {
        "atom_id": "reversal_leadership",
        "input": {
            "schema_version": "finance_reversal_leadership_input_v0",
            "as_of": "2026-07-21",
            "market": "a_share",
            "point_in_time_data": True,
            "lookahead_free": True,
            "checkpoint_session": 1,
            "market_whipsaw_observed": False,
            "candidates": [
                {
                    "symbol": symbol,
                    "sector": "optical-module",
                    "relative_strength_percentile": 0.70,
                    "early_response_percentile": early,
                    "pre_rebound_resilience_percentile": resilience,
                    "sector_confirmation_count": 3,
                    "driver_evidence": ["sector peers confirmed the response"],
                    "counterevidence": ["one-session response can still fail"],
                    "invalidation_flags": [],
                }
            ],
            "source_refs": [
                {
                    "source_id": "public-example",
                    "source_tier": "market_data",
                    "provider_label": "point-in-time public market data",
                    "observed_at": "2026-07-21",
                }
            ],
        },
    }

    result = build_market_judgment_packet(payload)["atom"]["result"]
    assert result["state"] == "early_strong_candidate_observation"
    assert result["early_strong_candidate_symbols"] == [symbol]
    assert result["second_phase_leader_symbols"] == []
    assert result["candidates"][0]["classification"] == "early_strong_candidate"
    assert result["candidates"][0]["early_candidate_routes"] == expected_routes
    assert result["candidates"][0]["durable_leadership_observed"] is False


def test_early_strength_without_sector_confirmation_remains_unproven() -> None:
    payload = _example()
    payload["atom"] = {
        "atom_id": "reversal_leadership",
        "input": {
            "schema_version": "finance_reversal_leadership_input_v0",
            "as_of": "2026-07-21",
            "market": "a_share",
            "point_in_time_data": True,
            "lookahead_free": True,
            "checkpoint_session": 3,
            "market_whipsaw_observed": False,
            "candidates": [
                {
                    "symbol": "SZ.300999",
                    "sector": "example-sector",
                    "relative_strength_percentile": 0.90,
                    "early_response_percentile": 0.90,
                    "pre_rebound_resilience_percentile": 0.90,
                    "sector_confirmation_count": 1,
                    "driver_evidence": ["single-name rebound"],
                    "counterevidence": ["sector did not confirm"],
                    "invalidation_flags": [],
                }
            ],
            "source_refs": [
                {
                    "source_id": "public-example",
                    "source_tier": "market_data",
                    "provider_label": "point-in-time public market data",
                    "observed_at": "2026-07-21",
                }
            ],
        },
    }

    result = build_market_judgment_packet(payload)["atom"]["result"]
    assert result["state"] == "no_durable_driver"
    assert result["candidates"][0]["classification"] == "unproven_rebound"
    assert result["early_strong_candidate_symbols"] == []


def test_paypal_value_discovery_is_reused_without_duplication() -> None:
    paypal = json.loads(PAYPAL_EXAMPLE.read_text(encoding="utf-8"))
    payload = _example()
    payload["case_id"] = "paypal-reused-value-case"
    payload["hypothesis"] = {
        "hypothesis_id": "paypal-debeta-value-v0",
        "as_of": paypal["as_of"],
        "market": "us",
        "claim": "PayPal has company-specific value evidence after de-beta controls.",
        "falsifiers": ["The candidate does not survive frozen peer controls."],
        "evaluation_horizon_sessions": 60,
    }
    payload["atom"] = {"atom_id": "value_discovery", "input": paypal}
    payload["events"] = []
    packet = build_market_judgment_packet(payload)
    assert packet["atom"]["result"]["projection"]["next_targets"] == ["PYPL"]
    assert packet["projection"]["state"] == "hypothesis_frozen"


def test_provider_doctor_is_side_effect_free() -> None:
    assert run(["--doctor"]) == 0


def test_extension_runs_through_verified_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = tmp_path / "market-judgment-provider"
    provider.write_text(
        f"#!{sys.executable}\n"
        "from loopx_market_judgment.cli import main\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )
    provider.chmod(0o755)
    manifest = tmp_path / "extension.toml"
    manifest.write_text(
        MANIFEST.read_text(encoding="utf-8").replace(
            'entrypoint = "loopx-market-judgment"',
            f"entrypoint = {json.dumps(str(provider))}",
        ),
        encoding="utf-8",
    )
    existing = os.environ.get("PYTHONPATH")
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join(
            part
            for part in [str(EXTENSION_SRC), str(FINANCE_SRC), str(ROOT), existing]
            if part
        ),
    )
    runtime_root = tmp_path / "runtime"
    install_extension(
        manifest, state_file=default_extension_state_file(runtime_root), execute=True
    )
    assert (
        main(
            [
                "--runtime-root",
                str(runtime_root),
                "--format",
                "json",
                "extension",
                "run",
                "loopx-market-judgment",
                "--input-json",
                str(EXAMPLE),
                "--execute",
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "succeeded"
    assert receipt["provider_result"]["projection"]["state"] == "quant_running"
