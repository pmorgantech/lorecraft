//! lorecraft-feature-look — the Rust `look` policy (Tier 2).
//!
//! A faithful port of `src/lorecraft/features/inventory/look_pure.py`'s
//! `look_effects`. It is a pure function of a materialized [`ScriptRequest`]: no
//! store, session, or repo access. The output reproduces, in order, exactly what
//! `InventoryService.look` emits today.
//!
//! This crate lives **outside** the Tier 1 mechanism crates
//! (`runtime`/`core`/`scheduler`) on purpose: `look`'s message ordering and
//! formatting *is* a feature opinion (policy). Placing it in a mechanism crate would
//! be a Tier 1/Tier 2 leak.

use lorecraft_protocol::{EntitySnapshot, OutboundMessage, ScriptRequest, ScriptResult};
use serde_json::Value;

/// `room_snapshot.attributes` keys this policy reads.
const ATTR_NAME: &str = "name";
const ATTR_DESCRIPTION: &str = "description";
const ATTR_TERRAIN_SUFFIX: &str = "terrain_suffix";
const ATTR_EXITS: &str = "exits";

/// `selected_related_entities` item-snapshot attribute keys.
const ITEM_ATTR_NAME: &str = "name";
const ITEM_ATTR_QUANTITY: &str = "quantity";

/// Message-type tag emitted for every feed line — mirrors `MessageType.SYSTEM`.
const SYSTEM: &str = "system";

/// Build the ordered `look` output from a materialized room snapshot.
///
/// Read-only: proposes zero effects, events, or scheduled work — only feed messages
/// and a trailing `room_id` panel update.
pub fn look_effects(request: &ScriptRequest) -> ScriptResult {
    let room = &request.room_snapshot;
    let attrs = &room.attributes;
    let mut messages: Vec<OutboundMessage> = Vec::new();

    // Name and description lines. Python wraps these in `str(... or "")`; for the
    // string-or-missing values `look` actually produces, that is the raw string or
    // the empty string.
    messages.push(feed(attr_string(attrs, ATTR_NAME)));
    messages.push(feed(attr_string(attrs, ATTR_DESCRIPTION)));

    // Optional terrain suffix — only when present and a non-empty string.
    if let Some(suffix) = attrs.get(ATTR_TERRAIN_SUFFIX).and_then(Value::as_str) {
        if !suffix.is_empty() {
            messages.push(feed(suffix.to_string()));
        }
    }

    // Exits: sorted, comma-joined, with a "no obvious exits" fallback.
    let mut visible_exits: Vec<String> = match attrs.get(ATTR_EXITS) {
        Some(Value::Array(items)) => items
            .iter()
            .map(|d| d.as_str().map(String::from).unwrap_or_default())
            .collect(),
        _ => Vec::new(),
    };
    if visible_exits.is_empty() {
        messages.push(feed("There are no obvious exits.".to_string()));
    } else {
        visible_exits.sort();
        messages.push(feed(format!("Exits: {}.", visible_exits.join(", "))));
    }

    // Room items summary — only item-kind related entities, grouped/sorted/joined.
    let room_items: Vec<&EntitySnapshot> = request
        .selected_related_entities
        .iter()
        .filter(|entity| entity.kind == "item")
        .collect();
    if !room_items.is_empty() {
        messages.push(feed(format!(
            "You see: {}.",
            room_items_summary(&room_items)
        )));
    }

    // Trailing panel refresh keyed by room id (Python's ctx.push_update).
    messages.push(OutboundMessage::PanelUpdate {
        key: "room_id".into(),
        value: Value::String(room.id.clone()),
    });

    ScriptResult {
        messages,
        proposed_effects: Vec::new(),
        emitted_events: Vec::new(),
        scheduled_work: Vec::new(),
        diagnostics: Vec::new(),
    }
}

/// A system-tagged feed line.
fn feed(text: String) -> OutboundMessage {
    OutboundMessage::Feed {
        text,
        message_type: SYSTEM.into(),
    }
}

/// Read a string attribute, defaulting to empty — the string-or-missing shape
/// Python's `str(attrs.get(key, ""))` produces for `look`'s room fields.
fn attr_string(attrs: &std::collections::BTreeMap<String, Value>, key: &str) -> String {
    attrs
        .get(key)
        .and_then(Value::as_str)
        .map(String::from)
        .unwrap_or_default()
}

