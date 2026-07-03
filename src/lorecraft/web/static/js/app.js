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
          appendToFeed(data.html || data.content || data.text);
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

  // === Command History (works with or without Alpine x-model) ===
  function setupCommandHistory() {
    const input = document.getElementById("command-input");
    if (!input) return;

    // Load from localStorage if wanted (optional persistence)
    try {
      const saved = localStorage.getItem("lorecraft_cmd_history");
      if (saved) commandHistory = JSON.parse(saved).slice(-50); // keep last 50
    } catch (e) {}

    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (commandHistory.length === 0) return;

        if (historyIndex === -1) {
          historyIndex = commandHistory.length - 1;
        } else if (historyIndex > 0) {
          historyIndex--;
        }
        input.value = commandHistory[historyIndex] || "";
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (historyIndex === -1) return;

        if (historyIndex < commandHistory.length - 1) {
          historyIndex++;
          input.value = commandHistory[historyIndex];
        } else {
          historyIndex = -1;
          input.value = "";
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
