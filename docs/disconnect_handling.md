# Disconnect Handling Implementation Guide

## Overview

**Disconnect is not logout.** A dropped WebSocket connection starts a grace period during which the player character remains in the world. This allows temporary network glitches or browser refreshes to not permanently eject a player mid-quest.

---

## Grace Period Behavior (60 seconds default)

When a WebSocket connection is dropped:

1. **PlayerSession.status → "grace"**
2. **grace_expires_at** set to `current_time + 60 seconds`
3. Player character **remains in the world** and can be seen by others
4. If in combat: combat **pauses** — player's slots neither act nor take damage
5. Other players in the room see: `"Alice's connection flickers..."`
6. Emit **PLAYER_DISCONNECTED** (notification event)

```python
async def handle_disconnect(player_id: str, reason: str = "unknown"):
    """
    Called when WebSocket closes or times out.
    """
    session = db.query(PlayerSession).filter(
        PlayerSession.player_id == player_id,
        PlayerSession.status == "active"
    ).first()

    if not session:
        return

    session.status = "grace"
    session.disconnected_at = time.time()
    session.grace_expires_at = time.time() + 60  # 60-second grace period

    db.commit()

    # Notify others in the room
    player = db.query(Player).filter(Player.id == player_id).first()
    if player:
        await connection_manager.broadcast_to_room(
            player.current_room_id,
            {"type": "system", "text": f"{player.username}'s connection flickers..."}
        )

    # Pause combat if applicable
    if player and player.active_combat_session_id:
        session = db.query(CombatSession).filter(
            CombatSession.id == player.active_combat_session_id
        ).first()
        if session:
            # Find this player's combatant slot and mark as paused
            for combatant in session.combatants:
                if combatant["entity_id"] == player_id:
                    combatant["paused"] = True
            db.commit()

    # Emit notification event
    bus.emit(GameEvent.PLAYER_DISCONNECTED, {
        "player_id": player_id,
        "status": "grace"
    })
```

---

## Reconnect (Before Grace Expires)

If the player reconnects before `grace_expires_at`:

