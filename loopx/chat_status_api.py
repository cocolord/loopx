"""Read-only status projection for the loopback Chat API."""

from __future__ import annotations

import json
from typing import Any

from .chat import redact_local_paths
from .chat_goal_subagent_api import goal_subagent_configuration_enabled
from .status import collect_status


class ChatStatusRequestMixin:
    server: Any

    def _send_error(self, message: str, **kwargs: Any) -> None:
        raise NotImplementedError

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        raise NotImplementedError

    def _status(self) -> None:
        try:
            projection = collect_status(
                registry_path=self.server.registry_path,
                runtime_root_override=self.server.runtime_root_override,
                scan_roots=self.server.scan_roots,
                limit=self.server.limit,
                goal_id=self.server.selected_goal_id,
                include_public_boundary_scan=False,
                include_goal_subagent_configuration=(
                    goal_subagent_configuration_enabled(self.server)
                ),
            )
            protected_paths = [self.server.registry_path, *self.server.scan_roots]
            projection = json.loads(
                redact_local_paths(
                    json.dumps(projection, ensure_ascii=False),
                    protected_paths=protected_paths,
                )
            )
        except Exception:
            self._send_error(
                "LoopX status could not be projected for the workspace.",
                status=500,
            )
            return
        self._send_json(projection)
