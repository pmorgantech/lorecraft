"""Live-tunable combat ruleset configuration."""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.features.combat.models import CombatRulesetConfig


def combat_ruleset_config_for(session: Session, ruleset_id: str) -> CombatRulesetConfig:
    """Return persisted ruleset config or an unsaved default config."""

    config = session.get(CombatRulesetConfig, ruleset_id)
    if config is not None:
        return config
    return CombatRulesetConfig(id=ruleset_id)


def get_or_create_combat_ruleset_config(
    session: Session, ruleset_id: str
) -> CombatRulesetConfig:
    """Return a persisted ruleset config, creating default dials if needed."""

    config = session.get(CombatRulesetConfig, ruleset_id)
    if config is not None:
        return config
    config = CombatRulesetConfig(id=ruleset_id)
    session.add(config)
    session.flush()
    return config
