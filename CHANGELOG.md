# Changelog

All notable changes to Lorecraft will be documented in this file.

## [0.11.1] - 2026-07-04

### Added

- **Sprint 29.2: Transit vehicle state machine & commands** — `services/transit.py`'s `TransitService` builds a Sprint 21 `RouteSpec`/`RouteHooks` per `TransitLine` at app lifespan (`load_lines()`) and starts it, entirely on the existing route runner — no new state machine or timing mechanism. `may_depart` grounds weather-sensitive lines when `WorldClock.weather` is in the line's `blocking_weather`; `on_depart`/`on_arrive` narrate to both the station room and the vehicle room. New `board [line]` (validates stop position + ticket, consumes it if configured, moves the player into the vehicle room), `disembark`/`leave` (moves the player back out at the current stop), and `schedule [line]`/`timetable` (stop order + live status) commands (`commands/transit.py`). `register_all_commands` gained an optional `transit=` keyword argument — `TransitService` needs the game engine and `ConnectionManager` at construction (like `MeterService`/`MobileRouteService`), so it can't live in the no-argument `ServiceContainer`; every existing call site is unaffected by the addition. 10 new unit tests (`test_transit.py`).

## [0.11.0] - 2026-07-04

### Added

- **Sprint 29.1: Transit data model** — New `TransitLine`/`TransitStop` tables (`models/transit.py`) for ferry/rail/balloon/caravan lines — line *configuration* only, per `docs/transit_systems.md` §4: there is deliberately no `TransitVehicleState` table, since runtime vehicle position reuses Sprint 21's `MobileRouteState` (`route_id=f"transit:{line_id}"`), wired up in Sprint 29.2. World YAML gains a top-level `transit.lines` section (mode, service type, vehicle room, ticket item, reverse/loop, weather sensitivity, ordered stops) plus content validators: every stop's `room_id` and a line's `ticket_item_id` must resolve, `vehicle_room_id` must exist and have no static exits (board/disembark only), stop sequences must be contiguous from 0, an `express` line needs at least 2 boarding stops, and `blocking_weather` values must be states `clock/weather.py`'s `WEATHER_TABLE` actually produces. 12 new unit tests (import/export/reimport round-trip in `test_world_loader.py` + 5 validator-rejection tests).

## [0.10.3] - 2026-07-04

### Summary

**Sprint 28.4 — Player-to-player trade.** Completes Sprint 28 (Trading & economy):
a safe `offer`/`accept`/`decline` handshake atop the Sprint 20 ledger's atomic
exchange. 676 focused tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 28.4: Player-to-player trade** — Finished two pre-existing half-done seams instead of adding parallel ones: the `TradeOffer` table (present since early on, never wired to any code) gained coin fields and `[stack_id, quantity]` pledge lists per side; the unused `GameEvent.TRADE_COMPLETED` now actually fires. `offer <item|N coins> to <player>` (`services/trade.py`) records a pledge onto an open trade between the two players (creating one if needed) and moves nothing; either side can keep pledging more. `accept` composes exactly one `LedgerService.execute_exchange` call with every pledge (both directions, coins and stacks) as legs — that call's own leg validation *is* the escrow revalidation the design called for: if a pledged stack or coin balance is gone since it was offered, the whole exchange raises and nothing moves. Room-presence and `tradeable`/`bound` are re-checked at accept time too, not just at offer time, and offers expire after 5 minutes. New `offer`/`accept`/`decline` commands (`commands/trade.py`). Added `"offer"` to the parser's `OBJECT_VERBS` (`game/grammar.py`) so `offer X to Y` splits into object/recipient roles the same way `give X to Y` already does. 7 new unit tests (`test_trade.py`).

## [0.10.2] - 2026-07-04

### Added

- **Sprint 28.3: Banks** — New `Bank` model (an NPC marker, like `Shop`) and `BankAccount` (identity/ownership only — the balance lives on the ledger as `CoinBalance("bank_account", account.id)`, a new holder type registered in `game/bank_holders.py`). `services/bank.py`'s `BankService` backs three new commands (`commands/bank.py`): `deposit <amount>`/`withdraw <amount>` (each one `LedgerService.execute_exchange` leg, gated on standing in a bank branch's room) and `balance` (shows carried + banked, works anywhere — you always know your own money). `BankRepo.get_or_create_account()` lazily creates the single per-player account on first use; **one logical account, many branches** — deposit in one room's branch, withdraw in another's, since banking code only ever keys off the account id, never the room. Mira's inn now also runs a strongbox (`world_content/world.yaml`). Banked money is immune to death/robbery by construction: that code only ever touches the `("player", id)` holder, never `("bank_account", ...)`. 8 new unit tests (`test_bank.py`) + a world-loader round-trip test.

## [0.10.1] - 2026-07-04

### Added

- **Sprint 28.2: Regional pricing & restocking** — New `RegionPricing` table (world YAML top-level `economy.regions`) contributes an area-wide `region_mult` and a per-item `bias` multiplier on top of a shop's own `region_mult` — the same good costs different amounts in different places, and specific goods can be cheap/dear per area regardless of the area default. `EconomyService._demand_mult()` reads a `ShopStock` row's current quantity against its `restock_to` target: depleted stock costs more, flooded stock (e.g. from players selling heavily into one shop) costs less, bounded to `[0.5, 1.5]` so prices never run away. New `services/restock.py`'s `RestockService` (scheduler-driven, same engine-holding shape as `LightFuelService`) counts `TIME_ADVANCED` ticks per stock row and jumps `quantity` to `restock_to` once `restock_every_ticks` elapses, independent of anyone visiting the shop. `world_content/world.yaml` now prices goods higher in the `wilderness`/`cave` areas than in `town`. 12 new unit tests (`test_economy.py`) + a world-loader region import/export round-trip test + a validator-rejection test.

## [0.10.0] - 2026-07-04

### Summary

