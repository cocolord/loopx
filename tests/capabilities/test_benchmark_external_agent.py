from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from loopx.capabilities.benchmark_toolkit.external_agent import (
    EXTERNAL_AGENT_REQUEST_SCHEMA_VERSION,
    EXTERNAL_AGENT_RESULT_SCHEMA_VERSION,
    execute_external_agent_request,
)
from loopx.cli import main


def _request(workspace: Path) -> dict[str, object]:
    return {
        "schema_version": EXTERNAL_AGENT_REQUEST_SCHEMA_VERSION,
        "instruction": "Implement the requested task without reading evaluator files.",
        "workspace": str(workspace),
        "timeout_seconds": 10,
    }


def test_external_agent_phase_runs_solver_with_request_reference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    marker = workspace / "marker.txt"
    request_path.write_text(json.dumps(_request(workspace)), encoding="utf-8")

    solver = [
        sys.executable,
        "-c",
        (
            "import os\n"
            "from pathlib import Path\n"
            "request = Path(os.environ['LOOPX_EXTERNAL_AGENT_REQUEST'])\n"
            "assert request.is_file()\n"
            "Path('marker.txt').write_text(os.environ['LOOPX_EXTERNAL_AGENT_INSTRUCTION_SHA256'])\n"
        ),
    ]
    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command=solver,
        execute=True,
    )

    assert result["schema_version"] == EXTERNAL_AGENT_RESULT_SCHEMA_VERSION
    assert result["status"] == "succeeded"
    assert marker.read_text(encoding="utf-8") == result["receipt"]["instruction_sha256"]
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted == result
    rendered = json.dumps(result, sort_keys=True)
    assert str(workspace) not in rendered
    assert "Implement the requested task" not in rendered
    assert "python" not in rendered


def test_external_agent_phase_sends_instruction_to_solver_stdin(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    instruction = str(_request(workspace)["instruction"])
    request_path.write_text(json.dumps(_request(workspace)), encoding="utf-8")

    solver = [
        sys.executable,
        "-c",
        (
            "import sys\n"
            "from pathlib import Path\n"
            "Path('instruction.txt').write_text(sys.stdin.read(), encoding='utf-8')\n"
        ),
    ]
    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command=solver,
        execute=True,
    )

    assert result["status"] == "succeeded"
    assert (workspace / "instruction.txt").read_text(encoding="utf-8") == instruction


def test_external_agent_phase_does_not_inherit_ambient_secrets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    marker = workspace / "ambient-secret.txt"
    request_path.write_text(json.dumps(_request(workspace)), encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_AGENT_SECRET", "must-not-cross-boundary")

    solver = [
        sys.executable,
        "-c",
        (
            "import os\n"
            "from pathlib import Path\n"
            "value = os.environ.get('SYNTHETIC_AGENT_SECRET')\n"
            "Path('ambient-secret.txt').write_text(value or 'absent', encoding='utf-8')\n"
        ),
    ]
    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command=solver,
        execute=True,
    )

    assert result["status"] == "succeeded"
    assert marker.read_text(encoding="utf-8") == "absent"


def test_external_agent_timeout_terminates_solver_descendants(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request = _request(workspace)
    request["timeout_seconds"] = 0.5
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    marker = workspace / "descendant-effect.txt"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    child_code = (
        "from pathlib import Path; import time; "
        "time.sleep(1.2); "
        "Path('descendant-effect.txt').write_text('effect', encoding='utf-8')"
    )
    solver_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(5)"
    )

    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command=[sys.executable, "-c", solver_code],
        execute=True,
    )

    assert result["status"] == "timed_out"
    assert result["exit_code"] == 124
    time.sleep(1)
    assert not marker.exists()


def test_external_agent_phase_fails_closed_for_invalid_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    result_path = tmp_path / "result.json"
    result = execute_external_agent_request(
        request_path=tmp_path / "missing.json",
        result_path=result_path,
        solver_command=[sys.executable, "-c", "raise SystemExit(0)"],
        execute=True,
    )

    assert result["status"] == "failed"
    assert result["receipt"]["classification"] == "agent_phase_input_invalid"
    assert json.loads(result_path.read_text(encoding="utf-8")) == result


def test_external_agent_phase_rejects_string_solver_command(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request(workspace)), encoding="utf-8")

    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command="not-an-argv",  # type: ignore[arg-type]
        execute=True,
    )

    assert result["status"] == "failed"
    assert result["receipt"]["classification"] == "agent_phase_input_invalid"


def test_benchmark_agent_phase_cli_reads_environment_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request(workspace)), encoding="utf-8")
    solver = [sys.executable, "-c", "raise SystemExit(0)"]

    monkeypatch.setenv("LOOPSBENCH_EXTERNAL_AGENT_REQUEST", str(request_path))
    monkeypatch.setenv("LOOPSBENCH_EXTERNAL_AGENT_RESULT", str(result_path))
    monkeypatch.setenv("LOOPX_EXTERNAL_AGENT_SOLVER_COMMAND_JSON", json.dumps(solver))

    assert main(["benchmark", "agent-phase", "--execute"]) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "succeeded"


def test_external_agent_phase_rejects_request_workspace_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()
    monkeypatch.chdir(other_workspace)
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request(workspace)), encoding="utf-8")

    result = execute_external_agent_request(
        request_path=request_path,
        result_path=result_path,
        solver_command=[sys.executable, "-c", "raise SystemExit(0)"],
        execute=True,
    )

    assert result["status"] == "failed"
    assert result["receipt"]["classification"] == "agent_phase_input_invalid"
