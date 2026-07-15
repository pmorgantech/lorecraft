# Archived Documentation

This directory contains shipped design docs and implementation notes that are no longer active.

**Rationale:** These documents describe features, systems, and work that have been completed and shipped. Their detail is preserved in `CHANGELOG.md` and `roadmap_completed.md`. The design decisions and implementation specifics they document are now frozen in code and are not subject to change. They are archived for historical reference only.

## Files

| Doc | Reason Archived | Shipped Version |
| Doc | Reason Archived | Shipped Version |
|-----|-----------------|-----------------|
| `combat_system_tickbased_superseded.md` | Tick-based combat design superseded by Scheduled Intent Combat (v0.105.0+) | Unimplemented; archived 2026-07-14 |
| `code_review_20260707.md` | Point-in-time code audit (v0.70.0–0.74.0) — findings resolved | v0.74.0 |
| `gamecontext_audit_20260710.md` | Point-in-time GameContext consistency pass — findings merged | v0.75.0+ |
| `trade_economy.md` | Trading/shop system fully designed and shipped (Sprint 28–42) | v0.46.0+ |
| `transit_systems.md` | Ferry/rail/balloon transit system fully designed and shipped (Sprint 24) | v0.40.0+ |
| `scavenger_hunt.md` | Scavenger hunt quests system fully designed and shipped (Sprint 47) | v0.62.0+ |
| `chat_feed_split.md` | Chat/feed split UI work fully designed and shipped (Sprint 45) | v0.60.0+ |
| `session_replay.md` | Session recording/replay system designed and shipped (Sprint 43) | v0.58.0+ |
| `inventory_equipment.md` | Inventory and equipment systems fully designed and shipped (Sprint 16–26) | v0.30.0+ |
## How to reference archived docs

- **For implementation details:** Refer to `CHANGELOG.md` (what shipped and when) and `roadmap_completed.md` (full per-sprint task breakdowns).
- **For design context:** The commit messages and PR histories in git record the rationale and constraints for each shipped feature.
- **For code:** The source code (`src/lorecraft/`) is the authoritative implementation reference.

Archived docs are not updated. If you're designing a *new* feature, refer to live docs in `docs/` instead.
