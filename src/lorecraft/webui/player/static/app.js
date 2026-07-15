const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  socket: null,
  playerId: "",
  sessionId: "",
  roomId: "",
  connected: false,
  messages: [],
  rooms: {},
  inventory: [],
  time: {},
  activeQuests: {},
};

const elements = {
  connectForm: document.querySelector("#connect-form"),
  playerId: document.querySelector("#player-id"),
  disconnectRow: document.querySelector("#disconnect-row"),
  disconnectBtn: document.querySelector("#disconnect-btn"),
  connectionState: document.querySelector("#connection-state"),
  roomStatus: document.querySelector("#room-status"),
  timeStatus: document.querySelector("#time-status"),
  weatherStatus: document.querySelector("#weather-status"),
  sessionStatus: document.querySelector("#session-status"),
  roomSummary: document.querySelector("#room-summary"),
  mapRoomLabel: document.querySelector("#map-room-label"),
  minimap: document.querySelector("#minimap"),
  inventoryList: document.querySelector("#inventory-list"),
  inventoryCount: document.querySelector("#inventory-count"),
  feed: document.querySelector("#message-feed"),
  commandForm: document.querySelector("#command-form"),
  commandInput: document.querySelector("#command-input"),
  commandButton: document.querySelector("#command-form button"),
  dialogueOverlay: document.querySelector("#dialogue-overlay"),
  dialogueNpcName: document.querySelector("#dialogue-npc-name"),
  dialogueNodeText: document.querySelector("#dialogue-node-text"),
  dialogueChoices: document.querySelector("#dialogue-choices"),
  dialogueClose: document.querySelector("#dialogue-close"),
  questList: document.querySelector("#quest-list"),
  roomInfo: document.querySelector("#room-info"),
  roomNameDisplay: document.querySelector("#room-name-display"),
  roomDescDisplay: document.querySelector("#room-desc-display"),
  exitCompass: document.querySelector("#exit-compass"),
};

function websocketUrl(playerId) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL("/ws", `${protocol}//${window.location.host}`);
  url.searchParams.set("player_id", playerId);
  return url.toString();
}

function setConnection(status, className = "") {
  elements.connectionState.textContent = status;
  elements.connectionState.className =
    `connection-state text-xs uppercase text-[var(--text-dim)] ${className}`.trim();
}

function setCommandEnabled(enabled) {
  elements.commandInput.disabled = !enabled;
  elements.commandButton.disabled = !enabled;
  elements.playerId.disabled = enabled;
  elements.disconnectRow?.classList.toggle("hidden", !enabled);
}

function appendMessage(kind, text) {
  const entry = { kind, text };
  state.messages.push(entry);

  const node = document.createElement("li");
  node.dataset.kind = kind;
  node.textContent = text;
  elements.feed.append(node);
  elements.feed.scrollTop = elements.feed.scrollHeight;
}

function applyUpdates(updates = {}) {
  if (updates.room_id) {
    state.roomId = updates.room_id;
  }
  if (updates.room) {
    state.rooms[updates.room.id] = updates.room;
    state.roomId = updates.room.id;
  }
  for (const room of updates.visited_rooms || []) {
    state.rooms[room.id] = room;
  }
  if (Array.isArray(updates.inventory)) {
    state.inventory = updates.inventory;
  }
  if (updates.time) {
    state.time = updates.time;
  }
  if ("dialogue" in updates) {
    updates.dialogue ? showDialogue(updates.dialogue) : hideDialogue();
  }
  if (updates.quest_update) {
    applyQuestUpdate(updates.quest_update);
  }

  renderStatus();
  renderInventory();
  renderMap();
}

function showDialogue(data) {
  if (!elements.dialogueOverlay) return;
  elements.dialogueNpcName.textContent = data.npc_name || "";
  elements.dialogueNodeText.textContent = data.node_text || "";
  elements.dialogueChoices.replaceChildren();
  for (const choice of data.choices || []) {
    const btn = document.createElement("button");
    btn.className =
      "w-full text-left rounded-md border border-[var(--muted)] bg-[var(--bg-raised)] px-3 py-2 text-sm hover:border-[var(--amber)] transition-colors";
    btn.textContent = `${choice.index}. ${choice.label}`;
    btn.addEventListener("click", () => sendCommand(`choice ${choice.index}`));
    elements.dialogueChoices.append(btn);
  }
  elements.dialogueOverlay.classList.remove("hidden");
}

function hideDialogue() {
  elements.dialogueOverlay?.classList.add("hidden");
}

