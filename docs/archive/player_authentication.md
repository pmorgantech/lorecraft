> **📦 Archived (2026-07-18).** Implementation is complete (Sprint 4); this doc's value was
> tracking deviations between the original design and the shipped code. For current auth
> behavior, read `src/lorecraft/webui/player/auth.py` and `src/lorecraft/webui/player/player_auth.py`
> directly, or `docs/admin_builder_guide.md` for the operator-facing summary.

# Player Authentication Implementation Guide

## Overview

The engine uses **local username + password** authentication for LAN-party deployments. The design is provider-agnostic so Google OAuth/OIDC can be added later without rearchitecting the `PlayerAuth` table.

**Design constraint:** No email verification, no password reset, no login rate limiting in v1. All reasonable for trusted LAN context.

**Implementation status (Sprint 4, complete):** this doc's code samples below are illustrative pseudocode from the original design; the real implementation (`src/lorecraft/web/auth.py`, `src/lorecraft/models/player_auth.py`) differs in a few deliberate ways:

- **Password hashing** reuses the existing PBKDF2-HMAC-SHA256 primitives in `admin/auth.py` (`hash_password`/`verify_password`) rather than adding bcrypt/argon2 as a new dependency — one hashing convention for the whole codebase, not bcrypt for admins and argon2 for players.
- **JWT issuance** reuses `admin/auth.py`'s `create_token`/`decode_token` rather than hand-rolling `jwt.encode`/`jwt.decode` calls, signed with `Settings.player_session_secret` (auto-generated/persisted, not a bare `SECRET_KEY` constant).
- **WS ticket storage** is an in-memory dict on `AppState` (`ws_tickets: dict[str, tuple[player_id, expires_at]]`), not Redis — this engine has no Redis dependency and doesn't need one for a single-process deployment. `POST /auth/ws-ticket` accepts either a bearer access token *or* the browser's signed `lorecraft_session` cookie (browsers can't easily attach custom headers to a same-origin fetch without extra JS, but send cookies automatically).
- **The browser lobby** (`/lobby/enter`, `/lobby/create`) shares the same `login_or_register()` function as `POST /auth/login`, rather than being a separate code path — one password-checking implementation for both the JSON API and the HTMX UI.
- **`allow_query_player_id`** (the pre-Sprint-4 dev/test fallback) defaults to `False`, not deleted outright — kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (see `docs/roadmap.md` Sprint 4.6).
- **The OAuth callback** (`POST /auth/oauth/{provider}/callback`) is a genuine stub returning 501 — the example Google OAuth code below shows the intended shape once a real provider integration is built, but nothing below is wired up.

---

## Account Creation & Login Flow

### Username & Password Validation

- **Username** must match `^[A-Za-z0-9_-]{3,30}$` (3–30 chars: letters, numbers, `-`, `_`). The browser create form validates this live (the field border turns red/green as you type, via the HTML5 `pattern`), and `login_or_register()` re-checks it server-side.
- **Password complexity** is enforced **only when a new credential is set** (account creation, or claiming a pre-existing passwordless player) — never on a normal login. The browser create form prompts for the password twice (with a live "passwords match" indicator and a per-requirement checklist) and disables submit until valid; the server (`PasswordPolicy.validate_password`, in `webui/player/password_policy.py`) is the authoritative backstop for both the HTMX form and the JSON `POST /auth/login`. The policy is **configuration with defaults**:

  | Env var | Default | Meaning |
  |---|---|---|
  | `LORECRAFT_PASSWORD_MIN_LENGTH` | `8` | Minimum length |
  | `LORECRAFT_PASSWORD_MAX_LENGTH` | `32` | Maximum length |
  | `LORECRAFT_PASSWORD_REQUIRE_MIXED_CASE` | `true` | Require both upper- and lower-case |
  | `LORECRAFT_PASSWORD_REQUIRE_NUMBER` | `true` | Require at least one digit |
  | `LORECRAFT_PASSWORD_REQUIRE_SYMBOL` | `false` | Require at least one non-alphanumeric |

  Validation failures re-render the lobby with an inline error (HTTP 400) rather than a raw error page; the API returns `400 {"detail": "..."}`.

### 1. First Login Creates Account

There is **no separate registration step**. The first successful login for a given username creates the account atomically.

```
Client                          Server
  |                               |
  | POST /auth/login              |
  | {username, password}          |
  |------------------------------>|
  |                          Look up PlayerAuth
  |                          where provider="local"
  |                          and provider_subject=username
  |
  |                          If not found:
  |                            - Hash password (bcrypt/argon2)
  |                            - Create Player row
  |                            - Create PlayerAuth row
  |                            - Spawn in respawn_room_id
  |
  |                          Else:
  |                            - Verify password
  |                            - Load existing Player
  |
  |                          Issue JWT access token
  |                          Issue refresh token
  |
  | 200 OK {access_token, ws_ticket}
  |<-----|
  |
  | POST /auth/ws-ticket         |
  | {access_token}               |
  |------------------------------>|
  |                          Validate JWT
  |                          Issue single-use ws_ticket
  |                          (60-second TTL, one-time use)
  |
  | 200 OK {ws_ticket}
  |<-----|
  |
  | WS /ws?ticket=<ws_ticket>    |
  |------------------------------>|
  |                          Validate & consume ticket
  |                          Map ticket -> player_id
  |                          Attach to ConnectionManager
  |
  | (WebSocket connected)
  |<-----|
```

---

## Database Schema

### PlayerAuth Table

```python
class PlayerAuth(SQLModel, table=True):
    """Credential binding. Provider-agnostic so OAuth can be added later without touching this shape."""
    id: int = Field(default=None, primary_key=True)
    player_id: str = Field(foreign_key="player.id", unique=True, index=True)

    # Provider & subject (durable identity)
    provider: str                      # "local" for now; "google" when OAuth added
    provider_subject: str = Field(index=True)  # username for local; google_sub for OAuth

    # Local auth only
    credential_hash: Optional[str] = None  # bcrypt/argon2 hash; null for providers that don't use one
    created_at: float
    last_login_at: float
```

### PlayerSession Table (for WebSocket lifecycle)

```python
class PlayerSession(SQLModel, table=True):
    """Tracks connection state; disconnect ≠ logout."""
    id: str = Field(primary_key=True)      # session UUID
    player_id: str = Field(index=True)
    connected_at: float
    disconnected_at: Optional[float] = None
    grace_expires_at: Optional[float] = None
    status: str = "active"                 # active | grace | expired | system_controlled
```

---

## JWT & Token Lifecycle

### Access Token

- **Lifetime:** 15 minutes
- **Scope:** Authorize HTTP requests (e.g., `GET /admin/players`, `POST /auth/ws-ticket`)
- **Claims:** `player_id`, `username`, `admin_roles` (if applicable)

```python
def issue_access_token(player_id: str, username: str, admin_roles: list[str] = None) -> str:
    payload = {
        "sub": player_id,
        "username": username,
        "admin_roles": admin_roles or [],
        "iat": time.time(),
        "exp": time.time() + 15 * 60,
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

### Refresh Token

- **Lifetime:** 8 hours
- **Scope:** Obtain new access token
- **Rotation:** Issued on every use (new token, old token invalidated)

```python
def issue_refresh_token(player_id: str) -> str:
    payload = {
        "sub": player_id,
        "iat": time.time(),
        "exp": time.time() + 8 * 60 * 60,
        "type": "refresh",
        "jti": str(uuid.uuid4())  # unique token ID for rotation
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

---

## WebSocket Ticket Flow

The access token **cannot** be attached directly to a WebSocket handshake (browsers cannot set custom headers on WebSocket upgrades). Instead, we use a **single-use ticket**:

```python
@app.post("/auth/ws-ticket")
async def get_ws_ticket(request: Request):
    """
    Validates access token and issues a single-use WebSocket ticket.
    Ticket is one-time use with 60-second TTL.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    access_token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Not an access token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    player_id = payload["sub"]
    ws_ticket = str(uuid.uuid4())

    # Store ticket with 60-second TTL
    redis_client.setex(f"ws_ticket:{ws_ticket}", 60, player_id)

    return {"ws_ticket": ws_ticket}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, ticket: str = Query(...)):
    """
    Consume one-time WebSocket ticket, then proceed with normal WebSocket flow.
    """
    player_id = redis_client.getdel(f"ws_ticket:{ticket}")  # atomic get + delete
    if not player_id:
        await websocket.close(code=1008, reason="Invalid or expired ticket")
        return

    await connection_manager.connect(player_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            await handle_message(player_id, data)
    finally:
        connection_manager.disconnect(player_id)
```

---

## Adding Google OAuth Later

When the engine moves off a private LAN, OAuth can be added as a second provider **without changing the `PlayerAuth` shape**:

```python
@app.post("/auth/oauth/google/callback")
async def google_oauth_callback(code: str, state: str):
    """
    Exchange Google authorization code for ID token.
    Verify token, extract google_sub claim, look up or create PlayerAuth.
    """
    # 1. Exchange code for ID token (via Google token endpoint)
    id_token = google_client.exchange_code_for_token(code)
    claims = jwt.decode(id_token, options={"verify_signature": False})

    google_sub = claims["sub"]
    email = claims["email"]

    # 2. Look up PlayerAuth where provider="google" and provider_subject=google_sub
    auth = db.query(PlayerAuth).filter(
        PlayerAuth.provider == "google",
        PlayerAuth.provider_subject == google_sub
    ).first()

    if not auth:
        # 3. First OAuth login for this Google account — create Player + PlayerAuth
        player = Player(
            id=str(uuid.uuid4()),
            username=email.split("@")[0],  # or prompt user to choose
            current_room_id=config.SPAWN_ROOM_ID,
            # ... other init ...
        )
        db.add(player)
        db.flush()

        auth = PlayerAuth(
            player_id=player.id,
            provider="google",
            provider_subject=google_sub,
            created_at=time.time(),
            last_login_at=time.time(),
        )
        db.add(auth)
    else:
        # 4. Existing account — update last_login_at
        auth.last_login_at = time.time()

    db.commit()

    # 5. Issue tokens (same as local auth path)
    access_token = issue_access_token(auth.player_id, auth.player.username)
    refresh_token = issue_refresh_token(auth.player_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "player_id": auth.player_id
    }
```

---

## Security Notes for LAN Deployment

- **No HTTPS required** if the server and clients are on the same LAN.
- **Passwords are hashed** (bcrypt/argon2); never stored plaintext.
- **JWT uses a shared SECRET_KEY** — rotate it only during maintenance (all sessions invalidate on secret rotation).
- **WebSocket tickets are one-time use** — stealing a ticket after it's consumed is useless.

---

## Refresh Token Rotation

Refresh tokens should rotate on every use (new token issued, old token invalidated):

```python
@app.post("/auth/refresh")
async def refresh_access_token(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    player_id = payload["sub"]
    player = db.query(Player).filter(Player.id == player_id).first()

    if not player:
        raise HTTPException(status_code=401, detail="Player not found")

    # Issue new access token
    new_access = issue_access_token(player.id, player.username)
    # Issue new refresh token (old one is implicitly invalid now)
    new_refresh = issue_refresh_token(player.id)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh
    }
```

---

## TUI Admin Credentials

The admin TUI stores credentials in `~/.config/{game_name}-admin/credentials.json` with mode `0600`:

```json
{
  "server_url": "http://localhost:8000",
  "username": "admin",
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "refresh_token_expires_at": 1719345600.0
}
```

On TUI startup, the app checks if the stored refresh token is still valid. If not, it prompts for username/password to log in again.

---

*This implementation is intentionally minimal for LAN play. When moving to a public deployment, revisit login rate limiting, password reset flow, and email verification.*