**Sprint 28.1 — Currency & vendor shops.** NPCs can now run a shop: `list`/`buy`/`sell`/
`appraise` against runtime-derived prices, backed by the Sprint 20 ledger's atomic
exchange. 650 focused tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 28.1: Currency & vendor shops** — New `Shop`/`ShopStock` tables (`models/economy.py`) attached to an NPC via a world YAML `shop:` block; a shop's cash is `CoinBalance("shop", shop.id)` (new `"shop"` ledger/item holder type, `game/economy_holders.py`), seeded once at world import via `LedgerService.credit` (idempotent — re-importing the same world file does not double-credit). New `Item.value`/`Item.category` fields. `services/economy.py`'s `EconomyService` derives `buy_price = value × quality_mult × region_mult × (1 - barter_discount) × (1 - rep_discount)` and `sell_price = buy_price × sell_ratio` at runtime, never stored — `bartering` skill and vendor reputation each shave a capped discount off the price. Every coin/item movement is one `LedgerService.execute_exchange` call (Sprint 20); sold items are `destroy()`ed rather than held as physical shop stock, since `ShopStock.quantity` is listing state only, materialized as a real `ItemStack` only on purchase. New commands (`commands/economy.py`): `list`/`shop` (stock + prices), `buy <item> [qty]`, `sell <item> [qty]` (gated on `tradeable`, not `bound`, and the shop's `buys_categories`), `appraise <item>` (not skill-gated in this cut — shows the derived value outright). Mira the innkeeper runs a working shop (`world_content/world.yaml`) selling mugs/candles/dried herbs. 15 new unit tests (`test_economy.py`) + a world-loader import/export/reimport round-trip test.

## [0.9.1] - 2026-07-04

### Added

- **Sprint 27.2: Sleep depth** — New `Room.safe_rest` field (YAML `safe_rest: true`, marked on the Wandering Crow Inn in `world_content/world.yaml`): `sleep` there always succeeds — full stamina restore, 8-hour clock-advance (`clock/world_clock.py`'s `apply_clock_fields`, plus a weather reroll via `apply_daily_weather` if the day rolls over), and a dream. Everywhere else, `sleep` is a `survival` `skill_check` gamble — harder in cold weather (`clock/weather.py`'s new `COLD_WEATHERS`: snow/blizzard/fog) unless the player has enough resolved warmth; failure interrupts the sleep into a shorter (3h), partial, dreamless rest. New `game/warmth.py` (`resolve_warmth()`, composing the Tier 1 modifier resolver) and a new `warmth_bonus` item effect descriptor (`game/item_effects.py`, `tools/validators.py`) give worn clothing a non-combat purpose — a cloak matters in a blizzard. Dreams reference a random discovered `lore:`-flagged fact (Sprint 25.3) when the player has one, otherwise a generic flavor line. 5 new unit tests (13 total in `test_fatigue.py`).

## [0.9.0] - 2026-07-04

### Summary

**Sprint 27.1 — Fatigue.** Light survival texture: traveling drains stamina (more when
encumbered), and running low saps skill checks. `rest`/`camp`/`sleep` commands restore it.

### Added

- **Sprint 27.1: Fatigue** — `game/fatigue_source.py` registers a "fatigue" `MeterDef` (remaining stamina, base scales with `PlayerStats.fortitude`) and a `FatigueModifierSource` applying a flat `mult` penalty to every registered skill (`game/skills.py`) once stamina drops below 50% (weary) or 20% (exhausted) of maximum — the "low fatigue penalizes skill checks" promise in `docs/wishlist.md`. `services/fatigue.py`'s `FatigueService` drains stamina on every `PLAYER_MOVED` event, scaled by the Sprint 23.2 encumbrance band (unburdened/burdened/overloaded), and backs three new commands (`commands/condition.py`): `rest` (quick, small restore), `camp` (slower, larger restore), and `sleep` (restores to full — clock-advance, safe/unsafe risk, and dream flavor are Sprint 27.2's job). Built on top of the [0.8.2](#082---2026-07-04) event-flush fix below (fatigue drain relies on the same post-command `PLAYER_MOVED` event handler pattern as quest progression). 8 new unit tests.

## [0.8.2] - 2026-07-04

### Fixed

- **Post-command event handler mutations were silently discarded** — `CommandEngine._execute_parsed` (`game/engine.py`) called `ctx.commit_state_changes()` *before* `ctx.flush_events()`, so any state mutated by a queued-event handler (notably `QuestService.check_progression`, which advances quest stages and sets completion flags on `PLAYER_MOVED`/`ITEM_TAKEN`/`ITEM_DROPPED`) was applied to the in-memory session but never committed — lost as soon as that request's session closed. Existing unit tests never caught this because they assert against the same still-open session. Found while designing Sprint 27's fatigue drain-on-move (which needed the same event-driven pattern to actually persist). Fixed by flushing events before the single commit; `EventBus.emit()` already isolates handler exceptions into `HandlerResult.error` rather than raising, so this can't turn a failed handler into an unwanted rollback of the command's own effects. New regression test (`test_websocket_movement_persists_quest_progression` in `tests/integration/test_main.py`) seeds a room-visited-gated quest stage and asserts the stage advance and completion flag survive a fresh session read after a real `go east` over the websocket; confirmed it fails without the fix and passes with it.

## [0.8.1] - 2026-07-04

### Fixed

- **CI: basedpyright venv configuration** — Removed hardcoded `.venv` path that caused CI to fail with "venv .venv subdirectory not found"; basedpyright now auto-detects the Python interpreter, working in both local dev and CI environments.
- **CI: e2e test dependency** — Added `pytest` to the `e2e` optional dependency group so browser tests can run without manually installing dev extras.

## [0.8.0] - 2026-07-04

### Summary

**Sprint 26 Complete — Map & Mobile UI.** UI polish serving exploration: a full-screen, pan/zoomable map modal integrated with cartography's reveal payoff, and a responsive mobile tab layout. Verified in a real headless-Chromium browser (screenshots of desktop, the modal, and all three mobile tabs) in addition to 3 new e2e tests and 4 new unit tests. 539 focused tests + 6 e2e + 5 simulation tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 26.1: Full-screen map modal** — An expand button (⛶) on the sidebar minimap opens a modal (`partials/map_modal.html`) with a larger SVG map (up to 60 rooms vs. the sidebar's 7), drag-to-pan and scroll/button-to-zoom (vanilla Alpine.js state, no new JS dependency). `build_map_data()` (`web/rendering.py`) gained `full`/`cartography_level` parameters: once a player's `cartography` skill (Sprint 24.2) reaches `CARTOGRAPHY_REVEAL_THRESHOLD` (20), rooms one non-hidden exit away from anywhere visited are plotted too — dimmer, labeled "Unexplored" — the cartography payoff Sprint 25.3 deferred here. Hidden exits are never revealed by cartography (that stays `search`'s job, Sprint 25.1).
- **Sprint 26.2: Responsive mobile tab layout** — Below the `lg` breakpoint, the three-column desktop layout (Room/Inventory/Map, Feed, Players/Quests) collapses to one column at a time, switched via a bottom tab bar (`Room`/`Feed`/`Players`); `lg:!flex` keeps the desktop three-column view untouched above that breakpoint (Tailwind's important-modifier overriding the mobile-only `hidden` class Alpine toggles).
- Added `[x-cloak] { display: none !important; }` to `custom.css` (avoids a flash of the map modal before Alpine initializes).

## [0.7.0] - 2026-07-04

### Summary

**Sprint 25 Complete — Exploration Depth.** Discovery as a first-class reward: `search` reveals hidden exits gated on perception, terrain types gate/flavor movement, and a `journal` command surfaces what a player has discovered. Fixed two real pre-existing bugs in movement (hidden exits always blocked; `condition_flags` never enforced) found while building this. 535 focused tests (12 new) + 5 simulation tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 25.1: Search + hidden-exit discovery** — New `search` command (`services/exploration.py`) runs a perception `skill_check()` (Sprint 17-18's existing resolution helper, base skill from Sprint 24's `SkillService`, modifiers from every registered source — equipment/traits/effects); on success, reveals any of the room's hidden exits the player hasn't found yet. Discovery is per-player (`game/exploration.py`'s `is_exit_discovered`/`mark_exit_discovered`, stored in the existing `Player.flags` dict — already save/load-snapshotted, no new persistence path needed) — `look` now lists a hidden exit once *that player* has discovered it, not room-globally. Finding something awards a flat XP tick (`PlayerStats.xp`) and rolls a `perception` use (Sprint 24.2's use-based improvement) regardless of outcome.
- **Sprint 25.2: Terrain** — New `Room.terrain: str` field (`game/terrain.py`'s `TerrainRegistry`, data-driven default set: normal/road/forest/mountain/swamp/water) with an optional `required_skill`/`required_skill_min` gate enforced in `MovementService.move()` and a `description_suffix` layered onto `look`. Content validator (`check_room_terrain`) flags unknown terrain names.
- **Sprint 25.3: Journal** — New `journal` command (`services/journal.py`) surfaces places visited (`Player.visited_rooms`, already tracked), people met (new `Player.met_npcs`, set on first `talk`), lore learned (any player flag an author prefixes `lore:` via existing dialogue `set_flags` side effects — no new authoring mechanism), and active quest titles (`QuestRepo.active_progress`). Cartography's map-reveal payoff is Sprint 26's job (the full-screen map modal task explicitly owns "integrated with cartography reveal") — this sprint only ships the skill identity and the journal's read-only view.
- New `traits`/`skills`/`reputation`-style visibility precedent extended: `journal` and `search` give players concrete, testable payoff for the trait/skill/reputation plumbing Sprint 24 shipped.

### Fixed

- **`MovementService.move()` always blocked hidden exits, contradicting the documented behavior** (`world_building.md`: "Exits can be hidden from descriptions but still usable... the player must try the command directly") — a hidden exit could never be traversed even by guessing the exact direction. Fixed: hidden only affects whether `look` lists the exit, never whether `go <direction>` works.
- **`Exit.condition_flags` was stored and round-tripped through YAML import/export but never enforced anywhere** — an exit authored with `condition_flags: ["blessed_by_priest"]` was, in practice, unconditional. Fixed: `move()` now blocks the exit unless every listed flag is set on the player.

## [0.6.0] - 2026-07-04

### Summary

**Sprint 24 Complete — Traits & Skills.** Character identity that gates exploration and social play: an innate trait source (background/earned traits, distinct from equipment/active-effect traits), use-based skill improvement, and NPC/faction reputation gating dialogue and commands. 523 focused tests (18 new) passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 24.1: Trait registry (innate/background/earned)** — `game/standard_traits.py` registers `InnateTraitSource` (reads `PlayerStats.traits`, populated by `services/traits.py`'s `TraitService.grant()`/`revoke()`) alongside 5 illustrative standard traits (2 boons: `keen_eyed`, `silver_tongued`, `sure_footed`; 2 banes: `clumsy`, `frail`) with real modifier effects — completing the three-source picture alongside Sprint 19's active-effect source and Sprint 23's equipment source. New `traits` command lists a player's currently active traits (from every source) with descriptions.
- **Sprint 24.2: Use-based skill improvement** — `game/skills.py`'s `SkillRegistry` defines skill *identity* (perception, lockpicking, bartering, cartography, survival, persuasion) on top of Sprint 17-18's `skill_check()`, which already defined how a check resolves. `services/skills.py`'s `SkillService.record_use()` is the "learn by doing" mechanic: each use has a 10% chance to raise the skill's level (stored in the existing `PlayerStats.skills` dict) by 1, capped at 100. New `skills` command lists all standard skills and the player's current level in each. No command calls `record_use()` yet — Sprint 25's `search` (perception) is the first real consumer, same "ships the primitive, next feature wires it in" precedent as `skill_check()` itself.
- **Sprint 24.3: Reputation/standing** — New `models/reputation.py`'s `Reputation` table (one row per player × target_type × target_id, "npc" or "faction"). `services/reputation.py`'s `ReputationService` clamps standing to [-100, 100]. `game/reputation_conditions.py` registers a `reputation_at_least:<type>:<id>:<min>` command condition and a `min_reputation` dialogue condition (`{"target_type", "target_id", "min"}`) on the existing Sprint 10 pluggable-condition registries — no core edits, gating dialogue/prices/quests behind standing exactly as the roadmap specifies. New `reputation`/`rep` command lists a player's standings.
- New `services/character_info.py`'s `CharacterInfoService` backs the `traits`/`skills`/`reputation` commands (`commands/character.py`), wired into `ServiceContainer` alongside the other gameplay services.

## [0.5.0] - 2026-07-04

### Summary

**Sprint 23 Complete — Inventory & Equipment.** Wear/wield slots, encumbrance, containers, and light/darkness gating, all built only on Tier 1 primitives per `docs/inventory_equipment.md`. 505 focused tests (69 new) + 5 simulation tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 23.1: Equipment** — Equipped-ness is a location, not a column (supersedes the roadmap's old `Player.equipment` draft): wearing a helm is `ItemLocationService.move()` to `Location("player", id, slot="head")`. `game/equipment_slots.py` ships the default slot set (14 slots: worn + wielded) as data, with a generic `"finger"` item-slot that the `wear` command resolves to whichever of `finger_l`/`finger_r` is free. `game/equipment_validators.py` registers a `player`-holder move validator (slot must be known, item must fit and match wearable/wieldable, slot must be empty). `InventoryService` gains `wear_item`/`remove_item`/`wield_item`/`unwield_item`/`list_equipment`, wired as `wear`/`remove`/`wield`/`unwield`/`equipment`/`eq` commands — extending the existing service rather than forking it. New `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events. `game/item_rules.py` adds the bound-item policy veto (`Item.bound` items can't be `drop`/`give`) as a fail-closed `RuleEngine` rule at the command layer, not inside the primitive — caught a real ordering bug along the way: `ctx.parsed_command` isn't set until *after* `rules.check()` runs (game/engine.py's lifecycle), so the rule reads the noun from the audit payload the engine already built instead.
- **Sprint 23.2: Encumbrance & equipment-derived modifiers** — `game/item_effects.py` compiles `Item.effects` descriptors into Tier 1 `Modifier`s (`stat_bonus`/`skill_bonus`/`carry_bonus`) or trait grants (`grant_trait`); `game/equipment_source.py` registers an `EquipmentModifierSource` and `EquipmentTraitSource` that walk a player's equipped stacks and feed Sprint 18's modifier resolver and Sprint 19's trait registry — equip/unequip changes what resolves immediately, nothing is cached. `game/encumbrance.py`: `carry_base(strength)`, `resolve_carry_capacity()` (resolved, never stored — a worn backpack's `carry_bonus` extends it live), `total_carried_weight()`, and `encumbrance_band()` (unburdened/burdened/overloaded at capacity/1.5×capacity). "Cannot pick up more" is enforced at the command layer (`InventoryService._would_overload`) rather than as a generic holder-registry validator — the validator signature has no visibility into the source location, so a naive implementation would double-count weight on `wear`/`remove` (same-owner slot changes, not new weight entering play); checking at the specific take/give-receipt call sites where weight genuinely increases avoids that bug.
- **Sprint 23.3: Containers & light/darkness** — `game/container_validators.py` registers a `container`-holder move validator: closed containers reject moves, moves exceeding declared `capacity` are rejected, and nesting past `MAX_NESTING_DEPTH=3` is rejected. `put <item> in <container>` / `take <item> from <container>` added to `InventoryService`, riding the parser's existing (previously unused) `ContainerRoles`/preposition-to-role machinery (`in`→destination, `from`→source). `light`/`extinguish` commands toggle the `lit` component; `services/light_fuel.py`'s `LightFuelService` is a `MeterService`-shaped scheduler sweep that drains one durability point per world-clock tick from every lit instance, auto-extinguishing at zero — creating the "demand for oil/torches" resource loop the design calls for. The `requires_light` command condition now also passes when the player has an *equipped* item with `light > 0` and `lit.lit == true` (previously it only ever checked `Room.light_level`).
- **Bug fix (found while building 23.3): container-cycle detection compared item *type*, not instance** — `ItemLocationService._check_container_cycle()` (Sprint 16) compared the moved item's `item_id` against the destination container's `item_id`, so nesting one chest inside a *different* chest instance of the same item definition falsely raised "cannot place a container inside itself" — any two same-type containers could never nest. Fixed to walk the destination's actual ancestry by `ItemInstance.id`, correctly rejecting only genuine cycles (including transitive ones: A inside B inside A), which the original single-hop check also missed entirely. 2 new regression tests in `test_item_location_service.py`.
- **Bug fix (found while testing 23.3): equipped items were invisible to open/close/light/extinguish** — `InventoryService._find_carried_or_visible_stacks()` used `ItemRepo.player_stacks_matching()`, which only returns *loose* (`slot=None`) stacks; a wielded lantern could never be found to light it. Fixed to search all of a player's stacks regardless of slot.

## [0.4.1] - 2026-07-04

### Added

- **Sprint 22.2: Standard Item Components** — Completes Sprint 22 (the first commit only shipped 22.1). Registers the four standard components from `docs/inventory_equipment.md` §7 on Sprint 16's `ComponentRegistry`: `durability` (applies when `max_durability` is set; state `{"current": N}`), `openable` (applies to containers; state `{"open": bool}`), `lit` (applies when `light > 0`; state `{"lit": bool}`), `container` (applies when `capacity` is set; state `{}`, contents are stacks not state). `game/standard_components.py` self-registers at import time (mirrors `game/traits.py`'s pattern); imported for side effects from `main.py`'s module scope. New `services/item_components.py` (`get_component_state`/`set_component_state`) centralizes instance-state mutation — JSON columns need a fresh dict object per write for SQLAlchemy to notice the change, so every setter reassigns `instance.state` rather than mutating in place. `open`/`close` commands added to `InventoryService`/`commands/inventory.py`, resolving carried-or-visible stacks with a registered `openable` component state. 6 new tests (component initial state on spawn, open/close round trip, already-open/already-closed messaging, non-openable item rejection). 354 focused tests passing; basedpyright 0 errors; ruff clean.