function applyQuestUpdate(update) {
  if (!update) return;
  const id = update.quest_id;
  if (update.status === "completed") {
    delete state.activeQuests[id];
  } else {
    state.activeQuests[id] = {
      title: update.title || id,
      stage_description: update.stage_description || "",
    };
  }
  renderQuests();
}

function renderQuests() {
  if (!elements.questList) return;
  const quests = Object.values(state.activeQuests);
  if (quests.length === 0) {
    elements.questList.innerHTML =
      '<p class="p-4 text-sm text-[var(--text-dim)]">No active quests.</p>';
    return;
  }
  elements.questList.replaceChildren();
  for (const quest of quests) {
    const item = document.createElement("div");
    item.className = "px-4 py-3 border-b border-[var(--muted)] last:border-0";
    const title = document.createElement("div");
    title.className = "text-sm font-bold text-[var(--amber)]";
    title.textContent = quest.title;
    const desc = document.createElement("p");
    desc.className = "text-xs text-[var(--text-dim)] mt-1 leading-5";
    desc.textContent = quest.stage_description;
    item.append(title, desc);
    elements.questList.append(item);
  }
}

function renderRoomInfo() {
  const room = state.rooms[state.roomId];
  if (!room) {
    elements.roomInfo?.classList.add("hidden");
    return;
  }
  elements.roomInfo?.classList.remove("hidden");
  if (elements.roomNameDisplay)
    elements.roomNameDisplay.textContent = room.name || room.id;
  if (elements.roomDescDisplay)
    elements.roomDescDisplay.textContent = room.description || "";
  renderExitCompass(
    (room.exits || []).filter((e) => !e.hidden).map((e) => e.direction),
  );
}

const COMPASS_CELLS = [
  { dir: "nw", label: "NW" },
  { dir: "n", label: "N" },
  { dir: "ne", label: "NE" },
  { dir: "w", label: "W" },
  { dir: null, label: "◆", center: true },
  { dir: "e", label: "E" },
  { dir: "sw", label: "SW" },
  { dir: "s", label: "S" },
  { dir: "se", label: "SE" },
];

function renderExitCompass(exitDirs) {
  if (!elements.exitCompass) return;
  const exits = new Set(exitDirs);
  elements.exitCompass.replaceChildren();

  for (const cell of COMPASS_CELLS) {
    const el = document.createElement(cell.center ? "span" : "button");
    el.textContent = cell.label;
    if (cell.center) {
      el.className = "exit-cell exit-cell-center";
    } else if (exits.has(cell.dir)) {
      el.className = "exit-cell exit-cell-open";
      el.title = `Go ${cell.dir}`;
      el.addEventListener("click", () => sendCommand(`go ${cell.dir}`));
    } else {
      el.className = "exit-cell exit-cell-closed";
    }
    elements.exitCompass.append(el);
  }

  const nonCardinal = exitDirs.filter(
    (d) => !["n", "s", "e", "w", "ne", "nw", "se", "sw"].includes(d),
  );
  if (nonCardinal.length > 0 && elements.exitCompass.parentElement) {
    let extra = elements.exitCompass.parentElement.querySelector(".exit-extra");
    if (!extra) {
      extra = document.createElement("div");
      extra.className = "exit-extra mt-1 flex flex-wrap gap-1";
      elements.exitCompass.parentElement.append(extra);
    }
    extra.replaceChildren();
    for (const dir of nonCardinal) {
      const btn = document.createElement("button");
      btn.className = "exit-cell exit-cell-open px-1 w-auto text-[8px]";
      btn.textContent = dir.toUpperCase();
      btn.title = `Go ${dir}`;
      btn.addEventListener("click", () => sendCommand(`go ${dir}`));
      extra.append(btn);
    }
  }
}

function renderStatus() {
  const room = state.rooms[state.roomId];
  elements.roomStatus.textContent = room?.name || state.roomId || "unknown";
  elements.sessionStatus.textContent = state.sessionId || "none";
  elements.roomSummary.textContent = room?.name || "not connected";
  elements.mapRoomLabel.textContent = room?.id || "unknown";

  if (
    typeof state.time.hour === "number" &&
    typeof state.time.minute === "number"
  ) {
    const hour = String(state.time.hour).padStart(2, "0");
    const minute = String(state.time.minute).padStart(2, "0");
    elements.timeStatus.textContent = `${hour}:${minute} day ${state.time.day || 1}`;
  } else {
    elements.timeStatus.textContent = "--:--";
  }

  const weather = [state.time.weather, state.time.season]
    .filter(Boolean)
    .join(" / ");
  elements.weatherStatus.textContent = weather || "unknown";
  renderRoomInfo();
}

