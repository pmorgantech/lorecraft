"""World YAML round-trip + validator tests for Sprint 30's new authoring
fields: quest `branches`/`terminal`/`timeout_ticks`/`on_timeout`, and item
`mechanism_states`/`mechanism_side_effects`/`combination_side_effects`."""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.models.quest import Quest
from lorecraft.engine.models.world import Item
from lorecraft.world.loader import export_world_document, load_world_yaml
from lorecraft.world.validator import WorldValidationError, validate_world_document

_WORLD_YAML = """
rooms:
  - id: square
    name: Square
    description: A busy square.
    map_x: 0
    map_y: 0
items:
  - id: lever
    name: Brass Lever
    description: A stiff lever.
    takeable: false
    mechanism_states: ["off", "on"]
    mechanism_side_effects:
      "on":
        set_flags: ["lever_pulled"]
  - id: acid
    name: Acid Vial
    description: Corrosive.
    usable_with: ["hinge"]
    combination_side_effects:
      hinge:
        set_flags: ["hinge_dissolved"]
  - id: hinge
    name: Rusted Hinge
    description: A rusted hinge.
quests:
  - id: rescue
    title: Rescue the Merchant
    description: Help a merchant in trouble.
    stages:
      - id: start
        description: Decide how to help.
        conditions:
          - type: flag_set
            flag: ready
        branches:
          - conditions:
              - type: room_visited
                room_id: square
            next_stage: safe_route
            side_effects:
              set_flags: ["took_safe_route"]
      - id: safe_route
        description: You made it safely.
        conditions: []
        terminal: true
        timeout_ticks: 100
        on_timeout:
          next_stage: null
          message: "Too late."
          set_flags:
            gave_up: true
"""


def test_world_loader_round_trips_quest_branches_and_mechanism_items(tmp_path) -> None:
    source = tmp_path / "world.yaml"
    source.write_text(_WORLD_YAML, encoding="utf-8")
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

        lever = session.get(Item, "lever")
        acid = session.get(Item, "acid")
        quest = session.get(Quest, "rescue")

        assert lever is not None
        assert lever.mechanism_states == ["off", "on"]
        assert lever.mechanism_side_effects == {"on": {"set_flags": ["lever_pulled"]}}

        assert acid is not None
        assert acid.combination_side_effects == {
            "hinge": {"set_flags": ["hinge_dissolved"]}
        }

        assert quest is not None
        start_stage = next(s for s in quest.stages if s["id"] == "start")
        assert start_stage["branches"][0]["next_stage"] == "safe_route"
        safe_stage = next(s for s in quest.stages if s["id"] == "safe_route")
        assert safe_stage["terminal"] is True
        assert safe_stage["timeout_ticks"] == 100
        assert safe_stage["on_timeout"]["message"] == "Too late."

        # Export round-trip: re-importing the exported document is a no-op.
        exported = export_world_document(session)
        exported_quest = next(q for q in exported.quests if q.id == "rescue")
        exported_start = next(s for s in exported_quest.stages if s.id == "start")
        assert exported_start.branches[0].next_stage == "safe_route"
        exported_lever = next(i for i in exported.items if i.id == "lever")
        assert exported_lever.mechanism_states == ["off", "on"]


class TestValidatorRejections:
    def test_rejects_mechanism_with_single_state(self) -> None:
        with pytest.raises(WorldValidationError, match="at least 2 states"):
            validate_world_document(
                {
                    "items": [
                        {
                            "id": "switch",
                            "name": "Switch",
                            "description": "d",
                            "mechanism_states": ["only"],
                        }
                    ]
                }
            )

    def test_rejects_mechanism_side_effect_for_unknown_state(self) -> None:
        with pytest.raises(WorldValidationError, match="unknown state"):
            validate_world_document(
                {
                    "items": [
                        {
                            "id": "switch",
                            "name": "Switch",
                            "description": "d",
                            "mechanism_states": ["off", "on"],
                            "mechanism_side_effects": {"jammed": {"set_flags": ["x"]}},
                        }
                    ]
                }
            )

    def test_rejects_combination_side_effect_for_missing_item(self) -> None:
        with pytest.raises(WorldValidationError, match="missing item"):
            validate_world_document(
                {
                    "items": [
                        {
                            "id": "acid",
                            "name": "Acid",
                            "description": "d",
                            "combination_side_effects": {"ghost_item": {}},
                        }
                    ]
                }
            )

    def test_rejects_quest_branch_with_unknown_next_stage(self) -> None:
        with pytest.raises(WorldValidationError, match="unknown next_stage"):
            validate_world_document(
                {
                    "quests": [
                        {
                            "id": "q1",
                            "title": "Q1",
                            "stages": [
                                {
                                    "id": "start",
                                    "branches": [
                                        {"conditions": [], "next_stage": "nowhere"}
                                    ],
                                }
                            ],
                        }
                    ]
                }
            )

    def test_rejects_duplicate_stage_ids(self) -> None:
        with pytest.raises(WorldValidationError, match="duplicate stage ids"):
            validate_world_document(
                {
                    "quests": [
                        {
                            "id": "q1",
                            "title": "Q1",
                            "stages": [
                                {"id": "start"},
                                {"id": "start"},
                            ],
                        }
                    ]
                }
            )

    def test_rejects_npc_remembers_condition_with_missing_npc(self) -> None:
        with pytest.raises(WorldValidationError, match="missing npc"):
            validate_world_document(
                {
                    "quests": [
                        {
                            "id": "q1",
                            "title": "Q1",
                            "stages": [
                                {
                                    "id": "start",
                                    "conditions": [
                                        {
                                            "type": "npc_remembers",
                                            "npc_id": "ghost_npc",
                                            "flag": "helped",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            )

    def test_rejects_on_timeout_without_timeout_ticks(self) -> None:
        with pytest.raises(WorldValidationError, match="on_timeout but no"):
            validate_world_document(
                {
                    "quests": [
                        {
                            "id": "q1",
                            "title": "Q1",
                            "stages": [
                                {
                                    "id": "start",
                                    "on_timeout": {"message": "too slow"},
                                }
                            ],
                        }
                    ]
                }
            )
