"""Command registration helpers."""

from lorecraft.commands.inventory import register_inventory_commands
from lorecraft.commands.meta import register_meta_commands
from lorecraft.commands.movement import register_movement_commands
from lorecraft.game.registry import CommandRegistry


def register_all_commands(registry: CommandRegistry) -> None:
    register_meta_commands(registry)
    register_movement_commands(registry)
    register_inventory_commands(registry)
