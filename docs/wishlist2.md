# Modern MUD Engine Design — Quick Reference

A synthesized design guide distilled from comparative analysis of Evennia, Ranvier, CoffeeMud, EmpireMUD, and live flagship games (Aardwolf, Discworld, BatMUD, Materia Magica, Alter Aeon).

## Core Design Philosophy

**Tiny core + everything else is a plugin.** The engine provides infrastructure; gameplay is layered on top as optional modules. This enables independent evolution, content versioning, and reusability across worlds.

**Hybrid entity model:** Compact relational core for identity/lifecycle; typed components for capabilities; plugin-owned schemas for specialized subsystems. Avoid deep inheritance; use flat entities with composable components.

**Data-driven definitions, versioned in Git.** World content (prototypes, areas, quests, dialogue) lives in YAML/JSON and rolls out via migrations. Runtime state (character position, inventory, quest progress) lives in the database.

**Event-driven subsystems.** Combat, quests, weather, economy publish events; systems subscribe without direct coupling. Use a small, named event taxonomy (not one-off strings everywhere).

## Architecture Layers (Six Planes)

```
[Telnet/WebSocket/REST Gateways]
           ↓
[Session & Identity Service]
           ↓
[Command Parser → Intent Resolver → Permission Engine → Simulation Orchestrator]
           ↓
[World | Combat | Quest | Economy | Social | Scheduling]
           ↓
[PostgreSQL (Primary) | Cache/Search | Event Outbox]
```

- **Gateways** normalize protocols (telnet, websocket, REST) into one session API.
- **Session service** owns accounts, logins, characters, capabilities.
- **Command pipeline** parses → resolves → authorizes → validates → executes → emits → renders.
- **Simulation services** are independent, event-driven plugins. No direct coupling.
- **Storage** is split: Git for definitions, DB for runtime state, cache for derived data.

## Critical Core Features (Must Ship)

| Feature | Why | How |
|---------|-----|-----|
| Unified entity model | Everything (rooms, NPCs, items, vehicles, quests) shares one identity | Use stable `entity_id` with component bags; avoid inheritance |
| Room + area + optional coordinates | Preserves room clarity while enabling maps and overland | Named exits + optional local coords per area; don't force one topology |
| Command-to-intent pipeline | Keeps parsing, permission, simulation, presentation separate | Parse → intent → authorize → execute in transaction → emit events → render |
| Explicit permissions & locks | Builder safety and live-ops sanity | Capability checks + readable lock DSL; log denied actions |
| Quest framework | Hand-authored quests become maintainable; non-coders can build | State machines composed from reusable goal/reward nodes |
| Effects, traits, derived stats | Buffs, debuffs, gauges, counters, computed values work consistently | Keep traits/effects data-driven; compute stats via dependency graphs |
| Multi-protocol networking | Text games need browser, telnet, accessibility, automation clients | Normalize input/output to one session API; keep rendering adapters separate |
| Accessibility-first UX | Good text games should work for screen readers and low-bandwidth clients | Semantic output channels, configurable verbosity, no essential info hidden in color |
| Content in Git, state in DB | Safe updates and reproducible deployments | Immutable definitions roll out via migrations; live state in DB |

## Recommended Tier-1 Features (Enable Retention)

- **Long-horizon meta-progression** — remort, class stacking, tiering, prestige goals
- **Player-built or player-modified world** — roads, outposts, cabins, cities, territorial claims
- **Housing, shops, civic identity** — social permanence matters more than combat complexity
- **Profession-based crafting** — recipe graphs, material properties, enhancement passes
- **Dynamic area behaviors** — respawn, ecology, events are content decisions, not engine constants
- **Rich client features** — map pane, vitals bars, channel tabs, structured data over OOB
- **External integrations** — Discord relay, RSS feeds, cross-game chat
- **In-game builder/admin tools** — safe OLC, content operations, live edit/preview/publish

## Recommended Tier-2 Features (Advanced)