## [0.4.0] - 2026-07-04

### Summary

**Sprint 22 Complete — Standard Item Definition Fields (Tier 2 Layer A, first feature-band sprint).** Item definition expanded with equipment, encumbrance, light, durability, and effect-descriptor fields. `models/world.py`'s `Item` model gains 8 new optional/nullable fields: `slot` (equipment slot key), `wearable` (worn vs. wielded), `weight` (drives encumbrance), `quality` (common/fine/superior/rare/legendary, affects trade), `max_durability` (None = indestructible, else tracked per-instance), `light` (light level when equipped & lit), `capacity` (makes item a container), `effects` (effect descriptor list, registry-driven). `world/validator.py`'s `ItemData` updated to match, with corresponding loader updates in `world/loader.py` (import/export). New `check_item_definition_fields()` validator in `tools/validators.py` enforces: known slot names, wearable items must have slots, known qualities, containers must be takeable, non-negative weight/light/durability, known effect descriptor types, known stat names in effect descriptors. 9 new validator unit tests, all passing. Tier 1 foundation consumed: Tier 2 now starts on this layer. 348 focused tests + 3 e2e + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. See `docs/inventory_equipment.md` §3–10 for the binding design. Next: Sprint 23 (equipment & encumbrance).

### Added

- **Sprint 22: Standard Item Definition Fields** — Tier 2 Layer A: item definition expansion for equipment/encumbrance/light mechanics. `Item` model gains 8 fields: `slot`, `wearable`, `weight`, `quality`, `max_durability`, `light`, `capacity`, `effects`. Content validators added for all fields (unknown slots, quality, effect types; wearable without slot; non-takeable containers; negative numeric values; unknown stats in effect descriptors). YAML loader updated to round-trip all fields on import/export. No new commands or services yet — just data modeling and validation. Sprints 23–35 build features on top of this foundation.

## [0.3.1] - 2026-07-04

### Changed

- `AGENTS.md`: codified strict semver discipline going forward — bump the version and update `CHANGELOG.md` in the same commit as every change from here on (minor bump per completed sprint, patch bump per fix/docs-only change), rather than batching version bumps only when explicitly requested.

## [0.3.0] - 2026-07-04

### Summary

**Sprints 20–21 Complete — Ledger & scheduled mobile entity (Tier 1 engine primitives), closing out the engine-core band.** `models/ledger.py`'s `CoinBalance` and `services/ledger.py`'s `LedgerService` add a coin balance on any registered holder (player/bank/corpse/shop; no `Player.coins` column) plus one atomic multi-leg `execute_exchange()` for coins and items together — validates every leg first, then applies every leg's mutations, so a failing leg leaves nothing partially applied. `models/mobile.py`'s `MobileRouteState` and `services/mobile_route.py`'s `MobileRouteService` add the generic scheduled route runner (the "moving room" primitive transit will ride on) — a waypoint state machine with ping-pong reversal or circular looping, position interpolation for the minimap, and pluggable `RouteHooks` (`may_depart`/`on_depart`/`on_arrive`/`on_tick`); reuses the existing `SchedulerService` for all timing, no second timing mechanism. 29 new tests, all green first run — no bugs caught, unlike Sprints 16/19. 538 focused tests + 3 e2e + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.7–3.8 for the binding specs. Tier 1 engine-core band (Sprints 16–21) is now complete; Tier 2 feature work starts at Sprint 22.

