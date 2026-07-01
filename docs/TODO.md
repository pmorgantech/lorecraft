# ToDo List

Bugs:

- [ ] Inventory quirkiness (item aliases, refer to items by shortened names, prompt for ambiguity)

ToDos:

- [x] create character does not work — `POST /lobby/create` validates + creates the player and logs in via a signed session cookie.
- [x] exposing the player id in the uri may be a security risk, esp with no auth — `/lobby/enter` and `/lobby/create` now mint a signed JWT session cookie (`lorecraft_session`, httponly) as the primary identity mechanism instead of redirecting to `/game?player_id=...`. See below for what's still open.
- [ ] no password/credential auth yet — `/lobby/enter` still lets anyone claim any existing username with no secret. Real accounts (`POST /auth/login`, register-on-first-login per `ARCHITECTURE.md` §29) are unimplemented.
- [ ] `/ws?player_id=...` still trusts the raw query param unconditionally — the WebSocket handshake doesn't verify the signed session cookie. Needs a short-lived ticket or equivalent.
- [ ] `LORECRAFT_ALLOW_QUERY_PLAYER_ID` legacy fallback (bare `?player_id=`/unsigned cookie) defaults **on** for dev/test back-compat; flip off once all callers use the signed cookie exclusively.
- [ ] timer / scheduler system
- [ ] use command, more commands!
- [ ] offline/irl commands ( /system, @someone )
- [ ] bug/todo system (letterbox, safe to update TODO.md?)
- [ ] inventory encumbrance? When/how do we get to supporting this? Carry slots, wear slots, etc.
- [ ] help system?
- [x] take N items, drop N items
- [x] exits mini-map

Wishlist:

- [ ] online todo/bug system
- [ ] playback scripts, harness for simulating many players
- [ ] sounds / music?
- [ ] GPT interface to descriptions/rooms/maps
- [ ] world building online?
