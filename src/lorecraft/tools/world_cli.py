"""World content CLI: import / export / validate / diff / merge / stats.

Usage:
    python -m lorecraft.tools.world_cli import --file world.yaml --db game.db [--fresh]
    python -m lorecraft.tools.world_cli export --db game.db --output world.yaml [--format yaml|json]
    python -m lorecraft.tools.world_cli validate --file world.yaml
    python -m lorecraft.tools.world_cli diff --from world.v1.yaml --to world.v2.yaml [--output diff.yaml]
    python -m lorecraft.tools.world_cli merge --base world.yaml --theirs world.new.yaml --output world.merged.yaml
    python -m lorecraft.tools.world_cli stats --db game.db
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from lorecraft.engine.scripting.vocabulary import Vocabulary
    from lorecraft.services.container import ServiceContainer
    from lorecraft.state import AppState

import yaml
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, delete

from lorecraft.db import create_tables, database_url
from lorecraft.features.npc.models import DialogueTree
from lorecraft.engine.models.items import ItemStack
from lorecraft.features.quests.models import Quest
from lorecraft.engine.models.world import Exit, Item, NPC, Room
from lorecraft.tools.validators import check_combat_action_definitions, run_all_checks
from lorecraft.world.loader import export_world_document, load_world_yaml
from lorecraft.world.yaml_io import load_world_yaml_text
from lorecraft.world.validator import (
    WorldDocument,
    WorldValidationError,
    validate_world_document,
)

_WORLD_CONTENT_MODELS = (Exit, NPC, DialogueTree, Quest, Item, Room)


def _open_engine(db_path: str) -> Engine:
    engine = create_engine(database_url(db_path))
    # A throwaway in-memory audit engine — world_cli never touches audit data.
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _wipe_world_tables(session: Session) -> None:
    """Delete all world-content rows (rooms/items/npcs/dialogue/quests/exits).

    Leaves players, admin users, and other non-world tables untouched. Room-owned
    item stacks are world content too (unlike player-owned stacks in the same
    ItemStack table), so they're deleted by owner_type rather than by model.
    """
    for model in _WORLD_CONTENT_MODELS:
        session.exec(delete(model))  # type: ignore[call-overload]
    session.exec(delete(ItemStack).where(ItemStack.owner_type == "room"))  # type: ignore[call-overload]


def cmd_import(args: argparse.Namespace) -> int:
    engine = _open_engine(args.db)
    with Session(engine) as session:
        if args.fresh:
            _wipe_world_tables(session)
            session.commit()
        document = load_world_yaml(args.file, session)
        session.commit()
    print(
        f"Imported {len(document.rooms)} rooms, {len(document.items)} items, "
        f"{len(document.npcs)} NPCs, {len(document.quests)} quests, "
        f"{len(document.dialogue_trees)} dialogue trees from {args.file}"
    )
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    engine = _open_engine(args.db)
    with Session(engine) as session:
        document = export_world_document(session)

    output_path = Path(args.output)
    payload = document.model_dump(mode="json")
    if args.format == "json":
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        output_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    print(f"Exported world to {output_path} ({args.format})")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    source_path = Path(args.file)
    data = load_world_yaml_text(source_path.read_text(encoding="utf-8")) or {}
    try:
        document = validate_world_document(data)
    except WorldValidationError as exc:
        print(f"✗ {exc}")
        return 1

    print(
        f"✓ Schema valid ({len(document.rooms)} rooms, {len(document.items)} items, "
        f"{len(document.npcs)} NPCs, {len(document.quests)} quests)"
    )
    print("✓ All room/item/NPC references resolved")

    lint = run_all_checks(document, start_room_id=args.start_room)
    combat_actions_file = (
        Path(args.combat_actions_file)
        if args.combat_actions_file
        else (source_path.parent / "combat_actions.yaml")
    )
    lint.merge(check_combat_action_definitions(combat_actions_file))
    for warning in lint.warnings:
        print(f"⚠ {warning}")
    for error in lint.errors:
        print(f"✗ {error}")
    if not lint.warnings and not lint.errors:
        print("✓ No lint warnings")

    if lint.errors:
        return 1
    if lint.warnings and args.strict:
        return 1
    return 0


def _entity_map(entities: list[Any]) -> dict[str, dict[str, Any]]:
    return {entity.id: entity.model_dump() for entity in entities}


def _diff_entity_lists(base: list[Any], theirs: list[Any]) -> dict[str, list[str]]:
    base_map = _entity_map(base)
    theirs_map = _entity_map(theirs)
    added = sorted(set(theirs_map) - set(base_map))
    removed = sorted(set(base_map) - set(theirs_map))
    changed = sorted(
        entity_id
        for entity_id in set(base_map) & set(theirs_map)
        if base_map[entity_id] != theirs_map[entity_id]
    )
    return {"added": added, "removed": removed, "changed": changed}


def _load_world_document(path: str | Path) -> WorldDocument:
    data = load_world_yaml_text(Path(path).read_text(encoding="utf-8")) or {}
    return validate_world_document(data)


def cmd_diff(args: argparse.Namespace) -> int:
    from_doc = _load_world_document(getattr(args, "from"))
    to_doc = _load_world_document(args.to)

    result = {
        "rooms": _diff_entity_lists(from_doc.rooms, to_doc.rooms),
        "items": _diff_entity_lists(from_doc.items, to_doc.items),
        "npcs": _diff_entity_lists(from_doc.npcs, to_doc.npcs),
        "quests": _diff_entity_lists(from_doc.quests, to_doc.quests),
        "dialogue_trees": _diff_entity_lists(
            from_doc.dialogue_trees, to_doc.dialogue_trees
        ),
    }
    rendered = yaml.safe_dump(result, sort_keys=False)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
        print(f"Wrote diff to {args.output}")
    else:
        print(rendered, end="")
    return 0


def _room_item_key(entity: Any) -> str:
    return f"{entity.room_id}:{entity.item_id}"


def _merge_entity_lists(
    base: list[Any], theirs: list[Any], *, key: Any = lambda e: e.id
) -> list[Any]:
    """`theirs` entities win on key collision; base-only entities are kept."""
    merged: dict[str, Any] = {key(entity): entity for entity in base}
    merged.update({key(entity): entity for entity in theirs})
    return list(merged.values())


def cmd_merge(args: argparse.Namespace) -> int:
    base_doc = _load_world_document(args.base)
    theirs_doc = _load_world_document(args.theirs)

    merged_doc = WorldDocument(
        rooms=_merge_entity_lists(base_doc.rooms, theirs_doc.rooms),
        items=_merge_entity_lists(base_doc.items, theirs_doc.items),
        room_items=_merge_entity_lists(
            base_doc.room_items, theirs_doc.room_items, key=_room_item_key
        ),
        npcs=_merge_entity_lists(base_doc.npcs, theirs_doc.npcs),
        dialogue_trees=_merge_entity_lists(
            base_doc.dialogue_trees, theirs_doc.dialogue_trees
        ),
        quests=_merge_entity_lists(base_doc.quests, theirs_doc.quests),
    )
    # Re-validate the merged result so a bad merge fails loudly.
    validate_world_document(merged_doc.model_dump(mode="json"))

    Path(args.output).write_text(
        yaml.safe_dump(merged_doc.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote merged world to {args.output}")
    return 0


def _load_scripting_vocabulary() -> "Vocabulary":
    """Populate and return the process-global scripting catalog.

    Two registration lifetimes feed the catalog and both must fire before it's rendered:

    * **Import-time** descriptors register as a side effect of importing the engine-core
      condition module and every feature package (via ``discover_features``). This catches
      every module-level ``register_spec(...)`` call.
    * **Enable-time** descriptors only register when a feature is *wired* — its manifest's
      ``register_fn(state)`` runs (e.g. ``reputation``'s ``actor_reputation_at_least`` /
      ``adjust_reputation``, registered inside ``features/reputation/conditions.py::register``).
      ``discover_features`` imports but does not enable, so we additionally wire every
      discovered feature here with a minimal doc-generation stand-in for ``AppState``.

    This is why the loader lives here in the composition layer and not in
    ``engine/scripting/catalog.py`` (which must not import features).
    """
    import lorecraft.engine.game.command_conditions  # noqa: F401
    import lorecraft.features.npc.dialogue_conditions  # noqa: F401
    import lorecraft.features.npc.side_effects  # noqa: F401
    from lorecraft.engine.scripting.vocabulary import global_vocabulary
    from lorecraft.features.loader import (
        discover_features,
        load_features,
        wire_features,
    )

    discovered = discover_features()
    # Wire in dependency order so a feature is enabled only after its dependencies
    # (``load_features`` validates + orders the full discovered set).
    ordered = load_features(list(discovered), registry=discovered)
    wire_features(_doc_gen_app_state(), ordered)
    return global_vocabulary()


def _doc_gen_app_state() -> "AppState":
    """Build a minimal ``AppState`` stand-in for one-shot vocabulary doc generation.

    Feature ``register_fn``s registering scripting vocabulary only read
    ``state.services`` during enablement (e.g. ``follow`` checks
    ``state.services.follow`` before wiring its escort conditions); none of AppState's
    other fields — DB engines, the event bus, the connection manager — are touched on
    the registration path. So we supply a fully-populated :class:`ServiceContainer` and
    nothing else, avoiding the heavy real-app bootstrap (DB, web host) for a pure
    catalog render. If a future feature's ``register_fn`` reads more of ``AppState`` at
    enable time, the doc-drift test (``test_scripting_api_doc``) will surface the crash
    and this stub should grow the missing field.
    """
    from lorecraft.services.container import ServiceContainer

    return cast("AppState", _DocGenState(services=ServiceContainer()))


@dataclass
class _DocGenState:
    """The only ``AppState`` surface a feature's ``register_fn`` reads at enable time."""

    services: ServiceContainer


