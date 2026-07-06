# Split the social/chat feed from the narrative feed — plan (Sprint 45)

**Goal:** chat must never scroll room/quest/action output out of view — the single biggest
client-UX takeaway ([`wishlist.md`](wishlist.md) → *Client UI · Separate the communication log from
the narrative feed*). Route social/chat messages into their own pane/tab, **as an opt-in player
preference** (default preserves today's single feed). Roadmap: [Sprint 45](roadmap.md).

## Current state (why there's no signal today)

Chat and ordinary room narration share **one channel end to end**:

- The only chat verb today is **`say`** (`commands/social.py`): `ctx.say('You say: "…"')` +
  `ctx.tell_room('X says: "…"')`. (shout/whisper/tell/global channels are still Backlog —
  `/system`, `@someone`.)
- `ctx.tell_room(...)` is *also* how movement etc. narrate ("X leaves north.", "X arrives from
  the south.").
- Both flow out identically: `command_result.room_messages` (own client) and
  `broadcast.broadcast_command_effects` → `broadcast_to_room({"type": "feed_append",
  "message_type": "room_event", …})` (other clients). `app.js`'s `appendMessage` puts everything in
  the single `#message-feed`.

So there is **no chat-vs-narrative signal** anywhere — the split has to introduce one.

## Design

**One new idea: a `chat` narration category, threaded end to end.** Extend each existing seam
rather than adding a parallel system (cf. §3.9 single-owner discipline).

1. **GameContext — a chat channel.** Add `ctx.say_chat(text)` (own client) and
   `ctx.tell_room_chat(text)` (room), backed by a new `chat_messages: list[str]` alongside
   `messages`/`room_messages`. `say_command` switches to these. Generic `tell_room` (movement,
   actions) is untouched → stays narrative.
2. **Protocol.** `command_result` gains a `chat_messages` field (parallel to `messages`/
   `room_messages`); `broadcast_command_effects` emits chat narration as
   `{"type": "feed_append", "message_type": "chat", …}`. One new field + one new `message_type`
   value — no protocol restructure.
3. **Preference.** `PlayerPreferences.separate_chat: bool = False` (`preferences.py` — same
   pattern as `reduced_motion`), surfaced in the settings UI and `to_context()` so the template
   knows whether to render the second pane.
4. **Client (`app.js` + `index.html` + `app.css`).** `appendMessage(kind, text, {chat})` routes
   `chat` messages to a `#chat-feed` pane **when `separate_chat` is on**; otherwise they fall back
   into `#message-feed` (today's behavior, unchanged for everyone by default). `routeMessage`
   handles `chat_messages` and `feed_append{message_type:"chat"}`. The pane is a sibling of the feed
   on desktop and **collapses to a tab on small screens** (Sprint 26 layout-budget note); channels
   get a colored/prefixed tag per the wishlist styling note.

**Scope of "chat":** `say` now; future `shout`/`whisper`/`tell`/global channels reuse the same
`chat` channel (that's the point of threading a category, not special-casing `say`). `player_joined`/
`player_left` stay **narrative/system**, not chat (they're presence, not conversation) — revisit if
a dedicated presence pane is ever wanted.

## Verification (needs a real browser)

Unit-testable (Phase 1): `say` populates `chat_messages` not `messages`; movement narration stays in
`room_messages`; `command_result` carries the field; the preference round-trips. **Phase 2 needs a
browser** (`run`/`verify` skill or an `e2e` Playwright test): a two-player scenario where A `say`s and
B sees it — in the **chat pane** with the preference on, in the **main feed** with it off — and where
"A leaves north." always lands in the narrative feed.

## Phasing

1. **Phase 1 (headless-testable)** — GameContext chat channel + `say_command` switch + `command_result.chat_messages` + `broadcast` `message_type:"chat"` + the `separate_chat` preference. Unit-tested.
2. **Phase 2 (browser)** — `app.js` dual-pane routing, `index.html` pane, `app.css` styling, settings toggle; verify in a real browser + a two-player e2e.
3. **Phase 3 (later)** — global channels (shout/tell) reuse the channel; colored/prefixed per-channel tags; mobile tab collapse polish.

## Non-goals (initially)

- No global chat channels yet (Backlog `/system`, `@someone`) — this only *makes room* for them.
- No chat history persistence beyond the existing audit log.
- Not a full multi-pane relayout (stats/vitals panel, region map) — that's a separate wishlist item.