/// Reproduce `format_room_items_summary`: grouped labels, sorted, comma-joined.
fn room_items_summary(items: &[&EntitySnapshot]) -> String {
    let mut labels: Vec<String> = items
        .iter()
        .map(|item| {
            let name = item
                .attributes
                .get(ITEM_ATTR_NAME)
                .and_then(Value::as_str)
                .unwrap_or_default();
            entry_label(name, quantity_of(item))
        })
        .collect();
    labels.sort();
    labels.join(", ")
}

/// Reproduce `format_inventory_entry`: `[qty] name` when qty > 1, else `name`.
fn entry_label(name: &str, quantity: i64) -> String {
    if quantity > 1 {
        format!("[{quantity}] {name}")
    } else {
        name.to_string()
    }
}

/// Read an item snapshot's quantity attribute, defaulting to 1.
///
/// JSON booleans are `Value::Bool` (not numbers) and floats are not `i64`, so
/// `as_i64` already excludes the non-integer values Python's
/// `isinstance(raw, int) and not isinstance(raw, bool)` guard rejects.
fn quantity_of(item: &EntitySnapshot) -> i64 {
    item.attributes
        .get(ITEM_ATTR_QUANTITY)
        .and_then(Value::as_i64)
        .unwrap_or(1)
}

#[cfg(test)]
mod tests {
    use super::*;
    use lorecraft_protocol::ScriptBudget;
    use lorecraft_replay::hash_canonical;
    use std::collections::BTreeMap;
    use std::path::PathBuf;

    fn snapshot(id: &str, kind: &str, attrs: Vec<(&str, Value)>) -> EntitySnapshot {
        let mut map: BTreeMap<String, Value> = BTreeMap::new();
        for (k, v) in attrs {
            map.insert(k.into(), v);
        }
        EntitySnapshot {
            id: id.into(),
            kind: kind.into(),
            attributes: map,
        }
    }

    fn request_with(room: EntitySnapshot, related: Vec<EntitySnapshot>) -> ScriptRequest {
        ScriptRequest {
            api_version: 1,
            script_id: "look".into(),
            script_version: 1,
            command_or_event: "look".into(),
            actor_snapshot: snapshot("player-1", "player", vec![]),
            room_snapshot: room,
            selected_related_entities: related,
            logical_time: 0,
            rng_stream_id: "look".into(),
            capability_set: vec![],
            budget: ScriptBudget {
                wall_ms: 0,
                instructions: 0,
                memory_bytes: 0,
                output_bytes: 0,
            },
        }
    }

    fn feed_text(msg: &OutboundMessage) -> Option<&str> {
        match msg {
            OutboundMessage::Feed { text, .. } => Some(text),
            OutboundMessage::PanelUpdate { .. } => None,
        }
    }

    #[test]
    fn full_look_message_order_and_text() {
        let room = snapshot(
            "tavern",
            "room",
            vec![
                (ATTR_NAME, Value::String("The Tavern".into())),
                (ATTR_DESCRIPTION, Value::String("A cozy room.".into())),
                (
                    ATTR_TERRAIN_SUFFIX,
                    Value::String("It is warm here.".into()),
                ),
                (ATTR_EXITS, serde_json::json!(["south", "north", "east"])),
            ],
        );
        let items = vec![
            snapshot(
                "sword",
                "item",
                vec![(ITEM_ATTR_NAME, Value::String("sword".into()))],
            ),
            snapshot(
                "coin",
                "item",
                vec![
                    (ITEM_ATTR_NAME, Value::String("coin".into())),
                    (ITEM_ATTR_QUANTITY, serde_json::json!(5)),
                ],
            ),
            // A non-item related entity must be excluded from the items summary.
            snapshot("guard", "npc", vec![]),
        ];
        let result = look_effects(&request_with(room, items));

        let texts: Vec<&str> = result.messages.iter().filter_map(feed_text).collect();
        assert_eq!(
            texts,
            vec![
                "The Tavern",
                "A cozy room.",
                "It is warm here.",
                // exits sorted: east, north, south
                "Exits: east, north, south.",
                // labels sorted: "[5] coin" then "sword"
                "You see: [5] coin, sword.",
            ]
        );
        // Last message is the room_id panel update.
        match result.messages.last().unwrap() {
            OutboundMessage::PanelUpdate { key, value } => {
                assert_eq!(key, "room_id");
                assert_eq!(value, &Value::String("tavern".into()));
            }
            other => panic!("expected trailing PanelUpdate, got {other:?}"),
        }
        // Read-only: no effects/events/work.
        assert!(result.proposed_effects.is_empty());
        assert!(result.emitted_events.is_empty());
        assert!(result.scheduled_work.is_empty());
    }

