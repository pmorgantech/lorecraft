"""Sprint 52.1: chat channel framework — scopes, descriptors, registry."""

from __future__ import annotations

import pytest

from lorecraft.engine.game.channels import (
    Channel,
    ChannelRegistry,
    ChatScope,
    get_registry,
)


class TestChannel:
    def test_p2all_channel_may_be_muteable(self) -> None:
        channel = Channel(
            id="newbie", scope=ChatScope.P2ALL, tag="Newbie", muteable=True
        )
        assert channel.muteable is True

    def test_room_and_direct_channels_may_not_be_muteable(self) -> None:
        with pytest.raises(ValueError, match="only P2ALL"):
            Channel(id="say", scope=ChatScope.P2ROOM, tag="Say", muteable=True)
        with pytest.raises(ValueError, match="only P2ALL"):
            Channel(id="tell", scope=ChatScope.P2P, tag="Tell", muteable=True)

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            Channel(id="  ", scope=ChatScope.P2ALL, tag="X")


class TestRegistry:
    def test_register_get_all(self) -> None:
        registry = ChannelRegistry()
        registry.register(Channel(id="ooc", scope=ChatScope.P2ALL, tag="OOC"))
        assert registry.get("ooc") is not None
        assert registry.get("missing") is None
        assert [c.id for c in registry.all()] == ["ooc"]

    def test_reregistration_overwrites(self) -> None:
        registry = ChannelRegistry()
        registry.register(Channel(id="ooc", scope=ChatScope.P2ALL, tag="OOC"))
        registry.register(
            Channel(id="ooc", scope=ChatScope.P2ALL, tag="Out-of-Character")
        )
        got = registry.get("ooc")
        assert got is not None and got.tag == "Out-of-Character"

    def test_topic_channels_are_p2all_only(self) -> None:
        registry = ChannelRegistry()
        registry.register(Channel(id="say", scope=ChatScope.P2ROOM, tag="Say"))
        registry.register(Channel(id="ooc", scope=ChatScope.P2ALL, tag="OOC"))
        assert [c.id for c in registry.topic_channels()] == ["ooc"]


class TestBuiltins:
    def test_say_and_tell_registered_at_import(self) -> None:
        registry = get_registry()
        say = registry.get("say")
        tell = registry.get("tell")
        assert say is not None and say.scope is ChatScope.P2ROOM
        assert tell is not None and tell.scope is ChatScope.P2P
        assert not say.muteable and not tell.muteable
