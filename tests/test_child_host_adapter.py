from __future__ import annotations

import pytest

from loopx.control_plane.turn_driver.child_host_adapter import (
    project_child_context_adapter,
    supported_child_context_modes,
)


@pytest.mark.parametrize(
    ("context_mode", "expected_operation", "expected_arguments", "requires_session"),
    [
        pytest.param(
            "fresh",
            "spawn_agent",
            {"fork_context": False},
            False,
            id="fresh_child_does_not_inherit_parent_context",
        ),
        pytest.param(
            "forked_snapshot",
            "spawn_agent",
            {"fork_context": True},
            False,
            id="explicit_parent_snapshot",
        ),
        pytest.param(
            "resume",
            "resume_agent",
            {},
            True,
            id="existing_child_session",
        ),
    ],
)
def test_codex_child_context_adapter_maps_modes(
    context_mode: str,
    expected_operation: str,
    expected_arguments: dict[str, bool],
    requires_session: bool,
) -> None:
    assert project_child_context_adapter(
        host="codex-cli",
        context_mode=context_mode,
    ) == {
        "host": "codex-cli",
        "native_operation": expected_operation,
        "arguments": expected_arguments,
        "requires_session": requires_session,
    }


def test_host_child_context_adapter_exposes_only_supported_modes() -> None:
    assert supported_child_context_modes("codex-cli") == (
        "fresh",
        "forked_snapshot",
        "resume",
    )
    assert supported_child_context_modes("claude-code") == ("fresh",)
    assert supported_child_context_modes("generic-cli") == ()
    assert (
        project_child_context_adapter(
            host="claude-code",
            context_mode="forked_snapshot",
        )
        is None
    )
