from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any


EXTENSION_ID = "loopx-futu-paper-trade"
PROTOCOL = "futu_paper_trade_extension_v0"
PERMISSION = "broker.order.submit.simulated"
REQUEST_SCHEMA = "futu_paper_trade_request_v0"
RESULT_SCHEMA = "futu_paper_trade_result_v0"
ACTION = "paper_trade.order.submit.simulated"
_SYMBOL_RE = re.compile(r"^[A-Z]{2,8}\.[A-Z0-9]{1,16}$")
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
_ORDER_FIELDS = {
    "schema_version",
    "account_ref",
    "environment",
    "symbol",
    "side",
    "quantity",
    "order_type",
    "limit_price",
    "time_in_force",
    "idempotency_key",
}


def _text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _token(value: object, label: str) -> str:
    token = _text(value, label)
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError(f"{label} must be a bounded execution token")
    return token


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def trade_market(symbol: str) -> str:
    venue = symbol.split(".", 1)[0]
    if venue in {"SH", "SZ"}:
        return "CN"
    if venue in {"HK", "US"}:
        return venue
    raise ValueError("Futu paper-trade v0 only supports HK, US, SH, and SZ stocks")


def normalize_order(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Futu paper-trade order must be an object")
    unknown = sorted(set(raw) - _ORDER_FIELDS)
    if unknown:
        raise ValueError(f"Futu paper-trade order has unsupported fields {unknown}")
    if raw.get("schema_version") != "paper_trade_order_request_v0":
        raise ValueError("Futu paper-trade order must use paper_trade_order_request_v0")
    if raw.get("environment") != "simulate":
        raise ValueError("Futu paper-trade only accepts environment=simulate")
    symbol = _text(raw.get("symbol"), "symbol").upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError("symbol must use an uppercase MARKET.CODE form")
    trade_market(symbol)
    side = _text(raw.get("side"), "side").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    quantity = raw.get("quantity")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    order_type = _text(raw.get("order_type"), "order_type").lower()
    if order_type not in {"limit", "market"}:
        raise ValueError("order_type must be limit or market")
    if _text(raw.get("time_in_force", "day"), "time_in_force").lower() != "day":
        raise ValueError("Futu paper-trade v0 only supports time_in_force=day")
    normalized: dict[str, Any] = {
        "schema_version": "paper_trade_order_request_v0",
        "account_ref": _token(raw.get("account_ref"), "account_ref"),
        "environment": "simulate",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "time_in_force": "day",
        "idempotency_key": _token(raw.get("idempotency_key"), "idempotency_key"),
    }
    limit_price = raw.get("limit_price")
    if order_type == "limit":
        if (
            not isinstance(limit_price, (int, float))
            or isinstance(limit_price, bool)
            or limit_price <= 0
        ):
            raise ValueError("limit orders require a positive limit_price")
        normalized["limit_price"] = float(limit_price)
    elif limit_price is not None:
        raise ValueError("market orders must not declare limit_price")
    return normalized


def validate_request(raw: Mapping[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != REQUEST_SCHEMA:
        raise ValueError(f"Futu paper-trade request must use {REQUEST_SCHEMA}")
    if raw.get("operation") != "submit_order" or raw.get("execute") is not True:
        raise ValueError("Futu paper-trade request must explicitly execute submit_order")
    return normalize_order(raw.get("order", {}))


def effect_scope(request: Mapping[str, Any]) -> dict[str, Any]:
    order = validate_request(request)
    return {
        "account_ref": order["account_ref"],
        "environment": "simulate",
        "symbol": order["symbol"],
        "market": trade_market(order["symbol"]),
        "side": order["side"],
        "quantity": order["quantity"],
        "order_type": order["order_type"],
        "idempotency_key": order["idempotency_key"],
        "order_digest": _digest(order),
    }
