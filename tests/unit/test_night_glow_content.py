"""World-content validation for the gap #5 G4 night-glow proof-of-concept.

Loads the *real* authored content (not fixtures) to prove the two `player_entered`
night-glow room triggers in `world_content/world.yaml`:

1. pass the same fail-closed load-time validation the server runs at startup
   (`parse_trigger` against the full `global_vocabulary()`), so a rename of the
   `time_of_day_is` condition, a dropped `register_spec`, or a typo'd effect would
   fail here instead of silently never firing in game; and
2. sit in a zone that actually carries the living-energy channel whose glow they
   narrate, per `world_content/harvest.yaml`'s `zones:` allowlist — the glow flavor
   and the harvestable resource must agree.

G3 (`test_triggers.py`) already proves the mechanism (load + fire/suppress) with
synthetic content; this pins the *authored* content to that mechanism.
"""

from __future__ import annotations

from lorecraft.engine.scripting.triggers import parse_trigger
from lorecraft.engine.scripting.vocabulary import global_vocabulary
from lorecraft.features.celestial.conditions import register as register_celestial

# Importing these modules self-registers `narrate_room` (side_effects) and the
# dialogue conditions into the global vocabulary, exactly as app startup does.
from lorecraft.features.living_energy.harvest import load_harvest_yaml
from lorecraft.features.npc import dialogue_conditions as _dialogue_conditions  # noqa: F401
from lorecraft.features.npc import side_effects as _side_effects  # noqa: F401
from lorecraft.world.yaml_io import load_world_yaml_text

_WORLD_YAML = "world_content/world.yaml"
_HARVEST_YAML = "world_content/harvest.yaml"

# The authored proof-of-concept glow rooms and the channel each one narrates.
_GLOW_ROOMS = {
    "old_oak_grove": "lumenroot",
    "soot_sump": "dreamveil",
}


def _load_rooms() -> dict[str, dict[str, object]]:
    doc = load_world_yaml_text(open(_WORLD_YAML).read())
    assert isinstance(doc, dict)
    return {r["id"]: r for r in doc["rooms"]}


def test_night_glow_rooms_have_a_time_of_day_night_player_entered_trigger() -> None:
    rooms = _load_rooms()
    for room_id in _GLOW_ROOMS:
        triggers = rooms[room_id].get("triggers", [])
        assert any(
            t.get("on") == "player_entered"
            and t.get("when") == {"time_of_day_is": "night"}
            for t in triggers
        ), room_id


def test_night_glow_triggers_pass_fail_closed_load_validation() -> None:
    register_celestial()
    vocab = global_vocabulary()
    rooms = _load_rooms()
    for room_id in _GLOW_ROOMS:
        for raw in rooms[room_id].get("triggers", []):
            # Raises TriggerLoadError on unknown condition/effect — same guard the
            # server applies at startup via scripting_wiring.load_triggers.
            trigger = parse_trigger("room", room_id, raw, vocab=vocab)
            assert trigger.on == "player_entered"


def test_night_glow_rooms_sit_in_their_channels_harvest_zone() -> None:
    rooms = _load_rooms()
    profiles = {p.channel: p for p in load_harvest_yaml(_HARVEST_YAML).profiles}
    for room_id, channel in _GLOW_ROOMS.items():
        zone = rooms[room_id].get("zone")
        assert zone in profiles[channel].zones, (room_id, channel, zone)
