# GameContext god-node audit

**Date:** 2026-07-10
**Question:** Graphify reports `GameContext` as the top god node (370 edges). Is this poor design?
**Verdict:** **No — it is a per-command parameter object with high fan-in by design.** The
smell audit came back mostly clean; two mild findings are worth tracking (below), neither urgent.
**Scope:** read-only analysis at commit `b2044a9` (v0.55.3); no code changes made.

---

## What GameContext actually is

`src/lorecraft/engine/game/context.py:48` — a per-command dataclass bundling:

- **Actor state:** `player`, `room`, `clock`
- **Repos (6):** `player_repo`, `room_repo`, `item_repo`, `stack_repo`, `npc_repo`, `audit`
- **Services (5):** `item_location`, `ledger`, `meters`, `effects`, plus `bus`/`manager`
- **Infrastructure:** `session`, `transaction`, `session_id`, `rng`, commit/rollback callbacks
- **Output accumulation:** `messages`, `room_messages`, `arrival_messages`, `chat_echoes`,
  `chat_outbox`, `updates`, `pending_events`, `pending_deliveries`

It is constructed by exactly **one factory**, `build_game_context()`, used by both real entry
points (`main.py`'s `/ws` command loop and `webui/player/frontend.py`'s `POST /command`), so
wiring cannot drift between them. It lives for one command, then dies.

## Why 370 edges is correct, not a smell

The edges are fan-**in**: 58 files under `src/` reference it (every feature's
`commands.py`/`service.py`, engine command plumbing, plus tests). The alternative to one
context parameter is every handler taking 8–10 separate arguments — that spreads identical
coupling across every signature and turns "add a dependency" into a repo-wide diff.

A hub with **one construction site, no stored references, per-command lifetime, and no
behavior beyond output collection and parser hooks** is the healthy form of a god node: a
deliberate seam. Note the other top god nodes are the same kind of intentional hub —
`CommandEngine` (265), `EventBus` (246), `Player` (238).

## Smell-by-smell results

| Smell checked | Finding |
|---|---|
| `cast(GameContext, ctx)` in production | **Zero.** One test-only sentinel (`tests/unit/test_condition_error_handling.py:27`, `cast(GameContext, object())`). The AGENTS.md ban is holding. |
| Services storing ctx (`self.ctx = ...`) | **Zero.** Every service receives it per-call; no long-lived coupling. |
| Deep reach-through chains (3+ hops) | Essentially none. Worst is `ctx.player.flags.get(...)` (24×) — a shallow dict read on the actor model, already slated for the scripting-engine A2 flags rename. |
| Dead/unused fields | None. Usage is dominated by `ctx.say` (268×) and `ctx.player` (234×) with a long tail; every field has real consumers. |
| Circular imports | Handled explicitly and documented in-file: TYPE_CHECKING-only imports for `ItemLocationService`/`LedgerService`/`MeterService`/`EffectService`, real imports inside the factory. 15 of the 58 importing files are themselves hint-only importers. |
| `ctx.game_engine` (no such field) | False positive — `features/hunts/service.py` receives a `SchedulerEventContext` there, properly `isinstance`-guarded. |

## Genuine findings (mild, keep on the radar)

### 1. Raw `ctx.session` leakage — 97 uses across ~26 files

Feature services construct their own repos ad hoc (`EconomyRepo(ctx.session)` appears three
separate times inside `features/economy/service.py` alone) and thread `ctx.session` into
engine services per-call (`ctx.meters.get(ctx.session, ...)`, skills lookups, encumbrance).
The style is at least *consistent*, but it means:

- features bypass the repos already wired into the context, and
- the raw SQLModel `Session` is a de facto public API — any future change to transaction
  handling has these ~97 sites as its blast radius.

Heaviest users: `fatigue/service.py` (15), `economy/service.py` (13),
`inventory/service.py` (10), `bank/service.py` (10), `trading/service.py` (8).

### 2. GameContext is accreting a second responsibility

The sprint-by-sprint additions (`chat_echoes`/`chat_outbox` in Sprints 45/52,
`pending_deliveries` in Sprint 47, `arrival_messages`) are all **response accumulation** —
distinct from the original **dependency bundle**. If growth continues, the natural cut is to
split a `CommandOutput`/`CommandIO` object out of it. At ~25 well-documented fields it has
not crossed that line yet; this is a "next time it grows" trigger, not a task.

## Methodology

- Graphify `god_nodes` / `get_node` / `get_neighbors` for degree ranking and edge direction.
- `grep` classification of all 58 importing files: runtime vs `TYPE_CHECKING`-only imports.
- Pattern scans: `cast(GameContext`, `self._?ctx [:=]` (stored context), `ctx\.<a>\.<b>\.<c>`
  (deep chains), `ctx.session` (repo bypass), and per-field usage frequency across
  `features/` + `commands/`.
