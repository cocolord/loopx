from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .reducer import build_market_judgment_packet


def _load(path_text: str) -> dict[str, Any]:
    raw = (
        sys.stdin.read()
        if path_text == "-"
        else Path(path_text).read_text(encoding="utf-8")
    )
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("market-judgment input must be a JSON object")
    return payload


def _error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": "market_judgment_error_v0",
        "mode": "market-judgment",
        "error": "market-judgment input must be valid JSON"
        if isinstance(exc, json.JSONDecodeError)
        else str(exc),
        "external_reads_performed": False,
        "external_writes_performed": False,
        "order_submitted": False,
    }


def run(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if not arguments:
        try:
            payload = json.load(sys.stdin)
            if not isinstance(payload, Mapping):
                raise ValueError("provider input must be a JSON object")
            packet = build_market_judgment_packet(payload)
        except Exception as exc:
            print(json.dumps(_error(exc), sort_keys=True))
            return 1
        print(json.dumps(packet, sort_keys=True))
        return 0
    parser = argparse.ArgumentParser(prog="loopx-market-judgment")
    parser.add_argument("--doctor", action="store_true")
    sub = parser.add_subparsers(dest="command")
    reduce_parser = sub.add_parser("reduce")
    reduce_parser.add_argument("--input-json", required=True)
    reduce_parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args(arguments)
    if args.doctor:
        return 0
    if args.command != "reduce":
        raise ValueError("use --doctor or reduce")
    try:
        packet = build_market_judgment_packet(_load(args.input_json))
    except Exception as exc:
        print(json.dumps(_error(exc), indent=2, sort_keys=True))
        return 1
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except Exception as exc:
        print(
            f"market-judgment extension failed: {type(exc).__name__}", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