**Sprint 19 Complete — Meters, timed effects & traits (Tier 1 engine primitives).** `models/meters.py`'s `Meter` (one named-bounded-resource primitive instead of one column per resource) and `ActiveEffect` (clock-driven buffs/debuffs); `services/meters.py`'s `MeterService` and `services/effects.py`'s `EffectService` (both stateless-per-call for command-path get/adjust/apply/remove, engine-holding for their scheduler-driven regen/expiry sweeps); `game/traits.py`'s trait registry, shipping the one Tier 1 `TraitSource` (active effects' `grants_traits`) and registering both a trait and an active-effect `ModifierSource` with Sprint 18's resolver. The HP migration proves the primitive: `PlayerStats.current_hp`/`NPC.current_hp` are deleted outright, replaced by `Meter(entity, "hp")`, with `max_hp` staying as the definitional base. 25 new tests caught two real bugs in the scheduler sweeps (reading ORM attributes after `session.commit()` expired them). 509 focused tests + 3 e2e + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.3–3.4 for the binding specs. Next: Sprint 20 (ledger + atomic transfer).

**Sprints 17–18 Complete — Determinism: seedable RNG, modifier resolution & skill-check (Tier 1 engine primitives).** `game/rng.py`'s `GameRng` is now the one sanctioned randomness source in `src/lorecraft` (deterministic when seeded; bare `import random` is ruff-banned everywhere else in `src/`); one app-wide instance threads through `GameContext`, `SchedulerEventContext`, and `clock/weather.py`. `game/modifiers.py`'s `resolve()` is the one runtime resolver for stacked bonuses (fixed add→mult→clamp bucket order), with a pluggable `ModifierSource`/`ModifierRegistry` for collection. `game/checks.py`'s `skill_check()` composes both into the one roll-under-d100 helper every future perception/lockpicking/bartering/combat-to-hit check will share. 21 new unit tests; 484 focused tests + 3 e2e + 5 simulation tests passing (including the audit-regression diff and the concurrent-take-no-duplication guarantee); basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.5–3.6 for the binding specs.

**Sprint 16 Complete — Item location/ownership & instance state (Tier 1 engine primitive).** Unified `ItemStack`/`ItemInstance` model (`models/items.py`) replaces `Player.inventory: list[str]` and the `RoomItem` table outright — one atomic move primitive (`ItemLocationService.move()`, plus `spawn()`/`destroy()`/`materialize()`) for every place an item changes hands (take/drop/give, world import, save/load, changeset item-deletion cleanup). A pluggable `ComponentRegistry` (`game/components.py`) and `HolderRegistry` (`game/holders.py`, built-ins: player/room/container) round out the primitive; Tier 1 registers no components or extra holder types, leaving those to Tier 2. Full blast-radius migration across services/inventory.py, repos/item_repo.py, game/context.py, game/command_conditions.py, services/movement.py, services/quest.py, npc/side_effects.py, services/save.py (v1-save-compatible load), world/loader.py, world/versioning.py, tools/world_cli.py, scripts/import_world.py, admin/routers/players.py, main.py, web/session.py, web/frontend.py. 454 focused tests (23 new invariant tests for the move primitive) + 3 e2e + 5 simulation tests passing (including the audit-regression diff and the concurrent-take-no-duplication guarantee); basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.1–3.2 for the binding spec.

**Sprints 4–15 Complete — Player authentication shipped, foundation gate is green.** Player authentication (password login, JWT access/refresh tokens, single-use WebSocket tickets, retired the `?player_id=` trust-by-default, OAuth extensibility stub), module decomposition (web/parser/admin split into 9 focused modules), service consistency (ServiceContainer, register(bus) convention), extensibility seams (pluggable registries for dialogue side effects, dialogue/command conditions, feature-registration pattern documented), tooling infrastructure (repo-tracked issues/news, world content CLI, analytics query API, content linting), a browser E2E harness (Playwright against a live server), a simulation harness (real WebSocket clients against a live server, multi-player scenarios, audit-log regression diffing), observability + CI quality gates (structured logging with correlation IDs, command/event timing instrumentation, required GitHub Actions checks), a unified command lifecycle (rollback-on-error, shared `/ws`/`POST /command` room-broadcast step, unified `GameContext` construction), and core UX completion (world clock/weather WS push to all connected players, multi-player live lists refreshed on room-leave). 431 focused tests + 3 E2E tests + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. All 8 foundation exit criteria now met — Sprints 16+ (engine-first Tier 1 primitives, then item/equipment/trading/exploration/combat/PvP; see `docs/engine_core.md` and `docs/roadmap.md`) are unblocked.

### Added

- **Sprint 21: Scheduled Mobile Entity ("moving room")** — The generic route-runner primitive transit vehicles (and, latently, wandering NPCs/patrols) ride on (`docs/engine_core.md` §3.8). `models/mobile.py`'s `MobileRouteState` (SQLModel table: `route_id` PK, `status` — `at_stop`/`in_transit`/`halted` — `current_index`/`next_index`, `direction`, `depart_epoch`/`arrive_epoch`) is the only persisted piece; `Waypoint` (`position_id`, `x`/`y`, `dwell_ticks`, `travel_ticks`) and `RouteSpec` (`route_id`, `waypoints`, `reverses`, `loop`, `tick_pushes`) in `services/mobile_route.py` are pure in-memory dataclasses the owning feature supplies at lifespan — Tier 1 never persists a spec. `MobileRouteService` is engine-holding schedulable, exactly the `SchedulerService` shape: `register(bus)` listens for `SCHEDULED_JOB_DUE` with `job_type="mobile_route"` (actions `depart`/`arrive`/`tick`, reusing `SchedulerService.schedule()` for all timing — no second timing mechanism); `add_route()` registers a spec/hooks pair and ensures a runtime state row exists without ever resetting one that's already there (a server restart resumes, it doesn't re-initialize); `start()`/`halt()`/`resume()` for manual control; pure `progress()`/`position()` for minimap interpolation. State machine: `at_stop` --(dwell elapses, `RouteHooks.may_depart` → `None`)--> `in_transit` --(arrive job)--> `at_stop` at the next waypoint, with index/direction advancing via reverse-at-ends (`reverses=True`, the default — ping-pongs regardless of `loop`) or loop-wraparound (`reverses=False, loop=True` — circular). A `may_depart` halt reason (e.g. weather) parks the route and reschedules a re-check after `dwell_ticks`; `resume()` forces an immediate re-check instead of waiting. `on_tick` fires `tick_pushes` times per segment with interpolated progress — throttled by design, never per world-tick; Tier 1 pushes nothing to clients itself, leaving the Tier 2 transit module to turn it into a `transit_update` WS message. A route whose spec/hooks disappear on restart (owning feature didn't re-`add_route()` before a pending job fires) halts instead of crashing. `AppState` gains a `mobile_routes: MobileRouteService` field, wired into `main.py`'s lifespan alongside the scheduler/meter/effect services. 15 new tests (full ping-pong round trip, circular looping, halt/resume, tick-push interpolation, spec-disappeared-on-restart) — all green first run.

- **Sprint 20: Ledger & Atomic Transfer** — A coin balance on any holder plus one atomic multi-party transfer for coins and items together (`docs/engine_core.md` §3.7). `models/ledger.py`'s `CoinBalance` (`holder_type`/`holder_id`/`balance`, one row per holder, using the same `HolderRegistry` as `ItemStack` — no `Player.coins` column). `services/ledger.py`'s `LedgerService` is stateless per-call (every method takes the caller's `Session` explicitly, matching `ItemLocationService`'s command-path shape — no engine/rng held, since there's no scheduler sweep for this primitive): `balance_of()`; `credit()` (the *only* way coins enter play — world import, admin, loot); `execute_exchange(legs: Sequence[ExchangeLeg])` — each leg is a `give_from`/`give_to` `Location` pair plus `coins`/`stacks` to move. Validates every leg first (sufficient coin balance, destination holder exists, every stack is actually at its declared `give_from` with sufficient quantity) and only if *every* leg passes does it apply *any* mutation — a P2P trade's `accept()` becomes one `execute_exchange()` call with both directions as legs, atomically; a failing second leg leaves the first leg's mutation entirely un-applied. Reuses Sprint 16's `ItemLocationService.move()` for the stack legs. `GameContext` gains a required `ledger` field; `build_game_context()` constructs a fresh `LedgerService()` with no new required kwarg (no engine/rng dependency, unlike Sprint 19's `meters`/`effects` — smaller blast radius). 14 new tests, including a two-way trade-shaped exchange verifying coin conservation across both directions and an atomicity test verifying a failing leg applies nothing from any leg — all green first run.

- **Sprint 19: Meters, Timed Effects & Traits** — Two more Tier 1 engine-core primitives (`docs/engine_core.md` §3.3–3.4). `models/meters.py`'s `Meter` (`entity_type`/`entity_id`/`key`/`current`/`maximum`, one row per named resource — hp, fatigue, hunger, mana, ... — instead of one column each) and `ActiveEffect` (clock-driven buff/debuff, distinct from equipment effects which last only while equipped and from traits which are semi-permanent). `game/meters.py`'s `MeterDef`/`MeterRegistry` (key, `base_maximum` callback, `regen_per_tick`, `start_full`) and `services/meters.py`'s `MeterService`: `get()` creates a meter lazily from its registered def; `adjust()`/`set_current()`/`recompute_maximum()` are stateless per-call, taking the caller's `Session` (command-path shape, same as `ItemLocationService`); `_on_time_advanced()` is the regen sweep — its own short-lived session, ticking every already-created meter with a registered `regen_per_tick`, emitting `METER_DEPLETED`/`METER_RECOVERED` directly since no `GameContext` exists in scheduler-driven work (command-path `adjust()` stays pure per Sprint 16's "primitives emit nothing" convention — callers decide whether to queue a domain event from the returned `MeterChange.depleted`/`.recovered` flags). `game/effects.py`'s `EffectDef`/`EffectRegistry` and `services/effects.py`'s `EffectService`: `apply()`/`remove()`/`active_for()` stateless per-call; `_on_time_advanced()` sweeps expired `ActiveEffect` rows and emits `EFFECT_EXPIRED`. `game/traits.py`'s `TraitDef`/`TraitSource`/`TraitRegistry`: Tier 1 ships exactly one `TraitSource` (`ActiveEffectTraitSource`, sourcing from each active effect's `grants_traits`) and registers both an `ActiveEffectModifierSource` and a `TraitModifierSource` with Sprint 18's `ModifierRegistry` — fulfilling that sprint's "Tier 1 registers the active-effect and trait sources" promise. New `PlayerStats.traits: list[str]` column (empty by default; Tier 2 populates it). The HP migration is the proof-of-primitive: `PlayerStats.current_hp` and `NPC.current_hp` are **deleted outright** (not deprecated) — `max_hp` stays as the definitional base, fed to the "hp" `MeterDef`'s `base_maximum`, registered as bootstrap in `main.py`'s lifespan. Full blast radius: `world/loader.py` (NPC seeding no longer sets `current_hp` — `MeterService.get()` creates it lazily), `admin/routers/world.py` (NPC listing does a read-only `MeterRepo` lookup rather than triggering lazy-creation from a GET, falling back to `max_hp` for an as-yet-uncreated meter), `services/save.py` (`stats_snapshot` drops `current_hp`, gains a `"meters": {"hp": ...}` dict; loading converts both the new shape and the old v1 flat `"current_hp"` key). `GameContext` gains required `session`/`meters`/`effects` fields; `build_game_context()` gains required `meters`/`effects` keywords — both real entry points and every test fixture updated (same "factory is the single construction path" precedent as Sprints 16 and 17). `AppState` gains `meters`/`effects`; new `web/session.py` `get_meters()`/`get_effects()` accessors mirror `get_rng()`'s app-state-with-fallback shape. New `GameEvent` members: `METER_DEPLETED`, `METER_RECOVERED`, `EFFECT_APPLIED`, `EFFECT_EXPIRED`, `EFFECT_REMOVED`. 25 new invariant tests caught two real bugs: both `_on_time_advanced` sweeps built a list of ORM rows inside a `with Session(...)` block, then read attributes off them (`entity_type`/`entity_id`/`key`) *after* the block closed the session — `session.commit()`'s default `expire_on_commit` invalidates every loaded attribute, so the post-block reads tried to lazy-refresh from a closed session and raised; fixed by capturing plain `(str, str, str)` tuples before the session closes, in both services. Also caught (and fixed) a test-isolation bug of its own: an early draft of the meter tests registered a throwaway `MeterDef` under the *real* `"hp"` key and popped it in fixture teardown, which — since `MeterRegistry` is a shared module-level singleton — deleted the real `"hp"` registration `test_save.py` (and `main.py`'s bootstrap) rely on; renamed the test-only keys to `__test_hp__`/`__test_fatigue__`. Full suite (509 unit/integration + 3 e2e + 5 simulation, including the audit-regression diff and concurrent-take-no-duplication guarantee) green throughout.

- **Sprints 17–18: Determinism (Seedable RNG, Modifier Resolution & Skill-Check)** — Two more Tier 1 engine-core primitives (`docs/engine_core.md` §3.5–3.6), implemented in dependency order (18 before 17.2) rather than roadmap numeric order, since `skill_check()`'s signature needs the `Modifier` type from Sprint 18 and the doc's own build-order table already notes Sprint 18 has no dependencies. `game/rng.py`'s `GameRng` wraps `random.Random` behind a seedable, deterministic interface (`randint`/`uniform`/`choice`/`chance`) — the *only* permitted `random` import in `src/lorecraft`, enforced by a new ruff `flake8-tidy-imports` banned-api rule (`TID251`) scoped to `src/` via `per-file-ignores` (test-harness timing jitter in `tests/simulation/virtual_player.py` isn't game logic and doesn't feed the audit-regression diff, so it's exempted). One `GameRng` instance per app, built in `main.py`'s lifespan from new `Settings.rng_seed` (env `LORECRAFT_RNG_SEED`, default `None` = OS entropy) and stored on `AppState`. `GameContext` gains a required `rng` field and `build_game_context()` a required `rng` keyword — both real entry points and every test fixture updated (the factory being the single construction path is what keeps this a bounded change, same as Sprint 16's `item_location` rollout). `SchedulerEventContext` gains `rng` too. `clock/weather.py` (previously the only `random` user, already structured around an injectable `choice` callable) now requires `rng: GameRng` in `register_weather_handlers()` instead of quietly defaulting to `random.choice`. `game/modifiers.py`'s `Modifier`/`resolve()` is the one runtime resolver for bonuses stacked from many sources — fixed bucket order (`add` → `mult` → `clamp_max`/`clamp_min`, commutative within each bucket, never stored/cached); a `ModifierSource` protocol + `ModifierRegistry` + `resolve_for()` handle collection, with Tier 1 registering zero sources (the active-effect/trait sources arrive with Sprint 19, equipment/terrain with Sprint 23+). `game/checks.py`'s `skill_check(rng, *, base, difficulty, modifiers=(), key="check")` resolves `effective` through the modifier resolver, clamps the success threshold to `[CHECK_FLOOR=5, CHECK_CEIL=95]` (no impossible checks, no sure things), and rolls 1-100 — one resolution path for perception, lockpicking, bartering, and combat-to-hit; skill *identity* (which skills exist, use-based improvement) stays Tier 2 (Sprint 24). 21 new unit tests: 9 for `GameRng` (seeded-sequence equality, bounds, chance boundaries), 12 for the modifier resolver (including the spec's worked example — base perception 30, `+5 add`, `×1.1`/`×0.8 mult`, `clamp_max 95` → `30.8`), 9 for `skill_check` (difficulty shifts, floor/ceiling clamps, same-seed determinism). Full suite (484 unit/integration + 3 e2e + 5 simulation, including the audit-regression diff and concurrent-take-no-duplication guarantee) green throughout — this band only adds plumbing, no command yet rolls through `ctx.rng`.

- **Sprint 16: Item Location/Ownership & Instance State** — First Tier 1 engine-core primitive (`docs/engine_core.md` §3.1–3.2). `models/items.py`'s `ItemStack` (`item_id`, `owner_type`/`owner_id`/`slot`, `quantity`, optional `instance_id`) is now the *only* way to say where an owned item lives — it **replaces** `Player.inventory: list[str]` and the `RoomItem` table outright (both deleted, not deprecated). `ItemInstance` carries per-instance component state (`state: JsonObject` keyed by component name); Tier 1 registers no components, but a new `ComponentRegistry` (`game/components.py`) lets Tier 2 (durability, openable, lit, container — Sprint 22) or any world author plug in without core edits. `game/holders.py`'s `HolderRegistry` defines which holder types exist (`player`, `room`, `container` built in) and their move validators (mechanical-capacity hooks like slot occupancy or container fullness — none registered yet, Tier 2's job). `services/item_location.py`'s `ItemLocationService` is the one atomic operation family: `spawn()` (create from nothing — world import, loot; merges into an existing fungible stack or creates one instance per unit for component-bearing items), `destroy()` (remove with quantity-underflow guard), `materialize()` (split one unit off a fungible stack into a fresh instance — a torch becoming *this* 40%-burned torch), and `move()` (the primitive everything else composes: validates source quantity/dest holder existence/registered validators/container-cycle freedom, then splits or merges as needed, all-or-nothing within the caller's transaction). Every place an item changed hands was migrated onto this: `services/inventory.py` (take/drop/give/use), `game/context.py` (`get_inventory()`/`get_visible_entities()`), `game/command_conditions.py` (`item_in_inventory`), `services/movement.py` (locked-exit key checks), `services/quest.py` (item-carried conditions/rewards), `npc/side_effects.py` (dialogue `give_item`), `services/save.py` (save-slot snapshots — v2 shape is a list of `{item_id, quantity, instance_id}` dicts; **loading a v1 flat `list[str]` snapshot still works**, converting on read by re-spawning one unit at a time, which naturally re-merges into a single fungible stack), `world/loader.py`/`world/versioning.py`/`tools/world_cli.py`/`scripts/import_world.py` (room-item YAML import/export and changeset item-deletion cleanup), and the admin/WS/HTMX inventory views (`admin/routers/players.py`, `main.py`, `web/session.py`, `web/frontend.py`). New `Item.bound: bool` field (data only here; enforcement — can't drop/sell/trade — is Tier 2 policy). New `InventoryEntry` TypedDict (`types.py`) documents the WS/HTMX inventory push shape. Caught two real bugs along the way, both fixed before they shipped: (1) every `raise` in `ItemLocationService` had `GameError`'s `(message, code)` constructor arguments backwards; (2) `StackRepo.delete_stack()` didn't flush after `session.delete()`, so a stack destroyed to exactly zero was still visible to a same-transaction `find_stack()` lookup (`Session.get()` consults the identity map before the DB). Also discovered and worked around a pydantic recursion bug unrelated to this feature: a bare `list[JsonValue]` SQLModel field type (as opposed to `dict[str, JsonValue]`, which is fine) sends pydantic's forward-ref resolver into infinite recursion on this pydantic/typing version — `SaveSlot.inventory` is typed `list[Any]` instead, with the JSON shape documented in a comment. 23 new unit tests for the primitive's invariants (`test_item_location_service.py`) plus the full existing suite (431 unit/integration + 3 e2e + 5 simulation, including the audit-regression diff and the concurrent-take-no-duplication guarantee) all green unchanged — no audit-event schema or ordering changes from this migration, by design.

- **Sprint 4: Player Authentication** — Real password auth replacing the previous zero-authentication lobby (anyone could one-click enter as any existing character). New `PlayerAuth` table (provider-agnostic `provider`/`provider_subject`/`credential_hash`, ready for OAuth without a schema change). `web/auth.py`'s `login_or_register()` creates an account atomically on first login, verifies the stored password hash on repeat login, and *claims* pre-existing passwordless players (e.g. dev-seeded `player-1`) on first authenticated login — shared by `POST /auth/login` (JSON API) and the browser's `/lobby/enter`/`/lobby/create` (one password-checking code path for both). Password hashing reuses `admin/auth.py`'s existing PBKDF2-HMAC-SHA256 primitives rather than adding bcrypt/argon2 as a second hashing convention. `POST /auth/login` issues 15-minute access + 8-hour refresh JWTs (reusing `admin/auth.py`'s `create_token`/`decode_token`, signed with `Settings.player_session_secret`, a distinct token `type` from the browser's `lorecraft_session` cookie so neither can be replayed as the other); `POST /auth/refresh` rotates them, verifying the player still exists. `POST /auth/ws-ticket` mints a single-use, 60-second ticket (in-memory on `AppState.ws_tickets`, matching the existing `pending_disambig` pattern) — accepts either a bearer access token or the browser's signed session cookie, since browsers can't easily attach custom headers to a WebSocket upgrade. `main.py`'s `/ws` endpoint now resolves the connecting player via `?ticket=` first, rejecting outright on an invalid/expired/reused ticket rather than silently falling back to `?player_id=`. `Settings.allow_query_player_id` now defaults to `False`; kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests) rather than the login UI. `POST /auth/oauth/{provider}/callback` is a genuine 501 stub marking the extension point — `PlayerAuth`'s shape already supports it, nothing is wired up. Fixed two bugs surfaced along the way: (1) JWT `create_token()` only had second-precision `iat`, so two tokens issued for the same subject within the same second were byte-for-byte identical — added a `jti` claim, fixing both the new player refresh endpoint and the pre-existing admin one; (2) flipping `allow_query_player_id` off exposed that `GET /lobby` depended on `get_current_player` (which now 401s with no session), so a brand-new visitor couldn't reach the page that lets them log in — a real e2e browser test failure caught this before unit tests would have; new `get_current_player_optional()` fixes it for `/lobby` only. 44 new/updated tests across `test_player_authentication.py` (15), `test_player_login.py` (9), and updated lobby/session/simulation/characterization tests for the password requirement.

- **Sprint 15: Core UX Completion** — Closed the last two `[~]` STATUS partials. **15.1 World clock/weather WS push:** `ConnectionManager.broadcast_global()` sends a message to every connected player regardless of room; `main.py` wires a `TIME_ADVANCED` handler that broadcasts current clock/weather state (`time_update`: hour, minute, day, season, weather) to all players on every tick, not just on connect/reconnect SSR. **15.2 Multi-player live lists:** `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player *left*, not just the room they entered — previously, occupants of the old room only saw the departure narration text in the feed, with no live players-list refresh until they took some other action. Both verified with new/updated simulation tests exercising the real WS broadcast path over a live server.

- **Sprint 14: Unify Command Lifecycle** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught: on a crash it rolls back the game DB session (new `GameContext.rollback_state`/`rollback_state_changes()`, wired at both entry points), discards any partial `ctx.messages`/`room_messages`/`updates`/`pending_events` the crashed handler produced (never tell clients something happened until the DB says it happened), replaces them with a generic error message, and records a new `GameEvent.COMMAND_FAILED` audit event (severity `ERROR`). New `game/broadcast.py`'s `broadcast_command_effects()` is now the one place step 12 of the architecture.md §26 lifecycle (room broadcast) lives — both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap Sprint 12's simulation tests surfaced: the raw `/ws` path never re-broadcast a command's `ctx.room_messages` narration or a `state_change` nudge to other WS-connected room occupants the way `POST /command` did. `web/frontend.py`'s previous inline copy of that logic is gone in favor of the shared function. New simulation test exercises the previously-broken `/ws` path over a real socket; full existing suite (unit/integration/e2e/simulation) confirms `POST /command` behavior is unchanged. **Follow-up:** `game/context.py`'s `build_game_context()` factory (Sprint 6.3) turned out to be unused by both real entry points, which still constructed `GameContext` inline — extended it to accept `audit_session` (a separate `Session`, matching real usage, replacing the old same-session `create_audit_repo` bool) and `rollback_state`, stopped it from synthesizing a fallback `WorldClock` when `clock` isn't given (a fabricated clock is silently wrong data, not a safe default — real callers pass `room_repo.world_clock()`, which can legitimately be `None`), and switched both `main.py` and `web/frontend.py` to call it. Neither entry point builds any repo by hand for `GameContext` anymore.

- **Sprint 13: Observability & CI Quality Gates** — `observability.py`: `configure_logging()` attaches a correlation-aware log formatter/filter to the root logger (idempotent; level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`, default `INFO`), and `bind_transaction_context()` publishes a `TransactionContext`'s IDs to a `contextvars.ContextVar` for the duration of one command so every log call anywhere in that call stack picks them up automatically — wired into `create_app()` and both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`). `CommandEngine._execute_parsed` (`game/engine.py`) now times each command handler and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload; `EventBus.emit()` (`game/events.py`) times each handler dispatch onto a new `HandlerResult.duration_ms` field and logs handler timing + registered-handler count ("depth") at DEBUG. New `analytics.command_latency_percentiles()` (p50/p95/p99) + `GET /admin/analytics/latency`. `.github/workflows/ci.yml`: three required jobs on push/PR to `main` — `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`); new `make lint`/`make typecheck`/`test-cov` targets; new `pytest-cov` dev dependency with `[tool.coverage.report] fail_under = 80` (baseline ~82%). Fixed a latent bug found while dry-running the CI commands locally: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only resolved under `python -m pytest`, not the bare `pytest` that `make test-simulation`/CI actually invoke — fixed by adding `"."` to `pythonpath` in `pyproject.toml`.

- **Sprint 12: Simulation Harness MVP** — `tests/simulation/`, a third test transport alongside the ASGI-transport integration tests and the Sprint 11 browser E2E harness: real `websockets` clients against a real, live `uvicorn` server, per `architecture.md` §25. `virtual_player.py`'s `VirtualPlayer` wraps one real `/ws` connection (`send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed messages). `conftest.py`'s `simulation_server`/`simulation_server_factory` fixtures boot the real app against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same no-synthetic-world-content pattern as `tests/e2e/`). `test_multiplayer_scenarios.py` covers `player_joined` broadcast fan-out and concurrent `take` of a single-quantity item (exactly one winner, no duplication). `test_audit_regression.py` runs a fixed script against two independent fresh servers and diffs the normalized audit trail for determinism. New `simulation` pytest marker excluded from `pytest`/`make test` by default (`-m "not simulation"`, run via `make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Surfaced but intentionally left unfixed: the raw `/ws` command loop doesn't yet re-broadcast `room_messages` to other room occupants the way `POST /command` does — tracked by Sprint 14 (unify command lifecycle).

- Launcher DB initialization: `./start.sh --init-dbs-if-missing` creates missing seed
  game/audit DBs before launch; `--init-dbs-only` performs setup and exits. Game DB
  import reads `world.yaml` from `--world-dir`/`--world`, defaulting to
  `world_content/`. Added `scripts/create_audit_db.py` for standalone audit schema
  creation.

- **Sprint 11: Browser E2E Harness** — `tests/e2e/` drives the HTMX/Alpine UI through a real headless-Chromium browser against a real, live `uvicorn` server, catching regressions (HTMX swaps, OOB panel updates) that the ASGI-transport integration tests can't see. `conftest.py`'s `live_server` fixture boots `create_app()` on a background thread with a disposable per-test sqlite DB and the real `world_content/world.yaml`; `test_gameplay_flows.py` covers character creation, movement with room/inventory panel updates, and dialogue → quest-start, exercising the same Ashmoore golden path documented in `docs/roadmap.md`. New optional `e2e` dependency group (`playwright`) and a `pytest` marker keep the suite out of the default `pytest`/`make test` run (`-m "not e2e"`); `make test-e2e` installs the extra + Chromium binary and runs it explicitly.

- **Sprint 10.5: Tooling Infrastructure** — `docs/tooling_infrastructure.md` design, implemented across five sub-sprints:
  - **10.5.1 Issues** — `docs/issues.yaml` (repo-tracked, git-blame-able) imported into the DB on first startup and re-exported on every admin mutation. `GET/POST/PUT /admin/issues` CRUD, TUI F6 screen, web panel Issues tab.
  - **10.5.2 News** — `docs/news.yaml` announcements with the same YAML↔DB sync pattern. In-game `news` command, public unauthenticated `/api/news` (JSON) and `/api/news/feed` (RSS 2.0), admin CRUD, TUI F7 screen, web panel News tab. `GameContext` gained an optional `news_repo`, wired at both direct construction sites and the `build_game_context()` factory.
  - **10.5.3 World CLI** — `python -m lorecraft.tools.world_cli {import,export,validate,diff,merge,stats}`. Added `export_world_document()` to `world/loader.py` (inverse of `import_world()`) as the shared basis for export/diff/merge/stats. Smoke-tested against the real `world_content/world.yaml`.
  - **10.5.4 Analytics** — `lorecraft.analytics` query functions over the audit log (top commands, NPC interaction counts, quest completions) and `PlayerSession` rows (player-hours), exposed via `GET /admin/analytics/{commands,npcs,quests,player-hours}`. No dashboard yet, per the design doc; command latency/event-bus-depth metrics wait on Sprint 13 instrumentation.
  - **10.5.5 Content linting** — `lorecraft.tools.validators`: dangling dialogue node references, room reachability from a start room, dead item references (`usable_with`, NPC `loot_table`), duplicate item names per room, oversized item stacks. Wired into `world_cli.py validate` via `--start-room`/`--strict`.

- **Sprint 10.4: Feature Registration Pattern** — `docs/feature-registration.md` documents the pattern for adding new gameplay features (combat, trading, PvP) without core edits: features define models, services, commands, and register with pluggable registries (CommandRegistry, CommandConditionRegistry, SideEffectRegistry, dialogue ConditionRegistry, RuleEngine, and ServiceContainer). Example structure shown for future combat feature (Sprint 18).

- **Sprint 10.3: Pluggable Command Conditions** — `game/command_conditions.py` — CommandConditionRegistry with pluggable condition predicates. Replaced hardcoded `_evaluate_condition` if/elif chain in registry.py with registry.evaluate(). Built-in conditions (requires_light, not_in_combat, flag_set, item_in_inventory, etc.) registered at module load; new predicates can be added without core edits.

- **Sprint 10.2: Pluggable Dialogue Conditions** — `npc/dialogue_conditions.py` — ConditionRegistry for dialogue choice/exit visibility. Replaced hardcoded flag checks in _visible_choices with registry-based _choice_visible() that evaluates all condition fields via registered predicates (required_flags, forbidden_flags initially; level_check, has_item, etc. can be added).

- **Sprint 10.1: Pluggable Dialogue Side Effects** — `npc/side_effects.py` — SideEffectRegistry replacing hardcoded if/elif branches in _apply_side_effects. Built-in handlers (set_flags, clear_flags, give_item, start_quest, end_dialogue) registered at module load; new effects can be added without touching dialogue.py.

- **Sprint 9.4: Item Matcher Consolidation** — Replaced three near-identical inline matching loops in `repos/item_repo.py` with one `_match_kind()` classifier plus two thin aggregators: `_best_matches()` (exact-wins, fuzzy-fallback; used by `search_in_room`/`search_player_items`) and `_any_matches()` (position-preserving any-match filter; used by `inventory_slots_matching`, which must stay positionally addressable for indexed take/drop like "2.sword"). Verified position ordering is unchanged with a mixed exact/fuzzy manual check. Same public API, same behavior.

- **Sprint 9.3: Inventory Take/Drop DRY** — Added `InventoryService._resolve_single()` (shared find→disambiguate step, generic over match shape via an `item_of` extractor) and `_do_take()`/`_do_drop()` (shared act step: remove, say, tell_room, emit event). Applied to `_take_one`, `_take_quantity`, `_take_indexed`, `_drop_one`, `_drop_quantity`, `_drop_indexed`, plus `examine`/`use_item`/`give_item` which had the same boilerplate. Behavior preserved exactly (same messages, same disambiguation prompts, same event counts).

- **Sprint 9.2: Event-Wiring Convention** — `QuestService.register(bus)` added, matching the convention already used by `NpcScheduler`/`SchedulerService`. Replaces the three inline `bus.on(GameEvent.X, quest_service.check_progression)` calls in `main.py`'s lifespan with one `services.quest.register(bus)` call.

- **Sprint 9.1: Service Container** — `services/container.py` — `ServiceContainer` dataclass holding the five stateless gameplay services (movement, inventory, save, dialogue, quest), built once via `ServiceContainer.build()`. `AppState` now carries a `services` field; `main.py` builds one container per app lifespan and passes it to both command registration and event wiring instead of each command module (and `main.py`'s inline `QuestService()`) constructing its own. `register_all_commands(registry, services=None)` defaults to a fresh container so existing direct-call test sites and the `web/session.py` standalone fallback keep working unchanged. `register_social_commands` gained an optional `dialogue_service` parameter, matching the other three command modules.

- **Sprint 8.3: Admin API Decomposition** — Split `admin/api.py` (817 lines) into per-resource routers under `admin/routers/`:
  - `players.py` (191 lines) — list/state/teleport/flags/freeze/unfreeze
  - `audit.py` (93 lines) — query_audit, session_replay
  - `world.py` (357 lines) — rooms, items, NPCs, and changesets (create/scan/promote)
  - `clock.py` (125 lines) — get/pause/resume/time-ratio/weather
  - `accounts.py` (93 lines) — list/create/revoke admin accounts
  - `admin/api.py` now 20 lines: mounts `auth_router` + the 5 resource routers onto `admin_router`. Same route paths, same `admin_router` export, so `main.py` required no changes.
  - HTTPException raises remain at the route layer per router (already separated from game-state logic — no service-layer HTTP leakage to fix).
  - All 23 admin API integration tests pass unchanged; basedpyright 0 errors on `admin/`.

- **Sprint 8.2: Parser Grammar Extraction** — Split `game/parser.py` (778 lines) into:
  - `game/grammar.py` (322 lines) — Grammar constants (ARTICLES, PREPOSITIONS, PHRASAL_VERBS, DIRECTIONS, VERB_ALIASES, etc), text processing (normalize, tokenize, make_phrase), semantic rules (extract_quantity_and_adjectives, direct_role_for_verb, find_first_preposition, map_prep_to_role), fuzzy matching (score_match).
  - `game/diagnostics.py` (119 lines) — ParseDiagnostics dataclass, diagnose_command, print_diagnostics for parser debugging.
  - `parser.py` now 399 lines, focused on command parsing (ParsedCommand, ParseResult, parse_command, parse). Re-exports diagnostics for backwards compatibility.
- Fuzzy matching and grammar rules now reusable for alternative parsers or CLI modes.
- All parser tests passing (37 comprehensive tests + full integration suite).

- **Sprint 8.1: Web Frontend Decomposition** — Split `web/frontend.py` (1,306 lines) into three focused modules:
  - `web/session.py` (380 lines) — Dependency injection (get_engines, get_app_state, get_command_engine, get_manager, get_bus), session auth (player_session_secret, set_player_session_cookie, ensure_player_session), state snapshots (inventory_snapshot, room_panel_context, active_quests_snapshot, world_time_snapshot), presence helpers (format_idle_duration, presence_for_player, players_here), grace period expiration, CommandResult dataclass.
  - `web/rendering.py` (180 lines) — Template rendering (build_map_data, audit_to_feed, feed_items_html), HTML output formatting (mark_oob_swap), command resolution (resolve_command_text), dev player creation.
  - `frontend.py` (784 lines) — Focuses exclusively on FastAPI routing and HTTP endpoints. Updated all endpoint handlers and test imports.
- Replaced `getattr`-chain state access in dependency injection with explicit functions (FastAPI `Depends()` ready for Sprint 9).

### Added

- **Sprint 7.4: Event-Flow Characterization Tests** — 10 unit tests locking in event-bus behavior before Sprint 8–9 refactors. Covers: event emission order and priority-based handler execution (higher priority runs first); exception isolation (one handler's error doesn't block others); multiple event types and handlers per event; handler result collection with success/error status; work-event classification. Tests verify core event dispatch guarantees. Tests in `tests/integration/test_event_flow.py`.
- **Sprint 7.3: Admin WebSocket Characterization Tests** — 7 integration tests locking in current behavior of `/admin/ws` endpoint before Sprint 8–9 refactors. Coverage: token validation (JWT accept/reject with code 1008), connection lifecycle (accept, receive, disconnect), multiple concurrent clients, error handling (malformed messages, connection errors). Verifies graceful error handling and state cleanup on disconnect. Tests in `tests/integration/test_admin_websocket.py`.
- **Sprint 7.2: Admin API Characterization Tests** — 6 additional integration tests extending admin endpoint coverage to 23/28 endpoints (~82% coverage) in `test_admin_api.py`. New coverage: player state manipulation (freeze/unfreeze with session status), world data queries (items, NPCs), clock management (time ratio), admin account management (list accounts). Tests verify proper HTTP status codes, role-based access control, and state mutations.
- **Sprint 7.1: Web Characterization Tests** — 23 integration tests locking in current behavior of `web/frontend.py` before Sprint 8–9 refactors. Coverage areas: (1) State resolution — game screen SSR with player/room/inventory/feed snapshots, error handling for missing rooms/players; (2) Session reconnect edge cases — grace period handling, presence status rendering (`online`/`grace`/`away`/idle duration); (3) Feed pagination — `/partials/feed?since=X` filtering, chronological ordering, COMMAND event exclusion; (4) Error rendering — missing room/player handling, empty inventory, many items, multiline OOB swap attributes. Tests in `tests/integration/test_frontend_characterization.py`.

### Fixed

- **Sprint 6: Type Safety Foundation** — Removed 18 `cast(GameContext, ctx)` calls from command handlers by properly typing the context parameter as `GameContext` instead of `object`. Command handlers are now type-checked by basedpyright to ensure safe context access. Replaced `cast(Any, ctx)` + unsafe `getattr()` in `game/registry.py` condition evaluation with direct `GameContext` attribute access. Upgraded basedpyright to `standard` mode (was `basic`); 0 errors.
- **Sprint 5: Error Handling Foundation** — Replaced 20 silent `except Exception` blocks with specific exception types and logging across auth, websocket, frontend, and parser modules (improves debuggability in production). Added guards against quantity underflow in `ItemRepo.remove_from_room()` (now raises `ConflictError` instead of silently deleting).
- Ambiguous `examine`/`inspect`/`x` targets now defer to `InventoryService`'s numbered disambiguation prompt (`disambig_pending` + choice number) instead of blocking at parse time with a plain "Perhaps you meant" list — matching `take`/`drop` behavior.
- HTMX `POST /command` now calls `CommandEngine.handle_command()` (commands were previously not executed).
- WebSocket client connects to `/ws?player_id=…` instead of the non-existent `/ws/game` path.
- Dev seed DB (`test_dbs/`) regenerated from Ashmoore `world_content/world.yaml`; `player-1` now starts at `village_square` with working exits.
- Removed hardcoded tavern/Mira/sword quest seed from `main.py`; empty databases bootstrap from `world_content/world.yaml` via `lorecraft.world.bootstrap`.
- Lobby and game templates use `current_player.username` instead of the nonexistent `name` field.
- Dialogue `choice 1` / numeric replies parse correctly (`choice_index`); bare digits during conversation map to `choice N`.
- HTMX out-of-band swaps for the dialogue overlay (and other panels) now attach `hx-swap-oob` even when partial markup splits attributes across lines.
- Dialogue overlay hides reliably on `bye` / End conversation (no conflicting Tailwind `flex` + `hidden` classes).
- Terminal dialogue nodes (e.g. Mira’s farewell) show their final line in the overlay instead of closing before the text appears.
- `quit` starts the disconnect grace period, notifies the room, and refreshes Here Now for other clients.
- WebSocket disconnect broadcasts feed text and refreshes the player list for roommates.

### Added

- **Sprint 6: Type Safety Foundation** — `CommandHandler` protocol in `types.py` for type-safe command dispatch. All 22 command handlers now use `ctx: GameContext` instead of `ctx: object`, enabling the type checker to verify context usage and catch errors at type-check time rather than runtime. Added `build_game_context()` factory in `game/context.py` for centralized GameContext construction (all entry points: websocket, scheduler, tests). Added TypedDict schemas for WebSocket and API payloads: `WsFeedAppend`, `WsStateChange`, `WsPlayerLeft`, `WsNarrative`, `ApiStatusResponse`.
- **Sprint 5: Error Hierarchy** — `lorecraft/errors.py` with `GameError` base class (machine-readable error codes) and five domain-specific exceptions: `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError`. Enables typed error handling, analytics tracking, and error-based testing. Comprehensive unit tests in `tests/unit/test_errors.py`.
- `services/scheduler.py` — `SchedulerService`, a persistent DB-backed job scheduler (Sprint 3, roadmap). `schedule(job_type, at_game_epoch, payload)` persists a `ScheduledJob` row; on every `TIME_ADVANCED` tick it marks due jobs `dispatched` and emits `GameEvent.SCHEDULED_JOB_DUE` for each so owning subsystems (combat, NPC movement, delayed world effects) can react without the scheduler knowing any game rules. `cancel(job_id)` marks a pending job cancelled. Wired into `AppState.scheduler` / `main.py` alongside the clock runner and NPC scheduler.
- `models/scheduler.py` — `ScheduledJob` table (`job_type`, `due_at_epoch`, `status`, `payload`, `created_at`), registered in `db.GAME_TABLE_MODELS`.
- `repos/scheduler_repo.py` — `SchedulerRepo.due(current_epoch)` for querying pending jobs at or before a game epoch.
- Graphify actually connected to the dev workflow: `make install-hooks` previously pointed `core.hooksPath` at a `.githooks/` directory that didn't exist. Added `.githooks/post-commit` (refreshes `graphify-out/graph.json` after each commit) and a Claude Code `SessionStart` hook (`.claude/settings.json` + `.claude/hooks/session-start.sh`) so web sessions get the graph refreshed automatically. `scripts/graphify-refresh.sh` now skips gracefully (exit 0) instead of failing when the `graphify` binary isn't installed.
- Item `aliases` (YAML/model/loader/validator) so players can refer to an item by a nickname sharing no words with its name (e.g. "blade"/"shortsword" for Rusty Iron Sword); wired through `GameContext.get_visible_entities()`/`get_inventory()` for parser fuzzy resolution and `ItemRepo` room/inventory search.
- Context-aware `help`: generated from real command metadata (`CommandDefinition.help_text`, `CommandRegistry.all_commands()`) instead of a hardcoded string; varies by dialogue (social + global only), combat (`NOT_IN_COMBAT`-gated commands drop out), and `Room.disabled_commands`.
- `use <item> [on/with <other>]` + `InventoryService.use_item()` — wires the previously-orphaned `Item.usable_with` field into gameplay; combining two items whose `usable_with` lists reference each other emits `GameEvent.ITEM_USED`. Added a `cage_key`/`cage_lock` `usable_with` example to `world_content/world.yaml`.
- `GameContext.parsed_command` — the dispatch loop now stashes the current `ParsedCommand` on context before invoking a handler, so handlers can read secondary roles (e.g. `use X on Y`, `give X to Y`) via `command_patterns.py` helpers instead of only the single noun string.
- `give <item> to <name>` + `InventoryService.give_item()` — hands a carried item to an NPC in the room and emits `GameEvent.ITEM_GIVEN`.
- `unlock <direction>` / `lock <direction>` + `MovementService.unlock()`/`lock()` — persist `Exit.locked` (while carrying `key_item_id`) so an exit unlocked once no longer needs the key for later movement, including by other players.
- `NpcRepo.find_in_room()` — shared NPC name lookup used by `talk` and `give`.
- `lorecraft.world.bootstrap` — YAML-driven empty-DB import and configurable dev player seeding.
- Config env vars: `LORECRAFT_WORLD_YAML_PATH`, `LORECRAFT_SEED_PLAYER_ID`, `LORECRAFT_SEED_PLAYER_USERNAME`, `LORECRAFT_SEED_PLAYER_START_ROOM`.
- NPC (Mira), dialogue tree, and sample quest in `world_content/world.yaml` for Ashmoore playtesting.
- Dialogue overlay and quest tracker partials for the HTMX game UI (OOB swaps on talk/quest updates).
- `dialogue_panel_state()` — rebuilds overlay content from persisted dialogue flags (node text and choices).
- `ConnectionManager.is_connected()` and Here Now presence from DB room occupancy plus live WS status.
- Here Now labels: online (green), grace **(Reconnecting…)**, away/idle (grey, e.g. `Idle 2h4m`).
- Dev `player-2` seeded for multi-player testing; `?player_id=` overrides the lobby cookie.
- World clock SSR in the game header; WS client handlers for `time_update` and `clock_tick`.
- Integration tests for HTMX command dispatch, dialogue choices, farewell nodes, and `bye` (`tests/integration/test_frontend_command.py`).
- Unit tests for world bootstrap, dialogue panel state, player presence, OOB markup, and `choice` parsing.

### Changed

- `import_world.py` wipes NPCs, dialogue trees, and quests on `--fresh`; seeds `player-1` and `player-2`; resets players on fresh import.
- `start.sh` copies `test_dbs/` seed databases again (not `game.db`).
- Admin and integration tests updated for Ashmoore room IDs (`village_square`, `wandering_crow_inn`, `market_stalls`, etc.).
- Key gallery disambiguation fixture exit link updated for Ashmoore topology (`blacksmith_forge`).
- Dialogue overlay styles NPC lines as a quoted blockquote; End conversation is a numbered option matching other choices.
- Removed duplicate panel wrapper IDs in `game.html` (inventory, Here Now) so OOB swaps target a single element.

## [0.2.0] - 2026.06.29

### Fixed

- `take`/`drop` item matching now singularizes item names as well as player input, so plural queries like `take herbs` match items named `Bundle of Dried Herbs`.
- Inventory command text and all inventory panels now group duplicate carried items with `[quantity]` prefixes (e.g. `[2] Worn Copper Coin`).

### Added

- Integrated Lorecraft parser v1 (`lorecraft_parser_v1`): semantic roles, prepositions, adjectives, quantities, quoted strings, phrasal verbs, compound commands (`;`), optional `GameContext` fuzzy resolution with disambiguation, in-character parse errors, and diagnostic tracing.
- Added `parse_command`, `ParseResult`, `diagnose_command`, and `registry_verb` helpers in `src/lorecraft/game/parser.py`; kept `parse()` as a backward-compatible wrapper for legacy callers.
- Added `GameContext.get_visible_entities()` and `GameContext.get_inventory()` for parser entity resolution.
- Wired `CommandEngine` and the HTMX frontend command path through `parse_command` (including compound execution and suggestion messages).
- Added comprehensive parser tests in `tests/game/test_parser_comprehensive.py`.
- Added offline parser diagnostic CLI at `tools/parser_diag.py`.
- Added `docs/command_parser.md` — parser output model, command pattern taxonomy, and handler integration guidance.
- Added `src/lorecraft/game/command_patterns.py` — `CommandPattern` enum, verb mapping, and typed role helpers (`speech_roles`, `transfer_roles`, `container_roles`, …).
- Added pattern-grouped parser tests in `tests/game/test_parser_patterns.py` and `tests/unit/test_command_patterns.py`; shared fixture in `tests/game/conftest.py`.
- Added `docs/parser_and_commands.md` — command authoring guide, item disambiguation layers, and Key Gallery testing notes.
- Added `key_gallery` room (Red Key, Iron Key, Rusty Iron Key, Steel Key, Cage Key, Cage Lock, Rusty Iron Sword, Red Rose) in `world_content/world.yaml` for in-game disambiguation testing; pytest helpers live in `tests/fixtures/disambig_fixtures.py`.
- Added `tests/unit/test_inventory_disambiguation.py` for shortened-name matching and numbered ambiguity prompts.
- `take`/`drop` object ambiguity now defers to `InventoryService` numbered disambiguation instead of blocking at parse time.
- `take` and `drop` now accept quantity, all, and indexed selectors: `take 2 coin`, `take 2 coins`, `take all coin`, `drop all coin`, and `take 2.coin` (second matching instance).
- Room `look` text and web room panel now group duplicate visible items with `[quantity]` prefixes, matching inventory display.
- HTMX inventory panel now refreshes when picking up another copy of an already-carried item (fixed set-based change detection).
- Replaced the primary player web UI with the HTMX + Alpine.js + Jinja2 server-rendered template (lorecraft_frontend_starter).
- Added `src/lorecraft/web/frontend.py` — lobby, game screen, command POST (with OOB updates), and all partial endpoints (`/partials/*`).
- Added `templates/` (base, game, lobby, partials for feed/room/inventory/minimap/players) and `static/css+js`.
- Wired Jinja2Templates + StaticFiles mount in `main.py`; root `/` now redirects to new lobby.
- Lobby provides player selector using existing seeded players; game screen SSRs panels using real repos + audit log for feed.
- `/command` executes via core CommandEngine/GameContext, returns feed items + OOB swaps for changed panels, and broadcasts `state_change` via ConnectionManager.
- Added `recent_for_room` / `recent_for_actor` + `get_exits_with_names` + `list_all` helpers to support the UI.
- Old vanilla client assets preserved under `/static` (flat) for backward compat during transition.
- Command processing, feed (audit-backed), movement, inventory, and minimap exits now work via the new UI.

### Added (Phase 4 — NPCs & Quests)

- Added `models/dialogue.py` — `DialogueTree` SQLModel table storing full dialogue tree as a JSON blob.
- Added `repos/dialogue_repo.py` and `repos/quest_repo.py` — data access for dialogue trees and quest progress.
- Added `npc/dialogue.py` — `DialogueService` with `start`, `choose`, and `end` methods; flag-gated choices; side effects (`set_flags`, `clear_flags`, `give_item`, `start_quest`, `end_dialogue`); dialogue state stored in `player.flags`.
- Added `npc/scheduler.py` — `NpcScheduler` subscribes to `HOUR_CHANGED` and moves NPCs according to their schedule.
- Added `services/quest.py` — `QuestService.check_progression` subscribes to `ITEM_TAKEN`, `PLAYER_MOVED`, and `ITEM_DROPPED`; evaluates stage conditions (`flag_set`, `flag_clear`, `room_visited`, `item_in_inventory`); advances or completes quests and awards rewards.
- Added `commands/social.py` — `talk`/`speak`, `choice`/`choose`, `say`, `bye`/`farewell`/`goodbye` commands.
- Extended world YAML validator and loader to accept `npcs`, `dialogue_trees`, and `quests` sections.
- Seeded starter world with Mira the Innkeeper (NPC), her dialogue tree, and a sample "Lights in the Square" quest.
- Added dialogue overlay to game client — appears with NPC name, node text, and clickable choice buttons; hides when dialogue ends; "End conversation" button closes via `bye` command.
- Added live quest tracker to game client right panel — shows active quest titles and current stage descriptions; updates on quest start, stage advance, and completion.
- Added `quest_repo` and `dialogue_repo` fields to `GameContext` (optional, backward-compatible).
- Added 14 new unit tests in `test_dialogue.py` and `test_quest_service.py`.

### Added (Phase 6 — Admin Tools)

- Added Phase 6 admin tools: JWT auth, role-based REST API, and admin push WebSocket at `/admin/ws`.
- Added `admin/auth.py` — PBKDF2-HMAC-SHA256 password hashing, PyJWT access/refresh token issue and verify, role hierarchy (`observer < moderator < world-builder < superadmin`), FastAPI dependency shortcuts.
- Added `admin/api.py` — admin router with endpoints for player management (list, state, teleport, flags, freeze/unfreeze), audit log query, world rooms/items/NPCs, changeset lifecycle (create, scan, promote), clock control (pause/resume, time-ratio, weather), and admin account management.
- Added `admin/websocket.py` — per-connection async queue, `AdminBroadcaster` fan-out, JWT auth via `?token=` query param.
- Added `admin/broadcaster.py` — `AdminBroadcaster` for safe push from synchronous EventBus handlers to async WS clients.
- Added `world/versioning.py` — `VersioningService` with changeset CRUD, conflict scanner (broken exits, displaced players, held items), and atomic promotion with `WorldMeta.schema_version` bump.
- Added `models/admin.py` — `AdminUser` SQLModel table with role and revocation support.
- Added `state.py` — `AppState` dataclass extracted from `main.py` to break circular imports.
- Added admin web panel at `/admin` — single-file SPA (Terminal Gothic styling) with login, live WS push, and tabs for all admin sections.
- Added Textual TUI (`admin/tui/app.py`) as an optional `admin-tui` dependency group; F1–F5 screen routing; credential storage at `~/.config/lorecraft-admin/credentials.json`.
- Added `LORECRAFT_ADMIN_JWT_SECRET`, `LORECRAFT_ADMIN_SEED_USERNAME`, `LORECRAFT_ADMIN_SEED_PASSWORD`, `LORECRAFT_ADMIN_SEED_ROLE` config env vars.
- Added `pyjwt>=2.9.0` as a production dependency.
- Added 39 new tests across `tests/unit/test_admin_auth.py`, `tests/integration/test_admin_api.py`, and `tests/integration/test_versioning.py`.

### Changed

- Updated `start.sh` to create `.venv` when missing and install Lorecraft editably with the admin TUI extra when dependencies are absent or incomplete.
- Excluded `admin/tui` from basedpyright checks (optional Textual dependency not installed in base venv).
- Extracted `AppState` from `main.py` into `lorecraft/state.py` to allow admin router import without circular dependency.
- Seeded `WorldMeta` singleton in `_ensure_starter_world` to support changeset promotion.

### Verified

- `.venv/bin/python -m pytest` passes with 89 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes (TUI excluded).

## [0.1.0] - 2026-06-27

### Added

- Added `docs/status.md` to track implementation progress against the architecture overview.
- Added initial `src/lorecraft` package scaffold for the multiplayer text adventure engine.
- Added environment-driven settings in `lorecraft.config`.
- Added core game primitives:
  - `GameContext` for per-command execution state.
  - `TransactionContext` and transaction source types.
  - `GameEvent`, `Event`, and synchronous `EventBus`.
  - `RuleEngine` and `RuleResult`.
  - `CommandRegistry`, command scopes, command conditions, and condition evaluation.
  - `ParsedCommand` parser with direction aliases, verb aliases, and article stripping.
  - `CommandEngine` dispatch scaffold.
  - `ConnectionManager` for WebSocket-style player connections and room broadcasts.
- Added pytest-based unit test structure under `tests/unit`.
- Added placeholder `tests/integration` and `tests/simulation` directories for future database and WebSocket coverage.
- Added `make test` for focused local verification.
- Added repository agent instructions in `AGENTS.md`, with `CLAUDE.md` importing them for Claude Code compatibility.
- Added guidance to keep `CHANGELOG.md` current and synchronize package versions in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Added guidance to aim for type hints in new and changed Python code while allowing pragmatic omissions.
- Added a `dev` optional dependency group for local development tools: BasedPyright, pytest, and Ruff.
- Added pre-commit configuration for file hygiene, secrets detection, Ruff, YAML linting, Prettier for JavaScript/TypeScript files, and BasedPyright push checks.
- Added SQLModel table definitions for world, player, session, quest, combat, versioning, interaction, and audit persistence.
- Added database bootstrap helpers for creating game tables and audit tables in separate SQLite databases.
- Added shared structural typing aliases and protocols for JSON payloads, WebSocket connections, command contexts, players, and rooms.
- Added thin SQLModel repository wrappers for players, rooms, items, NPCs, and audit events.
- Added repository unit tests covering core game model and audit event round trips.
- Added FastAPI service wiring with startup table initialization and shared app state.
- Added `/health` and `/ws` endpoints for service health checks and player command WebSocket sessions.
- Added direct ASGI integration tests for lifespan startup, health checks, WebSocket connection, and command dispatch.
- Added audit recording for blocked and executed commands.
- Added meta commands for `help` and `quit`.
- Added movement commands and `MovementService` room transitions.
- Added WebSocket movement integration coverage for persisted room changes.
- Added a minimal browser client harness with WebSocket connection, message routing, state tracking, text feed, command input, and room/session status display.
- Added static asset routes for the browser client.
- Added starter world bootstrap for empty databases so the browser harness can connect as `player-1`.
- Added browser client smoke coverage for the served HTML, CSS, and JavaScript contract.
- Added repo-local seed test database files that `start.sh` copies into `/tmp` for browser harness startup.
- Added a persistent world clock runner with startup fast-forwarding and boundary events.
- Added weather and season state transitions driven by day changes.
- Added inventory inspection and item movement commands for `look`, `examine`, `take`, `drop`, and `inventory`.
- Added YAML world validation and import helpers for rooms, exits, items, and room item placement.
- Added a Tailwind-powered world UI layout with minimap, status, feed, inventory, and quest panels.
- Added SVG minimap rendering for visited rooms and fog-of-war adjacent rooms.
- Added structured WebSocket UI snapshots for room, visited-room, inventory, and time state.
- Added save/load commands and `SaveSlotService` for player-owned state.
- Added WebSocket disconnect grace, reconnect session reuse, reconnect sync payloads, and grace-expiry state handling.
- Added system audit events for disconnect, reconnect, and expired grace transitions.

### Changed

- Documented the project package layout as `src/lorecraft` in `docs/architecture.md`.
- Configured pytest to import package code from `src`.
- Added `sqlmodel` as a production dependency for the persistence layer.
- Added a BasedPyright project configuration for the `src` package and local `.venv`.
- Replaced broad `Any` annotations in the command, event, rule, connection, and model layers with narrower protocols and JSON types.
- Preserved full SQLAlchemy database URLs while retaining existing SQLite path handling.
- Added FastAPI and Starlette as production dependencies for the service layer.
- Tightened `GameContext` to use concrete repository, model, event bus, and connection manager types.
- Extended `CommandEngine` to commit state changes, write audit events, and flush queued domain events.
- Packaged the browser client assets with the Python package.
- Declared PyYAML as a production dependency for world authoring imports.
- Updated the browser client router to render inventory and minimap state from structured updates.
- Added SQLite compatibility handling for the save-slot `visited_rooms` column.

### Verified

- `.venv/bin/python -m pytest` passes with 49 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes.