def cmd_vocabulary(args: argparse.Namespace) -> int:
    from lorecraft.engine.scripting import catalog

    vocab = _load_scripting_vocabulary()

    if args.out:
        Path(args.out).write_text(catalog.render_markdown(vocab), encoding="utf-8")
        print(
            f"Wrote scripting vocabulary reference to {args.out} ({len(vocab)} entries)"
        )
        return 0

    entries = vocab.all()
    if args.category:
        entries = [e for e in entries if e.category == args.category]

    if args.json:
        payload = {"entries": [e.to_json() for e in entries]}
        print(json.dumps(payload, indent=2))
        return 0

    if not entries:
        print(
            f"No vocabulary entries{f' in category {args.category!r}' if args.category else ''}."
        )
        return 0

    current: tuple[str, str] | None = None
    for entry in entries:
        key = (entry.kind.value, entry.category)
        if key != current:
            current = key
            print(f"\n[{entry.kind.value}] {entry.category}")
        params = ", ".join(p.name for p in entry.params) or "-"
        print(f"  {entry.name:<24} {entry.subject.value:<7} ({params})  {entry.doc}")
    for group in vocab.overlaps():
        names = ", ".join(e.name for e in group)
        print(f"\n⚠ overlap: {names} — all {group[0].capability}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    engine = _open_engine(args.db)
    with Session(engine) as session:
        document = export_world_document(session)
    print(f"rooms:          {len(document.rooms)}")
    print(f"items:          {len(document.items)}")
    print(f"npcs:           {len(document.npcs)}")
    print(f"quests:         {len(document.quests)}")
    print(f"dialogue_trees: {len(document.dialogue_trees)}")
    print(f"room_items:     {len(document.room_items)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m lorecraft.tools.world_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_import = subparsers.add_parser("import", help="Import world YAML into a DB")
    p_import.add_argument("--file", required=True)
    p_import.add_argument("--db", required=True)
    p_import.add_argument("--fresh", action="store_true")
    p_import.set_defaults(func=cmd_import)

    p_export = subparsers.add_parser(
        "export", help="Export DB world state to YAML/JSON"
    )
    p_export.add_argument("--db", required=True)
    p_export.add_argument("--output", required=True)
    p_export.add_argument("--format", choices=["yaml", "json"], default="yaml")
    p_export.set_defaults(func=cmd_export)

    p_validate = subparsers.add_parser("validate", help="Validate world YAML")
    p_validate.add_argument("--file", required=True)
    p_validate.add_argument(
        "--start-room", help="Room id to check reachability from (optional)"
    )
    p_validate.add_argument(
        "--strict", action="store_true", help="Exit non-zero on lint warnings too"
    )
    p_validate.add_argument(
        "--combat-actions-file",
        help=(
            "Combat action YAML to validate with the world file "
            "(default: combat_actions.yaml next to --file)"
        ),
    )
    p_validate.set_defaults(func=cmd_validate)

    p_diff = subparsers.add_parser(
        "diff", help="Diff two world YAML files by entity id"
    )
    p_diff.add_argument("--from", dest="from", required=True)
    p_diff.add_argument("--to", required=True)
    p_diff.add_argument("--output")
    p_diff.set_defaults(func=cmd_diff)

    p_merge = subparsers.add_parser(
        "merge", help="Merge two world YAML files (theirs wins on id collision)"
    )
    p_merge.add_argument("--base", required=True)
    p_merge.add_argument("--theirs", required=True)
    p_merge.add_argument("--output", required=True)
    p_merge.set_defaults(func=cmd_merge)

    p_stats = subparsers.add_parser("stats", help="Print entity counts from a DB")
    p_stats.add_argument("--db", required=True)
    p_stats.set_defaults(func=cmd_stats)

    p_vocab = subparsers.add_parser(
        "vocabulary", help="Show/generate the scripting vocabulary catalog"
    )
    p_vocab.add_argument("--category", help="Filter the listing to one category")
    p_vocab.add_argument("--json", action="store_true", help="Emit the catalog as JSON")
    p_vocab.add_argument(
        "--out",
        help="Write the full Markdown reference to this file (e.g. docs/worldbuilding/scripting_api.md)",
    )
    p_vocab.set_defaults(func=cmd_vocabulary)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
