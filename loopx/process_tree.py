from __future__ import annotations

import os
import signal
import subprocess
from typing import Any


PROCESS_TERMINATE_GRACE_SECONDS = 1.0


def isolated_process_creation_flags() -> int:
    if os.name == "nt":  # pragma: no cover - exercised on Windows hosts.
        return int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP"))
    return 0


def _wait_for_process(process: subprocess.Popen[Any], timeout: float) -> bool:
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


def _terminate_posix_process_group(process: subprocess.Popen[Any]) -> None:
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        process.wait()
        return
    _wait_for_process(process, PROCESS_TERMINATE_GRACE_SECONDS)
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.kill()
        process.wait()


def _terminate_windows_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PROCESS_TERMINATE_GRACE_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
    if not _wait_for_process(process, PROCESS_TERMINATE_GRACE_SECONDS):
        process.kill()
        process.wait()


def terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if os.name == "posix":
        _terminate_posix_process_group(process)
        return
    if os.name == "nt":  # pragma: no cover - exercised on Windows hosts.
        _terminate_windows_process_tree(process)
        return
    if process.poll() is not None:  # pragma: no cover - unsupported platform fallback.
        return
    process.terminate()
    if not _wait_for_process(process, PROCESS_TERMINATE_GRACE_SECONDS):
        process.kill()
        process.wait()