    #[test]
    fn no_exits_fallback_and_no_items_line() {
        let room = snapshot(
            "void",
            "room",
            vec![
                (ATTR_NAME, Value::String("The Void".into())),
                (ATTR_DESCRIPTION, Value::String("Nothing here.".into())),
            ],
        );
        let result = look_effects(&request_with(room, vec![]));
        let texts: Vec<&str> = result.messages.iter().filter_map(feed_text).collect();
        assert_eq!(
            texts,
            vec!["The Void", "Nothing here.", "There are no obvious exits."]
        );
    }

    #[test]
    fn empty_terrain_suffix_is_omitted() {
        let room = snapshot(
            "r",
            "room",
            vec![
                (ATTR_NAME, Value::String("R".into())),
                (ATTR_DESCRIPTION, Value::String("D".into())),
                (ATTR_TERRAIN_SUFFIX, Value::String("".into())),
                (ATTR_EXITS, serde_json::json!(["north"])),
            ],
        );
        let result = look_effects(&request_with(room, vec![]));
        let texts: Vec<&str> = result.messages.iter().filter_map(feed_text).collect();
        // No empty suffix line between description and exits.
        assert_eq!(texts, vec!["R", "D", "Exits: north."]);
    }

    /// Local proof (independent of the cross-language fixture) that the port and the
    /// hasher compose: hashing a fixed `ScriptResult` yields a stable digest, and an
    /// identical result hashes identically.
    #[test]
    fn look_result_hashes_deterministically() {
        let room = snapshot(
            "tavern",
            "room",
            vec![
                (ATTR_NAME, Value::String("The Tavern".into())),
                (ATTR_DESCRIPTION, Value::String("A cozy room.".into())),
                (ATTR_EXITS, serde_json::json!(["north"])),
            ],
        );
        let a = look_effects(&request_with(room.clone(), vec![]));
        let b = look_effects(&request_with(room, vec![]));
        let ha = hash_canonical(&a).unwrap();
        let hb = hash_canonical(&b).unwrap();
        assert_eq!(ha, hb);
        assert_eq!(ha.len(), 64); // sha256 hex
    }

    /// The Phase 2 exit-criterion parity test: run the shared `look_only` fixture
    /// request through the Rust port, hash its `ScriptResult`, and assert equality
    /// with the Python-captured golden hash.
    ///
    /// The two fixture files are produced by the parallel Python capture task and may
    /// not exist yet. When absent, this test soft-skips (prints a notice and returns)
    /// so it never fails spuriously; once the fixtures land it performs the real
    /// cross-language assertion with no code change.
    #[test]
    fn look_only_fixture_parity() {
        let dir = PathBuf::from(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../fixtures/look_only"
        ));
        let request_path = dir.join("request.json");
        let hash_path = dir.join("expected_result_hash.txt");

        if !request_path.exists() || !hash_path.exists() {
            eprintln!(
                "SKIP look_only_fixture_parity: fixture not present at {} \
                 (produced by the parallel Python capture task)",
                dir.display()
            );
            return;
        }

        let request_json =
            std::fs::read_to_string(&request_path).expect("read fixture request.json");
        let request: ScriptRequest =
            serde_json::from_str(&request_json).expect("deserialize ScriptRequest fixture");
        let expected = std::fs::read_to_string(&hash_path)
            .expect("read expected_result_hash.txt")
            .trim()
            .to_string();

        let result = look_effects(&request);
        let actual = hash_canonical(&result).expect("hash ScriptResult");
        assert_eq!(
            actual, expected,
            "Rust look ScriptResult hash must match the Python golden"
        );
    }
}
