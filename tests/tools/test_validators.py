"""Tests for content linting rules in lorecraft.tools.validators."""

from __future__ import annotations

from lorecraft.tools.validators import (
    check_combat_action_definitions,
    check_dead_item_references,
    check_dialogue_node_references,
    check_duplicate_item_names_per_room,
    check_item_definition_fields,
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


def test_check_combat_action_definitions_warns_when_missing(tmp_path) -> None:
    result = check_combat_action_definitions(tmp_path / "missing.yaml")

    assert result.ok
    assert any("not found" in warning for warning in result.warnings)


def test_check_combat_action_definitions_rejects_unknown_resolver(tmp_path) -> None:
    path = tmp_path / "combat_actions.yaml"
    path.write_text(
        """
version: 1
actions:
  - id: custom
    action_range: engaged
    calculator: opposed_attack
    resolver: missing
    timing:
      windup: 0.1
      recovery: 1.0
""",
        encoding="utf-8",
    )

    result = check_combat_action_definitions(path)

    assert not result.ok
    assert any("unknown resolver" in error for error in result.errors)


def test_check_combat_action_definitions_accepts_valid_file(tmp_path) -> None:
    path = tmp_path / "combat_actions.yaml"
    path.write_text(
        """
version: 1
actions:
  - id: basic_attack
    action_range: engaged
    calculator: opposed_attack
    resolver: opposed_attack
    timing:
      windup: 0.25
      recovery: 2.0
""",
        encoding="utf-8",
    )

    result = check_combat_action_definitions(path)

    assert result.ok
    assert result.warnings == []


def test_check_item_definition_fields_flags_unknown_slot() -> None:
    document = WorldDocument(
        items=[
            ItemData(id="item-1", name="Item", description="An item.", slot="unknown")
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("unknown" in e and "slot" in e for e in result.errors)


def test_check_item_definition_fields_flags_wearable_without_slot() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="armor", name="Armor", description="Armor.", wearable=True, slot=None
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("wearable" in e and "slot" in e for e in result.errors)


def test_check_item_definition_fields_flags_unknown_quality() -> None:
    document = WorldDocument(
        items=[
            ItemData(id="item-1", name="Item", description="An item.", quality="broken")
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("quality" in e for e in result.errors)


def test_check_item_definition_fields_flags_untakeable_container() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="chest",
                name="Chest",
                description="A chest.",
                takeable=False,
                capacity=50.0,
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("container" in e and "takeable" in e for e in result.errors)


def test_check_item_definition_fields_flags_negative_weight() -> None:
    document = WorldDocument(
        items=[ItemData(id="item-1", name="Item", description="An item.", weight=-5.0)]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("negative weight" in e for e in result.errors)


def test_check_item_definition_fields_flags_negative_durability() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="sword", name="Sword", description="A sword.", max_durability=-1
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("durability" in e for e in result.errors)


def test_check_item_definition_fields_flags_unknown_effect_type() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="item-1",
                name="Item",
                description="An item.",
                effects=[{"type": "explode"}],
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("explode" in e and "unknown type" in e for e in result.errors)


def test_check_item_definition_fields_flags_bad_stat_in_effect() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="item-1",
                name="Item",
                description="An item.",
                effects=[{"type": "stat_bonus", "stat": "luck", "amount": 2}],
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("luck" in e for e in result.errors)


def test_check_item_definition_fields_flags_bad_weapon_profile_effect() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="pistol",
                name="Pistol",
                description="A pistol.",
                effects=[
                    {
                        "type": "weapon_profile",
                        "base_damage": "loud",
                        "accuracy_bonus": "sharp",
                    }
                ],
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("base_damage" in error for error in result.errors)
    assert any("accuracy_bonus" in error for error in result.errors)


def test_check_item_definition_fields_flags_bad_armor_profile_effect() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="coat",
                name="Coat",
                description="A coat.",
                effects=[{"type": "armor_profile", "block": 2.0}],
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert not result.ok
    assert any("resistance_factor" in error for error in result.errors)


def test_check_item_definition_fields_passes_for_valid_equipment() -> None:
    document = WorldDocument(
        items=[
            ItemData(
                id="helm",
                name="Iron Helm",
                description="A sturdy helm.",
                slot="head",
                wearable=True,
                weight=2.0,
                quality="fine",
                light=0,
                capacity=None,
                effects=[
                    {"type": "stat_bonus", "stat": "vitality", "amount": 1},
                    {"type": "skill_bonus", "skill": "defense", "amount": 5},
                    {"type": "armor_profile", "block": 1.0, "resistance_factor": 0.03},
                ],
            )
        ]
    )

    result = check_item_definition_fields(document)

    assert result.ok
