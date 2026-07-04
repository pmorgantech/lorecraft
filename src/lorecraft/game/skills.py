"""Skill identity: which skills exist (Sprint 24.2).

game/checks.py already defines *how* a check resolves (Tier 1, Sprints
17-18); this module defines *which* skills exist and their metadata. Skill
levels themselves live in PlayerStats.skills (a dict, already present) —
this registry doesn't store per-player state, only definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDef:
    name: str
    description: str
    governing_stat: str  # PlayerStats attribute this skill's base derives from


class SkillRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, SkillDef] = {}

    def register(self, skill_def: SkillDef) -> None:
        self._defs[skill_def.name] = skill_def

    def get(self, name: str) -> SkillDef | None:
        return self._defs.get(name)

    def all_skills(self) -> list[SkillDef]:
        return list(self._defs.values())

    def __contains__(self, name: str) -> bool:
        return name in self._defs


_registry = SkillRegistry()


def get_registry() -> SkillRegistry:
    return _registry


STANDARD_SKILLS = [
    SkillDef("perception", "Spotting hidden things, reading a room.", "intellect"),
    SkillDef("lockpicking", "Opening locks without a key.", "agility"),
    SkillDef("bartering", "Getting a better price when trading.", "presence"),
    SkillDef("cartography", "Reading and drawing maps.", "intellect"),
    SkillDef("survival", "Handling terrain, weather, and exposure.", "fortitude"),
    SkillDef("persuasion", "Convincing others in conversation.", "presence"),
]

for _skill_def in STANDARD_SKILLS:
    _registry.register(_skill_def)
