"""Phase 4 snapshot building — the Python half of ``BuildSnapshot`` (Option A).

Under the Phase 4 execution round-trip (see ``protocol/gateway.py``), Rust owns
execution but holds no authoritative world state yet, so it asks Python to
materialize the immutable :class:`~lorecraft.protocol.script.ScriptRequest`
snapshot a migrated verb executes against. This module builds that snapshot for
``look`` by **reusing the live look path's builder verbatim** —
:meth:`InventoryService._build_look_request` — rather than re-deriving the
snapshot shape here, so the Rust-executed ``look`` can never drift from the
Python ``look`` it is replacing.

For ``move`` (Phase 4c) :func:`build_move_request` materializes the room's
traversable exits and the actor into the snapshot contract documented by the
``lorecraft-feature-move`` crate, reusing the *same* repo/registry calls the live
:meth:`~lorecraft.features.movement.service.MovementService.move` makes so the
Rust-derived move can't drift from the Python move it replaces. A skill-gated
target's ``required_skill`` gate draws RNG in Python (``record_use``); since
cross-language RNG parity is deferred (migration-plan OPEN ITEM #3), the adapter
uses :func:`move_target_is_skill_gated` to defer such a move to Python wholesale
rather than executing it in Rust.

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

from lorecraft.engine.game.context import GameContext, build_game_context
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.errors import ValidationError
from lorecraft.features.inventory.service import InventoryService
from lorecraft.features.movement.service import _carries
from lorecraft.features.terrain import definitions as terrain_module
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.protocol import EntitySnapshot, ScriptBudget
from lorecraft.protocol.envelope import CommandEnvelope
from lorecraft.protocol.script import ScriptRequest
from lorecraft.protocol.version import PROTOCOL_VERSION
from lorecraft.state import AppState
from lorecraft.types import JsonValue


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


# Move-snapshot attribute keys — the contract the ``lorecraft-feature-move`` crate
# reads (see its module docs). Kept as constants so the Python producer and the
# Rust consumer name every field identically.
_ATTR_EXITS = "exits"
_ATTR_USERNAME = "username"
_ATTR_FLAGS = "flags"
_EXIT_TARGET_ROOM_ID = "target_room_id"
_EXIT_TARGET_ACTIVE = "target_active"
_EXIT_LOCKED = "locked"
_EXIT_KEY_ITEM_ID = "key_item_id"
_EXIT_ACTOR_HAS_KEY = "actor_has_key"
_EXIT_CONDITION_FLAGS = "condition_flags"
_EXIT_TARGET_REQUIRED_SKILL = "target_required_skill"


def build_move_request(state: AppState, envelope: CommandEnvelope) -> ScriptRequest:
    """Build the ``move`` :class:`ScriptRequest` snapshot for ``envelope``.

    Opens a read-only game session, loads the actor and their room, and
    materializes every traversable exit plus the actor into the immutable snapshot
    the Rust ``move_effects`` consumes. Every read reuses the *same* repo/registry
    call the live :meth:`~lorecraft.features.movement.service.MovementService.move`
    makes — :meth:`RoomRepo.exits`/:meth:`RoomRepo.active`, the terrain registry's
    ``required_skill``, the locked-exit key check
    (:func:`~lorecraft.features.movement.service._carries` →
    :meth:`StackRepo.quantity_of`), and ``player.flags`` — so the snapshot can
    never drift from the move it feeds.

    Raises :class:`~lorecraft.errors.ValidationError` if the actor or their room no
    longer exists (there is no snapshot to execute against a vanished actor).
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
        return _move_request_from_context(ctx)


def _move_request_from_context(ctx: GameContext) -> ScriptRequest:
    """Materialize the move snapshot from a wired context (reused read logic).

    Every exit in the current room is exposed keyed by its canonical direction,
    including hidden exits — the live move (``RoomRepo.exit``) reaches hidden exits
    directly, so the snapshot must too. Each exit carries the booleans/ids Rust
    needs to reach the *same* allow/block decision without any store access.
    """
    registry = terrain_module.get_registry()
    exits: dict[str, JsonValue] = {}
    for exit_ in ctx.room_repo.exits(ctx.room.id):
        target = ctx.room_repo.active(exit_.target_room_id)
        required_skill: str | None = None
        if target is not None:
            terrain_def = registry.get(target.terrain)
            if terrain_def is not None:
                required_skill = terrain_def.required_skill
        has_key = exit_.key_item_id is not None and _carries(ctx, exit_.key_item_id)
        exits[exit_.direction] = {
            _EXIT_TARGET_ROOM_ID: exit_.target_room_id,
            _EXIT_TARGET_ACTIVE: target is not None,
            _EXIT_LOCKED: exit_.locked,
            _EXIT_KEY_ITEM_ID: exit_.key_item_id,
            _EXIT_ACTOR_HAS_KEY: has_key,
            _EXIT_CONDITION_FLAGS: list(exit_.condition_flags),
            _EXIT_TARGET_REQUIRED_SKILL: required_skill,
        }
    room_snapshot = EntitySnapshot(
        id=ctx.room.id,
        kind="room",
        attributes={_ATTR_EXITS: exits},
    )
    actor_snapshot = EntitySnapshot(
        id=ctx.player.id,
        kind="player",
        attributes={
            _ATTR_USERNAME: ctx.player.username,
            _ATTR_FLAGS: dict(ctx.player.flags),
        },
    )
    return ScriptRequest(
        api_version=PROTOCOL_VERSION,
        script_id="movement",
        script_version=1,
        command_or_event="move",
        actor_snapshot=actor_snapshot,
        room_snapshot=room_snapshot,
        selected_related_entities=[],
        logical_time=0,
        rng_stream_id="",
        capability_set=[],
        budget=ScriptBudget(wall_ms=0, instructions=0, memory_bytes=0, output_bytes=0),
    )


def move_target_is_skill_gated(request: ScriptRequest, direction: str | None) -> bool:
    """Whether the move ``direction``'s target terrain is skill-gated in ``request``.

    Reads the already-built snapshot's exits map (no second DB round-trip), so the
    adapter can defer a skill-gated move to Python — its ``record_use`` RNG draw
    stays Python-side (migration-plan OPEN ITEM #3). A direction with no exit, an
    inactive target, or an ungated terrain is *not* gated: Rust executes it (or
    derives the block) directly. Because the live move checks locked/condition/
    active *before* the skill gate, a skill-gated exit that is also blocked never
    draws RNG in Python either, so deferring it is always safe.
    """
    if not direction:
        return False
    exits = request.room_snapshot.attributes.get(_ATTR_EXITS)
    if not isinstance(exits, dict):
        return False
    exit_ = exits.get(direction)
    if not isinstance(exit_, dict):
        return False
    return exit_.get(_EXIT_TARGET_REQUIRED_SKILL) is not None
