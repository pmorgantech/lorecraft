"""Unit tests for EffectService and the trait registry (engine_core.md §3.4)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.errors import ValidationError
from lorecraft.engine.game import traits as traits_module
from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.effects import get_registry as get_effect_registry
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.modifiers import Modifier, resolve_for
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.traits import TraitDef
from lorecraft.engine.game.traits import get_registry as get_trait_registry
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.services.effects import EffectService
from lorecraft.features.traits.sources import register as _register_trait_sources


_register_trait_sources()


def _make_engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


@pytest.fixture
def registered_weakened_effect() -> Iterator[None]:
    """Registers a test-scoped "weakened" EffectDef with a modifier and a
    granted trait, then removes it afterward."""
    registry = get_effect_registry()
    registry.register(
        EffectDef(
            key="weakened",
            modifiers=lambda effect: [
                Modifier("skill.perception", "mult", 0.8, f"effect:{effect.id}")
            ],
            grants_traits=lambda effect: ["frail"],
        )
    )
    yield
    registry._defs.pop("weakened", None)  # type: ignore[attr-defined]


class TestEffectServiceApply:
    def test_apply_creates_active_effect_with_expiry(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            effect = service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=100.0,
                clock_epoch=50.0,
            )

            assert effect.entity_type == "player"
            assert effect.entity_id == "p1"
            assert effect.applied_at_epoch == 50.0
            assert effect.expires_at_epoch == 150.0

    def test_apply_permanent_effect_has_no_expiry(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            effect = service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            assert effect.expires_at_epoch is None

    def test_apply_rejects_unregistered_effect_key(self) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            with pytest.raises(ValidationError):
                service.apply(
                    session,
                    "player",
                    "p1",
                    "no-such-effect",
                    duration_ticks=None,
                    clock_epoch=0.0,
                )


class TestEffectServiceRemoveAndQuery:
    def test_remove_deletes_the_row(self, registered_weakened_effect: None) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            effect = service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            session.commit()

            service.remove(session, effect.id)
            session.commit()

            assert session.get(ActiveEffect, effect.id) is None

    def test_active_for_returns_effects_for_entity_only(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            service.apply(
                session,
                "player",
                "p2",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            session.commit()

            active = service.active_for(session, "player", "p1")
            assert len(active) == 1
            assert active[0].entity_id == "p1"


class TestEffectExpirySweep:
    def test_expired_effects_are_deleted_and_emit_event(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        bus = EventBus()
        service = EffectService(engine, GameRng())
        service.register(bus)

        observed: list[dict] = []
        bus.on(
            GameEvent.EFFECT_EXPIRED, lambda event, ctx: observed.append(event.payload)
        )

        with Session(engine) as session:
            effect = service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=10.0,
                clock_epoch=0.0,
            )
            effect_id = effect.id
            session.commit()

        bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 20.0}), ctx=None)

        assert len(observed) == 1
        assert observed[0]["entity_id"] == "p1"
        assert observed[0]["effect_key"] == "weakened"
        with Session(engine) as session:
            assert session.get(ActiveEffect, effect_id) is None

    def test_unexpired_effects_survive_the_sweep(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        bus = EventBus()
        service = EffectService(engine, GameRng())
        service.register(bus)

        with Session(engine) as session:
            effect = service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=1000.0,
                clock_epoch=0.0,
            )
            effect_id = effect.id
            session.commit()

        bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 20.0}), ctx=None)

        with Session(engine) as session:
            assert session.get(ActiveEffect, effect_id) is not None

    def test_permanent_effects_never_expire(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        bus = EventBus()
        service = EffectService(engine, GameRng())
        service.register(bus)

        with Session(engine) as session:
            effect = service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            effect_id = effect.id
            session.commit()

        bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 999999.0}), ctx=None)

        with Session(engine) as session:
            assert session.get(ActiveEffect, effect_id) is not None


class TestActiveEffectContributesModifiersAndTraits:
    def test_active_effect_modifiers_feed_resolve_for(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            session.commit()

            result = resolve_for(session, "player", "p1", "skill.perception", 30.0)
            assert result == 24.0  # 30 * 0.8

    def test_active_effect_grants_traits_via_trait_registry(
        self, registered_weakened_effect: None
    ) -> None:
        engine = _make_engine()
        with Session(engine) as session:
            service = EffectService(engine, GameRng())
            service.apply(
                session,
                "player",
                "p1",
                "weakened",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            session.commit()

            names = get_trait_registry().traits_for(session, "player", "p1")
            assert "frail" in names


class TestTraitModifiers:
    def test_registered_trait_modifiers_feed_resolve_for(self) -> None:
        registry = get_trait_registry()
        registry.register(
            TraitDef(
                name="__test_sure_eyed__",
                modifiers=[Modifier("skill.perception", "mult", 1.1, "trait:test")],
                description="test trait",
            )
        )

        class _AlwaysGrantsSource:
            def traits_for(self, session, entity_type, entity_id) -> set[str]:
                return {"__test_sure_eyed__"}

        registry.register_source(_AlwaysGrantsSource())
        try:
            engine = _make_engine()
            with Session(engine) as session:
                result = resolve_for(session, "player", "p1", "skill.perception", 30.0)
                assert result == pytest.approx(33.0)
        finally:
            registry._defs.pop("__test_sure_eyed__", None)  # type: ignore[attr-defined]
            registry._sources.pop()  # type: ignore[attr-defined]


def test_active_effect_trait_source_and_modifier_source_are_registered_by_default() -> (
    None
):
    """Confirms the feature-owned active-effect trait source and modifier sources
    are registered for effect/trait integration."""
    from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry

    assert len(traits_module.get_registry()._sources) >= 1  # type: ignore[attr-defined]
    assert len(get_modifier_registry()._sources) >= 2  # type: ignore[attr-defined]


class TestRoomEffectHooks:
    """§3.9 on_apply / on_expire — the room-state write/restore mechanism."""

    def _register(self, key: str, **hooks: object) -> None:
        get_effect_registry().register(
            EffectDef(key=key, modifiers=lambda effect: [], **hooks)  # type: ignore[arg-type]
        )

    def _unregister(self, *keys: str) -> None:
        for key in keys:
            get_effect_registry()._defs.pop(key, None)  # type: ignore[attr-defined]

    def test_on_apply_fires_after_flush_in_caller_transaction(self) -> None:
        engine = _make_engine()
        applied: list[str] = []
        self._register("gate_open", on_apply=lambda s, e: applied.append(e.entity_id))
        try:
            with Session(engine) as session:
                EffectService(engine, GameRng()).apply(
                    session,
                    "room",
                    "vault",
                    "gate_open",
                    duration_ticks=10.0,
                    clock_epoch=0.0,
                )
            assert applied == ["vault"]
        finally:
            self._unregister("gate_open")

    def test_on_apply_raise_rolls_back_the_apply(self) -> None:
        engine = _make_engine()

        def boom(session: Session, effect: ActiveEffect) -> None:
            raise RuntimeError("gate stuck")

        self._register("gate_open", on_apply=boom)
        try:
            with pytest.raises(RuntimeError, match="gate stuck"):
                with Session(engine) as session:
                    EffectService(engine, GameRng()).apply(
                        session,
                        "room",
                        "vault",
                        "gate_open",
                        duration_ticks=10.0,
                        clock_epoch=0.0,
                    )
            # The uncommitted, flushed row is discarded when the session rolls back.
            with Session(engine) as session:
                assert (
                    EffectService(engine, GameRng()).active_for(
                        session, "room", "vault"
                    )
                    == []
                )
        finally:
            self._unregister("gate_open")

    def test_on_expire_fires_before_delete_during_sweep(self) -> None:
        engine = _make_engine()
        expired: list[str] = []
        self._register("gate_open", on_expire=lambda s, e: expired.append(e.entity_id))
        try:
            bus = EventBus()
            service = EffectService(engine, GameRng())
            service.register(bus)
            with Session(engine) as session:
                effect = service.apply(
                    session,
                    "room",
                    "vault",
                    "gate_open",
                    duration_ticks=10.0,
                    clock_epoch=0.0,
                )
                effect_id = effect.id
                session.commit()

            bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 20.0}), ctx=None)

            assert expired == ["vault"]
            with Session(engine) as session:
                assert session.get(ActiveEffect, effect_id) is None
        finally:
            self._unregister("gate_open")

    def test_on_expire_failure_keeps_its_row_and_isolates_the_rest(self) -> None:
        engine = _make_engine()
        emitted: list[dict] = []

        def boom(session: Session, effect: ActiveEffect) -> None:
            raise RuntimeError("stuck")

        self._register("good_gate", on_expire=lambda s, e: None)
        self._register("bad_gate", on_expire=boom)
        try:
            bus = EventBus()
            service = EffectService(engine, GameRng())
            service.register(bus)
            bus.on(
                GameEvent.EFFECT_EXPIRED,
                lambda ev, ctx: emitted.append(ev.payload),
            )
            with Session(engine) as session:
                good = service.apply(
                    session,
                    "room",
                    "r1",
                    "good_gate",
                    duration_ticks=10.0,
                    clock_epoch=0.0,
                )
                bad = service.apply(
                    session,
                    "room",
                    "r2",
                    "bad_gate",
                    duration_ticks=10.0,
                    clock_epoch=0.0,
                )
                good_id, bad_id = good.id, bad.id
                session.commit()

            bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 20.0}), ctx=None)

            with Session(engine) as session:
                assert session.get(ActiveEffect, good_id) is None  # expired cleanly
                assert session.get(ActiveEffect, bad_id) is not None  # kept for retry
            # no EFFECT_EXPIRED for the failed one
            assert [p["effect_key"] for p in emitted] == ["good_gate"]
        finally:
            self._unregister("good_gate", "bad_gate")
