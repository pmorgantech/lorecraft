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
};

const elements = {
  connectForm: document.querySelector("#connect-form"),
  playerId: document.querySelector("#player-id"),
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

  renderStatus();
  renderInventory();
  renderMap();
}

function renderStatus() {
  const room = state.rooms[state.roomId];
  elements.roomStatus.textContent = room?.name || state.roomId || "unknown";
  elements.sessionStatus.textContent = state.sessionId || "none";
  elements.roomSummary.textContent = room?.description || "not connected";
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
}

function renderInventory() {
  elements.inventoryList.replaceChildren();
  elements.inventoryCount.textContent = String(state.inventory.length);

  for (const item of state.inventory) {
    const node = document.createElement("li");
    node.className =
      "rounded-md border border-[var(--muted)] bg-[var(--bg-raised)] p-3";

    const name = document.createElement("div");
    name.className = "text-sm font-bold text-[var(--amber)]";
    name.textContent = item.name || item.id;

    const description = document.createElement("p");
    description.className = "mt-1 text-xs leading-5 text-[var(--text-dim)]";
    description.textContent = item.description || "";

    node.append(name, description);
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
    x: 28 + ((node.map_x - bounds.minX) / width) * 164,
    y: 28 + ((node.map_y - bounds.minY) / height) * 164,
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
    applyUpdates(message.updates || {});
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
appendMessage("system", "Enter a player id and connect.");

window.lorecraftClient = {
  state,
  applyUpdates,
  routeMessage,
  renderInventory,
  renderMap,
  websocketUrl,
};
