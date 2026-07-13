//! lorecraft-feature-move — the Rust `movement` policy (Tier 2).
//!
//! A faithful port of the *non-RNG* portion of
//! `src/lorecraft/features/movement/service.py`'s `MovementService.move`. It is a
//! pure function of a materialized [`ScriptRequest`] plus the parsed [`Direction`]:
//! no store, session, or repo access. On a valid, non-skill-gated move it derives
//! the authoritative [`Effect::MoveEntity`] plus the byte-identical narration the
//! Python service emits; on a blocked move it produces the same warning message.
//!
//! Like `lorecraft-feature-look`, this lives **outside** the Tier 1 mechanism
//! crates on purpose: movement's block messages, narration templates, and the
//! decision of *what* a move does are feature opinions (policy).
//!
//! ## What stays in Python this phase (migration-plan OPEN ITEM #3)
//!
//! The Python service has a **terrain-skill gate** on the target room
//! (`terrain_def.required_skill` → `SkillService.get_level` + `resolve_for` +
//! `record_use(ctx.rng, ...)`). The `record_use` call **draws RNG**, and
//! cross-language RNG parity is deferred to Phase 5, so that path **must not run in
//! Rust**. When the snapshot's target exit is skill-gated (its
//! `target_required_skill` attribute is a non-null string) this crate returns
//! [`MoveDecision::DeferToPython`] instead of executing — the driver then runs the
//! whole command in Python. Python's `BuildSnapshot` handler is expected to filter
//! skill-gated targets out *before* Rust ever runs (returning
//! `GatewayOutbound::DeferToPython`); this crate's own check is a defense-in-depth
//! backstop so Rust can never draw RNG or fabricate a skill-gated move even if a
//! gated snapshot leaks through.
//!
//! ## The move snapshot contract (for the Python `build_move_request`, task 2)
//!
//! `move_effects` reads a [`ScriptRequest`] whose snapshots carry these attributes
//! (all resolved Python-side; Rust does only the boolean/derivation logic —
//! migration-plan Decision 2):
//!
//! - `room_snapshot.id` — the room the player is in (the [`Effect::MoveEntity`]
//!   `from`).
//! - `room_snapshot.attributes["exits"]` — an object mapping each **traversable**
//!   canonical direction (including hidden exits, which are directly usable) to an
//!   exit object:
//!   - `target_room_id` (str) — the destination room id.
//!   - `target_active` (bool) — `RoomRepo.active(target) is not None`.
//!   - `locked` (bool) — the exit's locked state.
//!   - `key_item_id` (str | null) — the exit's key item, if any.
//!   - `actor_has_key` (bool) — resolved `StackRepo.quantity_of(key) > 0`.
//!   - `condition_flags` (array of str) — the exit's required condition flags.
//!   - `target_required_skill` (str | null) — the target terrain's
//!     `required_skill` (the DEFER marker; non-null ⇒ skill-gated).
//! - `actor_snapshot.id` — the player id (the [`Effect::MoveEntity`] `entity`).
//! - `actor_snapshot.attributes["username"]` (str) — used in the narration.
//! - `actor_snapshot.attributes["flags"]` (object) — the player's flag values, for
//!   the condition-flag gate (Python truthiness applied per flag).

#![warn(missing_docs)]

use lorecraft_protocol::{Effect, OutboundMessage, ScriptRequest};
use serde_json::{Map, Value};

/// A canonical compass/vertical direction a movement command can take.
///
/// Exactly the ten directions the Python `DIRECTION_ALIASES`/`OPPOSITE_DIRECTIONS`
/// tables cover; every variant has an [`opposite`](Direction::opposite), so arrival
/// narration always names the direction the player came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    /// North.
    North,
    /// South.
    South,
    /// East.
    East,
    /// West.
    West,
    /// Up.
    Up,
    /// Down.
    Down,
    /// Northeast.
    Northeast,
    /// Northwest.
    Northwest,
    /// Southeast.
    Southeast,
    /// Southwest.
    Southwest,
}

