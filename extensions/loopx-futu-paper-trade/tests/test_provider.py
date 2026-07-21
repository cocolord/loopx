from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[3]
EXTENSION_SRC = ROOT / "extensions" / "loopx-futu-paper-trade" / "src"
sys.path.insert(0, str(EXTENSION_SRC))

from loopx.extensions.authority import (  # noqa: E402
    EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION,
    build_authorized_extension_request,
    extension_authority_request_digest,
)
from loopx.extensions.manifest import load_extension_manifest  # noqa: E402
from loopx_futu_paper_trade.contract import (  # noqa: E402
    ACTION,
    EXTENSION_ID,
    PERMISSION,
    PROTOCOL,
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    effect_scope,
)
from loopx_futu_paper_trade.provider import execute_provider_request  # noqa: E402


NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
REVISION = "revision-1"
MANIFEST = ROOT / "extensions" / "loopx-futu-paper-trade" / "extension.toml"


def _request() -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "operation": "submit_order",
        "execute": True,
        "order": {
            "schema_version": "paper_trade_order_request_v0",
            "account_ref": "futu-hk-sim-example",
            "environment": "simulate",
            "symbol": "HK.00700",
            "side": "buy",
            "quantity": 100,
            "order_type": "market",
            "time_in_force": "day",
            "idempotency_key": "paper-tencent-example",
        },
    }


def _authority(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": EXTENSION_AUTHORITY_DECISION_SCHEMA_VERSION,
        "decision": "allow",
        "extension_id": EXTENSION_ID,
        "extension_revision": REVISION,
        "protocol": PROTOCOL,
        "action": ACTION,
        "scope": effect_scope(request),
        "permissions": [PERMISSION],
        "subject": {"agent_id": "paper-agent", "goal_id": "paper-goal"},
        "nonce": "paper-authority-1",
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "request_digest": extension_authority_request_digest(request),
    }


def _provider_request() -> dict[str, Any]:
    request = _request()
    return build_authorized_extension_request(
        request,
        authority_decision=_authority(request),
        extension_id=EXTENSION_ID,
        extension_revision=REVISION,
    )


def _environment(*, revision: str = REVISION) -> dict[str, str]:
    return {
        "LOOPX_EXTENSION_ID": EXTENSION_ID,
        "LOOPX_EXTENSION_REVISION": revision,
        "LOOPX_EXTENSION_GRANTED_PERMISSIONS": PERMISSION,
    }


class FakeBroker:
    instances: list["FakeBroker"] = []

    def __init__(
        self,
        *,
        account_ref: str,
        market: str,
        host: str,
        port: int,
    ) -> None:
        self.account_ref = account_ref
        self.market = market
        self.host = host
        self.port = port
        self.closed = False
        self.order: dict[str, Any] | None = None
        self.instances.append(self)

    def submit(self, order: dict[str, Any]) -> dict[str, Any]:
        self.order = dict(order)
        return {
            "ok": True,
            "schema_version": RESULT_SCHEMA,
            "environment": "simulate",
            "submitted": True,
            "readback_verified": True,
            "broker_order_ref": "futu-order-redacted",
            "external_writes_performed": True,
        }

    def close(self) -> None:
        self.closed = True


def test_manifest_registers_one_flat_permissioned_extension() -> None:
    manifest = load_extension_manifest(MANIFEST)
    assert manifest["provider"]["id"] == EXTENSION_ID
    assert manifest["provider"]["permissions"] == [PERMISSION]
    assert manifest["runtime"]["protocol"] == PROTOCOL
    assert manifest["capabilities"] == []
    assert manifest["implementations"] == []


def test_provider_revalidates_authority_envelope_and_simulated_order() -> None:
    FakeBroker.instances.clear()
    result = execute_provider_request(
        _provider_request(),
        environment=_environment(),
        broker_factory=FakeBroker,
        now=NOW,
    )
    assert result["environment"] == "simulate"
    assert result["readback_verified"] is True
    broker = FakeBroker.instances[0]
    assert broker.order is not None
    assert broker.order["symbol"] == "HK.00700"
    assert broker.market == "HK"
    assert broker.closed is True


def test_provider_rejects_tampered_order_before_broker_creation() -> None:
    FakeBroker.instances.clear()
    request = _provider_request()
    request["order"]["quantity"] = 200
    with pytest.raises(ValueError, match="request_digest"):
        execute_provider_request(
            request,
            environment=_environment(),
            broker_factory=FakeBroker,
            now=NOW,
        )
    assert FakeBroker.instances == []


def test_provider_rejects_mismatched_runtime_revision() -> None:
    with pytest.raises(ValueError, match="extension_revision"):
        execute_provider_request(
            _provider_request(),
            environment=_environment(revision="revision-2"),
            broker_factory=FakeBroker,
            now=NOW,
        )


def test_provider_rejects_real_environment() -> None:
    request = _request()
    request["order"]["environment"] = "real"
    with pytest.raises(ValueError, match="environment=simulate"):
        effect_scope(request)


def test_provider_routes_us_stock_to_us_simulated_market() -> None:
    FakeBroker.instances.clear()
    request = _request()
    request["order"]["symbol"] = "US.AAPL"
    authority = _authority(request)
    provider_request = build_authorized_extension_request(
        request,
        authority_decision=authority,
        extension_id=EXTENSION_ID,
        extension_revision=REVISION,
    )
    execute_provider_request(
        provider_request,
        environment=_environment(),
        broker_factory=FakeBroker,
        now=NOW,
    )
    broker = FakeBroker.instances[0]
    assert broker.market == "US"
    assert broker.order is not None
    assert broker.order["symbol"] == "US.AAPL"


@pytest.mark.parametrize("symbol", ["SH.600000", "SZ.000001"])
def test_provider_routes_a_share_to_cn_simulated_market(symbol: str) -> None:
    FakeBroker.instances.clear()
    request = _request()
    request["order"]["symbol"] = symbol
    provider_request = build_authorized_extension_request(
        request,
        authority_decision=_authority(request),
        extension_id=EXTENSION_ID,
        extension_revision=REVISION,
    )
    execute_provider_request(
        provider_request,
        environment=_environment(),
        broker_factory=FakeBroker,
        now=NOW,
    )
    broker = FakeBroker.instances[0]
    assert broker.market == "CN"
    assert broker.order is not None
    assert broker.order["symbol"] == symbol


def test_provider_rejects_unsupported_market() -> None:
    request = _request()
    request["order"]["symbol"] = "SG.D05"
    with pytest.raises(ValueError, match="only supports HK, US, SH, and SZ"):
        effect_scope(request)
