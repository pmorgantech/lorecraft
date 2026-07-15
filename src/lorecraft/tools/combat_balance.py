"""Headless combat balance report CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lorecraft.features.combat.simulation import (
    CombatBalanceScenario,
    run_combat_balance_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", default="basic_attack", help="Combat action id")
    parser.add_argument("--trials", type=int, default=100, help="Number of trials")
    parser.add_argument("--seed", type=int, default=1, help="Deterministic RNG seed")
    parser.add_argument("--actor-strength", type=int, default=30)
    parser.add_argument("--actor-agility", type=int, default=12)
    parser.add_argument("--target-strength", type=int, default=10)
    parser.add_argument("--target-agility", type=int, default=8)
    parser.add_argument("--target-hp", type=float, default=50.0)
    parser.add_argument("--weapon-base-damage", type=float, default=4.0)
    parser.add_argument("--weapon-accuracy-bonus", type=float, default=0.0)
    parser.add_argument("--weapon-penetration", type=float, default=0.0)
    parser.add_argument("--armor-block", type=float, default=0.0)
    parser.add_argument("--armor-resistance-factor", type=float, default=0.0)
    parser.add_argument("--output", "-o", help="Optional JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_combat_balance_report(
        CombatBalanceScenario(
            action_key=args.action,
            trials=args.trials,
            seed=args.seed,
            actor_strength=args.actor_strength,
            actor_agility=args.actor_agility,
            target_strength=args.target_strength,
            target_agility=args.target_agility,
            target_hp=args.target_hp,
            weapon_base_damage=args.weapon_base_damage,
            weapon_accuracy_bonus=args.weapon_accuracy_bonus,
            weapon_penetration=args.weapon_penetration,
            armor_block=args.armor_block,
            armor_resistance_factor=args.armor_resistance_factor,
        )
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(f"{text}\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