function groupInventory(items) {
  const groups = new Map();
  for (const item of items) {
    const quantity = item.quantity ?? 1;
    const entry = groups.get(item.id);
    if (entry) {
      entry.count += quantity;
    } else {
      groups.set(item.id, { ...item, count: quantity });
    }
  }
  return [...groups.values()];
}

function renderInventory() {
  elements.inventoryList.replaceChildren();
  const groups = groupInventory(state.inventory);
  elements.inventoryCount.textContent = String(
    groups.reduce((total, item) => total + item.count, 0),
  );
  for (const item of groups) {
    const node = document.createElement("li");
    node.className =
      "flex items-center gap-2 rounded-md border border-[var(--muted)] bg-[var(--bg-raised)] px-3 py-2 cursor-pointer hover:border-[var(--phosphor)] transition-colors";

    const name = document.createElement("span");
    name.className = "text-sm text-[var(--amber)] flex-1 min-w-0 truncate";
    const label = item.name || item.id;
    name.textContent = item.count > 1 ? `[${item.count}] ${label}` : label;

    node.append(name);

    node.addEventListener("click", () => {
      appendMessage(
        "response",
        `${item.name || item.id}: ${item.description || "No description."}`,
      );
    });

    elements.inventoryList.append(node);
  }
}

function renderMap() {
  elements.minimap.replaceChildren();

  const nodes = mapNodes();
  if (nodes.length === 0) {
    appendSvgText(elements.minimap, 110, 110, "No map", "map-label");
    return;
  }

  const bounds = mapBounds(nodes);
  const points = new Map(
    nodes.map((node) => [node.key, mapPoint(node, bounds)]),
  );

  for (const link of mapLinks(nodes)) {
    const from = points.get(link.fromKey);
    const to = points.get(link.toKey);
    if (!from || !to) {
      continue;
    }
    appendSvgLine(
      elements.minimap,
      from.x,
      from.y,
      to.x,
      to.y,
      link.known ? "map-link is-known" : "map-link",
    );
    const hitTarget = appendSvgLine(
      elements.minimap,
      from.x,
      from.y,
      to.x,
      to.y,
      "map-hit-target",
    );
    hitTarget.addEventListener("click", () =>
      sendCommand(`go ${link.direction}`),
    );
  }

  for (const node of nodes) {
    const point = points.get(node.key);
    if (!point) {
      continue;
    }
    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("cx", String(point.x));
    circle.setAttribute("cy", String(point.y));
    circle.setAttribute("r", node.current ? "13" : "10");
    circle.setAttribute("class", mapRoomClass(node));
    if (node.direction) {
      circle.addEventListener("click", () =>
        sendCommand(`go ${node.direction}`),
      );
    }
    elements.minimap.append(circle);

    appendSvgText(
      elements.minimap,
      point.x,
      point.y,
      node.label,
      node.current ? "map-label is-current" : "map-label",
    );
  }
}

function mapNodes() {
  const nodes = Object.values(state.rooms).map((room) => ({
    key: room.id,
    id: room.id,
    label: shortLabel(room.name || room.id),
    map_x: room.map_x,
    map_y: room.map_y,
    known: true,
    current: room.id === state.roomId,
  }));
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const currentRoom = state.rooms[state.roomId];

  for (const exit of currentRoom?.exits || []) {
    if (exit.hidden || exit.visited || typeof exit.target_map_x !== "number") {
      continue;
    }
    const key = `fog:${exit.target_room_id}`;
    if (!byKey.has(key)) {
      byKey.set(key, {
        key,
        id: exit.target_room_id,
        label: "?",
        map_x: exit.target_map_x,
        map_y: exit.target_map_y,
        known: false,
        current: false,
        direction: exit.direction,
      });
    }
  }

  return [...byKey.values()];
}

function mapLinks(nodes) {
  const nodeKeys = new Set(nodes.map((node) => node.key));
  const links = [];

  for (const room of Object.values(state.rooms)) {
    for (const exit of room.exits || []) {
      if (exit.hidden) {
        continue;
      }
      const fogKey = `fog:${exit.target_room_id}`;
      const toKey = nodeKeys.has(exit.target_room_id)
        ? exit.target_room_id
        : fogKey;
      if (!nodeKeys.has(toKey)) {
        continue;
      }
      links.push({
        fromKey: room.id,
        toKey,
        direction: exit.direction,
        known: nodeKeys.has(exit.target_room_id),
      });
    }
  }

  return links;
}