- **Instanced adventures** — private group dungeons on a persistent world
- **Knowledge/research systems** — libraries, rumor archives, clue synthesis
- **Vehicles & ships** — mobile spaces create memorable travel and trade
- **World-time, weather, tides** — sparse, meaningful simulation; avoid tick spam
- **AI-assisted NPCs & content** — dialogue, flavor, assistance; never core logic
- **Procgen with constraints** — randomized quest objects, shuffled clues, parameterized dungeons
- **Deep social institutions** — guilds, contracts, elections, newspapers, city law
- **Patch-note & roadmap discipline** — public development cadence, change tagging

## Data Model Outline

**Minimal entity schema** (YAML):
```yaml
entity:
  id: "ent_01J..."
  kind: "npc|room|item|player|vehicle|building"
  template_id: "mob.goblin.v2"
  location_id: "room.frontier.keep"
  owner_account_id: null
  components:
    description: { short: "...", long: "...", keywords: [...] }
    stats: { level: 12, hp: 84, ... }
    ai: { brain: "combat.skirmisher", leash_radius: 6 }
    loot: { table_id: "loot.goblin.common" }
```

**Runtime relational core** (PostgreSQL):
```sql
account (username, password_hash, role_flags, status)
character (account_id, name, current_room_id, progression_json)
entity_instance (template_id, kind, room_id, owner_id, state_json)
component_state (entity_id, component_key, state_json)
quest_state (character_id, quest_key, status, progress_json)
scheduled_job (due_at, topic, payload_json)
event_outbox (topic, aggregate_id, payload_json)
```

**Split storage:**
- **Git:** Engine code, plugins, prototypes, room/area definitions, quest catalogs, dialogue, help, migrations, tests, seed data
- **DB:** Accounts, characters, live entity instances, inventories, effects, quest progress, claims, buildings, shops, guilds, mail, analytics
- **Cache:** Pathfinding, rendered maps, search indexes, compiled scripts

## Plugin API Pattern

```python
class Plugin:
    key = "crafting_frontier"
    version = "1.3.0"
    requires = ["economy>=1.0", "items>=1.0"]

    def setup(self, api):
        api.migrations.register(self.version, self.migrate)
        api.components.register("recipe_book", RecipeBookComponent)
        api.commands.register(CraftCommand)
        api.intents.register("craft.item", CraftIntentHandler)
        api.events.subscribe("entity.gathered", self.on_gathered)
        api.scheduler.register_topic("recipe.restock")
        api.permissions.register("craft.use_station")

    def start(self, api):
        api.scheduler.ensure_recurring(
            dedupe_key="frontier_daily_restock",
            topic="recipe.restock",
            cron="0 5 * * *"
        )

    def stop(self, api):
        api.events.unsubscribe_owner(self.key)
        api.commands.unregister_owner(self.key)
```

