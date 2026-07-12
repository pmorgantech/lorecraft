"""Operational/process-lifecycle helpers (composition layer).

These modules coordinate the *running* of the engine — the cold-boot DB reset
and the admin-requested restart handshake — and are shared by the admin web host
(``webui.admin``) and the out-of-process supervisor (``scripts/supervisor.py``).

They are deliberately Tier-agnostic infrastructure: pure stdlib, importing no
engine/feature/web code, so the supervisor can import them without dragging the
whole app in and the web host can import them without a tier violation. The
engine never imports ``lorecraft.ops``.
"""

from __future__ import annotations

from lorecraft.ops.restart_control import (
    RestartControl,
    RestartRequest,
    SupervisorStatus,
)

__all__ = [
    "RestartControl",
    "RestartRequest",
    "SupervisorStatus",
]
