from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import os
import socket
import sys
from typing import Any, Protocol

from loopx.extensions.authority import validate_extension_authority_decision
from loopx.extensions.execution_envelope import (
    validate_extension_execution_envelope,
)
from .contract import (
    ACTION,
    EXTENSION_ID,
    PERMISSION,
    PROTOCOL,
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    effect_scope,
    trade_market,
    validate_request,
)


class Broker(Protocol):
    def submit(self, order: Mapping[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


def _account_ref(account_id: object) -> str:
    digest = hashlib.sha256(str(account_id).encode("utf-8")).hexdigest()[:12]
    return f"futu-hk-sim-{digest}"


def _broker_ref(order_id: object) -> str:
    digest = hashlib.sha256(str(order_id).encode("utf-8")).hexdigest()[:16]
    return f"futu-order-{digest}"


def _records(frame: object) -> list[dict[str, Any]]:
    to_dict = getattr(frame, "to_dict", None)
    if not callable(to_dict):
        raise RuntimeError("Futu OpenD returned an unsupported table")
    rows = to_dict("records")
    if not isinstance(rows, list):
        raise RuntimeError("Futu OpenD returned an unsupported table")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


class FutuBroker:
    def __init__(
        self,
        *,
        account_ref: str,
        market: str,
        host: str,
        port: int,
    ) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Futu OpenD host must be loopback")
        self._requested_account_ref = account_ref
        self._market = market
        self._host = host
        self._port = port
        self._context: Any = None
        self._futu: Any = None
        self._account_id: Any = None

    def _connect(self) -> None:
        if self._context is not None:
            return
        with redirect_stdout(sys.stderr):
            import futu

            if self._market == "HK":
                trade_market_enum = futu.TrdMarket.HK
                simulated_account_type = futu.SimAccType.STOCK
            elif self._market == "US":
                trade_market_enum = futu.TrdMarket.US
                simulated_account_type = futu.SimAccType.STOCK_AND_OPTION
            elif self._market == "CN":
                trade_market_enum = futu.TrdMarket.CN
                simulated_account_type = futu.SimAccType.STOCK
            else:
                raise ValueError("Futu broker only supports HK, US, or CN simulated stocks")
            context = futu.OpenSecTradeContext(
                filter_trdmarket=trade_market_enum,
                host=self._host,
                port=self._port,
                security_firm=futu.SecurityFirm.FUTUSECURITIES,
            )
            ret, accounts = context.get_acc_list()
        if ret != futu.RET_OK:
            context.close()
            raise RuntimeError(f"Futu OpenD account discovery failed: {accounts}")
        matches = [
            row
            for row in _records(accounts)
            if row.get("trd_env") == futu.TrdEnv.SIMULATE
            and row.get("sim_acc_type") == simulated_account_type
            and _account_ref(row.get("acc_id")) == self._requested_account_ref
        ]
        if len(matches) != 1:
            context.close()
            raise ValueError("requested simulated stock account_ref was not found")
        self._context = context
        self._futu = futu
        self._account_id = matches[0]["acc_id"]

    def _existing_order(self, idempotency_key: str) -> dict[str, Any] | None:
        with redirect_stdout(sys.stderr):
            ret, orders = self._context.order_list_query(
                order_id="",
                trd_env=self._futu.TrdEnv.SIMULATE,
                acc_id=self._account_id,
                refresh_cache=True,
            )
        if ret != self._futu.RET_OK:
            raise RuntimeError(f"Futu OpenD order query failed: {orders}")
        matches = [
            row for row in _records(orders) if row.get("remark") == idempotency_key
        ]
        if len(matches) > 1:
            raise RuntimeError("idempotency key matched multiple simulated orders")
        return matches[0] if matches else None

    def _result(self, row: Mapping[str, Any], *, submitted: bool) -> dict[str, Any]:
        return {
            "ok": True,
            "schema_version": RESULT_SCHEMA,
            "environment": "simulate",
            "submitted": submitted,
            "readback_verified": True,
            "broker_order_ref": _broker_ref(row.get("order_id")),
            "order_status": str(row.get("order_status") or "unknown"),
            "dealt_quantity": float(row.get("dealt_qty") or 0),
            "dealt_average_price": float(row.get("dealt_avg_price") or 0),
            "external_reads_performed": True,
            "external_writes_performed": submitted,
        }

    def submit(self, order: Mapping[str, Any]) -> dict[str, Any]:
        self._connect()
        existing = self._existing_order(str(order["idempotency_key"]))
        if existing is not None:
            return self._result(existing, submitted=False)
        futu = self._futu
        order_type = (
            futu.OrderType.MARKET
            if order["order_type"] == "market"
            else futu.OrderType.NORMAL
        )
        price = 0.0 if order["order_type"] == "market" else order["limit_price"]
        side = futu.TrdSide.BUY if order["side"] == "buy" else futu.TrdSide.SELL
        with redirect_stdout(sys.stderr):
            ret, submitted = self._context.place_order(
                price=price,
                qty=order["quantity"],
                code=order["symbol"],
                trd_side=side,
                order_type=order_type,
                trd_env=futu.TrdEnv.SIMULATE,
                acc_id=self._account_id,
                remark=order["idempotency_key"],
                time_in_force=futu.TimeInForce.DAY,
            )
        if ret != futu.RET_OK:
            raise RuntimeError(f"Futu OpenD simulated order failed: {submitted}")
        submitted_rows = _records(submitted)
        if len(submitted_rows) != 1 or not submitted_rows[0].get("order_id"):
            raise RuntimeError("Futu OpenD did not return one order id")
        raw_order_id = submitted_rows[0]["order_id"]
        with redirect_stdout(sys.stderr):
            ret, readback = self._context.order_list_query(
                order_id=raw_order_id,
                trd_env=futu.TrdEnv.SIMULATE,
                acc_id=self._account_id,
                refresh_cache=True,
            )
        if ret != futu.RET_OK:
            raise RuntimeError(f"Futu OpenD order readback failed: {readback}")
        rows = _records(readback)
        if len(rows) != 1 or rows[0].get("order_id") != raw_order_id:
            raise RuntimeError("Futu OpenD order readback did not match submission")
        return self._result(rows[0], submitted=True)

    def close(self) -> None:
        if self._context is not None:
            with redirect_stdout(sys.stderr):
                self._context.close()
            self._context = None


def doctor(*, host: str, port: int) -> dict[str, Any]:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Futu OpenD host must be loopback")
    with redirect_stdout(io.StringIO()):
        import futu
    with socket.create_connection((host, port), timeout=2):
        pass
    return {
        "ok": True,
        "schema_version": "futu_paper_trade_doctor_v0",
        "provider": EXTENSION_ID,
        "sdk_version": str(getattr(futu, "__version__", "unknown")),
        "opend_reachable": True,
    }


def execute_provider_request(
    request: Mapping[str, Any],
    *,
    environment: Mapping[str, str] | None = None,
    broker_factory: Callable[..., Broker] = FutuBroker,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise ValueError("provider request must be an object")
    if request.get("schema_version") != REQUEST_SCHEMA:
        raise ValueError(f"provider request must use {REQUEST_SCHEMA}")
    if set(request) != {
        "schema_version",
        "operation",
        "execute",
        "order",
        "authority_decision",
        "execution_envelope",
    }:
        raise ValueError("provider request fields do not match the schema")
    if request.get("operation") != "submit_order" or request.get("execute") is not True:
        raise ValueError("provider request must explicitly execute submit_order")
    order = validate_request(request)
    authority = request.get("authority_decision")
    if not isinstance(authority, Mapping):
        raise ValueError("provider authority_decision must be an object")
    env = dict(environment or os.environ)
    extension_id = str(env.get("LOOPX_EXTENSION_ID") or "").strip()
    extension_revision = str(env.get("LOOPX_EXTENSION_REVISION") or "").strip()
    granted_permissions = [
        value
        for value in str(
            env.get("LOOPX_EXTENSION_GRANTED_PERMISSIONS") or ""
        ).split(",")
        if value
    ]
    validate_extension_authority_decision(
        authority,
        extension_id=extension_id,
        extension_revision=extension_revision,
        protocol=PROTOCOL,
        required_permissions=[PERMISSION],
        available_capabilities=granted_permissions,
        request=request,
        now=now,
    )
    envelope = request.get("execution_envelope")
    if not isinstance(envelope, Mapping):
        raise ValueError("provider execution_envelope must be an object")
    validate_extension_execution_envelope(
        envelope,
        action=ACTION,
        scope=effect_scope(request),
        extension_id=extension_id,
        extension_revision=extension_revision,
        request=request,
    )
    host = str(env.get("LOOPX_FUTU_OPEND_HOST") or "127.0.0.1")
    port = int(env.get("LOOPX_FUTU_OPEND_PORT") or "11111")
    broker = broker_factory(
        account_ref=order["account_ref"],
        market=trade_market(order["symbol"]),
        host=host,
        port=port,
    )
    try:
        return broker.submit(order)
    finally:
        broker.close()
