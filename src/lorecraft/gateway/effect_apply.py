"""Phase 4 outcome persistence — the Python half of ``ApplyOutcome`` (Option A).

Under the Phase 4 execution round-trip (see ``protocol/gateway.py``), Rust owns
execution and derives an authoritative :class:`CommandOutcome`; Python owns
persistence. :func:`apply_outcome` takes that outcome and reproduces exactly the
persistence tail of the live command path
(:func:`~lorecraft.webui.player.ws_command.handle_ws_command`):

1. apply the outcome's validated ``applied_effects`` to game state (for ``look``
   this is empty — the effect-applier dispatch exists so ``MoveEntity`` slots in
   at Phase 4c);
2. apply the outcome's ``messages`` to a live :class:`GameContext` via the same
   ``ctx.say``/``ctx.push_update`` the feature would have called, so the legacy
   ``command_result`` reply is assembled from identically-constructed state;
3. commit the game DB, then write the ``command_executed`` audit row and commit
   the audit DB — **commit-before-publish** and the game→audit commit order are
   preserved exactly;
4. compute the post-command fan-out by driving the *same*
   :func:`~lorecraft.engine.game.broadcast.broadcast_command_effects` the live
   path drives, through a directive-recording manager, so the returned
   ``deliveries`` are byte-identical to the ``/ws`` path's.

The returned ``(direct_reply, deliveries)`` pair is what the adapter packs into
``OutcomeApplied`` for Rust to publish.

Composition/web-host layer: imports engine + features + player-UI projection,
never a web host; not imported *by* ``engine/``.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlmodel import Session

from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.context import GameContext, build_game_context
from lorecraft.engine.game.engine import (
    _command_audit_payload,
    _command_summary_text,
    _npc_target_id,
)
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.parser import ParsedCommand, parse_command
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.audit import AuditService
from lorecraft.errors import ValidationError
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.protocol.effects import Effect
from lorecraft.protocol.envelope import CommandEnvelope, CommandOutcome
from lorecraft.protocol.gateway import DeliveryDirective
from lorecraft.protocol.messages import Feed, PanelUpdate
from lorecraft.state import AppState
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.player.ui_snapshots import player_ui_updates

# --- effect appliers (Tier-2-agnostic dispatch, keyed by effect tag) ---------
#
# Each entry persists one validated effect against authoritative game state.
# ``look`` derives no effects, so the map is empty for this slice; ``MoveEntity``
# (and the rest) register here as their verbs migrate (Phase 4c onward). The
# dispatch is deliberately explicit so an unrecognized effect fails loudly rather
# than being silently dropped after Rust already validated and ordered it.
EffectApplier = Callable[[GameContext, Effect], None]

_EFFECT_APPLIERS: dict[str, EffectApplier] = {
    # MoveEntity.TAG: _apply_move_entity,   # wired in Phase 4c
}


def _apply_effect(ctx: GameContext, effect: Effect) -> None:
    """Persist one validated effect, dispatched on its wire tag."""
    applier = _EFFECT_APPLIERS.get(effect.TAG)
    if applier is None:
        raise ValidationError(
            f"no persistence applier registered for effect {effect.TAG!r}"
        )
    applier(ctx, effect)


def _parse_command_metadata(ctx: GameContext, raw: str) -> ParsedCommand:
    """Recover the parsed verb/noun/raw for the reply + audit summary.

    Rust owns execution, but neither the envelope nor the outcome carries the
    parsed verb/noun, and the legacy ``command_result`` frame and the
    ``command_executed`` audit summary both need them. We re-parse ``raw`` with
    the *same* parser the live path uses, so the recovered metadata is
    byte-identical to what ``handle_ws_command`` would have produced. This is
    read-only (no effect derivation, no state mutation). Mirrors the engine's
    "last parsed command wins" for a compound line; a parse failure degrades to a
    bare-verb placeholder, exactly as the engine's blocked path does.
    """
    result = parse_command(raw, context=ctx)
    if result.commands:
        return result.commands[-1]
    return ParsedCommand(verb="", raw=raw)


async def apply_outcome(
    state: AppState,
    envelope: CommandEnvelope,
    outcome: CommandOutcome,
) -> tuple[JsonObject, list[DeliveryDirective]]:
    """Persist ``outcome`` and return the actor reply plus fan-out directives.

    Reproduces the persistence tail of ``handle_ws_command`` for the (currently
    only) migrated verb ``look``: applies effects + messages, commits game then
    audit, and drains the post-command broadcast as ``DeliveryDirective``s. The
    returned ``direct_reply`` is byte-identical to the live ``command_result``
    frame for the same command.

    Raises :class:`~lorecraft.errors.ValidationError` if the actor or room has
    vanished since Rust built the snapshot (there is nothing to persist against).
    """
    player_id = envelope.player_id
    with (
        Session(state.game_engine) as game_session,
        Session(state.audit_engine) as audit_session,
    ):
        player = PlayerRepo(game_session).get(player_id)
        if player is None:
            raise ValidationError(f"unknown player for outcome: {player_id!r}")
        room_repo = RoomRepo(game_session)
        room = room_repo.get(player.current_room_id)
        if room is None:
            raise ValidationError(
                f"missing room for outcome: {player.current_room_id!r}"
            )
        # Captured before applying effects: a mover's pre-command room is where its
        # "leaves" narration is heard (feeds broadcast_command_effects at 4c). For
        # look, unchanged.
        pre_room_id = player.current_room_id

        # A local directive-recording manager isolates this outcome's fan-out: it is
        # returned in OutcomeApplied, never drained from the adapter's shared buffer,
        # so no directive lock or cross-contamination with concurrent lifecycle/
        # command handling is possible.
        manager = DirectiveConnectionManager()
        transaction = TransactionContext.create(
            actor_id=player.id,
            correlation_id=envelope.session_id,
        )
        ctx = build_game_context(
            game_session,
            player,
            room,
            bus=state.bus,
            manager=manager,
            transaction=transaction,
            session_id=envelope.session_id,
            rng=state.rng,
            meters=state.meters,
            effects=state.effects,
            clock=room_repo.world_clock(),
            audit_session=audit_session,
            commit_state=game_session.commit,
            commit_audit=audit_session.commit,
        )

        # (1) Persist the validated effects (empty for look).
        for effect in outcome.applied_effects:
            _apply_effect(ctx, effect)

        # (2) Replay the outcome's messages into the context the same way the
        # feature would have, so the reply is built from identical ctx state.
        for message in outcome.messages:
            if isinstance(message, Feed):
                ctx.say(message.text, MessageType(message.message_type))
            elif isinstance(message, PanelUpdate):
                ctx.push_update(message.key, message.value)

        parsed = _parse_command_metadata(ctx, envelope.raw)

        # (3) Commit-before-publish: game DB first, then the audit row + audit DB —
        # preserving the engine's _record_success ordering. The Python-side audit
        # omits the execution-timing perf breakdown (Rust owns execution, not this
        # persistence step); the canonical command_executed fields are identical.
        ctx.commit_state_changes()
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_EXECUTED,
            target_id=_npc_target_id(parsed, ctx),
            severity="INFO",
            summary=f"Command executed: {_command_summary_text(parsed)}",
            payload=_command_audit_payload(parsed),
        )
        ctx.commit_audit_events()

        # (4) Post-command fan-out via the SAME function the live path drives, so
        # the deliveries (and their coalesce keys, stamped by the manager) match
        # byte-for-byte. For look this is a single players-excluded room
        # state_change.
        await broadcast_command_effects(manager, ctx, pre_room_id=pre_room_id)
        deliveries = manager.drain()

        # Assemble the legacy command_result exactly as handle_ws_command does.
        # `Message` is a `str` subclass, so the explicit `JsonValue` element type
        # mirrors handle_ws_command's own annotations for a serializable reply.
        messages: list[JsonValue] = list(ctx.messages)
        room_messages: list[JsonValue] = list(ctx.room_messages)
        chat_messages: list[JsonValue] = [
            {"text": echo.text, "channel": echo.channel} for echo in ctx.chat_echoes
        ]
        disambig = ctx.updates.pop("disambig_pending", None)
        if isinstance(disambig, dict):
            state.pending_disambig[player_id] = disambig
        updates = {
            **ctx.updates,
            **player_ui_updates(player, ctx.room, room_repo, ctx.item_repo),
        }
        direct_reply: JsonObject = {
            "type": "command_result",
            "command": parsed.raw,
            "verb": parsed.verb,
            "noun": parsed.noun,
            "messages": messages,
            "room_messages": room_messages,
            "chat_messages": chat_messages,
            "updates": updates,
        }
        return direct_reply, deliveries
