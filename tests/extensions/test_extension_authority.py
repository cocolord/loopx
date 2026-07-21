from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

from loopx.extensions.authority import (
    EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION,
    extension_authority_request_digest,
    validate_extension_authority_decision,
)
from loopx.extensions.runtime import install_extension, run_standalone_extension


NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


def _authority(request: dict[str, object], **updates: object) -> dict[str, object]:
    decision: dict[str, object] = {
        "schema_version": EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION,
        "decision": "allow",
        "extension_id": "test-effect-extension",
        "extension_revision": "revision-1",
        "protocol": "test_effect_extension_v0",
        "action": "test.effect.write",
        "scope": {"resource": "example"},
        "permissions": ["test.effect.write"],
        "subject": {"agent_id": "test-agent", "goal_id": "test-goal"},
        "nonce": "test-authority-1",
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "request_digest": extension_authority_request_digest(request),
    }
    decision.update(updates)
    return decision


def _validate(
    authority: dict[str, object],
    request: dict[str, object],
    *,
    available: tuple[str, ...] = ("test.effect.write",),
) -> dict[str, object]:
    return validate_extension_authority_decision(
        authority,
        extension_id="test-effect-extension",
        extension_revision="revision-1",
        protocol="test_effect_extension_v0",
        required_permissions=["test.effect.write"],
        available_capabilities=available,
        request=request,
        now=NOW,
    )


def test_authority_binds_request_revision_permission_and_expiry() -> None:
    request = {"schema_version": "test_effect_request_v0", "value": 1}
    assert _validate(_authority(request), request)["decision"] == "allow"
    with pytest.raises(ValueError, match="request_digest"):
        _validate(_authority(request), {**request, "value": 2})
    with pytest.raises(ValueError, match="observed capabilities"):
        _validate(_authority(request), request, available=())
    with pytest.raises(ValueError, match="expired"):
        _validate(
            _authority(
                request,
                expires_at=(NOW - timedelta(seconds=1)).isoformat(),
            ),
            request,
        )


def test_authority_rejects_reserved_request_fields() -> None:
    request = {"schema_version": "test_effect_request_v0"}
    digest = extension_authority_request_digest(
        {**request, "authority_decision": {"ignored": True}}
    )
    assert digest == extension_authority_request_digest(request)


def test_permissioned_flat_extension_runs_only_with_typed_authority(
    tmp_path: Path,
) -> None:
    provider = tmp_path / "provider"
    provider.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "if '--doctor' in sys.argv:\n"
        "    raise SystemExit(0)\n"
        "request = json.load(sys.stdin)\n"
        "print(json.dumps({'ok': True, 'schema_version': "
        "'test_effect_result_v0', 'authority': "
        "request['authority_decision']['schema_version'], 'extension_id': "
        "os.environ['LOOPX_EXTENSION_ID']}))\n",
        encoding="utf-8",
    )
    provider.chmod(0o755)
    manifest = tmp_path / "extension.toml"
    manifest.write_text(
        f'''schema_version = "loopx_extension_manifest_v0"
id = "test-effect-extension"
version = "1.0.0"
requires_loopx_api = ">=1,<2"
permissions = ["test.effect.write"]

[runtime]
protocol = "test_effect_extension_v0"
entrypoint = {json.dumps(str(provider))}
doctor_args = ["--doctor"]
required_permissions = ["test.effect.write"]
timeout_seconds = 5
''',
        encoding="utf-8",
    )
    state_file = tmp_path / "extensions.json"
    installed = install_extension(manifest, state_file=state_file, execute=True)
    request = {"schema_version": "test_effect_request_v0", "value": 1}
    authority = _authority(
        request,
        extension_revision=installed["revision"],
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )

    receipt = run_standalone_extension(
        "test-effect-extension",
        state_file=state_file,
        request=request,
        authority_decision=authority,
        available_capabilities=["test.effect.write"],
        execute=True,
    )

    assert receipt["status"] == "succeeded"
    assert receipt["authority_validated"] is True
    assert receipt["provider_result"]["extension_id"] == "test-effect-extension"