impl Direction {
    /// The canonical direction word used in exit keys and narration (`"north"`, …).
    pub fn as_str(self) -> &'static str {
        match self {
            Direction::North => "north",
            Direction::South => "south",
            Direction::East => "east",
            Direction::West => "west",
            Direction::Up => "up",
            Direction::Down => "down",
            Direction::Northeast => "northeast",
            Direction::Northwest => "northwest",
            Direction::Southeast => "southeast",
            Direction::Southwest => "southwest",
        }
    }

    /// Resolve an already-canonicalized direction word (post-alias, e.g. `"north"`,
    /// not `"n"`) to its [`Direction`], or `None` if it is not a direction.
    pub fn from_canonical(word: &str) -> Option<Self> {
        Some(match word {
            "north" => Direction::North,
            "south" => Direction::South,
            "east" => Direction::East,
            "west" => Direction::West,
            "up" => Direction::Up,
            "down" => Direction::Down,
            "northeast" => Direction::Northeast,
            "northwest" => Direction::Northwest,
            "southeast" => Direction::Southeast,
            "southwest" => Direction::Southwest,
            _ => return None,
        })
    }

    /// The word an arriving player is said to have come *from* — the reverse of this
    /// direction. Mirrors Python's `OPPOSITE_DIRECTIONS` exactly (note `up → below`
    /// and `down → above`, which are not the direction words themselves).
    pub fn opposite(self) -> &'static str {
        match self {
            Direction::North => "south",
            Direction::South => "north",
            Direction::East => "west",
            Direction::West => "east",
            Direction::Up => "below",
            Direction::Down => "above",
            Direction::Northeast => "southwest",
            Direction::Northwest => "southeast",
            Direction::Southeast => "northwest",
            Direction::Southwest => "northeast",
        }
    }
}

/// The derived, authoritative parts of a valid move: the acting player's own feed
/// messages, the state effect to apply, and the two room-directed narration lines.
#[derive(Debug, Clone, PartialEq)]
pub struct MoveExecution {
    /// The actor's own feed (the `"You go {dir}."` line + the `room_id` panel
    /// refresh), in order.
    pub actor_messages: Vec<OutboundMessage>,
    /// The single authoritative state change: move the player between rooms.
    pub effect: Effect,
    /// Narration for the room the player left (`"{username} leaves {dir}."`).
    pub room_narration: String,
    /// Narration for the room the player entered
    /// (`"{username} arrives from the {opposite}."`).
    pub arrival_narration: String,
}

/// The outcome of evaluating a move against a snapshot.
#[derive(Debug, Clone, PartialEq)]
pub enum MoveDecision {
    /// The move failed validation: a single warning feed line, no state change.
    /// The `message` is byte-identical to the Python service's `ctx.say(..., WARNING)`.
    Blocked {
        /// The warning text shown to the acting player.
        message: String,
    },
    /// The target is skill-gated (or the snapshot is not Rust-executable): do **not**
    /// execute in Rust — run the whole command in Python (keeps the RNG draw
    /// Python-side, OPEN ITEM #3).
    DeferToPython,
    /// A valid, non-skill-gated move.
    Moved(MoveExecution),
}

/// The default (system) message-type tag for the `"You go {dir}."` line —
/// `MessageType.SYSTEM`.
const SYSTEM: &str = "system";
/// The message-type tag for a blocked-move warning — `MessageType.WARNING`.
const WARNING: &str = "warning";

// Block messages — byte-identical to `MovementService.move`.
const MSG_NO_EXIT: &str = "You can't go that way.";
const MSG_CONDITION: &str = "Something prevents you from going that way.";
const MSG_LOCKED: &str = "The way is locked.";

// room_snapshot / actor_snapshot attribute keys.
const ATTR_EXITS: &str = "exits";
const ATTR_USERNAME: &str = "username";
const ATTR_FLAGS: &str = "flags";

// Exit-object keys (see the module-level snapshot contract).
const EXIT_TARGET_ROOM_ID: &str = "target_room_id";
const EXIT_TARGET_ACTIVE: &str = "target_active";
const EXIT_LOCKED: &str = "locked";
const EXIT_KEY_ITEM_ID: &str = "key_item_id";
const EXIT_ACTOR_HAS_KEY: &str = "actor_has_key";
const EXIT_CONDITION_FLAGS: &str = "condition_flags";
const EXIT_TARGET_REQUIRED_SKILL: &str = "target_required_skill";

/// The `room_id` panel key `ctx.push_update("room_id", ...)` uses.
const PANEL_ROOM_ID: &str = "room_id";

