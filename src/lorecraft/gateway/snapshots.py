"""Phase 4 snapshot building — the Python half of ``BuildSnapshot`` (Option A).

Under the Phase 4 execution round-trip (see ``protocol/gateway.py``), Rust owns
execution but holds no authoritative world state yet, so it asks Python to
materialize the immutable :class:`~lorecraft.protocol.script.ScriptRequest`
snapshot a migrated verb executes against. This module builds that snapshot for
``look`` by **reusing the live look path's builder verbatim** —
:meth:`InventoryService._build_look_request` — rather than re-deriving the
snapshot shape here, so the Rust-executed ``look`` can never drift from the
Python ``look`` it is replacing.

The builder needs a :class:`~lorecraft.engine.game.context.GameContext` (it reads
``ctx.room``/``ctx.room_repo``/``ctx.item_repo``/``ctx.player``), so we construct
one exactly as :func:`~lorecraft.webui.player.ws_command.handle_ws_command` does —
same :func:`~lorecraft.engine.game.context.build_game_context` factory — but the
build is **read-only**: no audit session, no commit callbacks, a throwaway
directive-recording manager. Nothing is committed.

Composition/web-host layer: imports engine + features, never a web host; not
imported *by* ``engine/``.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.errors import ValidationError
from lorecraft.features.inventory.service import InventoryService
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.protocol.envelope import CommandEnvelope
from lorecraft.protocol.script import ScriptRequest
from lorecraft.state import AppState


def build_look_request(state: AppState, envelope: CommandEnvelope) -> ScriptRequest:
    """Build the ``look`` :class:`ScriptRequest` snapshot for ``envelope``.

    Opens a read-only game session, loads the actor and their room, and delegates
    to :meth:`InventoryService._build_look_request` — the *same* builder the live
    ``look`` handler uses — so the snapshot handed to Rust is byte-for-byte what
    the Python look path would consume.

    Raises :class:`~lorecraft.errors.ValidationError` if the actor or their room
    no longer exists (the caller surfaces this as a failed snapshot build; there
    is no snapshot to execute against a vanished actor).
    """
    with Session(state.game_engine) as game_session:
        player = PlayerRepo(game_session).get(envelope.player_id)
        if player is None:
            raise ValidationError(
                f"unknown player for snapshot: {envelope.player_id!r}"
            )
        room_repo = RoomRepo(game_session)
        room = room_repo.get(player.current_room_id)
        if room is None:
            raise ValidationError(
                f"missing room for snapshot: {player.current_room_id!r}"
            )
        # Mirror handle_ws_command's context construction so the reused builder sees
        # an identically-wired context — but read-only: a throwaway manager, no audit
        # session, and no commit callbacks (nothing here mutates or commits).
        transaction = TransactionContext.create(
            actor_id=player.id,
            correlation_id=envelope.session_id,
        )
        ctx = build_game_context(
            game_session,
            player,
            room,
            bus=state.bus,
            manager=DirectiveConnectionManager(),
            transaction=transaction,
            session_id=envelope.session_id,
            rng=state.rng,
            meters=state.meters,
            effects=state.effects,
            clock=room_repo.world_clock(),
        )
        # Reuse the live look-path snapshot builder rather than duplicating it, so
        # the Rust-executed look and the Python look consume the same request shape.
        return InventoryService()._build_look_request(ctx)
