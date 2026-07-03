# Trade & Economy — Design

> **Status:** Design (2026-07-03). Roadmap **[Sprint 28](roadmap.md#sprint-28--trading--economy)** (see [`roadmap.md`](roadmap.md)).
> Currency, vendor shops, regional pricing, player-to-player trade, and banks.
>
> **Pillars this serves** (see [`wishlist.md`](wishlist.md) → *Design pillars*): **Trading** is
> pillar #2, and the signature pairing is *transit network = trade network* — regional price
> differences only create gameplay because moving goods between towns costs time, fare, and
> risk ([`transit_systems.md`](transit_systems.md)). Banks and carried-vs-banked money also
> underpin the death penalty ([`death_resurrection.md`](death_resurrection.md)).

---

## 1. Where we build from (existing primitives)

- **`Player`** — no money field yet; add carried `coins`. `inventory: list[str]` holds items.
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

Two balances, deliberately split so death and robbery have stakes:

```python
class Player(SQLModel, table=True):
    # ... existing fields ...
    coins: int = 0          # CARRIED money — spendable anywhere, AT RISK on death/robbery

class BankAccount(SQLModel, table=True):
    player_id: str = Field(primary_key=True, foreign_key="player.id")
    balance: int = 0        # BANKED money — safe from death/robbery, only at a bank branch (§9)
```

- **Carried `coins`** — what you spend at shops and hand to other players; what you can lose.
- **Banked `balance`** — safe, but only accessible at a bank branch. Creates the risk/convenience
  tension that makes banks (and robbers) matter.

Single currency ("coins") for now; multi-currency is a non-goal (§13). Coins are a scalar, not
inventory items, so they don't consume carry weight.

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
| `buy <item> [qty]` | validate coins + stock → transfer item, deduct coins, decrement stock |
| `sell <item> [qty]` | vendor buys (if `tradeable` + category matches) → add coins, add to stock |
| `appraise <item>` | show a value estimate (accuracy scales with `appraisal` skill) |

Buying/selling emits `ITEM_PURCHASED` / `ITEM_SOLD` (audited).

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

A safe two-party handshake (no item/coin loss to bugs or scams-by-disconnect):

- `offer <item|coins> to <player>` builds a pending offer; `accept` / `decline` resolves it.
- Both sides' goods are escrowed in the transaction and swapped atomically, or the whole thing
  rolls back (reuses the [Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-) rollback-on-error lifecycle).
- Only `tradeable` items; bound/quest items refuse (from [`inventory_equipment.md`](inventory_equipment.md)).
- A strong simulation-harness target (two real WS clients, concurrent accept, disconnect mid-trade).

---

## 9. Banks

Banks are economy infrastructure **and** the death/robbery safety valve.

- A **bank branch** is an NPC or room feature (data-driven, like shops). Banking commands only
  work at a branch — that's the whole point (safe money you must travel to reach).
- Commands: `deposit <amount>`, `withdraw <amount>`, `balance`.
- `deposit` moves carried `coins` → `BankAccount.balance`; `withdraw` reverses. Banked money is
  **immune to death loss and robbery** ([`death_resurrection.md`](death_resurrection.md)).
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
  regions:                      # area price multipliers + per-good bias
    - area_id: coast
      region_mult: 1.0
      bias: { salt: 0.6, furs: 1.4 }
    - area_id: highlands
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
`tradeable` shop item; bank `npc_id` exists; region `area_id` exists; bias keys resolve to items.

---

## 12. Testing

- **Unit:** price derivation (quality/region/demand/barter/rep stacking + caps); buy/sell coin
  and stock math; demand adjustment; deposit/withdraw invariants (no coin creation/loss).
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