/// Evaluate a movement command against a materialized snapshot.
///
/// Reproduces, in the same order, the validation of
/// `MovementService.move`: exit-exists → condition-flag gate → locked/key gate →
/// target-active → (skill-gate ⇒ defer) → success. On success it derives the
/// [`Effect::MoveEntity`] and byte-identical narration; it never draws RNG (that
/// path stays Python — see the module docs).
pub fn move_effects(direction: Direction, request: &ScriptRequest) -> MoveDecision {
    let room = &request.room_snapshot;
    let actor = &request.actor_snapshot;

    // 1. Exit exists in the traversable set (hidden exits are still usable).
    let Some(exit) = room
        .attributes
        .get(ATTR_EXITS)
        .and_then(Value::as_object)
        .and_then(|exits| exits.get(direction.as_str()))
        .and_then(Value::as_object)
    else {
        return blocked(MSG_NO_EXIT);
    };

    // 2. Condition-flag gate: every required flag must be truthy in the actor's
    //    flags (Python `all(ctx.player.flags.get(flag) for flag in ...)`).
    let condition_flags = exit_str_list(exit, EXIT_CONDITION_FLAGS);
    if !condition_flags.is_empty() {
        let player_flags = actor.attributes.get(ATTR_FLAGS).and_then(Value::as_object);
        let satisfied = condition_flags.iter().all(|flag| {
            player_flags
                .and_then(|flags| flags.get(flag.as_str()))
                .map(is_truthy)
                .unwrap_or(false)
        });
        if !satisfied {
            return blocked(MSG_CONDITION);
        }
    }

    // 3. Locked/key gate: a locked exit needs a keyed exit whose key the actor carries.
    let locked = exit
        .get(EXIT_LOCKED)
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let key_item_id = exit.get(EXIT_KEY_ITEM_ID).and_then(Value::as_str);
    let actor_has_key = exit
        .get(EXIT_ACTOR_HAS_KEY)
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if locked && (key_item_id.is_none() || !actor_has_key) {
        return blocked(MSG_LOCKED);
    }

    // 4. Target room must be active (`RoomRepo.active(target) is not None`).
    let target_active = exit
        .get(EXIT_TARGET_ACTIVE)
        .and_then(Value::as_bool)
        .unwrap_or(false);
    if !target_active {
        return blocked(MSG_NO_EXIT);
    }

    // 5. Skill-gate ⇒ DEFER (OPEN ITEM #3): the target terrain's skill gate draws
    //    RNG in Python via `record_use`; never execute it in Rust this phase.
    if exit
        .get(EXIT_TARGET_REQUIRED_SKILL)
        .and_then(Value::as_str)
        .is_some()
    {
        return MoveDecision::DeferToPython;
    }

    // 6. Success. A missing target_room_id on an active exit is a malformed snapshot;
    //    defer rather than fabricate a move (Rust owns truth — it does not invent state).
    let Some(target_room_id) = exit.get(EXIT_TARGET_ROOM_ID).and_then(Value::as_str) else {
        return MoveDecision::DeferToPython;
    };
    let dir = direction.as_str();
    let username = actor
        .attributes
        .get(ATTR_USERNAME)
        .and_then(Value::as_str)
        .unwrap_or_default();

    let actor_messages = vec![
        OutboundMessage::Feed {
            text: format!("You go {dir}."),
            message_type: SYSTEM.into(),
        },
        OutboundMessage::PanelUpdate {
            key: PANEL_ROOM_ID.into(),
            value: Value::String(target_room_id.to_string()),
        },
    ];
    MoveDecision::Moved(MoveExecution {
        actor_messages,
        effect: Effect::MoveEntity {
            entity: actor.id.clone(),
            from: room.id.clone(),
            to: target_room_id.to_string(),
        },
        room_narration: format!("{username} leaves {dir}."),
        arrival_narration: format!("{username} arrives from the {}.", direction.opposite()),
    })
}

/// Build a [`MoveDecision::Blocked`] warning line.
fn blocked(message: &str) -> MoveDecision {
    MoveDecision::Blocked {
        message: message.to_string(),
    }
}

/// Read an exit's string-array attribute (e.g. `condition_flags`), dropping any
/// non-string entries. A missing key yields an empty list.
fn exit_str_list(exit: &Map<String, Value>, key: &str) -> Vec<String> {
    match exit.get(key) {
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|item| item.as_str().map(String::from))
            .collect(),
        _ => Vec::new(),
    }
}

