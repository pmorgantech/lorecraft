"""Full-world connectivity regression against the shipped world_content/world.yaml.

Unlike ``tests/tools/test_validators.py`` (which exercises
``check_room_reachability`` against synthetic fixtures), this test runs the
checker against the *real* world content and asserts the ``docs/roadmap_world.md``
Success Criteria: every room is reachable from the seed start room, and no room
is an accidental orphan.

The one legitimate exception is transit vehicle rooms: they are entered only via
the ``board`` command (which sets ``current_room_id`` directly), never through
the walkable exit graph, so ``check_room_reachability``'s directed BFS reports
them as unreachable by design. That exception is derived generically from the
document's transit lines (``vehicle_room_id``) rather than hard-coded, so a newly
added *real* orphan room would still fail these tests.
"""

from __future__ import annotations

import re

from lorecraft.tools.validators import check_room_reachability
from lorecraft.world.bootstrap import resolve_world_yaml_path
from lorecraft.world.validator import WorldDocument, validate_world_document
from lorecraft.world.yaml_io import load_world_yaml_text

# The canonical seed/start room (config.Settings.seed_player_start_room).
_START_ROOM = "village_square"

# check_room_reachability emits one warning per unreachable room, shaped
# "room '<id>' unreachable (no exit path from '<start>')". This matches the
# *subject* room id (the leading quoted token), never the trailing start-room id.
_WARNING_SUBJECT = re.compile(r"^room '([^']+)' unreachable")


def _load_real_world() -> WorldDocument:
    """Load and validate the shipped world file, exactly as ``world_cli validate`` does."""
    path = resolve_world_yaml_path("world_content/world.yaml")
    data = load_world_yaml_text(path.read_text(encoding="utf-8")) or {}
    return validate_world_document(data)


def _transit_vehicle_room_ids(document: WorldDocument) -> set[str]:
    """Rooms entered only via ``board`` — legitimately unreachable in the exit graph."""
    if document.transit is None:
        return set()
    return {
        line.vehicle_room_id
        for line in document.transit.lines
        if line.vehicle_room_id is not None
    }


def test_every_room_reachable_except_transit_vehicles() -> None:
    document = _load_real_world()
    vehicle_rooms = _transit_vehicle_room_ids(document)
    # The reachability assertion only means something if there IS a known
    # exception to subtract; without one a "no unexpected orphans" check could
    # pass vacuously, so require the transit vehicle set to be non-empty.
    assert vehicle_rooms, "expected at least one transit vehicle room to account for"

    result = check_room_reachability(document, _START_ROOM)

    unreachable_ids: set[str] = set()
    for warning in result.warnings:
        match = _WARNING_SUBJECT.match(warning)
        assert match is not None, f"unexpected reachability warning shape: {warning!r}"
        unreachable_ids.add(match.group(1))

    # No room outside the transit vehicle set may be unreachable.
    unexpected = unreachable_ids - vehicle_rooms
    assert not unexpected, (
        f"unexpected unreachable (orphaned) rooms: {sorted(unexpected)}"
    )

    # And confirm the checker actually flagged the known vehicle rooms — this
    # proves the BFS ran and the derived exception lines up with reality, so the
    # assertion above can't pass merely because the warning list was empty.
    missing = vehicle_rooms - unreachable_ids
    assert not missing, (
        f"transit vehicle rooms expected to be BFS-unreachable but weren't: {sorted(missing)}"
    )


def test_no_orphaned_rooms_have_zero_exits() -> None:
    """Every room has at least one exit, except transit vehicle rooms (board-only)."""
    document = _load_real_world()
    vehicle_rooms = _transit_vehicle_room_ids(document)

    zero_exit_rooms = {room.id for room in document.rooms if not room.exits}
    orphans = zero_exit_rooms - vehicle_rooms
    assert not orphans, (
        f"rooms with zero exits that are not transit vehicle rooms: {sorted(orphans)}"
    )
