"""Run one external-agent phase without taking benchmark ownership.

The surrounding benchmark harness owns task provisioning, container lifecycle,
verification, and score calculation. This module only consumes a small
versioned request, invokes a runner-selected solver command in the supplied
workspace, and writes a public-safe result receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

EXTERNAL_AGENT_REQUEST_SCHEMA_VERSION = "external_agent_request_v1"
EXTERNAL_AGENT_RESULT_SCHEMA_VERSION = "external_agent_result_v1"
LOOPX_EXTERNAL_AGENT_PHASE_RECEIPT_SCHEMA_VERSION = (
    "loopx_external_agent_phase_receipt_v1"
)
_MAX_TIMEOUT_SECONDS = 86_400.0
_RESULT_STATUSES = {"succeeded", "failed", "timed_out"}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("external_agent_request_unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError("external_agent_request_not_object")
    return value


def _validate_request(value: Mapping[str, Any]) -> tuple[str, Path, float]:
    if value.get("schema_version") != EXTERNAL_AGENT_REQUEST_SCHEMA_VERSION:
        raise ValueError("external_agent_request_schema_unsupported")

    instruction = value.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("external_agent_request_instruction_missing")

    workspace_value = value.get("workspace")
    if not isinstance(workspace_value, str) or not workspace_value.strip():
        raise ValueError("external_agent_request_workspace_missing")
    workspace = Path(workspace_value)
    if not workspace.is_absolute() or not workspace.is_dir():
        raise ValueError("external_agent_request_workspace_invalid")

    timeout_value = value.get("timeout_seconds")
    if isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float)):
        raise ValueError("external_agent_request_timeout_invalid")
    timeout_seconds = float(timeout_value)
    if not 0 < timeout_seconds <= _MAX_TIMEOUT_SECONDS:
        raise ValueError("external_agent_request_timeout_invalid")

    return instruction, workspace, timeout_seconds


def _validate_solver_command(value: Sequence[str]) -> list[str]:
    if isinstance(value, (str, bytes)):
        raise ValueError("external_agent_solver_command_invalid")
    command = [item for item in value if isinstance(item, str) and item]
    if len(command) != len(value) or not command:
        raise ValueError("external_agent_solver_command_invalid")
    return command


def _result(
    *,
    status: str,
    exit_code: int | None,
    duration_ms: int,
    instruction: str | None,
    command: Sequence[str],
    classification: str,
) -> dict[str, Any]:
    if status not in _RESULT_STATUSES:
        raise ValueError("external_agent_result_status_invalid")
    receipt: dict[str, Any] = {
        "schema_version": LOOPX_EXTERNAL_AGENT_PHASE_RECEIPT_SCHEMA_VERSION,
        "classification": classification,
        "command_recorded": False,
        "command_argument_count": len(command),
        "duration_ms": max(0, duration_ms),
        "instruction_recorded": False,
        "workspace_recorded": False,
    }
    if instruction is not None:
        receipt["instruction_sha256"] = _sha256(instruction)
        receipt["instruction_chars"] = len(instruction)
    return {
        "schema_version": EXTERNAL_AGENT_RESULT_SCHEMA_VERSION,
        "status": status,
        "exit_code": exit_code,
        "receipt": receipt,
    }


def run_external_agent_phase(
    request: Mapping[str, Any],
    *,
    solver_command: Sequence[str],
    request_path: Path | None = None,
) -> dict[str, Any]:
    """Execute one runner-owned solver command from an external-agent request."""

    instruction, workspace, timeout_seconds = _validate_request(request)
    command = _validate_solver_command(solver_command)
    environment = {
        "LOOPX_EXTERNAL_AGENT_REQUEST_SCHEMA_VERSION": (
            EXTERNAL_AGENT_REQUEST_SCHEMA_VERSION
        ),
        "LOOPX_EXTERNAL_AGENT_INSTRUCTION_SHA256": _sha256(instruction),
        "LOOPX_EXTERNAL_AGENT_INSTRUCTION_CHARS": str(len(instruction)),
        "LOOPX_EXTERNAL_AGENT_WORKSPACE": str(workspace),
        "LOOPX_EXTERNAL_AGENT_TIMEOUT_SECONDS": str(timeout_seconds),
    }
    if request_path is not None:
        environment["LOOPX_EXTERNAL_AGENT_REQUEST"] = str(request_path)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env={**os.environ, **environment},
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _result(
            status="timed_out",
            exit_code=124,
            duration_ms=int((time.monotonic() - started) * 1000),
            instruction=instruction,
            command=command,
            classification="solver_timeout",
        )
    except OSError:
        return _result(
            status="failed",
            exit_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
            instruction=instruction,
            command=command,
            classification="solver_startup_failed",
        )

    return _result(
        status="succeeded" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        duration_ms=int((time.monotonic() - started) * 1000),
        instruction=instruction,
        command=command,
        classification=(
            "solver_completed"
            if completed.returncode == 0
            else "solver_exited_nonzero"
        ),
    )


def write_external_agent_result(path: Path, result: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(dict(result), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def execute_external_agent_request(
    *,
    request_path: Path,
    result_path: Path,
    solver_command: Sequence[str],
    execute: bool,
) -> dict[str, Any]:
    """Validate one request and optionally run its solver command."""

    try:
        command = _validate_solver_command(solver_command)
        request = _load_json_object(request_path)
        instruction, _workspace, _timeout_seconds = _validate_request(request)
        result = (
            run_external_agent_phase(
                request,
                solver_command=command,
                request_path=request_path,
            )
            if execute
            else _result(
                status="succeeded",
                exit_code=0,
                duration_ms=0,
                instruction=instruction,
                command=command,
                classification="request_validated_not_executed",
            )
        )
    except (TypeError, ValueError):
        result = _result(
            status="failed",
            exit_code=None,
            duration_ms=0,
            instruction=None,
            command=(),
            classification="agent_phase_input_invalid",
        )
    write_external_agent_result(result_path, result)
    return result
