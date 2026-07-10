---
name: webui-theming
description: Create or modify Lorecraft player-webui theming — Layouts (panel arrangement + typography) and Color schemes (colours only), the CSS custom-property token architecture in custom.css, per-mode template shells (game_dock/game_ereader/game_immersive/game_classic.html), preferences.py, and the settings/top-bar pickers. Use when asked to add a layout, add a color scheme, retint a scheme, restyle a panel, fix minimap/compass rendering, or make the UI match a docs/lorecraft-export/ reference mockup.
---

# Lorecraft webui theming

Use the canonical repo skill at `.agents/skills/webui-theming/SKILL.md` — read that file
directly before touching any player-webui theming code.

Quick orientation (full detail is in the canonical file): a **Theme** is the combination
of a **Layout** (panel arrangement + typography — `preferences.py`'s `LAYOUTS`) and a
**Color scheme** (colours only, never typography — `THEMES`). The two axes are
deliberately decoupled across `preferences.py` (valid values + resolution),
`static/css/custom.css` (`body.theme-*` = colour tokens, `body.layout-*` = typography +
bespoke shell CSS), `templates/base.html` (Tailwind semantic-colour config + body-class
wiring), and `templates/game.html` (dispatches to a bespoke shell partial per layout,
e.g. `partials/game_dock.html`).

The canonical file covers: the full token architecture, the `MODE_DEFAULT_THEME`
"3-places gotcha" (duplicated in `preferences.py` + two JS literals — miss one and
previews flash the wrong scheme), `MUD_CHRONICLE_LAYOUTS`, the bare-content convention
for `partials/minimap.html`, step-by-step recipes for adding a scheme or a layout, the
testing/live-verification recipe, and a list of previously-real bugs to not repeat.
