# Lorecraft — Classic mode (htmx export)

A self-contained, framework-free version of the "classic" old-MUD pane.
Plain HTML + one `<style>` block. Open `index.html` in a browser to see it;
drop the markup into your htmx server templates as-is.

## Files
- `index.html` — full page shell + all styles. This is the layout host.
- `partials/room.html` — room readout fragment (name → description → items → occupants).
- `partials/chat.html` — a single chat line fragment.
- `partials/minimap.html` — the compass minimap SVG fragment.

## Layout
```
┌───────────────────────────── mud__bar (status line) ─────────────────────────────┐
│ mud__main (chronicle, flex:1)                       │ mud__side (420px)           │
│  ├ #chronicle  (scrolling log)                      │  ├ panel--map  #minimap     │
│  └ mud__prompt (#vitals + command input)            │  └ panel--chat #chat + input│
└───────────────────────────────────────────────────────────────────────────────────┘
```

## htmx wiring (swap targets already set in index.html)
- **Command line** → `hx-post="/command"`, appended to `#chronicle`
  (`hx-swap="beforeend scroll:bottom"`). Your `/command` response = the
  `partials/room.html` style fragment. Include an `hx-swap-oob` `#vitals`
  (and `#minimap` on movement) in the same response to refresh them in one trip.
- **Chat line** → `hx-post="/chat"`, appended to `#chat`.
- **Movement** → return an out-of-band `<div id="minimap" hx-swap-oob="true">…</div>`
  (see `partials/minimap.html`) plus the new room block for `#chronicle`.

## Theming / player controls
All colors are CSS variables on `:root` (`--fg`, `--item`, `--hp`, …).
Two ready toggles (wire to buttons or a settings menu):
- `document.body.classList.toggle('no-crt')` — scanlines on/off.
- `document.body.classList.toggle('amber')` — green ⇄ amber CRT palette
  (the `body.amber` block redefines the same variables).

## Line class reference (use in server fragments)
- `.echo` — command echo (`> look`)
- `.room-name`, `.room-desc`
- `.item` / `.item b` — items (b = highlighted noun)
- `.char` / `.char b` — occupants
- `.say--self`, `.say`, `.sys` — speech / system lines
- `.tight` — reduces bottom margin to group adjacent lines
- Chat: `.chan`, `.chan--ooc`, `.chan--trade`, `.who`, `.who--self`

## Notes
- htmx is loaded from a CDN in `index.html`; vendor your own copy for production.
- Fonts load from Google Fonts (IBM Plex Mono); self-host if you prefer.
