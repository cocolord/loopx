from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from .contract import EXTENSION_ID
from .provider import doctor, execute_provider_request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=EXTENSION_ID)
    parser.add_argument("--doctor", action="store_true")
    return parser


def _emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.doctor:
            payload = doctor(
                host=os.environ.get("LOOPX_FUTU_OPEND_HOST", "127.0.0.1"),
                port=int(os.environ.get("LOOPX_FUTU_OPEND_PORT", "11111")),
            )
        else:
            request = json.load(sys.stdin)
            payload = execute_provider_request(request)
    except Exception as exc:
        payload = {
            "ok": False,
            "schema_version": "futu_paper_trade_error_v0",
            "provider": EXTENSION_ID,
            "error": str(exc),
        }
    _emit(payload)
    return 0 if payload.get("ok") else 1


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