/// Python truthiness for a JSON flag value: `null`/`false`/`0`/`""`/`[]`/`{}` are
/// falsy, everything else truthy — so the condition-flag gate reaches the same
/// allow/block decision as `all(ctx.player.flags.get(flag) for flag in ...)`.
fn is_truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i != 0
            } else if let Some(u) = n.as_u64() {
                u != 0
            } else {
                // A float: falsy only at exactly 0.0 (matches Python `bool(0.0)`).
                n.as_f64().map(|f| f != 0.0).unwrap_or(true)
            }
        }
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// The message-type tag a blocked warning carries — exposed so the execution driver
/// can build the actor's warning feed line without hardcoding the string.
pub const WARNING_MESSAGE_TYPE: &str = WARNING;

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_protocol::{EntitySnapshot, ScriptBudget};
    use std::collections::BTreeMap;

    fn exit_json(entries: &[(&str, Value)]) -> Value {
        let mut map = serde_json::Map::new();
        for (k, v) in entries {
            map.insert((*k).to_string(), v.clone());
        }
        Value::Object(map)
    }

    /// A request with one exit `dir` on the room and the given actor attributes.
    fn request(dir: &str, exit: Value, actor_attrs: Vec<(&str, Value)>) -> ScriptRequest {
        let mut exits = serde_json::Map::new();
        exits.insert(dir.to_string(), exit);
        let mut room_attrs: BTreeMap<String, Value> = BTreeMap::new();
        room_attrs.insert(ATTR_EXITS.into(), Value::Object(exits));

        let mut a_attrs: BTreeMap<String, Value> = BTreeMap::new();
        for (k, v) in actor_attrs {
            a_attrs.insert(k.into(), v);
        }
        ScriptRequest {
            api_version: 1,
            script_id: "movement".into(),
            script_version: 1,
            command_or_event: "go".into(),
            actor_snapshot: EntitySnapshot {
                id: "player-1".into(),
                kind: "player".into(),
                attributes: a_attrs,
            },
            room_snapshot: EntitySnapshot {
                id: "village_square".into(),
                kind: "room".into(),
                attributes: room_attrs,
            },
            selected_related_entities: vec![],
            logical_time: 0,
            rng_stream_id: String::new(),
            capability_set: vec![],
            budget: ScriptBudget {
                wall_ms: 0,
                instructions: 0,
                memory_bytes: 0,
                output_bytes: 0,
            },
        }
    }

    /// A plain, valid, non-gated exit north to `north_road`.
    fn open_exit() -> Value {
        exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("north_road".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
        ])
    }

    fn actor(username: &str) -> Vec<(&str, Value)> {
        vec![(ATTR_USERNAME, Value::String(username.into()))]
    }

    #[test]
    fn no_exit_that_way_is_blocked() {
        // The room has a `north` exit; going `south` finds no exit.
        let req = request("north", open_exit(), actor("alice"));
        assert_eq!(
            move_effects(Direction::South, &req),
            MoveDecision::Blocked {
                message: MSG_NO_EXIT.into()
            }
        );
    }

    #[test]
    fn condition_flag_gate_blocks_when_flag_missing_or_falsy() {
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("vault".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
            (
                EXIT_CONDITION_FLAGS,
                Value::Array(vec![Value::String("bridge_raised".into())]),
            ),
        ]);
        // Flag absent → blocked.
        let req = request("north", exit.clone(), actor("alice"));
        assert_eq!(
            move_effects(Direction::North, &req),
            MoveDecision::Blocked {
                message: MSG_CONDITION.into()
            }
        );
        // Flag present but falsy → blocked.
        let mut flags = serde_json::Map::new();
        flags.insert("bridge_raised".into(), Value::Bool(false));
        let req = request(
            "north",
            exit,
            vec![
                (ATTR_USERNAME, Value::String("alice".into())),
                (ATTR_FLAGS, Value::Object(flags)),
            ],
        );
        assert_eq!(
            move_effects(Direction::North, &req),
            MoveDecision::Blocked {
                message: MSG_CONDITION.into()
            }
        );
    }

    #[test]
    fn condition_flag_gate_allows_when_all_flags_truthy() {
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("vault".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
            (
                EXIT_CONDITION_FLAGS,
                Value::Array(vec![Value::String("bridge_raised".into())]),
            ),
        ]);
        let mut flags = serde_json::Map::new();
        flags.insert("bridge_raised".into(), Value::Bool(true));
        let req = request(
            "north",
            exit,
            vec![
                (ATTR_USERNAME, Value::String("alice".into())),
                (ATTR_FLAGS, Value::Object(flags)),
            ],
        );
        assert!(matches!(
            move_effects(Direction::North, &req),
            MoveDecision::Moved(_)
        ));
    }

    #[test]
    fn locked_exit_without_key_is_blocked() {
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("cellar".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
            (EXIT_LOCKED, Value::Bool(true)),
            (EXIT_KEY_ITEM_ID, Value::String("iron_key".into())),
            (EXIT_ACTOR_HAS_KEY, Value::Bool(false)),
        ]);
        let req = request("down", exit, actor("alice"));
        assert_eq!(
            move_effects(Direction::Down, &req),
            MoveDecision::Blocked {
                message: MSG_LOCKED.into()
            }
        );
    }

    #[test]
    fn locked_exit_with_carried_key_opens() {
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("cellar".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
            (EXIT_LOCKED, Value::Bool(true)),
            (EXIT_KEY_ITEM_ID, Value::String("iron_key".into())),
            (EXIT_ACTOR_HAS_KEY, Value::Bool(true)),
        ]);
        let req = request("down", exit, actor("alice"));
        assert!(matches!(
            move_effects(Direction::Down, &req),
            MoveDecision::Moved(_)
        ));
    }

    #[test]
    fn inactive_target_is_blocked_as_no_exit() {
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("ruin".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(false)),
        ]);
        let req = request("east", exit, actor("alice"));
        assert_eq!(
            move_effects(Direction::East, &req),
            MoveDecision::Blocked {
                message: MSG_NO_EXIT.into()
            }
        );
    }

    #[test]
    fn skill_gated_target_defers_to_python() {
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("swamp".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
            (
                EXIT_TARGET_REQUIRED_SKILL,
                Value::String("wilderness_lore".into()),
            ),
        ]);
        let req = request("west", exit, actor("alice"));
        assert_eq!(
            move_effects(Direction::West, &req),
            MoveDecision::DeferToPython
        );
    }

    #[test]
    fn successful_move_derives_effect_and_byte_identical_narration() {
        let req = request("north", open_exit(), actor("Aldric"));
        let MoveDecision::Moved(exec) = move_effects(Direction::North, &req) else {
            panic!("expected a Moved decision");
        };
        // The single state effect: player moves village_square → north_road.
        assert_eq!(
            exec.effect,
            Effect::MoveEntity {
                entity: "player-1".into(),
                from: "village_square".into(),
                to: "north_road".into(),
            }
        );
        // Actor feed: "You go north." (system) + a room_id panel refresh.
        assert_eq!(
            exec.actor_messages,
            vec![
                OutboundMessage::Feed {
                    text: "You go north.".into(),
                    message_type: SYSTEM.into(),
                },
                OutboundMessage::PanelUpdate {
                    key: PANEL_ROOM_ID.into(),
                    value: Value::String("north_road".into()),
                },
            ]
        );
        // Room-directed narration — byte-identical to the Python service.
        assert_eq!(exec.room_narration, "Aldric leaves north.");
        assert_eq!(exec.arrival_narration, "Aldric arrives from the south.");
    }

    #[test]
    fn vertical_arrival_uses_below_not_up() {
        // OPPOSITE_DIRECTIONS maps up→below (not "down"), so a move `up` narrates
        // an arrival "from the below.".
        let exit = exit_json(&[
            (EXIT_TARGET_ROOM_ID, Value::String("loft".into())),
            (EXIT_TARGET_ACTIVE, Value::Bool(true)),
        ]);
        let req = request("up", exit, actor("Aldric"));
        let MoveDecision::Moved(exec) = move_effects(Direction::Up, &req) else {
            panic!("expected a Moved decision");
        };
        assert_eq!(exec.arrival_narration, "Aldric arrives from the below.");
    }

    #[test]
    fn direction_round_trips_canonical_and_opposite() {
        for (word, opp) in [
            ("north", "south"),
            ("south", "north"),
            ("east", "west"),
            ("west", "east"),
            ("up", "below"),
            ("down", "above"),
            ("northeast", "southwest"),
            ("northwest", "southeast"),
            ("southeast", "northwest"),
            ("southwest", "northeast"),
        ] {
            let dir = Direction::from_canonical(word).expect("known direction");
            assert_eq!(dir.as_str(), word);
            assert_eq!(dir.opposite(), opp);
        }
        assert_eq!(Direction::from_canonical("nowhere"), None);
        assert_eq!(Direction::from_canonical("n"), None); // aliases resolved upstream
    }
}
