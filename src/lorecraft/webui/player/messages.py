"""Shared player-facing message text for the command path.

These strings are the canonical copy of two client-facing replies that are
produced from more than one place in the command pipeline — the live ``/ws``
handler (:mod:`lorecraft.webui.player.ws_command`) and the Rust-port gateway
adapter (:mod:`lorecraft.gateway.adapter`). Hoisting them here keeps the intra-
Python copies from drifting apart (a code-review advisory from Phase 4b).

The Rust side carries its own copy of the equivalent error text on its
``ws_player`` error frame; cross-language duplication is unavoidable, so only the
Python copies are de-duplicated here.
"""

from __future__ import annotations

#: Reply text when a frozen session tries to run a command. Mirrors
#: ``handle_ws_command``'s frozen guard and the gateway adapter's
#: ``_frozen_reply``; carried on a ``system`` frame.
FROZEN_SESSION_MESSAGE = "Your session is frozen. Contact an administrator."

#: Reply text when the command pipeline (or the Phase 4 persistence handlers)
#: degrades an unexpected fault to a clean in-game error; carried on an
#: ``error`` frame.
EXECUTION_ERROR_MESSAGE = (
    "Something went wrong processing that command. It has been logged for review."
)