Small manifest, clear capabilities, explicit migrations, explicit hooks, limited extension points. Plugins should register (commands, intents, event consumers, prototypes, jobs, REST endpoints, builders' forms, migrations) and cleanly unload.

## Event Taxonomy (Keep Small)

Good starter set: `session.connected`, `input.received`, `command.parsed`, `intent.resolved`, `security.denied`, `entity.created`, `entity.moved`, `combat.damage_applied`, `effect.applied`, `quest.progressed`, `channel.published`, `job.due`, `plugin.loaded`, `plugin.unloaded`, `llm.requested`, `llm.responded`.

Resist one-off plugin-specific event strings everywhere.

## Security & Permissions (Three Layers)

1. **Static capabilities:** `builder.zone.edit`, `guild.bank.withdraw`, `admin.plugin.reload`
2. **Object-scoped checks:** ownership, faction, containment
3. **Contextual locks:** "Can they do it here, now, under these conditions?"

Result: "Can this role?", then "Can this actor do it to this thing?", then "Can they do it here?" Keep audit tables for builder actions, economy, punitive actions, migrations.

## Networking & Clients

Ship telnet + websocket + REST API first. Add structured OOB payloads (GMCP-style) early even if full protocol support comes later.

- **Telnet:** compatibility
- **WebSocket:** browser play, modern clients
- **REST:** dashboards, patch tools, maps, moderation, account flows
- **OOB/GMCP:** structured data for clients that support it

Render the same narrative prose for all clients, but emit JSON payloads so clients can parse, route, and enhance.

## AI Integration (Keep on the Edge)

- **Do use AI for:** dialogue drafting, lore summarization, codex search, builder assistance, moderation triage, localization drafts
- **Never use AI for:** authoritative game state, combat math, quest outcomes, persistence

Keep AI asynchronous and non-authoritative. Example: Evennia's optional LLM NPC contrib (async client, treats AI as dialogue feature). Restrict general scripting to trusted plugins only; use CEL/Starlark expressions for formulas and predicates.

## Operational Checklist

✅ **Builder/admin tools:** zone editors, prototype browser, diff preview, restore-from-version, safe publish, help authoring, permission delegation, economy dashboards, moderation.

✅ **Analytics:** command latency, room heatmaps, quest funnels, item sink/source, economy inflation, retention cohorts, builder activity, accessibility usage.

✅ **Testing:** transcript tests for commands, property tests for parsers, simulation tests for combat, migration tests, load tests, snapshot tests, plugin contract tests.

✅ **Deployment:** stateless gateways, separate simulation/scheduler/admin APIs, PostgreSQL + cache, migration-aware deploys, audit logging, backup/restore procedures.

## Implementation Priorities

**Core (6–9 months):** Accounts, sessions, telnet/websocket, room graph, entities, movement, inventory, permissions, logging, migrations, event outbox, scheduler.

**V1 (8–12 months):** Combat, effects, quests, builder tools, map support, help, commands, crafting, economy, channels, admin UI, accessibility.

**V2 (9–15 months):** Housing, shops, institutions, overland + instances, player-built world, analytics, AI edge, procgen, simulation.

## Top Reference Sources

| Project | Key Resources |
|---------|---|
| **Evennia** | Docs, API, protocol settings, contribs, releases |
| **Ranvier** | GitHub, release notes, community bundles, scripting/quest/NPC docs |
| **CoffeeMUD** | GitHub, guides, CHANGES, forums |
| **EmpireMUD** | Official site, patch notes, adventures page, GitHub beta notes |
| **Aardwolf** | Wiki recent changes, remort/tier/help pages, news |
| **Discworld** | Recent developments blog, architecture page, creator manuals |
| **BatMUD** | Help/client pages, Steam community, forums |
| **Materia Magica** | Game guide, news hub, patch archives |
| **Alter Aeon** | Help index, class guide, DClient page, crafting, forums |

## Key Takeaways

1. **World permanence, social institutions, craft, and client quality are co-equal with combat.** The most durable MUDs invest in them equally.

2. **Builder safety and content operations are product features, not afterthoughts.** Invest in tools early.

3. **Protocol abstraction is not optional once you move past telnet.** Design for multiple clients from day one.

4. **Data-driven content + plugin boundaries = safe updates and independent evolution.** This is the strongest pattern across all surveyed engines.

5. **Live-ops and public communication matter.** Visible patch notes, status updates, and roadmaps build credibility.

6. **Accessibility is not a feature — it's infrastructure.** Screen readers, reduced motion, configurable verbosity, and semantic output should be designed in, not bolted on.

7. **Long-horizon progression systems (remort, tiering, prestige) retain players better than combat complexity alone.**

8. **Do not pre-build multi-host scale. Measure first, then choose the next tier.** Single-process single-VPS is fine until ~50 concurrent players.

---

_Distilled from analysis of Evennia, Ranvier, CoffeeMUD, EmpireMUD, Aardwolf, Discworld, BatMUD, Materia Magica, and Alter Aeon (2026-07). See `wishlist.md` for Lorecraft-specific ideas._
