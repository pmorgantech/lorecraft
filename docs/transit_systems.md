# Transit & Travel Systems — Design

> **Status:** Implementation-ready design (2026-07-03; revised same day for Tier 1 alignment).
> Roadmap **[Sprint 29](roadmap.md#sprint-29--transit--travel-systems)** (see [`roadmap.md`](roadmap.md)).
> The signature Materia-Magica-inspired feature: ferries, balloons, rail, and caravans that
> move on the world clock, take tickets, and animate on the minimap.
>
> **Tier 1 dependencies (build first — [`engine_core.md`](engine_core.md)):** the **route
> runner** (`RouteSpec`/`MobileRouteState`/`MobileRouteService` + `RouteHooks`, engine_core
> §3.8, [Sprint 21](roadmap.md#sprint-21--scheduled-moving-entity-moving-room)) owns the
> vehicle state machine, scheduler wiring, and position interpolation. This feature supplies
> **line semantics only**: routes built from its YAML, doors/boarding, tickets, weather
> grounding, and the `transit_update` message. Where the earlier draft specified a
> `TransitVehicleState` table and a hand-rolled state machine, both are superseded (§4–§5).
>
> **Pillars this serves** (see [`wishlist.md`](wishlist.md) → *Design pillars*): **Exploration**
> (the network *is* how you reach new areas) and **Trading** — the signature pairing is
> *transit network = trade network*: regional price differences ([`roadmap.md`](roadmap.md)
> [Sprint 28](roadmap.md#sprint-28--trading--economy)) only matter if getting goods between towns takes time, money, and planning.

---

## 1. Where we build from (existing primitives)

Everything composes engine infrastructure that exists by the end of the Tier 1 band:

- **`MobileRouteService`** (engine_core §3.8) — the generic route runner: state machine
  (`at_stop → in_transit → at_stop`, reverse/loop), scheduler jobs (`job_type="mobile_route"`),
  `may_depart`/`on_depart`/`on_arrive`/`on_tick` hooks, progress + position interpolation.
  **This drives every vehicle** — transit writes no timing or state-machine code.
- **`WorldClock`** — `game_epoch`, `current_hour/minute/day`, `weather`. Timetables and
  weather delays read from here.
- **`Room.map_x` / `map_y` / `area_id`** — real map coordinates + area grouping. Stops are
  rooms; the minimap animation interpolates between stop coordinates (`web/rendering.py`
  already builds minimap tiles from these).
- **`ConnectionManager`** + **`game/broadcast.py`** — `broadcast_command_effects()`,
  `players_in_room()`, `broadcast_global()`. Arrival/departure narration and the
  `transit_update` push reuse these.
- **WS message pattern** — `time_update` / `state_change` / `room_event` (`main.py`,
  `web/static/js/app.js` switch). We add one new type: **`transit_update`** (§9).
- **`Item`** — tickets are items (gating boarding); fares tie to the [Sprint 28](roadmap.md#sprint-28--trading--economy) currency model.
- **Pluggable conditions / side-effects** registries ([Sprint 10](roadmap.md#sprint-10--extensibility-seams-)) and the
  [feature-registration pattern](feature-registration.md) — transit ships as a self-contained
  feature module.

---

## 2. Travel patterns (the design space)

A single data model must express all of these — they are **line configuration, not code
branches**:

| Dimension | Options | Field |
|---|---|---|
| **Mode** | ferry, rail, balloon, caravan, coach, … (open-ended, data-driven) | `mode` |
| **Stopping pattern** | *local* (boards/alights at every stop) vs *express* (end-to-end, no intermediate boarding) | `service_type` + per-stop `boarding` |
| **Speed** | slow ↔ fast, and uneven legs | per-segment `travel_ticks` |
| **Shape** | out-and-back (reverses) vs loop | `reverses` / `loop` |
| **Animation** | animate a marker on the minimap, or not | `animate_minimap` |
| **Ticketing** | free, ticket-gated, consumed vs pass | `ticket_item_id`, `ticket_consumed` |
| **Weather** | grounded/delayed by weather, or immune | `weather_sensitive` |

Worked examples:

- **Coastal Ferry** — `ferry`, *local*, 3 stops, reverses, slow (20–25 ticks/leg), ticket
  consumed, animates, weather-sensitive (fog delays).
- **Skyward Express** — `balloon`, *express*, 2 terminals only, fast single hop, pricey pass,
  animates a slow arc, grounded in storms.
- **Kingsroad Rail** — `rail`, *local*, 5 stops, fixed timetable, loop line, animates, immune
  to weather.
- **Merchant Caravan** — `caravan`, *local*, many stops, very slow, free to ride but slow
  enough that fast-travel is a paid upgrade; escort/quest hooks.

---

## 3. Two vehicle models

### 3a. Physical vehicle = a moving room (primary)

A line owns a **`vehicle_room`** — an ordinary `Room` that players ride inside. Passengers are
simply the room's occupants; **no passenger table is needed** — the vehicle carries whoever is
in its room. This gives social travel, lets off-vehicle players see it come and go, and reuses
all existing room/broadcast machinery.

Key rule: the vehicle room has **no static `Exit` rows**. The only way in is `board` and the
only way out is `disembark`, both gated by the transit service on live vehicle state (doors
open only when `at_stop`). This avoids rewriting `Exit` rows every stop.

The vehicle room's `map_x/map_y` are `null` (it is *off* the fixed map); its live position for
the minimap comes from interpolating between stop coordinates (§9).

**Used for:** ferry, rail, balloon, caravan — anything with stops, other-player visibility, or
animation.

### 3b. Abstract direct travel = virtual journey (variant)

For quick point-to-point hops with no conveyance to inhabit (a hired coach, a recall stone), a
player books a **journey**: pay fare, enter a brief transit state, and arrive after N ticks. No
vehicle room; a per-player `TransitJourney` row plus a scheduled arrival job. Optional
minimap animation of the player's own marker.

**Used for:** express fast-travel, recall, single-rider services. Simpler; no shared vehicle.

The rest of this doc details **3a** (the richer case); 3b is a strict simplification of it.

---

## 4. Data model

New tables (feature module `features/transit/models.py`), all additive:

```python
class TransitLine(SQLModel, table=True):
    id: str = Field(primary_key=True)            # "coastal_ferry"
    name: str                                    # "Coastal Ferry"
    mode: str                                    # "ferry"|"rail"|"balloon"|... (data-driven)
    service_type: str = "local"                  # "local" | "express"
    vehicle_room_id: str | None = None           # 3a moving room; None => 3b virtual
    ticket_item_id: str | None = None            # required to board; None => free
    ticket_consumed: bool = True                 # consume on board vs. reusable pass
    reverses: bool = True                         # A→B→C then C→B→A; else loop
    loop: bool = False                            # C→A jump instead of reversing
    animate_minimap: bool = True
    weather_sensitive: bool = False
    blocking_weather: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # ["storm","fog"]

class TransitStop(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    line_id: str = Field(foreign_key="transitline.id", index=True)
    room_id: str = Field(foreign_key="room.id")  # the station room (has map_x/map_y)
    sequence: int                                 # order along the route (0-based)
    dwell_ticks: int = 5                          # wait time at this stop
    travel_ticks: int = 20                        # ticks from THIS stop to the next
    boarding: bool = True                         # express passes through non-boarding stops

```

**Runtime vehicle state (superseded draft):** there is **no `TransitVehicleState` table** —
runtime position is the Tier 1 `MobileRouteState` row (engine_core §3.8), keyed
`route_id = f"transit:{line_id}"`. At app lifespan the transit module builds a `RouteSpec`
per line from `TransitStop` rows (`Waypoint(position_id=stop.room_id, x=room.map_x,
y=room.map_y, dwell_ticks, travel_ticks)`, plus `reverses`/`loop` and
`tick_pushes` from `animate_minimap`) and calls `MobileRouteService.add_route(spec, hooks)`.
"Grounded" is the runner's generic `halted` status with a transit-supplied reason (§10).

Tickets are plain `Item`s (§1); no new ticket table. Journeys for model 3b:

```python
class TransitJourney(SQLModel, table=True):       # only for 3b virtual travel
    id: str = Field(primary_key=True)
    player_id: str = Field(foreign_key="player.id", index=True)
    line_id: str
    origin_room_id: str
    dest_room_id: str
    arrive_epoch: float
```

---

## 5. Vehicle lifecycle (the state machine)

Driven entirely by the Tier 1 route runner (which itself runs on `SchedulerService`). A
line's vehicle cycles:

```
 at_stop(A) ──depart──▶ in_transit(A→B) ──arrive──▶ at_stop(B) ──depart──▶ …
     ▲                                                                      │
     └──────────────── reverse / loop at terminal ◀────────────────────────┘
```

The cycle, dwell timing, index/direction advance, reverse/loop, and all scheduler jobs are the
Tier 1 runner's (engine_core §3.8). Transit implements the four `RouteHooks`:

| Hook | Transit behavior |
|---|---|
| `may_depart` | if `weather_sensitive` and `clock.weather in blocking_weather` → return a reason string (`"grounded: storm"`); the runner sets `halted` and re-checks after `dwell_ticks`. Transit narrates the delay (`"The balloon is grounded — high winds."`). Return `None` to go. |
| `on_depart` | close doors (boarding flag off); broadcast departure to (a) station occupants (`"The ferry pulls away from Saltmarsh Pier."`) and (b) vehicle-room occupants (`"The ferry casts off."`); audit `TRANSIT_DEPARTED`. |
| `on_tick` | receives interpolated `progress` 0..1; emit the `transit_update` WS message (§9). Only lines with `animate_minimap` set `tick_pushes > 0`. |
| `on_arrive` | open doors at the new stop; broadcast arrival to station + vehicle occupants; audit `TRANSIT_ARRIVED`. Express lines: non-`boarding` stops are still waypoints (for animation), but `on_arrive` keeps doors closed there. |

`TRANSIT_DEPARTED` / `TRANSIT_ARRIVED` (new additive `GameEvent` members) keep the
audit-regression simulation harness able to diff a timetable run.

---

## 6. Stopping patterns: local vs express

- **Local** — every stop has `boarding: true`. Ride and `disembark` at whichever stop you want.
  More stops = slower end-to-end but more reach. The "milk run".
- **Express** — either only two terminal stops, or intermediate stops flagged `boarding: false`
  (the vehicle passes through without opening doors, purely for animation waypoints). End-to-end,
  faster, usually pricier. The "direct".

Both are the same machine; only `service_type` + per-stop `boarding` differ. A single mode
(e.g. rail) can run both a local and an express line over overlapping stops.

---

## 7. Speed & timetables

- **Speed** is per-segment `travel_ticks` (ticks are world-clock game-minutes-ish). Fast lines
  use small values; slow caravans use large ones; uneven legs are natural (a long open-water
  crossing vs. a short hop).
- **Timetables** derive from the running state: `schedule <line>` lists stops in order with the
  next departure time computed from `dwell_ticks` + current `arrive_epoch`, rendered against the
  `WorldClock`. Missing the boat is a real cost — reinforces planning.

---

## 8. Tickets & fares (trade tie-in)

- `ticket_item_id` names an `Item` the player must hold to `board`. `ticket_consumed` decides
  single-use ticket vs. reusable pass.
- Tickets are sold by vendor NPCs ([Sprint 28](roadmap.md#sprint-28--trading--economy) shops); fare pricing rides on the [Sprint 28](roadmap.md#sprint-28--trading--economy)
  currency model. Until then a line can be `ticket_item_id: null` (free) or gated on a
  quest-granted pass item.
- Passes as trade/quest rewards: a "Rail Pass" that unlocks fast hops between visited stations
  pairs the transit theme with the exploration-progression loop.

---

## 9. Minimap animation (`transit_update`)

A new WS message, emitted during `in_transit` for lines with `animate_minimap`:

```jsonc
{
  "type": "transit_update",
  "line_id": "coastal_ferry",
  "mode": "ferry",              // frontend picks an icon (⛴ / 🚂 / 🎈 / 🐎)
  "from": { "x": 4, "y": 7 },   // origin stop room map coords
  "to":   { "x": 9, "y": 6 },   // destination stop room map coords
  "progress": 0.42,             // 0..1 along the segment
  "eta_ticks": 12
}
```

- **Position** = `lerp(from, to, progress)`; the frontend draws a mode icon at that point on the
  existing minimap grid (`web/rendering.py` already maps room coords → tiles). No server-side
  minimap re-render needed — this is a lightweight marker overlay.
- **Who receives it:**
  - Vehicle occupants — their minimap centers on the live vehicle position (the vehicle room is
    off-map, so its marker *is* the interpolated point) and shows motion.
  - Optionally, players whose current area contains the segment's stops — they watch the ferry
    cross the bay from shore.
- **Cadence:** throttled `transit_tick` jobs (e.g. every few game-minutes or fixed N steps per
  segment), not every clock tick — keep WS traffic sane.
- `animate_minimap: false` lines simply never emit these; boarding/arrival still narrate via
  `room_event`.

Frontend: add a `case "transit_update"` to the `app.js` message switch that upserts a marker
keyed by `line_id` and removes it on arrival (a final `progress: 1` / an explicit clear).

---

## 10. Weather interplay

`weather_sensitive` lines consult `WorldClock.weather` (from `clock/weather.py`) at departure:

- Balloon `blocking_weather: ["storm","gale"]` → grounded until clear; departures postponed,
  narrated, and the timetable slips.
- Ferry `blocking_weather: ["fog"]` → delayed, not cancelled (longer `travel_ticks` in fog is an
  alternative to a hard block).
- Rail — `weather_sensitive: false`, runs regardless.

This gives weather real mechanical weight and rewards checking conditions before a trip.

---

## 11. Commands

Extend the parser/registry with a transit command group (`features/transit/commands.py`):

| Command | When | Effect |
|---|---|---|
| `board [line]` | at a station, vehicle `at_stop` | validate ticket → move player into `vehicle_room`; consume ticket if configured. `[line]` disambiguates multiple lines at one station. |
| `disembark` / `leave` | aboard, vehicle `at_stop` | move player from `vehicle_room` into the current station room. |
| `schedule [line]` / `timetable` | anywhere / at a station | show stops in order + next departure vs. world clock. |
| `travel <destination>` | at a station served by a 3b line | book a virtual journey (fare, ETA) — abstract fast-travel. |

Boarding/disembarking route through the transit service (not normal `go`), which enforces
vehicle state and doors. Attempting to `board` an in-transit or grounded line gives a clear
message (`"The ferry has already departed; next sailing at 14:00."`).

---

## 12. World YAML

Additive `transit:` section; worlds without it are unaffected:

```yaml
transit:
  lines:
    - id: coastal_ferry
      name: Coastal Ferry
      mode: ferry
      service_type: local
      vehicle_room_id: ferry_deck
      ticket_item_id: ferry_token
      ticket_consumed: true
      reverses: true
      animate_minimap: true
      weather_sensitive: true
      blocking_weather: [fog, storm]
      stops:
        - { room_id: saltmarsh_pier, sequence: 0, dwell_ticks: 5, travel_ticks: 20 }
        - { room_id: gull_rock,      sequence: 1, dwell_ticks: 5, travel_ticks: 25 }
        - { room_id: harbor_end,     sequence: 2, dwell_ticks: 8, travel_ticks: 0 }

    - id: skyward_express
      name: Skyward Balloon
      mode: balloon
      service_type: express
      vehicle_room_id: balloon_basket
      ticket_item_id: sky_pass
      ticket_consumed: false        # reusable pass
      reverses: true
      animate_minimap: true
      weather_sensitive: true
      blocking_weather: [storm, gale]
      stops:
        - { room_id: capital_spire, sequence: 0, dwell_ticks: 10, travel_ticks: 8 }
        - { room_id: harbor_end,    sequence: 1, dwell_ticks: 10, travel_ticks: 0 }
```

Content validators (`lorecraft.tools.validators`) gain: stop `room_id` exists; `vehicle_room_id`
exists and has no static exits; sequences are contiguous from 0; `ticket_item_id` resolves; an
express line has ≥2 boarding stops; `blocking_weather` values are known weather states.

---

## 13. Events

- `TRANSIT_DEPARTED` / `TRANSIT_ARRIVED` (severity INFO) — audited per stop; feed the
  audit-regression harness and analytics.
- `TRANSIT_BOARDED` / `TRANSIT_DISEMBARKED` — per player, for standing/quest hooks (a quest can
  require "arrive at Gull Rock by ferry").
- Reuses `SCHEDULED_JOB_DUE` internally; no new bus wiring beyond the feature's `register(bus)`.

---

## 14. Testing

- **Unit:** the state machine, reverse/loop, and interpolation are **Tier 1's tests**
  (engine_core §3.8) — don't re-test them here. Transit units: RouteSpec construction from
  YAML; hook behavior (doors on express non-boarding stops, weather `may_depart` reasons);
  ticket validation/consumption; timetable derivation.
- **Integration:** `board`/`disembark`/`schedule` via `POST /command` and `/ws`; ticket
  consumed; disembark places player in the right station; missing-ticket and departed-vehicle
  errors.
- **Simulation:** two players ride the same ferry (shared `vehicle_room`), one disembarks mid-
  route while the other stays; a `transit_update` sequence reaches an onboard client;
  audit-regression diff of a fixed timetable run across two fresh servers.
- **Content lint:** the §12 validators.

---

## 15. Non-goals / open questions

- **Vehicle capacity / crowding** — unlimited seats for now; add a cap only if demand appears.
- **Player-piloted vehicles** — out of scope; vehicles are scheduled services, not steerable.
- **Dynamic routing / delays cascading across a network** — each line is independent; no
  transfers modeled beyond "walk between two stations". Revisit if a real network emerges.
- **Open:** does missing an express connection strand a player, or is there always a slow local
  fallback? (Lean: always a slow fallback so no one is hard-stuck.)
- **Open:** fare = flat per-line or per-segment distance? (Lean: flat per boarding until the
  [Sprint 28](roadmap.md#sprint-28--trading--economy) economy says otherwise.)

---

*See [`roadmap.md`](roadmap.md) [Sprint 29](roadmap.md#sprint-29--transit--travel-systems), [`wishlist.md`](wishlist.md) → Featured idea, and
[`inventory_equipment.md`](inventory_equipment.md) (tickets are items). Built on
[`feature-registration.md`](feature-registration.md).*
