/**
 * Lorecraft Frontend - Minimal JS (HTMX + Alpine do the heavy lifting)
 *
 * Responsibilities:
 * - WebSocket connection + reconnect logic (for server push notifications)
 * - On WS message: trigger targeted HTMX updates or append feed items
 * - Command history (keyboard arrows) - works alongside Alpine in game.html
 * - Global keyboard shortcuts
 * - Small utilities (scroll, flash, etc.)
 */

(function () {
  "use strict";

  let ws = null;
  let wsReady = false;
  let reconnectAttempts = 0;
  const MAX_RECONNECT = 10;
  let commandHistory = [];
  let historyIndex = -1;

  // === WebSocket Management ===
  // The signed `lorecraft_session` cookie (set by /lobby/enter or
  // /lobby/create) authenticates a POST /auth/ws-ticket request, which mints
  // a single-use, short-TTL ticket. Browsers can't attach custom headers to
  // a WebSocket upgrade, hence the ticket exchange instead of connecting
  // with the session directly.
  async function connectWebSocket() {
    const wsPath = window.LORECRAFT_WS_PATH || "/ws";
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const base =
      window.LORECRAFT_WS_URL ||
      `${protocol}//${window.location.host}${wsPath}`;

    let ticket;
    try {
      const resp = await fetch("/auth/ws-ticket", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!resp.ok) {
        console.log(
          "[Lorecraft] No active session, skipping WS connection (ws-ticket request returned",
          resp.status,
          ")",
        );
        return;
      }
      const data = await resp.json();
      ticket = data.ws_ticket;
    } catch (e) {
      console.error("[Lorecraft] Failed to fetch WS ticket:", e);
      return;
    }

    const wsUrl = `${base}${base.includes("?") ? "&" : "?"}ticket=${encodeURIComponent(ticket)}`;

    console.log("[Lorecraft] Connecting to WS");

    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      console.log("[Lorecraft] WebSocket connected");
      reconnectAttempts = 0;
      wsReady = true;

      // Optional: send auth/identify message if your backend expects it
      // ws.send(JSON.stringify({ type: 'identify', player_id: CURRENT_PLAYER_ID }));

      // Visual feedback
      const statusDot = document.querySelector(".w-2.h-2.rounded-full");
      if (statusDot) statusDot.classList.add("bg-emerald-500");
    };

    ws.onmessage = function (event) {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.warn("[Lorecraft] Non-JSON WS message:", event.data);
        return;
      }

      handleWebSocketMessage(data);
    };

    ws.onclose = function () {
      console.log("[Lorecraft] WebSocket disconnected");
      wsReady = false;
      const statusDot = document.querySelector(".w-2.h-2.rounded-full");
      if (statusDot) statusDot.classList.remove("bg-emerald-500");

      // Reconnect with backoff
      if (reconnectAttempts < MAX_RECONNECT) {
        const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 15000);
        reconnectAttempts++;
        console.log(
          `[Lorecraft] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})...`,
        );
        setTimeout(connectWebSocket, delay);
      }
    };

    ws.onerror = function (err) {
      console.error("[Lorecraft] WebSocket error:", err);
    };
  }

  function handleWebSocketMessage(data) {
    // Expected message shapes from backend (customize to your event system):
    // { type: 'feed_append', html: '<div class="msg...">...</div>' }
    // { type: 'panel_update', panel: 'room-description', html: '...' }
    // { type: 'state_change', affected: ['room-description', 'inventory'] }
    // { type: 'world_event', text: 'The ground shakes...', level: 'important' }

    switch (data.type) {
      case "feed_append":
      case "feed_new":
        const feedEl = document.getElementById("feed");
        if (feedEl && data.since !== undefined) {
          // Preferred append-only path: server tells us the new since value or we use current data-last-id
          const lastId = feedEl.dataset.lastId || data.since || 0;
          htmx
            .ajax("GET", `/partials/feed?since=${lastId}`, {
              target: feedEl,
              swap: "beforeend",
            })
            .then(() => {
              // Update the last-id from the newest inserted element (or trust server)
              const newLast = feedEl.lastElementChild?.dataset?.msgId;
              if (newLast) feedEl.dataset.lastId = newLast;
              feedEl.scrollTop = feedEl.scrollHeight;
            });
        } else if (data.html || data.content || data.text) {
          // Chat/feed split (Sprint 45): chat-tagged broadcasts go to the
          // chat pane when the separate_chat preference rendered one;
          // otherwise they fall into the single feed like before.
          if (data.message_type === "chat") {
            // Per-channel mute (Sprint 45.3): drop other players' chat
            // client-side when muted (own echo arrives via command_result).
            if (window.LORECRAFT_MUTE_CHAT) break;
            appendToChat(data.html || data.content || data.text);
          } else {
            appendToFeed(data.html || data.content || data.text);
          }
        }
        break;

      case "room_event":
        if (data.messages && Array.isArray(data.messages)) {
          data.messages.forEach((msg) => appendToFeed(msg));
        } else if (data.text) {
          appendToFeed(data.text);
        }
        break;

      case "panel_update":
      case "partial_update":
        if (data.panel && data.html) {
          const target = document.getElementById(data.panel);
          if (target) {
            target.outerHTML = data.html;
            // Re-process any HTMX attributes in the new content
            if (window.htmx) htmx.process(target.parentNode || document.body);
          }
        } else if (data.target && data.html) {
          const el = document.querySelector(data.target);
          if (el) el.outerHTML = data.html;
        }
        break;

      case "state_change":
      case "world_update":
        // Refresh multiple panels without full page reload
        const panels = data.affected_panels ||
          data.panels || ["room-description", "inventory", "players-online"];
        panels.forEach((panelId) => {
          const el = document.getElementById(panelId);
          if (!el) return;
          if (panelId === "players-online") {
            refreshPlayersOnline();
            return;
          }
          htmx.ajax("GET", `/partials/${panelId}`, {
            target: el,
            swap: "outerHTML",
          });
        });
        break;

      case "feed_refresh":
        // Full feed replace (use when many changes or initial sync)
        const feed = document.getElementById("feed");
        if (feed) {
          htmx
            .ajax("GET", "/partials/feed", {
              target: feed,
              swap: "innerHTML",
            })
            .then(() => {
              feed.scrollTop = feed.scrollHeight;
            });
        }
        break;

      case "player_joined":
      case "player_left":
        refreshPlayersOnline();
        break;

      case "connected":
      case "reconnect_sync":
        console.log(
          "[Lorecraft] WS session ready for player",
          data.player_id || data.player?.id || "unknown",
        );
        if (data.updates?.time) {
          updateWorldClock(data.updates.time);
        }
        refreshPlayersOnline();
        break;

      case "time_update":
      case "clock_tick":
        if (data.hour !== undefined) {
          updateWorldClock(data);
        }
        break;

      case "transit_update":
        updateTransitMarker(data);
        break;

      default:
        console.log("[Lorecraft] Unhandled WS message type:", data.type, data);
        // Fallback: if server sends raw HTML snippet
        if (data.html && data.target) {
          const el = document.querySelector(data.target);
          if (el) {
            if (data.swap === "beforeend") {
              el.insertAdjacentHTML("beforeend", data.html);
              el.scrollTop = el.scrollHeight;
            } else {
              el.outerHTML = data.html;
            }
          }
        }
    }
  }

  function refreshPlayersOnline() {
    const playersEl = document.getElementById("players-online");
    if (!playersEl || !window.htmx) return;
    htmx.ajax("GET", "/partials/players-online", {
      target: playersEl,
      swap: "outerHTML",
    });
  }

  function updateWorldClock(time) {
    const el = document.getElementById("world-clock");
    if (!el || !time) return;
    const hour = time.hour ?? 0;
    const minute = time.minute ?? 0;
    el.textContent = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  }

  function updateTransitMarker(data) {
    // Handle transit_update WS message: upsert a vehicle marker on the minimap
    // Format: { type: 'transit_update', line_id, mode, from, to, progress, eta_ticks }
    if (!data.line_id || data.progress === undefined) return;

    const minimap = document.getElementById("minimap");
    if (!minimap) return;

    // Compute interpolated position: lerp(from, to, progress)
    const x = data.from.x + (data.to.x - data.from.x) * data.progress;
    const y = data.from.y + (data.to.y - data.from.y) * data.progress;

    // Remove existing marker for this line if present
    const existing = minimap.querySelector(
      `[data-transit-line="${data.line_id}"]`,
    );
    if (existing) existing.remove();

    // If progress >= 1, arrival is imminent/done; don't re-render (final message will clear)
    if (data.progress >= 1.0) return;

    // Create a new marker with mode-specific icon
    // Mode icons: ferry ⛴, rail 🚂, balloon 🎈, caravan 🐎, coach 🚌, etc.
    const modeIcons = {
      ferry: "⛴",
      rail: "🚂",
      balloon: "🎈",
      caravan: "🐎",
      coach: "🚌",
      default: "🚚",
    };
    const icon = modeIcons[data.mode] || modeIcons.default;

    // Scale minimap coords to SVG viewport (30–190 range for 160px viewport)
    // This matches the logic in mapToScaledCoordinates
    const minX = Math.min(
      ...Object.values(state.rooms).map((r) => r.map_x ?? 0),
    );
    const maxX = Math.max(
      ...Object.values(state.rooms).map((r) => r.map_x ?? 0),
    );
    const minY = Math.min(
      ...Object.values(state.rooms).map((r) => r.map_y ?? 0),
    );
    const maxY = Math.max(
      ...Object.values(state.rooms).map((r) => r.map_y ?? 0),
    );

    const width = Math.max(maxX - minX, 1);
    const height = Math.max(maxY - minY, 1);

    const svgX = 30 + ((x - minX) / width) * 160;
    const svgY = 30 + ((y - minY) / height) * 160;

    // Create a text element to display the vehicle icon
    const marker = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "text",
    );
    marker.setAttribute("x", String(svgX));
    marker.setAttribute("y", String(svgY));
    marker.setAttribute("text-anchor", "middle");
    marker.setAttribute("dominant-baseline", "middle");
    marker.setAttribute("font-size", "20");
    marker.setAttribute("data-transit-line", data.line_id);
    marker.setAttribute("class", "transit-marker");
    marker.textContent = icon;

    minimap.appendChild(marker);
  }

  function appendToFeed(htmlOrText) {
    const feed = document.getElementById("feed");
    if (!feed) return;

    if (typeof htmlOrText === "string" && htmlOrText.trim().startsWith("<")) {
      // Server sent ready-to-insert HTML fragment
      feed.insertAdjacentHTML("beforeend", htmlOrText);
      // Process any HTMX bindings in the new node
      const lastChild = feed.lastElementChild;
      if (lastChild && window.htmx) htmx.process(lastChild);
    } else {
      // Plain text fallback - create simple message
      const div = document.createElement("div");
      div.className = "msg narrative text-zinc-400";
      div.innerHTML = `<span>${htmlOrText}</span>`;
      feed.appendChild(div);
    }

    // Auto-scroll if user is near bottom
    const threshold = 80;
    const isNearBottom =
      feed.scrollHeight - feed.scrollTop - feed.clientHeight < threshold;
    if (isNearBottom) {
      feed.scrollTop = feed.scrollHeight;
    }
  }

  function appendToChat(htmlOrText) {
    // Chat/feed split (Sprint 45): target the chat pane; without one
    // (separate_chat preference off) chat degrades into the single feed.
    const chatFeed = document.getElementById("chat-feed");
    if (!chatFeed) {
      appendToFeed(htmlOrText);
      return;
    }

    if (typeof htmlOrText === "string" && htmlOrText.trim().startsWith("<")) {
      chatFeed.insertAdjacentHTML("beforeend", htmlOrText);
      const lastChild = chatFeed.lastElementChild;
      if (lastChild && window.htmx) htmx.process(lastChild);
    } else {
      const div = document.createElement("div");
      div.className = "msg chat text-zinc-200";
      div.innerHTML = `<span>${htmlOrText}</span>`;
      chatFeed.appendChild(div);
    }
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  // === Command History (works with or without Alpine x-model) ===
  function setupCommandHistory() {
    const input = document.getElementById("command-input");
    if (!input) return;

    // Load from localStorage if wanted (optional persistence)
    try {
      const saved = localStorage.getItem("lorecraft_cmd_history");
      if (saved) commandHistory = JSON.parse(saved).slice(-50); // keep last 50
    } catch (e) {}

    // Setting .value directly (as the history recall below does) never
    // fires a native "input" event, so Alpine's x-model="localCommand"
    // binding on this field never sees the change -- localCommand stays
    // stale (usually ""), which keeps the Send button's
    // :disabled="!localCommand.trim()" true even though the field visibly
    // shows recalled text, and a disabled submit control blocks Enter from
    // submitting the form. Dispatch a real "input" event after every
    // programmatic .value write so Alpine's model stays in sync.
    function setInputValue(value) {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }

    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (commandHistory.length === 0) return;

        if (historyIndex === -1) {
          historyIndex = commandHistory.length - 1;
        } else if (historyIndex > 0) {
          historyIndex--;
        }
        setInputValue(commandHistory[historyIndex] || "");
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (historyIndex === -1) return;

        if (historyIndex < commandHistory.length - 1) {
          historyIndex++;
          setInputValue(commandHistory[historyIndex]);
        } else {
          historyIndex = -1;
          setInputValue("");
        }
      } else if (e.key === "Enter" && !e.shiftKey) {
        // Record in history (after form submit or here)
        const val = input.value.trim();
        if (
          val &&
          (commandHistory.length === 0 ||
            commandHistory[commandHistory.length - 1] !== val)
        ) {
          commandHistory.push(val);
          if (commandHistory.length > 50) commandHistory.shift();
          try {
            localStorage.setItem(
              "lorecraft_cmd_history",
              JSON.stringify(commandHistory),
            );
          } catch (e) {}
        }
        historyIndex = -1;
      }
    });

    // Expose for game.html / other code if needed.
    // "clear" wipes everything (rarely wanted). Prefer resetIndex after submit.
    window.LorecraftCommandHistory = {
      add: (cmd) => {
        if (
          cmd &&
          (commandHistory.length === 0 || commandHistory.at(-1) !== cmd)
        ) {
          commandHistory.push(cmd);
        }
      },
      clear: () => {
        commandHistory = [];
        historyIndex = -1;
      },
      resetIndex: () => {
        historyIndex = -1;
      },
    };
  }

  // === Public API / Utilities ===
  window.Lorecraft = {
    refreshPanel: function (panelId) {
      const el = document.getElementById(panelId);
      if (el) {
        htmx.ajax("GET", `/partials/${panelId}`, {
          target: el,
          swap: "outerHTML",
        });
      }
    },

    sendCommand: function (cmd) {
      const form = document.getElementById("command-form");
      const input = document.getElementById("command-input");
      if (input) input.value = cmd;
      if (form) {
        // Trigger HTMX submit
        htmx.trigger(form, "submit");
      }
    },

    // For backend to push HTML directly if desired
    handlePushHTML: appendToFeed,

    // True once the WS handshake completes (ws.onopen), false after close.
    // Exposed for console debugging and as the e2e "WS-settled" signal, since
    // the header status dot is server-rendered with bg-emerald-500 already and
    // so can't distinguish "connecting" from "connected".
    isConnected: () => wsReady,

    // Force-close the live socket to exercise the reconnect/backoff path.
    // A debugging aid (drop the connection and watch it come back) that also
    // lets e2e tests trigger a genuine reconnect — Playwright's
    // context.set_offline() does NOT sever an already-open WebSocket, so it
    // can't stand in for a real drop.
    debugDropSocket: () => {
      if (ws) ws.close();
    },
  };

  // === Boot ===
  function boot() {
    // Connect WS as soon as possible
    connectWebSocket();

    // Setup history navigation
    setupCommandHistory();

    // Optional: ping to keep connection alive (if backend requires)
    setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        // ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    console.log(
      "%c[Lorecraft] Frontend initialized (HTMX + Alpine + minimal JS)",
      "color:#10b981",
    );
  }

  // Ensure command input clears on successful submit (HTMX), while history
  // (readline arrows) continues to work from the keydown listener above.
  function setupCommandClearOnSubmit() {
    document.body.addEventListener("htmx:afterRequest", function (evt) {
      const form = evt.detail.elt;
      if (!form || form.id !== "command-form") return;

      // Only act on successful requests (no network/htmx error)
      const xhr = evt.detail.xhr;
      if (xhr && (xhr.status < 200 || xhr.status >= 300)) return;

      const input = document.getElementById("command-input");
      if (input) {
        input.value = "";

        // Reset readline browsing index (history list itself is preserved)
        historyIndex = -1;

        // Also clear Alpine model on the form if present
        if (window.Alpine && form) {
          try {
            const data = window.Alpine.$data(form);
            if (data && typeof data === "object") data.localCommand = "";
          } catch (_) {}
        }

        // Focus so the user can immediately type the next command
        setTimeout(() => input.focus(), 0);
      }
    });
  }

  // Auto-boot when script loads
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Also wire the clear-on-submit behavior (can be called early too)
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupCommandClearOnSubmit);
  } else {
    setupCommandClearOnSubmit();
  }
})();
