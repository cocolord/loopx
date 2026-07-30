from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

from loopx.cli import main
from loopx.extensions.presentation import (
    collect_active_extension_presentation_surfaces,
    default_extension_projection_root,
    publish_extension_projection,
    validate_decision_research_view,
)
from loopx.extensions.runtime import (
    disable_extension,
    doctor_installed_extension,
    enable_extension,
    install_extension,
)


def _valid_view() -> dict[str, object]:
    return {
        "identity": {
            "title": "Synthetic Technology Research",
            "subtitle": "Evidence-gated decision review",
            "as_of": "2026-01-15T12:00:00+00:00",
            "evidence_cutoff": "2026-01-15",
        },
        "adjudication": {
            "status": "insufficient_evidence",
            "label": "Insufficient Evidence",
            "summary": "The frozen gates do not yet support a selected conclusion.",
            "confidence": "medium",
        },
        "metrics": [
            {
                "id": "validated-alpha",
                "label": "Validated alpha",
                "value": "0",
                "detail": "No company-specific residual passed every frozen gate.",
                "tone": "warning",
            },
            {
                "id": "method-state",
                "label": "Method state",
                "value": "unchanged",
                "detail": "The active method was not promoted or replaced.",
                "tone": "neutral",
            },
        ],
        "dashboard_summaries": [
            {
                "id": "adjudication-summary",
                "label": "Current adjudication",
                "title": "Evidence remains insufficient",
                "summary": "Continue monitoring frozen event gates.",
                "tone": "warning",
                "destination_anchor": "executive-adjudication",
            }
        ],
        "layers": [
            {
                "id": "beta",
                "order": 1,
                "label": "Beta",
                "status": "supported",
                "summary": "Discount-rate exposure explains part of the move.",
                "evidence_points": [
                    "Broad peer dispersion remains limited.",
                    "Rate sensitivity is visible across the synthetic group.",
                ],
            },
            {
                "id": "residual-alpha",
                "order": 4,
                "label": "Residual alpha",
                "status": "rejected",
                "summary": "Validated company alpha = 0.",
                "evidence_points": [
                    "The candidate did not pass persistence controls.",
                    "Counterevidence remains unresolved.",
                ],
            },
        ],
        "entities": [
            {
                "entity_id": "synthetic-cloud",
                "symbol": "SYN",
                "display_name": "Synthetic Cloud",
                "classification": "Watchlist",
                "status": "insufficient_evidence",
                "confidence": "medium",
                "inference": "A quality business is not yet a validated mispricing.",
                "observations": [
                    {
                        "id": "observation-range",
                        "label": "Observation range",
                        "kind": "observation_range",
                        "value": "90-100 synthetic units",
                        "as_of": "2026-01-15T12:00:00+00:00",
                        "source_ref": "filing:syn-q4",
                        "source_type": "company_filing",
                        "confidence": "high",
                        "invalidation": "A verified close below 90 with worsening fundamentals.",
                    }
                ],
                "scenario_estimates": [
                    {
                        "scenario": "bull",
                        "label": "Bull scenario estimate",
                        "value": "140 synthetic units",
                        "horizon": "24 months",
                        "probability": 0.25,
                        "assumptions": [
                            "Growth reaccelerates.",
                            "Free cash flow conversion improves.",
                        ],
                    },
                    {
                        "scenario": "base",
                        "label": "Base scenario estimate",
                        "value": "112 synthetic units",
                        "horizon": "24 months",
                        "probability": 0.5,
                        "assumptions": [
                            "Growth remains durable.",
                            "The valuation multiple is stable.",
                        ],
                    },
                    {
                        "scenario": "bear",
                        "label": "Bear scenario estimate",
                        "value": "72 synthetic units",
                        "horizon": "24 months",
                        "probability": 0.25,
                        "assumptions": [
                            "Growth slows.",
                            "The valuation multiple compresses.",
                        ],
                    },
                ],
                "counterevidence": [
                    "Capital intensity may remain above the frozen assumption."
                ],
                "thesis_breakers": [
                    "Two consecutive periods of slowing growth and weaker cash conversion."
                ],
                "next_events": [
                    "Next official earnings release.",
                    "Updated capital expenditure guidance.",
                ],
            }
        ],
        "research_ledger": [
            {
                "case_id": "case-synthetic-cloud",
                "label": "Synthetic Cloud residual-alpha case",
                "gate_states": [
                    {
                        "gate_id": "de-beta",
                        "label": "De-beta control",
                        "status": "passed",
                        "summary": "The peer control was available.",
                    },
                    {
                        "gate_id": "persistence",
                        "label": "Persistence",
                        "status": "failed",
                        "summary": "The residual did not persist.",
                    },
                ],
                "decision": "rejected",
                "summary": "The company-specific alpha claim was rejected.",
                "evidence_refs": ["filing:syn-q4", "market:synthetic-peer-control"],
            }
        ],
        "event_gates": [
            {
                "event_id": "E1",
                "label": "Synthetic cloud earnings",
                "status": "pending",
                "observation_window": "Next official reporting window",
                "frozen_hypothesis": "Returns depend on monetization, not capex alone.",
                "observables": [
                    "Cloud growth versus frozen guidance.",
                    "Capital expenditure and free cash flow direction.",
                ],
                "current_evidence": [
                    "No official result was available at the evidence cutoff."
                ],
                "supports": [
                    "Growth above the frozen range with stable cash conversion."
                ],
                "refutes": [
                    "Higher capital expenditure without measurable cloud return."
                ],
                "thesis_breakers": [
                    "Official guidance shows deteriorating returns on investment."
                ],
                "next_review": "After the official filing is available.",
            }
        ],
        "method_state": {
            "revision": "candidate-v1",
            "lifecycle_state": "active_method_unchanged",
            "active_method_changed": False,
            "summary": "Active method unchanged.",
        },
        "boundary": {
            "research_aid_only": True,
            "investment_advice": False,
            "trading_allowed": False,
            "raw_provider_payload_recorded": False,
            "private_source_content_read": False,
        },
    }


