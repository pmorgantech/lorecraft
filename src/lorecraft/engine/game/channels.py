"""Chat channel framework: delivery scopes and named channels (Sprint 52).

Two orthogonal axes, deliberately separated:

- **`ChatScope`** — fixed delivery topology: one player (`P2P`), the actor's
  room (`P2ROOM`), or everyone online (`P2ALL`). Maps 1:1 onto
  `ConnectionManager.send_to_player` / `broadcast_to_room` / `broadcast_global`.
- **`Channel`** — a named identity layered on a scope (`say`, `tell`,
  `newbie`, later `auction`/`ooc`/…), held in a `ChannelRegistry`. The engine
  owns the *mechanism* (mirroring `CommandRegistry`); adding a channel is a
  registry row, no new code.

The engine registers the two mechanism-level built-ins (`say` — P2ROOM, and
`tell` — P2P) at module load, the `command_conditions` built-in precedent.
Topic channels (`newbie`, …) are content and register from the composition
layer (`commands/social.py` for now; world-YAML channel defs are a planned
additive follow-on — this registry is the seam).

Subscription/mute semantics: only P2ALL topic channels are `muteable`
(you can tune out a topic; you can't tune out the room you're standing in or
a direct tell). `default_subscribed` is the state for players who never
touched the preference.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChatScope(str, Enum):
    P2P = "p2p"
    P2ROOM = "p2room"
    P2ALL = "p2all"


@dataclass(frozen=True)
class Channel:
    """One named chat channel.

    Args:
        id: Registry key and payload ``channel`` tag; for P2ALL topic
            channels this is also the speaking verb (``newbie <msg>``).
        scope: Delivery topology (see `ChatScope`).
        tag: Display prefix clients show, e.g. "Newbie" → "(Newbie)".
        color: Client styling hint (a CSS-friendly color word); clients map
            unknown channels to a neutral style, so this is advisory.
        muteable: Whether players may unsubscribe. Only valid for P2ALL.
        default_subscribed: Subscription state for players who never set the
            preference. Meaningful only when `muteable`.
    """

    id: str
    scope: ChatScope
    tag: str
    color: str = "cyan"
    muteable: bool = False
    default_subscribed: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("channel id must be non-empty")
        if self.muteable and self.scope is not ChatScope.P2ALL:
            raise ValueError(
                f"channel {self.id!r}: only P2ALL channels are muteable "
                "(you can't tune out your own room or a direct tell)"
            )


class ChannelRegistry:
    """Name-keyed registry of channels; re-registration overwrites."""

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        self._channels[channel.id] = channel

    def get(self, channel_id: str) -> Channel | None:
        return self._channels.get(channel_id)

    def all(self) -> list[Channel]:
        return list(self._channels.values())

    def topic_channels(self) -> list[Channel]:
        """P2ALL topic channels — the ones that get a speaking verb and a
        subscription toggle."""
        return [c for c in self._channels.values() if c.scope is ChatScope.P2ALL]


_registry = ChannelRegistry()


def get_registry() -> ChannelRegistry:
    return _registry


# Mechanism-level built-ins, registered at module load (the
# command_conditions precedent): `say` is the room conversation the Sprint 45
# chat split shipped; `tell` is the direct line. Neither is muteable.
SAY_CHANNEL = "say"
TELL_CHANNEL = "tell"

_registry.register(Channel(id=SAY_CHANNEL, scope=ChatScope.P2ROOM, tag="Say"))
_registry.register(
    Channel(id=TELL_CHANNEL, scope=ChatScope.P2P, tag="Tell", color="violet")
)
