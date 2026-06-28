const state = {
  socket: null,
  playerId: "",
  sessionId: "",
  roomId: "",
  connected: false,
  messages: [],
};

const elements = {
  connectForm: document.querySelector("#connect-form"),
  playerId: document.querySelector("#player-id"),
  connectionState: document.querySelector("#connection-state"),
  roomStatus: document.querySelector("#room-status"),
  sessionStatus: document.querySelector("#session-status"),
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
  elements.connectionState.className = `connection-state ${className}`.trim();
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

function renderStatus() {
  elements.roomStatus.textContent = state.roomId || "unknown";
  elements.sessionStatus.textContent = state.sessionId || "none";
}

function routeMessage(message) {
  if (message.type === "connected") {
    state.connected = true;
    state.playerId = message.player_id || state.playerId;
    state.roomId = message.room_id || "";
    state.sessionId = message.session_id || "";
    setConnection("online", "is-online");
    setCommandEnabled(true);
    renderStatus();
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
    if (message.updates && message.updates.room_id) {
      state.roomId = message.updates.room_id;
      renderStatus();
    }
    return;
  }

  if (message.type === "error") {
    appendMessage("error", message.message || "Unknown server error.");
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
  setConnection("connecting");
  setCommandEnabled(false);

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
appendMessage("system", "Enter a player id and connect.");

window.lorecraftClient = {
  state,
  routeMessage,
  websocketUrl,
};
