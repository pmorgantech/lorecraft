"""Tests for content linting rules in lorecraft.tools.validators."""

from __future__ import annotations

from lorecraft.tools.validators import (
    check_dead_item_references,
    check_dialogue_node_references,
    check_duplicate_item_names_per_room,
    check_item_quantity_warnings,
    check_room_reachability,
    run_all_checks,
)
from lorecraft.world.validator import (
    DialogueChoiceData,
    DialogueNodeData,
    DialogueTreeData,
    ExitData,
    ItemData,
    NpcData,
    QuestData,
    RoomData,
    RoomItemData,
    WorldDocument,
)


def _room(id_: str, *, exits: list[ExitData] | None = None) -> RoomData:
    return RoomData(
        id=id_,
        name=id_.title(),
        description="A room.",
        map_x=0,
        map_y=0,
        exits=exits or [],
    )


def test_check_dialogue_node_references_flags_missing_root_and_choice() -> None:
    document = WorldDocument(
        dialogue_trees=[
            DialogueTreeData(
                id="tree-1",
                root_node="missing_root",
                nodes={
                    "start": DialogueNodeData(
                        text="Hi",
                        choices=[
                            DialogueChoiceData(label="Bye", next_node="ghost_node")
                        ],
                    )
                },
            )
        ]
    )

    result = check_dialogue_node_references(document)

    assert not result.ok
    assert any("missing_root" in e for e in result.errors)
    assert any("ghost_node" in e for e in result.errors)


def test_check_dialogue_node_references_passes_for_valid_tree() -> None:
    document = WorldDocument(
        dialogue_trees=[
            DialogueTreeData(
                id="tree-1",
                root_node="start",
                nodes={
                    "start": DialogueNodeData(
                        text="Hi",
                        choices=[DialogueChoiceData(label="Bye", next_node=None)],
                    )
                },
            )
        ]
    )

    result = check_dialogue_node_references(document)

    assert result.ok
    assert result.errors == []


def test_check_room_reachability_flags_isolated_room() -> None:
    document = WorldDocument(
        rooms=[
            _room(
                "start",
                exits=[ExitData(direction="east", target_room_id="hallway")],
            ),
            _room("hallway"),
            _room("island"),
        ]
    )

    result = check_room_reachability(document, "start")

    assert result.ok  # warnings only, not errors
    assert any("island" in w for w in result.warnings)
    assert not any("hallway" in w for w in result.warnings)


def test_check_room_reachability_warns_on_unknown_start_room() -> None:
    document = WorldDocument(rooms=[_room("start")])

    result = check_room_reachability(document, "does-not-exist")

    assert any("does-not-exist" in w for w in result.warnings)


def test_check_dead_item_references_flags_bad_usable_with_and_loot_table() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="key", name="Key", description="A key", usable_with=["ghost_item"]
            )
        ],
        npcs=[
            NpcData(
                id="npc-1",
                name="NPC",
                description="An NPC",
                home_room_id="start",
                loot_table={"ghost_loot": 1},
            )
        ],
    )

    result = check_dead_item_references(document)

    assert not result.ok
    assert any("ghost_item" in e for e in result.errors)
    assert any("ghost_loot" in e for e in result.errors)


def test_check_duplicate_item_names_per_room_flags_same_display_name() -> None:
    document = WorldDocument(
        items=[
            ItemData(id="coin_gold", name="Coin", description="A gold coin."),
            ItemData(id="coin_silver", name="coin", description="A silver coin."),
        ],
        room_items=[
            RoomItemData(room_id="start", item_id="coin_gold", quantity=1),
            RoomItemData(room_id="start", item_id="coin_silver", quantity=1),
        ],
    )

    result = check_duplicate_item_names_per_room(document)

    assert result.ok  # warning, not error
    assert len(result.warnings) == 1
    assert "start" in result.warnings[0]


def test_check_item_quantity_warnings_flags_large_stack() -> None:
    document = WorldDocument(
        room_items=[RoomItemData(room_id="start", item_id="coin", quantity=500)]
    )

    result = check_item_quantity_warnings(document, threshold=20)

    assert result.ok
    assert len(result.warnings) == 1
    assert "500" in result.warnings[0]


def test_check_item_quantity_warnings_ignores_small_stack() -> None:
    document = WorldDocument(
        room_items=[RoomItemData(room_id="start", item_id="coin", quantity=3)]
    )

    result = check_item_quantity_warnings(document, threshold=20)

    assert result.warnings == []


def test_run_all_checks_skips_reachability_without_start_room() -> None:
    document = WorldDocument(rooms=[_room("start"), _room("island")])

    result = run_all_checks(document)

    assert not any("unreachable" in w for w in result.warnings)


def test_run_all_checks_aggregates_across_all_checks() -> None:
    document = WorldDocument(
        rooms=[_room("start"), _room("island")],
        items=[ItemData(id="coin", name="Coin", description="A coin.")],
        room_items=[RoomItemData(room_id="start", item_id="coin", quantity=999)],
    )

    result = run_all_checks(document, start_room_id="start")

    assert any("island" in w for w in result.warnings)
    assert any("999" in w for w in result.warnings)


def test_run_all_checks_ignores_quests_without_dependency_field() -> None:
    # Quests have no quest-to-quest dependency field in the schema today, so
    # there's nothing to cycle-check — this just documents that quests don't
    # break run_all_checks.
    document = WorldDocument(
        quests=[QuestData(id="quest-1", title="Quest", description="A quest.")]
    )

    result = run_all_checks(document)

    assert result.ok