function mapBounds(nodes) {
  const xs = nodes.map((node) => node.map_x);
  const ys = nodes.map((node) => node.map_y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function mapPoint(node, bounds) {
  const width = Math.max(1, bounds.maxX - bounds.minX);
  const height = Math.max(1, bounds.maxY - bounds.minY);
  return {
    x: 30 + ((node.map_x - bounds.minX) / width) * 160,
    y: 30 + ((node.map_y - bounds.minY) / height) * 160,
  };
}

function mapRoomClass(node) {
  if (node.current) {
    return "map-room is-current";
  }
  if (node.known) {
    return "map-room is-known";
  }
  return "map-room is-fog";
}

function shortLabel(value) {
  const firstWord = String(value).split(/\s+/)[0] || "?";
  return firstWord.length > 8 ? `${firstWord.slice(0, 7)}.` : firstWord;
}

function appendSvgLine(parent, x1, y1, x2, y2, className) {
  const line = document.createElementNS(SVG_NS, "line");
  line.setAttribute("x1", String(x1));
  line.setAttribute("y1", String(y1));
  line.setAttribute("x2", String(x2));
  line.setAttribute("y2", String(y2));
  line.setAttribute("class", className);
  parent.append(line);
  return line;
}

function appendSvgText(parent, x, y, text, className) {
  const label = document.createElementNS(SVG_NS, "text");
  label.setAttribute("x", String(x));
  label.setAttribute("y", String(y));
  label.setAttribute("class", className);
  label.textContent = text;
  parent.append(label);
  return label;
}

function routeMessage(message) {
  if (message.type === "connected") {
    state.connected = true;
    state.playerId = message.player_id || state.playerId;
    state.roomId = message.room_id || "";
    state.sessionId = message.session_id || "";
    setConnection("online", "is-online");
    setCommandEnabled(true);
    applyUpdates(message.updates || {});
    appendMessage("system", `Connected as ${state.playerId}.`);
    return;
  }

  if (message.type === "command_result") {
    for (const text of message.messages || []) {
      appendMessage("response", text);
    }
    for (const text of message.room_messages || []) {
      appendMessage("room_event", text);
    }
    for (const entry of message.chat_messages || []) {
      // Sprint 52: entries are {text, channel} objects (plain strings before).
      appendMessage("chat", typeof entry === "string" ? entry : entry.text);
    }
    applyUpdates(message.updates || {});
    if (message.updates?.disconnect) {
      state.socket?.close(1000, "quit");
    }
    return;
  }

  if (message.type === "error") {
    appendMessage("error", message.message || "Unknown server error.");
    return;
  }

  if (message.type === "reconnect_sync") {
    state.sessionId = message.session_id || state.sessionId;
    applyUpdates(message.updates || {});
    appendMessage("system", "Session restored.");
    return;
  }

  if (message.type === "combat_update") {
    state.combat = message;
    return;
  }

  appendMessage("system", JSON.stringify(message));
}

function connect(playerId) {
  if (state.socket) {
    state.socket.close();
  }

  state.playerId = playerId;
  state.connected = false;
  state.roomId = "";
  state.rooms = {};
  state.inventory = [];
  state.time = {};
  state.activeQuests = {};
  setConnection("connecting");
  setCommandEnabled(false);
  applyUpdates({});

  const socket = new WebSocket(websocketUrl(playerId));
  state.socket = socket;

  socket.addEventListener("message", (event) => {
    routeMessage(JSON.parse(event.data));
  });

  socket.addEventListener("close", () => {
    state.connected = false;
    setConnection("offline");
    setCommandEnabled(false);
    appendMessage("system", "Disconnected.");
  });

  socket.addEventListener("error", () => {
    setConnection("error", "is-error");
    appendMessage("error", "WebSocket error.");
  });
}

function sendCommand(command) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    appendMessage("error", "Not connected.");
    return;
  }
  state.socket.send(command);
}

elements.connectForm.addEventListener("submit", (event) => {
  event.preventDefault();
  connect(elements.playerId.value.trim());
});

elements.disconnectBtn?.addEventListener("click", () => {
  state.socket?.close(1000, "user disconnect");
});

elements.dialogueClose?.addEventListener("click", () => {
  sendCommand("bye");
});

elements.commandForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const command = elements.commandInput.value.trim();
  if (!command) {
    return;
  }
  appendMessage("command", `> ${command}`);
  elements.commandInput.value = "";
  sendCommand(command);
});

renderStatus();
renderInventory();
renderMap();
renderRoomInfo();
appendMessage("system", "Enter a player id and connect.");

window.lorecraftClient = {
  state,
  applyUpdates,
  routeMessage,
  renderInventory,
  renderMap,
  renderQuests,
  websocketUrl,
};