def _provider_projection() -> dict[str, object]:
    return {
        "schema_version": "finance_research_dashboard_packet_v0",
        "presentation_projection": {
            "schema_version": "extension_presentation_projection_v0",
            "surface_id": "investment-research",
            "goal_id": "synthetic-research-goal",
            "generated_at": "2026-01-15T12:00:00+00:00",
            "review_due_at": "2026-02-15T12:00:00+00:00",
            "lineage": {
                "source_id": "synthetic-research-2026-01-15",
                "version": 1,
                "row_lifecycle": "active",
                "supersedes": [],
                "superseded_by": None,
            },
            "view_schema": "decision_research_dashboard_v0",
            "view": _valid_view(),
        },
    }


def _projection_provider(
    path: Path,
    *,
    projection: dict[str, object] | None = None,
    invocation_marker: Path | None = None,
) -> Path:
    response = projection if projection is not None else _provider_projection()
    marker_statement = (
        ""
        if invocation_marker is None
        else f"Path({str(invocation_marker)!r}).write_text('called', encoding='utf-8')\n"
    )
    path.write_text(
        f"""#!{sys.executable}
import json
from pathlib import Path
import sys

if "--doctor" in sys.argv:
    raise SystemExit(0)

json.load(sys.stdin)
{marker_statement}json.dump({response!r}, sys.stdout)
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _projection_manifest(
    path: Path,
    *,
    entrypoint: Path,
    version: str = "1.0.0",
) -> Path:
    path.write_text(
        f"""\
schema_version = "loopx_extension_manifest_v0"
id = "test-research-extension"
version = "{version}"
requires_loopx_api = ">=1,<2"
permissions = []

[runtime]
protocol = "test_research_extension_v0"
entrypoint = {json.dumps(str(entrypoint))}
doctor_args = ["--doctor"]
required_permissions = []
timeout_seconds = 5

[[presentation_surfaces]]
id = "investment-research"
kind = "decision_research_dashboard"
title = "Investment Research"
view_schema = "decision_research_dashboard_v0"
visibility = "owner-only"
empty_state_title = "No validated research yet"
empty_state_detail = "Publish a validated projection."
""",
        encoding="utf-8",
    )
    return path


def _installed_projection_extension(
    tmp_path: Path,
    *,
    projection: dict[str, object] | None = None,
    invocation_marker: Path | None = None,
) -> tuple[Path, dict[str, object]]:
    provider = _projection_provider(
        tmp_path / "provider",
        projection=projection,
        invocation_marker=invocation_marker,
    )
    manifest = _projection_manifest(
        tmp_path / "extension.toml",
        entrypoint=provider,
    )
    state_file = tmp_path / "runtime" / "extensions" / "state.json"
    installed = install_extension(manifest, state_file=state_file, execute=True)
    return state_file, installed


def test_decision_research_view_preserves_strict_research_truth() -> None:
    validated = validate_decision_research_view(_valid_view())

    assert validated["adjudication"]["status"] == "insufficient_evidence"
    assert validated["metrics"][0]["value"] == "0"
    assert validated["metrics"][1]["value"] == "unchanged"
    assert validated["layers"][1]["status"] == "rejected"
    assert validated["research_ledger"][0]["decision"] == "rejected"
    assert [item["probability"] for item in validated["entities"][0]["scenario_estimates"]] == [
        0.25,
        0.5,
        0.25,
    ]
    assert validated["boundary"]["trading_allowed"] is False


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda view: view.update({"unsupported": "field"}),
            "unsupported keys",
        ),
        (
            lambda view: view["identity"].update({"as_of": "not-a-timestamp"}),
            "as_of",
        ),
        (
            lambda view: view["entities"][0]["observations"][0].update(
                {"invalidation": ""}
            ),
            "invalidation",
        ),
        (
            lambda view: view["entities"][0]["scenario_estimates"][0].update(
                {"assumptions": []}
            ),
            "assumptions",
        ),
        (
            lambda view: view["entities"][0]["scenario_estimates"][0].update(
                {"probability": 0.4}
            ),
            "sum to 1",
        ),
        (
            lambda view: view["entities"][0].update(
                {"counterevidence": []}
            ),
            "counterevidence",
        ),
        (
            lambda view: view["entities"][0].update(
                {"thesis_breakers": []}
            ),
            "thesis_breakers",
        ),
        (
            lambda view: view["identity"].update(
                {"subtitle": "<script>alert(1)</script>"}
            ),
            "plain text",
        ),
        (
            lambda view: view["identity"].update(
                {"subtitle": "Owner account ID 998877 remains linked."}
            ),
            "sensitive material",
        ),
        (
            lambda view: view["identity"].update(
                {"subtitle": "Owner account_id 998877 remains linked."}
            ),
            "sensitive material",
        ),
        (
            lambda view: view["identity"].update(
                {"subtitle": "Research source: .codex/goals/private-research.md"}
            ),
            "local path",
        ),
        (
            lambda view: view["identity"].update(
                {"subtitle": "Research source: ../.codex/goals/private-research.md"}
            ),
            "local path",
        ),
        (
            lambda view: view["identity"].update(
                {"subtitle": "Research source: project/.local/private-research.md"}
            ),
            "local path",
        ),
        (
            lambda view: view["layers"][0]["evidence_points"].append(
                "/tmp/private-research.json"
            ),
            "local path",
        ),
        (
            lambda view: view["layers"][0].update(
                {"raw_provider_response": "secret"}
            ),
            "forbidden key",
        ),
        (
            lambda view: view["boundary"].update({"investment_advice": True}),
            "research boundary",
        ),
        (
            lambda view: view.update(
                {
                    "dashboard_summaries": [
                        *view["dashboard_summaries"],
                        *deepcopy(view["dashboard_summaries"]),
                        *deepcopy(view["dashboard_summaries"]),
                        *deepcopy(view["dashboard_summaries"]),
                    ]
                }
            ),
            "at most 3",
        ),
    ],
)
def test_decision_research_view_rejects_invalid_or_private_content(
    mutator,
    message: str,
) -> None:
    view = deepcopy(_valid_view())
    mutator(view)

    with pytest.raises(ValueError, match=message):
        validate_decision_research_view(view)


def test_decision_research_view_rejects_non_finite_probability() -> None:
    view = deepcopy(_valid_view())
    view["entities"][0]["scenario_estimates"][0]["probability"] = float("nan")

    with pytest.raises(ValueError, match="finite"):
        validate_decision_research_view(view)


def test_decision_research_view_allows_explicit_public_evidence_url() -> None:
    view = _valid_view()
    view["research_ledger"][0]["evidence_refs"].append(
        "https://www.sec.gov/Archives/edgar/data/000000/example.htm"
    )

    validated = validate_decision_research_view(view)

    assert validated["research_ledger"][0]["evidence_refs"][-1].startswith(
        "https://www.sec.gov/"
    )


@pytest.mark.parametrize(
    "reference",
    [
        "http://example.com/evidence",
        "https://localhost/evidence",
        "https://127.0.0.1/evidence",
        "https://private.example.internal/evidence",
        "https://example.com/private/report?"
        + "".join(("to", "ken"))
        + "=synthetic-value",
        "https://example.com/report?"
        + "".join(("refresh_", "to", "ken"))
        + "=synthetic-value",
    ],
)
def test_decision_research_view_rejects_unsafe_evidence_urls(
    reference: str,
) -> None:
    view = _valid_view()
    view["research_ledger"][0]["evidence_refs"].append(reference)

    with pytest.raises(ValueError, match="evidence reference"):
        validate_decision_research_view(view)


def test_projection_publication_dry_run_does_not_invoke_or_write(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "provider-called"
    state_file, installed = _installed_projection_extension(
        tmp_path,
        invocation_marker=marker,
    )

    receipt = publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
    )

    assert receipt == {
        "ok": True,
        "schema_version": "extension_projection_publish_receipt_v0",
        "operation": "publish_projection",
        "extension_id": "test-research-extension",
        "surface_id": "investment-research",
        "revision": installed["revision"],
        "dry_run": True,
        "executed": False,
        "status": "ready",
    }
    assert not marker.exists()
    assert not default_extension_projection_root(state_file).exists()


def test_projection_publication_binds_revision_hash_and_exact_readback(
    tmp_path: Path,
) -> None:
    state_file, installed = _installed_projection_extension(tmp_path)

    receipt = publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
        execute=True,
    )

    projection_file = (
        default_extension_projection_root(state_file)
        / "test-research-extension"
        / "investment-research.json"
    )
    persisted = json.loads(projection_file.read_text(encoding="utf-8"))
    assert receipt["ok"] is True
    assert receipt["status"] == "published"
    assert receipt["revision"] == installed["revision"]
    assert receipt["payload_sha256"] == persisted["payload_sha256"]
    assert receipt["readback_verified"] is True
    assert persisted["schema_version"] == "extension_projection_surface_v0"
    assert persisted["extension_id"] == "test-research-extension"
    assert persisted["extension_revision"] == installed["revision"]
    assert persisted["surface_id"] == "investment-research"
    assert persisted["visibility"] == "owner-only"
    assert persisted["view"]["metrics"][0]["value"] == "0"
    assert projection_file.stat().st_mode & 0o777 == 0o600
    assert not list(projection_file.parent.glob(".*.tmp.*"))


def test_failed_projection_publication_preserves_previous_file(
    tmp_path: Path,
) -> None:
    state_file, _ = _installed_projection_extension(tmp_path)
    first = publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
        execute=True,
    )
    projection_file = (
        default_extension_projection_root(state_file)
        / "test-research-extension"
        / "investment-research.json"
    )
    previous_bytes = projection_file.read_bytes()

    invalid = _provider_projection()
    invalid["presentation_projection"]["view"]["entities"][0][
        "scenario_estimates"
    ][0]["probability"] = 0.9
    _projection_provider(tmp_path / "provider", projection=invalid)
    doctor_installed_extension(
        "test-research-extension",
        state_file=state_file,
        execute=True,
    )

    with pytest.raises(ValueError, match="sum to 1"):
        publish_extension_projection(
            "test-research-extension",
            "investment-research",
            state_file=state_file,
            request={"schema_version": "synthetic_request_v0"},
            execute=True,
        )

    assert projection_file.read_bytes() == previous_bytes
    assert json.loads(previous_bytes)["payload_sha256"] == first["payload_sha256"]


def test_projection_publication_rejects_undeclared_surface(
    tmp_path: Path,
) -> None:
    state_file, _ = _installed_projection_extension(tmp_path)

    with pytest.raises(ValueError, match="does not declare presentation surface"):
        publish_extension_projection(
            "test-research-extension",
            "other-surface",
            state_file=state_file,
            request={"schema_version": "synthetic_request_v0"},
            execute=True,
        )


def test_active_presentation_surfaces_project_empty_ready_and_review_due(
    tmp_path: Path,
) -> None:
    state_file, _ = _installed_projection_extension(tmp_path)

    empty = collect_active_extension_presentation_surfaces(
        state_file=state_file,
        now=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )
    assert empty["count"] == 1
    assert empty["empty_count"] == 1
    assert empty["items"][0]["state"] == "empty"
    assert "view" not in empty["items"][0]

    publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
        execute=True,
    )
    ready = collect_active_extension_presentation_surfaces(
        state_file=state_file,
        now=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )
    assert ready["ready_count"] == 1
    assert ready["items"][0]["state"] == "ready"
    assert ready["items"][0]["view"]["metrics"][0]["value"] == "0"

    review_due = collect_active_extension_presentation_surfaces(
        state_file=state_file,
        now=datetime(2026, 2, 16, tzinfo=timezone.utc),
    )
    assert review_due["review_due_count"] == 1
    assert review_due["items"][0]["state"] == "review_due"
    assert review_due["items"][0]["view"]["method_state"][
        "active_method_changed"
    ] is False


def test_active_presentation_surfaces_hide_disabled_or_stale_extension(
    tmp_path: Path,
) -> None:
    state_file, _ = _installed_projection_extension(tmp_path)
    publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
        execute=True,
    )

    disable_extension(
        "test-research-extension",
        state_file=state_file,
        execute=True,
    )
    assert collect_active_extension_presentation_surfaces(
        state_file=state_file
    )["items"] == []

    enable_extension(
        "test-research-extension",
        state_file=state_file,
        execute=True,
    )
    assert collect_active_extension_presentation_surfaces(
        state_file=state_file,
        now=datetime(2026, 1, 20, tzinfo=timezone.utc),
    )["ready_count"] == 1

    _projection_provider(tmp_path / "provider")
    assert collect_active_extension_presentation_surfaces(
        state_file=state_file
    )["items"] == []


def test_active_presentation_surfaces_fail_closed_on_current_file_corruption(
    tmp_path: Path,
) -> None:
    state_file, _ = _installed_projection_extension(tmp_path)
    publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
        execute=True,
    )
    projection_file = (
        default_extension_projection_root(state_file)
        / "test-research-extension"
        / "investment-research.json"
    )
    persisted = json.loads(projection_file.read_text(encoding="utf-8"))
    persisted["view"]["metrics"][0]["value"] = "forged"
    projection_file.write_text(json.dumps(persisted), encoding="utf-8")

    collection = collect_active_extension_presentation_surfaces(
        state_file=state_file
    )

    assert collection["invalid_count"] == 1
    assert collection["items"][0]["state"] == "invalid"
    assert collection["items"][0]["diagnostic"] == "projection_hash_invalid"
    assert "view" not in collection["items"][0]


def test_active_presentation_surfaces_do_not_reuse_old_revision_projection(
    tmp_path: Path,
) -> None:
    state_file, installed = _installed_projection_extension(tmp_path)
    publish_extension_projection(
        "test-research-extension",
        "investment-research",
        state_file=state_file,
        request={"schema_version": "synthetic_request_v0"},
        execute=True,
    )
    manifest_v2 = _projection_manifest(
        tmp_path / "extension-v2.toml",
        entrypoint=tmp_path / "provider",
        version="2.0.0",
    )
    upgraded = install_extension(
        manifest_v2,
        state_file=state_file,
        operation="upgrade",
        execute=True,
    )
    assert upgraded["revision"] != installed["revision"]

    collection = collect_active_extension_presentation_surfaces(
        state_file=state_file
    )

    assert collection["empty_count"] == 1
    assert collection["items"][0]["state"] == "empty"
    assert collection["items"][0]["extension_revision"] == upgraded["revision"]


def test_publish_projection_cli_supports_dry_run_and_execute(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state_file, installed = _installed_projection_extension(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps({"schema_version": "synthetic_request_v0"}),
        encoding="utf-8",
    )
    arguments = [
        "--format",
        "json",
        "extension",
        "publish-projection",
        "test-research-extension",
        "investment-research",
        "--state-file",
        str(state_file),
        "--input-json",
        str(request_file),
    ]

    assert main(arguments) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["status"] == "ready"
    assert preview["executed"] is False

    assert main([*arguments, "--execute"]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["status"] == "published"
    assert published["revision"] == installed["revision"]
    assert published["readback_verified"] is True
