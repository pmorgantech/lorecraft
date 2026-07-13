# Trade & Economy — Design

> **Status:** Implementation-ready design (2026-07-03; revised same day for Tier 1 alignment).
> Roadmap **[Sprint 28](roadmap.md#sprint-28--trading--economy)** (see [`roadmap.md`](roadmap.md)).
> Currency, vendor shops, regional pricing, player-to-player trade, and banks.
>
> **Tier 1 dependencies (build first — [`engine_core.md`](engine_core.md)):** the **ledger +
> atomic exchange** (`CoinBalance`, `LedgerService.execute_exchange`, engine_core §3.7,
> [Sprint 20](roadmap.md#sprint-20--ledger--atomic-transfer)) — there is **no `Player.coins`
> column**; the **item location model** (§3.2 — this feature registers the `shop` and `escrow`
> holder types); the **skill-check helper** (§3.6) for barter/appraise. Every money or item
> movement in this doc is one `execute_exchange` call; this feature never mutates balances or
> stacks directly.
>
> **Pillars this serves** (see [`wishlist.md`](wishlist.md) → *Design pillars*): **Trading** is
> pillar #2, and the signature pairing is *transit network = trade network* — regional price
> differences only create gameplay because moving goods between towns costs time, fare, and
> risk ([`transit_systems.md`](transit_systems.md)). Banks and carried-vs-banked money also
> underpin the death penalty ([`death_resurrection.md`](death_resurrection.md)).

---

## 1. Where we build from (existing primitives)

- **Ledger** (engine_core §3.7) — carried money is `CoinBalance("player", player_id)`,
  created lazily at first credit. Items are `ItemStack`s (§3.2); there is no inventory list.
- **`Item`** — has `tradeable`; **no** `value`. Add a base `value`; final price derives from
  `value` × `quality` (from [`inventory_equipment.md`](inventory_equipment.md)) × regional/skill
  modifiers.
- **`NPC`** — has `loot_table`; add optional vendor/shop config so an NPC can buy/sell.
- **`Room.area_id`** — regional pricing keys off area (or per-shop overrides).
- **`WorldClock`** — supply/demand restock runs on `TIME_ADVANCED` via `SchedulerService`.
- **`PlayerStats.skills`** — `bartering` skill flexes prices ([Sprint 24](roadmap.md#sprint-24--traits--skills) traits/skills).
- **Reputation/standing** ([Sprint 24](roadmap.md#sprint-24--traits--skills)) — flexes prices and unlocks stock.
- **Transaction/event lifecycle** — every purchase/sale/trade is one transaction, audited.

---

## 2. Currency model

Two balances, deliberately split so death and robbery have stakes. **Both are ledger holders**
(engine_core §3.7) — no money columns anywhere:

| Money | Ledger holder | Risk |
|---|---|---|
| **Carried** | `CoinBalance("player", player_id)` | spendable anywhere; **at risk** on death/robbery |
| **Banked** | `CoinBalance("bank_account", account_id)` | safe; only accessible at a branch (§9) |

```python
class BankAccount(SQLModel, table=True):     # identity/ownership only — balance lives in the ledger
    id: str = Field(primary_key=True)        # uuid4
    player_id: str = Field(foreign_key="player.id", unique=True, index=True)
```

This feature registers the `bank_account` and `shop` holder types (and `escrow`, §8) with the
Tier 1 holder registry. A corpse's dropped coins are `CoinBalance("container", corpse_instance_id)`
([`death_resurrection.md`](death_resurrection.md)) — same mechanism, zero special-casing.

Single currency ("coins") for now; multi-currency is a non-goal (§13). Coins are a ledger
scalar, not inventory items, so they don't consume carry weight.

---

## 3. Item value & pricing

Base `value: int` on `Item`. The **price a shop quotes** is derived at runtime, never stored:

```
buy_price  = round(base_value × quality_mult × region_mult × demand_mult × (1 - barter_discount) × (1 - rep_discount))
sell_price = round(buy_price × sell_ratio)      # sell_ratio ~0.4–0.6; shops buy low
```

- `quality_mult` — common→legendary from [`inventory_equipment.md`](inventory_equipment.md).
- `region_mult` — §5 regional pricing.
- `demand_mult` — §6 supply/demand.
- `barter_discount` — from the `bartering` skill ([Sprint 24](roadmap.md#sprint-24--traits--skills)); capped (e.g. ≤ 25%).
- `rep_discount` — standing with the vendor/faction ([Sprint 24](roadmap.md#sprint-24--traits--skills)); capped.

Deriving at runtime (not storing prices) matches the derived-stat rule used across the engine.

---

## 4. NPC vendor shops

A vendor is an `NPC` with a shop config (data-driven; new `Shop`/`ShopStock` tables or a JSON
block on the NPC — tables preferred for querying/restock):

```python
class Shop(SQLModel, table=True):
    id: str = Field(primary_key=True)
    npc_id: str = Field(foreign_key="npc.id", index=True)
    name: str                       # "Saltmarsh General Store"
    buys_categories: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # what it will purchase
    sell_ratio: float = 0.5         # fraction of buy price paid when buying FROM players
    region_mult: float = 1.0        # per-shop price multiplier (overrides area default)

class ShopStock(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    shop_id: str = Field(foreign_key="shop.id", index=True)
    item_id: str = Field(foreign_key="item.id")
    quantity: int                   # finite; restocks on the clock (§6); -1 = unlimited
    restock_to: int = 0             # target quantity on restock
    restock_every_ticks: int = 0    # 0 = no restock
```

Commands (`features/economy/commands.py`):

| Command | Effect |
|---|---|
| `list` / `shop` | show the current room's shop stock with derived buy prices |
| `buy <item> [qty]` | validate stock; coins move player→shop via `execute_exchange`; stock decrements; item `spawn()`s to the player |
| `sell <item> [qty]` | vendor buys (if `tradeable` + category matches, **and not `bound`** — a fail-closed rule); coins move shop→player; the player's stack is `destroy()`ed; stock increments |
| `appraise <item>` | show a value estimate (accuracy scales with `appraisal` via `skill_check`) |

**Money flow (decided):** a shop holds `CoinBalance("shop", shop_id)`, seeded with a
configurable float at world import (via `LedgerService.credit`, audited) and topped back up on
the restock schedule. Buy/sell therefore go through the same conserving `execute_exchange` as
every other flow — and a shop *can* run out of cash for the day, which is a feature (sell your
furs across towns, not all in one). `ShopStock.quantity` is vendor listing state, not stacks:
items materialize as `ItemStack`s only when bought (a `-1` unlimited row never materializes
until purchase).

Buying/selling emits `ITEM_PURCHASED` / `ITEM_SOLD` — new `GameEvent` members (additive
one-line enum entries are the sanctioned core edit for features; the registries handle
everything else).

---

## 5. Regional pricing (the transit–trade pairing)

The core trade loop: **buy low here, sell high there.** Prices vary by place:

- Each area has a default `region_mult`; each `Shop` may override it. Salt is cheap on the coast,
  dear in the mountains; furs the reverse.
- A per-item **regional bias** table lets specific goods be cheap/expensive in specific areas
  (data-driven, in world YAML), so trade routes have character beyond a flat area multiplier.
- Profit exists **because** moving goods costs a ferry/rail fare and time
  ([`transit_systems.md`](transit_systems.md)) — the arbitrage is the reward for mastering the
  network. Without transit cost, regional pricing is free money; with it, it's a game.

This is the one system that most directly ties pillars #1 (exploration — you learn where things
are cheap) and #2 (trade) together.

---

## 6. Supply & demand

Lightweight, clock-driven, emergent:

- Shop stock is finite and **restocks toward `restock_to` every `restock_every_ticks`** via a
  scheduled job.
- `demand_mult` rises as stock is depleted and falls as it's flooded: dumping 50 furs on one
  town tanks the local fur price (temporary), rewarding players who spread sales across the
  network. Bounded to avoid runaway prices.
- Keep it simple: a per-shop-per-item running adjustment, not a full market simulation.

---

## 7. Bartering & reputation

- `bartering` skill (use-based, [Sprint 24](roadmap.md#sprint-24--traits--skills)) improves buy/sell terms within a cap; improves through
  use, fitting the exploration-progression ethos.
- Standing with a vendor/faction unlocks restricted stock and better prices; hostility raises
  prices or refuses service. Reputation is the social spine ([Sprint 24](roadmap.md#sprint-24--traits--skills)) reused here.

---

## 8. Player-to-player trade

A safe two-party handshake (no item/coin loss to bugs or scams-by-disconnect), built directly
on `execute_exchange` (engine_core §3.7 — the escrow shape is **decided** there):

- `offer <item|coins> to <player>` records intent (a `TradeOffer` row: both sides' promised
  coins + stack ids, a TTL) and **moves nothing**.
- `accept` composes **one** `execute_exchange` with both directions as legs. Validation of
  every leg at accept-time *is* the escrow revalidation — if either side no longer holds the
  goods, the whole exchange raises `ConflictError` and nothing moves. Command-lifecycle
  rollback ([Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-)) covers crashes.
- Policy gates run **before** the exchange as fail-closed `RuleEngine` rules (engine_core §2):
  `tradeable`, not `bound`, both players present in the same room, offer not expired.
- A strong simulation-harness target (two real WS clients, concurrent `accept` — exactly one
  succeeds; disconnect mid-trade loses nothing).

---

## 9. Banks

Banks are economy infrastructure **and** the death/robbery safety valve.

- A **bank branch** is an NPC or room feature (data-driven, like shops). Banking commands only
  work at a branch — that's the whole point (safe money you must travel to reach).
- Commands: `deposit <amount>`, `withdraw <amount>`, `balance`.
- `deposit` is one `execute_exchange` leg, `("player", id)` → `("bank_account", account_id)`;
  `withdraw` reverses. Banked money is **immune to death loss and robbery**
  ([`death_resurrection.md`](death_resurrection.md)) simply because the death/robbery code
  only ever touches the `("player", id)` holder.
- **One logical account, many branches** — deposit in Saltmarsh, withdraw in the capital. This
  makes banks a *travel and trade convenience* (carry less cash on dangerous routes), not just a
  vault. Naturally reinforces the transit/trade loop.
- Optional later: withdrawal/transfer fees, interest, a physical bankbook item, safe-deposit box
  for items. All deferred (§13) until the base loop proves out.
- Events: `MONEY_DEPOSITED` / `MONEY_WITHDRAWN` (audited).

---

## 10. Fares & tickets (transit tie-in)

Transit tickets ([`transit_systems.md`](transit_systems.md)) are purchased with coins at vendor
NPCs; a fare is just a `buy` of a ticket item. Express/pass fares are pricier ticket items. This
keeps transit and economy on one currency and one purchase path — no separate fare system.

---

## 11. World YAML

Additive `economy:` / shop sections; worlds without them are unaffected:

```yaml
economy:
  currency: coins
  regions:                      # per-zone price multipliers + per-good bias
    - zone: coast
      region_mult: 1.0
      bias: { salt: 0.6, furs: 1.4 }
    - zone: highlands
      region_mult: 1.1
      bias: { salt: 1.5, furs: 0.7 }
  banks:
    - { npc_id: teller_maren, name: "Saltmarsh Bank" }

items:
  - id: salt_sack
    name: "sack of salt"
    value: 20
    tradeable: true

npcs:
  - id: shopkeep_bram
    # ... existing npc fields ...
    shop:
      name: "Saltmarsh General Store"
      sell_ratio: 0.5
      buys_categories: [food, supplies, trade_good]
      stock:
        - { item_id: salt_sack, quantity: 40, restock_to: 40, restock_every_ticks: 720 }
        - { item_id: ferry_token, quantity: -1 }        # unlimited fares
```

Validators (`lorecraft.tools.validators`): shop stock item ids exist; `value` present on any
`tradeable` shop item; bank `npc_id` exists; region `zone` exists; bias keys resolve to items.
`region_mult`/`bias` are also live-tunable per zone from the admin console's **Economy** tab
without a reseed — see [admin_builder_guide.md § Region pricing](admin_builder_guide.md#region-pricing-sprint-76).

---

## 12. Testing

- **Unit:** price derivation (quality/region/demand/barter/rep stacking + caps — caps clamped
  in this module *before* becoming `mult` factors, per engine_core §3.5); buy/sell coin and
  stock math; demand adjustment; deposit/withdraw invariants. **Conservation:** across any
  buy/sell/trade/deposit sequence, total coins and the item multiset change only at audited
  `credit`/`spawn`/`destroy` boundaries (engine_core §3.7 invariant, asserted end-to-end).
- **Integration:** `buy`/`sell`/`list`/`deposit`/`withdraw` via `POST /command` and `/ws`;
  insufficient-funds, out-of-stock, untradeable, not-at-a-branch errors; balances survive
  save/load and disconnect/reconnect.
- **Simulation:** two players `offer`/`accept` a trade concurrently (atomic swap, no
  duplication/loss); buy-low-in-A / sell-high-in-B round trip; audit-regression diff.
- **Content lint:** the §11 validators.

---

## 13. Non-goals / open questions

- Multi-currency, exchange rates — single "coins" only.
- Auction house, player-run storefronts, dynamic global market — see [`wishlist.md`](wishlist.md)
  (🚫, scale-gated).
- Bank interest/fees, safe-deposit item storage — deferred until the base loop proves out.
- **Open:** does selling loot to shops crash prices enough to need a per-region cap, or is
  depletion/restock sufficient? (Start simple; add caps only if abuse appears.)
- **Open:** are prices ever shown pre-`appraise`, or is appraisal always skill-gated? (Lean:
  shops show a price; `appraise` reveals true value/margins.)

---

*See [`roadmap.md`](roadmap.md) [Sprint 28](roadmap.md#sprint-28--trading--economy), [`transit_systems.md`](transit_systems.md) (fares +
the trade-network pairing), [`death_resurrection.md`](death_resurrection.md) (banks vs. carried
money), and [`inventory_equipment.md`](inventory_equipment.md) (item value/quality). Built on
[`feature-registration.md`](feature-registration.md).*