1. **Reattach to existing PlayerSession**
2. **PlayerSession.status → "active"**
3. Resume combat if applicable (unpause the player's slots)
4. Send **full reconnect sync message** (see [WebSocket Protocol](architecture.md#23-websocket-protocol))
5. Emit **PLAYER_RECONNECTED**

```python
async def handle_reconnect(player_id: str, websocket: WebSocket):
    """
    Player reconnected before grace period expired.
    Reattach them and resume their session.
    """
    session = db.query(PlayerSession).filter(
        PlayerSession.player_id == player_id,
        PlayerSession.status == "grace"
    ).first()

    if not session:
        # Grace period already expired; this is a fresh login
        return None

    # Grace period still active — reattach
    session.status = "active"
    session.disconnected_at = None
    session.grace_expires_at = None

    player = db.query(Player).filter(Player.id == player_id).first()

    # Unpause combat if applicable
    if player and player.active_combat_session_id:
        combat_session = db.query(CombatSession).filter(
            CombatSession.id == player.active_combat_session_id
        ).first()
        if combat_session:
            for combatant in combat_session.combatants:
                if combatant["entity_id"] == player_id:
                    combatant["paused"] = False
            db.commit()

    db.commit()

    # Broadcast to room
    await connection_manager.broadcast_to_room(
        player.current_room_id,
        {"type": "system", "text": f"{player.username} reconnects."}
    )

    # Send full reconnect sync
    room = db.query(Room).filter(Room.id == player.current_room_id).first()
    await websocket.send_json({
        "type": "reconnect_sync",
        "player": {
            "id": player.id,
            "username": player.username,
            "current_room_id": player.current_room_id,
            "inventory": player.inventory,
            "flags": player.flags,
        },
        "room": {
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "exits": {exit.direction: exit.target_room_id for exit in room.exits},
            "occupants": [
                {"id": p.id, "username": p.username}
                for p in db.query(Player).filter(
                    Player.current_room_id == room.id
                ).all()
            ],
        },
        "inventory": player.inventory,
        "quests": [
            {
                "id": qp.quest_id,
                "title": qp.quest.title,
                "current_stage_id": qp.current_stage_id,
                "status": qp.status,
            }
            for qp in db.query(PlayerQuestProgress).filter(
                PlayerQuestProgress.player_id == player_id
            ).all()
        ],
        "time": {
            "hour": clock.current_hour,
            "minute": clock.current_minute,
            "day": clock.current_day,
            "season": clock.current_season,
        }
    })

    # Emit reconnect event
    bus.emit(GameEvent.PLAYER_RECONNECTED, {
        "player_id": player_id,
        "session_id": session.id
    })

    return session
```

---

## Grace Period Expired (No Reconnect)

If grace period expires without reconnect, the scheduler fires a **GRACE_PERIOD_EXPIRED** work event:

1. **PlayerSession.status → "system_controlled"** (or "expired" if not in combat)
2. If in combat: NPC's combat AI **takes over** for the player character (defensive behavior, will not attack)
3. If in dialogue: **dialogue session cancelled** safely
4. If holding trade offer: **trade offer auto-cancelled**, items returned to both players
5. Emit **GRACE_PERIOD_EXPIRED** (work event for the scheduler)

```python
async def handle_grace_period_expired(player_id: str):
    """
    Grace period ended without reconnect.
    Transition player to system-controlled or expired state.
    """
    session = db.query(PlayerSession).filter(
        PlayerSession.player_id == player_id,
        PlayerSession.status == "grace"
    ).first()

    if not session:
        return

    player = db.query(Player).filter(Player.id == player_id).first()

    # If in combat, take over with defensive AI
    if player and player.active_combat_session_id:
        session.status = "system_controlled"
        combat_sess = db.query(CombatSession).filter(
            CombatSession.id == player.active_combat_session_id
        ).first()
        if combat_sess:
            # Mark this combatant as system-controlled
            for combatant in combat_sess.combatants:
                if combatant["entity_id"] == player_id:
                    combatant["ai_behavior"] = "defensive"
                    combatant["controlled_by_system"] = True
    else:
        session.status = "expired"

    # Cancel any active dialogue
    # (This is a simple flag; dialogue state is session-scoped, not persistent)

    # Cancel any pending trade offers
    trade_offers = db.query(TradeOffer).filter(
        (TradeOffer.initiator_id == player_id) | (TradeOffer.recipient_id == player_id),
        TradeOffer.status == "pending"
    ).all()
    for offer in trade_offers:
        offer.status = "cancelled"
        # Return items to both players
        # (implementation depends on how items are held during trades)

    db.commit()

    # Notify the room
    await connection_manager.broadcast_to_room(
        player.current_room_id,
        {"type": "system", "text": f"{player.username} is no longer responding."}
    )

    # Record audit event
    audit_service.record(
        ctx=None,  # System-generated, no GameContext
        event_type=GameEvent.PLAYER_DISCONNECTED,
        target_id=player_id,
        severity="WARNING",
        summary=f"Grace period expired for {player.username}",
        source_type="SYSTEM"
    )

    # Emit work event for scheduler (for any follow-up actions)
    bus.emit(GameEvent.GRACE_PERIOD_EXPIRED, {
        "player_id": player_id,
        "session_id": session.id
    })
```

---

## Scheduler Integration

The scheduler queries for expired sessions and emits the **GRACE_PERIOD_EXPIRED** event:

```python
class SchedulerService:
    async def tick(self, current_epoch: float):
        """
        Called on every TIME_ADVANCED event.
        """
        # Check for expired grace periods
        expired_sessions = db.query(PlayerSession).filter(
            PlayerSession.status == "grace",
            PlayerSession.grace_expires_at <= current_epoch
        ).all()

        for session in expired_sessions:
            await handle_grace_period_expired(session.player_id)
```

---

## Audit Trail

All state transitions are recorded in the audit log with `source_type="SYSTEM"`:

- **PLAYER_DISCONNECTED:** when the WebSocket closes
- **PLAYER_RECONNECTED:** when they reconnect within the grace period
- **GRACE_PERIOD_EXPIRED:** when the grace period elapses

The audit log can be queried to reconstruct a player's session history across disconnects.

---

## ConnectionManager Changes

The `ConnectionManager` needs to track active sessions and broadcast messages only to connected players:

```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.player_rooms: dict[str, str] = {}  # player_id -> room_id

    async def connect(self, player_id: str, websocket: WebSocket, room_id: str):
        self.active_connections[player_id] = websocket
        self.player_rooms[player_id] = room_id

    async def disconnect(self, player_id: str):
        # Don't remove from active_connections immediately — grace period applies
        # Just mark the WebSocket as disconnected
        if player_id in self.active_connections:
            del self.active_connections[player_id]

    async def send_to_player(self, player_id: str, message: dict):
        """Send only if player is currently connected."""
        if player_id in self.active_connections:
            await self.active_connections[player_id].send_json(message)

    async def broadcast_to_room(self, room_id: str, message: dict):
        """Broadcast to all connected players in a room."""
        for player_id, ws in self.active_connections.items():
            if self.player_rooms.get(player_id) == room_id:
                await ws.send_json(message)
```

---

## Configuration

Grace period duration should be configurable:

```python
# config.py
GRACE_PERIOD_SECONDS = int(os.getenv("GRACE_PERIOD_SECONDS", "60"))
```

---

## Testing

```python
@pytest.mark.asyncio
async def test_disconnect_grace_period():
    """Verify that disconnecting starts a grace period."""
    db = create_in_memory_db()
    player = create_test_player(db)
    session = create_test_session(db, player.id)

    # Simulate disconnect
    await handle_disconnect(player.id)

    # Check session state
    session = db.query(PlayerSession).filter(
        PlayerSession.player_id == player.id
    ).first()

    assert session.status == "grace"
    assert session.grace_expires_at is not None
    assert session.disconnected_at is not None


@pytest.mark.asyncio
async def test_reconnect_within_grace_period():
    """Verify that reconnecting within grace period restores session."""
    db = create_in_memory_db()
    player = create_test_player(db)
    session = create_test_session(db, player.id)

    # Simulate disconnect
    await handle_disconnect(player.id)
    session_after_disconnect = db.query(PlayerSession).filter(
        PlayerSession.player_id == player.id
    ).first()
    assert session_after_disconnect.status == "grace"

    # Reconnect (before grace expires)
    websocket = AsyncMock()  # Mock WebSocket
    await handle_reconnect(player.id, websocket)

    # Check session state
    session_after_reconnect = db.query(PlayerSession).filter(
        PlayerSession.player_id == player.id
    ).first()
    assert session_after_reconnect.status == "active"


@pytest.mark.asyncio
async def test_grace_period_expiration():
    """Verify that expired grace period transitions to system-controlled state."""
    db = create_in_memory_db()
    player = create_test_player(db)
    session = create_test_session(db, player.id)

    # Simulate disconnect
    await handle_disconnect(player.id)

    # Fast-forward time past grace period
    expired_session = db.query(PlayerSession).filter(
        PlayerSession.player_id == player.id
    ).first()
    expired_session.grace_expires_at = time.time() - 1  # Already expired
    db.commit()

    # Call grace period handler
    await handle_grace_period_expired(player.id)

    # Check final state
    final_session = db.query(PlayerSession).filter(
        PlayerSession.player_id == player.id
    ).first()
    assert final_session.status in ("system_controlled", "expired")
```

---

*See also: [architecture.md § Disconnect Handling](architecture.md#18-subsystem-disconnect-handling)*
