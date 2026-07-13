"""Phase 4 outcome persistence — the Python half of ``ApplyOutcome`` (Option A).

Under the Phase 4 execution round-trip (see ``protocol/gateway.py``), Rust owns
execution and derives an authoritative :class:`CommandOutcome`; Python owns
persistence. :func:`apply_outcome` takes that outcome and reproduces exactly the
persistence tail of the live command path
(:func:`~lorecraft.webui.player.ws_command.handle_ws_command`):

1. apply the outcome's validated ``applied_effects`` to game state (empty for
   ``look``; ``MoveEntity`` from Phase 4c reproduces the move's state mutations);
2. apply the outcome's ``messages`` to a live :class:`GameContext` via the same
   ``ctx.say``/``ctx.push_update`` the feature would have called, plus its
   ``room_narration``/``arrival_narration`` via ``ctx.tell_room``/
   ``ctx.tell_arrival``, so the legacy ``command_result`` reply and the room
   fan-out are assembled from identically-constructed state;
3. queue the post-command events the applied effects imply (movement's
   ``PLAYER_MOVED``) and ``flush_events()`` them **before** the commit, mirroring
   the engine's step 9→10 so quest/follow/trigger handlers mutate the same
   transaction (no-op for ``look``);
4. commit the game DB, then write the ``command_executed`` audit row and commit
   the audit DB — **commit-before-publish** and the game→audit commit order are
   preserved exactly;
5. compute the post-command fan-out by driving the *same*
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
from lorecraft.protocol.effects import Effect, MoveEntity
from lorecraft.protocol.envelope import CommandEnvelope, CommandOutcome
from lorecraft.protocol.gateway import DeliveryDirective
from lorecraft.protocol.messages import Feed, PanelUpdate
from lorecraft.state import AppState
from lorecraft.types import JsonObject, JsonValue
from lorecraft.webui.player.ui_snapshots import player_ui_updates

# --- effect appliers (Tier-2-agnostic dispatch, keyed by effect tag) ---------
#
# Each entry persists one validated effect against authoritative game state.
# ``look`` derives no effects; ``MoveEntity`` (Phase 4c) is the first registered.
# The dispatch is deliberately explicit so an unrecognized effect fails loudly
# rather than being silently dropped after Rust already validated and ordered it.
EffectApplier = Callable[[GameContext, Effect], None]


def _apply_move_entity(ctx: GameContext, effect: Effect) -> None:
    """Persist a validated ``MoveEntity`` — the state mutations of
    :meth:`~lorecraft.features.movement.service.MovementService.move`, byte-for-byte.

    Rust derived and ordered this move against the authoritative snapshot; here we
    apply only its *state* changes, in the service's order: set the player's
    ``current_room_id``, append the destination to ``visited_rooms`` (order-
    preserving, deduped), record the room move on the connection manager (``from``
    is the pre-command room, ``MoveEntity.from``), then repoint ``ctx.room`` at the
    destination. The actor feed + ``room_id`` panel arrive via ``outcome.messages``;
    the leave/arrival narration via ``outcome.room_narration``/``arrival_narration``
    (placed by :func:`apply_outcome`); the ``PLAYER_MOVED`` event is queued by
    :func:`apply_outcome` — it needs the typed direction, which the effect does not
    carry — and flushed before commit, mirroring the live path.

    ``ctx.manager.move_player`` here updates the (per-outcome, advisory) mirror;
    forwarding the resulting `MovePlayer` frame to Rust's authoritative registry is
    a live-cutover concern (movement is not default-on this phase), out of scope
    here and not needed for the returned ``deliveries`` (they target rooms by id).
    """
    if not isinstance(effect, MoveEntity):  # dispatch guarantees the tag; be explicit
        raise ValidationError(f"expected a MoveEntity effect, got {effect.TAG!r}")
    target_room = ctx.room_repo.active(effect.to)
    if target_room is None:
        raise ValidationError(f"move target vanished since snapshot: {effect.to!r}")
    ctx.player.current_room_id = effect.to
    if effect.to not in ctx.player.visited_rooms:
        ctx.player.visited_rooms = [*ctx.player.visited_rooms, effect.to]
    ctx.manager.move_player(ctx.player.id, effect.from_, effect.to)
    ctx.room = target_room


_EFFECT_APPLIERS: dict[str, EffectApplier] = {
    MoveEntity.TAG: _apply_move_entity,
}


def _apply_effect(ctx: GameContext, effect: Effect) -> None:
    """Persist one validated effect, dispatched on its wire tag."""
    applier = _EFFECT_APPLIERS.get(effect.TAG)
    if applier is None:
        raise ValidationError(
            f"no persistence applier registered for effect {effect.TAG!r}"
        )
    applier(ctx, effect)


def _queue_outcome_events(
    ctx: GameContext, outcome: CommandOutcome, parsed: ParsedCommand
) -> None:
    """Queue the post-command events the applied effects imply, so the pre-commit
    :meth:`GameContext.flush_events` runs their handlers exactly as the live path.

    Movement: one ``PLAYER_MOVED`` per applied ``MoveEntity``, with the same
    payload :meth:`MovementService.move` queues. ``entity``/``from``/``to`` come
    straight off the effect; the ``direction`` is recovered from the parsed command
    (``parsed.noun`` is the canonical direction — the value the live handler passes
    to the service), so a move's quest/follow/trigger handlers see identical input.
    """
    for effect in outcome.applied_effects:
        if isinstance(effect, MoveEntity):
            ctx.queue_event(
                GameEvent.PLAYER_MOVED,
                player_id=effect.entity,
                from_room_id=effect.from_,
                to_room_id=effect.to,
                direction=parsed.noun,
            )


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

    Follow-up 4c(a) — the reviewer flagged that Rust already parsed this line, so
    re-parsing is redundant. **Decision: keep the re-parse for now.** The parser is
    deterministic and this recovery is byte-identical to what Rust parsed (for a
    move, ``parsed.noun`` is the same canonical direction the engine resolves), so
    nothing drifts. Carrying the parsed verb/noun forward instead would need a new
    additive field on the versioned ``CommandEnvelope``/``CommandOutcome`` contract
    (touching the Rust side too); that is deferred to a dedicated follow-up rather
    than bundled into the movement port.
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

    Reproduces the persistence tail of ``handle_ws_command`` for the migrated verbs
    (``look``; ``move`` from Phase 4c): applies effects + messages + narration,
    flushes queued events, commits game then audit, and drains the post-command
    broadcast as ``DeliveryDirective``s. The returned ``direct_reply`` is
    byte-identical to the live ``command_result`` frame for the same command.

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

        # (2b) Route the outcome's room/arrival narration into the same ctx buffers
        # the feature's ctx.tell_room/ctx.tell_arrival would fill (task 1 decision
        # (a)), so broadcast_command_effects fans a move's "X leaves north." to the
        # origin room and "X arrives from the south." to the destination room
        # byte-identically. Empty for verbs that produce none (e.g. look).
        for line in outcome.room_narration:
            ctx.tell_room(line)
        for line in outcome.arrival_narration:
            ctx.tell_arrival(line)

        parsed = _parse_command_metadata(ctx, envelope.raw)

        # (2c) Queue the post-command events the applied effects imply (movement:
        # PLAYER_MOVED), so the flush below runs their handlers.
        _queue_outcome_events(ctx, outcome, parsed)

        # (3) Run queued event handlers BEFORE the game commit (engine.py step 9 ->
        # 10). PLAYER_MOVED drives quest progression, NPC reactions, follow (a
        # follower moving with the leader, or a follow breaking), and room triggers,
        # any of which may further mutate this session — so they must be flushed
        # inside the one transaction or their writes are silently discarded when the
        # session closes. For look (no queued events) this is a no-op. EventBus.emit
        # isolates handler exceptions into HandlerResult.error, so a misbehaving
        # handler cannot roll back the command's own already-applied state.
        ctx.flush_events()

        # (4) Commit-before-publish: game DB first, then the audit row + audit DB —
        # preserving the engine's _record_success ordering. The Python-side audit
        # omits the execution-timing perf breakdown (Rust owns execution, not this
        # persistence step); the canonical command_executed fields are identical,
        # and timing is non-deterministic and stripped by the parity normalizer.
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

        # (4b) Announce the executed command on the bus, mirroring the engine's
        # tail (engine.py:_execute_command, after the audit record+commit). This
        # is what lets composition-layer observers registered on
        # GameEvent.COMMAND_EXECUTED fire for Rust-executed commands too — most
        # visibly main.py:_push_command_executed, which pushes the `audit_appended`
        # admin audit-feed broadcast. Without it, an admin watching the live audit
        # tab misses every Rust-executed command (and quest/achievement/analytics
        # listeners are likewise skipped). Payload keys/values match engine.py
        # exactly. `ctx.emit` reaches `state.bus` (passed as `bus=` above), the
        # same bus those observers register on; the bus isolates handler
        # exceptions into HandlerResult.error, so a misbehaving observer cannot
        # break this function's return — matching the engine's behavior. The
        # pre-commit `ctx.flush_events()` above (step 3) runs any queued game events
        # (movement's PLAYER_MOVED; none for look) before this bus announcement,
        # mirroring engine.py's step 9 (flush) -> 12 (COMMAND_EXECUTED emit) order.
        ctx.emit(
            GameEvent.COMMAND_EXECUTED,
            actor_id=ctx.player.id,
            verb=parsed.verb,
            summary=_command_summary_text(parsed),
            room_id=ctx.room.id,
        )

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
