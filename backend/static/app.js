// The Patrol Jetbot - Web Monitoring & Control Dashboard JavaScript
let ws = null;
let currentSpeed = 0.4;
let activeRecordingRouteId = null;
let activePatrolSessionId = null;

// DOM Elements
const connDot = document.getElementById("conn-dot");
const connText = document.getElementById("conn-text");
const modeVal = document.getElementById("mode-val");
const batteryBar = document.getElementById("battery-bar");
const batteryVal = document.getElementById("battery-val");
const wifiVal = document.getElementById("wifi-val");
const hudX = document.getElementById("hud-x");
const hudY = document.getElementById("hud-y");
const hudSpd = document.getElementById("hud-spd");
const speedSlider = document.getElementById("speed-slider");
const speedLabel = document.getElementById("speed-label");

// Patrol Elements
const patrolRouteName = document.getElementById("patrol-route-name");
const patrolStatusBadge = document.getElementById("patrol-status-badge");
const patrolProgressBar = document.getElementById("patrol-progress-bar");
const patrolPct = document.getElementById("patrol-pct");
const patrolCpVal = document.getElementById("patrol-cp-val");
const patrolObsCount = document.getElementById("patrol-obs-count");
const patrolPersonCount = document.getElementById("patrol-person-count");
const activePatrolActions = document.getElementById("active-patrol-actions");
const btnPausePatrol = document.getElementById("btn-pause-patrol");
const btnResumePatrol = document.getElementById("btn-resume-patrol");
const btnStopPatrol = document.getElementById("btn-stop-patrol");

// Route Elements
const btnStartRecord = document.getElementById("btn-start-record");
const btnStopRecord = document.getElementById("btn-stop-record");
const recordingBanner = document.getElementById("recording-banner");
const recRouteName = document.getElementById("rec-route-name");
const recCpCount = document.getElementById("rec-cp-count");
const routesTbody = document.getElementById("routes-tbody");
const btnRefreshRoutes = document.getElementById("btn-refresh-routes");

// Events Elements
const eventsTbody = document.getElementById("events-tbody");
const btnRefreshEvents = document.getElementById("btn-refresh-events");

// Modal
const snapshotModal = document.getElementById("snapshot-modal");
const modalImg = document.getElementById("modal-img");
const modalDesc = document.getElementById("modal-desc");
const modalTitle = document.getElementById("modal-title");
const btnModalClose = document.getElementById("btn-modal-close");
const modalBackdrop = document.getElementById("modal-backdrop");

// --- WebSocket Connection ---
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/web`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    connDot.className = "status-dot connected";
    connText.textContent = "Online";
  };

  ws.onclose = () => {
    connDot.className = "status-dot disconnected";
    connText.textContent = "Offline (Reconnecting...)";
    setTimeout(initWebSocket, 2000);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWebSocketMessage(msg);
    } catch (e) {
      console.error("Error parsing WS message:", e);
    }
  };
}

function handleWebSocketMessage(msg) {
  const { type, data } = msg;

  if (type === "INITIAL_STATE") {
    updateRobotUI(data.robot);
  } else if (type === "TELEMETRY") {
    updateRobotUI(data);
  } else if (type === "SECURITY_EVENT") {
    prependEventRow(data);
    showFlashNotification(data);
  } else if (type === "PATROL_STARTED") {
    activePatrolSessionId = data.session_id;
    patrolRouteName.textContent = data.route_name || data.route_id;
    updatePatrolStatusBadge("RUNNING");
    activePatrolActions.classList.remove("hidden");
    btnPausePatrol.classList.remove("hidden");
    btnResumePatrol.classList.add("hidden");
  } else if (type === "PATROL_PROGRESS") {
    patrolProgressBar.style.width = `${data.progress_percent}%`;
    patrolPct.textContent = `${data.progress_percent}%`;
    patrolCpVal.textContent = `${data.current_checkpoint_idx} / ${data.total_checkpoints}`;
    if (data.status) {
      updatePatrolStatusBadge(data.status);
      if (data.status === "COMPLETED") {
        activePatrolActions.classList.add("hidden");
      }
    }
  } else if (type === "PATROL_STATUS_CHANGED") {
    updatePatrolStatusBadge(data.status);
    if (data.status === "PAUSED") {
      btnPausePatrol.classList.add("hidden");
      btnResumePatrol.classList.remove("hidden");
    } else if (data.status === "RUNNING") {
      btnPausePatrol.classList.remove("hidden");
      btnResumePatrol.classList.add("hidden");
    } else if (data.status === "ABORTED" || data.status === "COMPLETED") {
      activePatrolActions.classList.add("hidden");
    }
  } else if (type === "TEACH_STARTED") {
    activeRecordingRouteId = data.route_id;
    recordingBanner.classList.remove("hidden");
    recRouteName.textContent = data.route_name;
    recCpCount.textContent = "0";
    btnStartRecord.classList.add("hidden");
    btnStopRecord.classList.remove("hidden");
  } else if (type === "CHECKPOINT_ADDED") {
    recCpCount.textContent = data.total_checkpoints;
  } else if (type === "TEACH_FINISHED") {
    activeRecordingRouteId = null;
    recordingBanner.classList.add("hidden");
    btnStartRecord.classList.remove("hidden");
    btnStopRecord.classList.add("hidden");
    fetchRoutes();
  }
}

function updateRobotUI(r) {
  if (!r) return;
  modeVal.textContent = r.current_mode || "IDLE";
  
  // Mode color coding
  if (r.current_mode === "BLOCKED") {
    modeVal.style.color = "var(--accent-amber)";
  } else if (r.current_mode === "EMERGENCY_STOP") {
    modeVal.style.color = "var(--accent-red)";
  } else {
    modeVal.style.color = "var(--primary)";
  }

  // Battery
  const batt = r.battery_percentage !== undefined ? r.battery_percentage : 100;
  batteryVal.textContent = `${batt.toFixed(1)}%`;
  batteryBar.style.width = `${batt}%`;
  if (batt < 20) {
    batteryBar.style.background = "var(--accent-red)";
  } else if (batt < 50) {
    batteryBar.style.background = "var(--accent-amber)";
  } else {
    batteryBar.style.background = "var(--accent-green)";
  }

  // WiFi
  wifiVal.textContent = `${r.wifi_rssi || -50} dBm`;

  // HUD
  hudX.textContent = (r.current_x || 0).toFixed(2);
  hudY.textContent = (r.current_y || 0).toFixed(2);
  hudSpd.textContent = (r.linear_speed || 0).toFixed(2);
}

function updatePatrolStatusBadge(status) {
  patrolStatusBadge.textContent = status;
  patrolStatusBadge.className = "badge";
  if (status === "RUNNING") patrolStatusBadge.classList.add("badge-blue");
  else if (status === "COMPLETED") patrolStatusBadge.classList.add("badge-green");
  else if (status === "BLOCKED" || status === "PAUSED") patrolStatusBadge.classList.add("badge-amber");
  else if (status === "ABORTED" || status === "EMERGENCY_STOPPED") patrolStatusBadge.classList.add("badge-red");
}

// --- Teleoperation Commands ---
function sendTeleop(command) {
  const payload = {
    action: "TELEOP",
    command: command,
    linear_speed: currentSpeed,
    angular_speed: 0.5
  };

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  } else {
    // Fallback to HTTP
    fetch("/api/v1/teleop/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }
}

function triggerEmergencyStop() {
  const payload = { action: "EMERGENCY_STOP", reason: "User pressed E-STOP button" };
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  } else {
    fetch("/api/v1/teleop/emergency-stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "User pressed E-STOP button" })
    });
  }
}

// Button Bindings
document.getElementById("btn-fwd").onclick = () => sendTeleop("FORWARD");
document.getElementById("btn-back").onclick = () => sendTeleop("BACKWARD");
document.getElementById("btn-left").onclick = () => sendTeleop("LEFT");
document.getElementById("btn-right").onclick = () => sendTeleop("RIGHT");
document.getElementById("btn-stop").onclick = () => sendTeleop("STOP");
document.getElementById("btn-top-estop").onclick = triggerEmergencyStop;

// Slider
speedSlider.oninput = (e) => {
  currentSpeed = parseFloat(e.target.value);
  speedLabel.textContent = currentSpeed.toFixed(2);
};

// Keyboard listener
window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  const key = e.key.toLowerCase();
  if (key === "w" || key === "arrowup") { sendTeleop("FORWARD"); e.preventDefault(); }
  else if (key === "s" || key === "arrowdown") { sendTeleop("BACKWARD"); e.preventDefault(); }
  else if (key === "a" || key === "arrowleft") { sendTeleop("LEFT"); e.preventDefault(); }
  else if (key === "d" || key === "arrowright") { sendTeleop("RIGHT"); e.preventDefault(); }
  else if (key === " " || key === "x") { sendTeleop("STOP"); e.preventDefault(); }
  else if (key === "escape") { triggerEmergencyStop(); e.preventDefault(); }
});

// --- Route Management ---
btnStartRecord.onclick = async () => {
  const name = prompt("Nhập tên hành trình tuần tra:", `Tuyến Tuần Tra ${new Date().toLocaleTimeString()}`);
  if (!name) return;

  const desc = prompt("Mô tả tuyến (tùy chọn):", "Được dạy bằng Manual Teleoperation");

  try {
    const res = await fetch("/api/v1/routes/start-recording", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: desc })
    });
    const data = await res.json();
    if (!res.ok) alert(data.detail || "Error starting recording");
  } catch (err) {
    alert("Connection error: " + err);
  }
};

btnStopRecord.onclick = async () => {
  if (!activeRecordingRouteId) return;
  try {
    const res = await fetch(`/api/v1/routes/${activeRecordingRouteId}/stop-recording`, {
      method: "POST"
    });
    const data = await res.json();
    if (!res.ok) alert(data.detail || "Error stopping recording");
  } catch (err) {
    alert("Connection error: " + err);
  }
};

async function fetchRoutes() {
  try {
    const res = await fetch("/api/v1/routes");
    const routes = await res.json();
    renderRoutesTable(routes);
  } catch (err) {
    console.error("Error fetching routes:", err);
  }
}

function renderRoutesTable(routes) {
  if (!routes || routes.length === 0) {
    routesTbody.innerHTML = `<tr><td colspan="5" class="text-muted">Chưa có hành trình nào được ghi.</td></tr>`;
    return;
  }

  routesTbody.innerHTML = routes.map(r => `
    <tr>
      <td><b>${escapeHtml(r.name)}</b><br><small class="text-muted">${escapeHtml(r.description || "")}</small></td>
      <td>${r.checkpoint_count} cps</td>
      <td>${r.total_distance.toFixed(1)} m</td>
      <td><span class="badge ${r.status === 'SAVED' ? 'badge-green' : 'badge-amber'}">${r.status}</span></td>
      <td>
        <button class="btn btn-primary btn-sm" onclick="startPatrolRoute('${r.id}')" ${r.checkpoint_count === 0 ? 'disabled' : ''}>
          Tuần Tra
        </button>
        <button class="btn btn-outline-danger btn-sm" onclick="deleteRoute('${r.id}')">
          Xóa
        </button>
      </td>
    </tr>
  `).join("");
}

window.startPatrolRoute = async (routeId) => {
  try {
    const res = await fetch("/api/v1/patrol/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_id: routeId })
    });
    const data = await res.json();
    if (!res.ok) alert(data.detail || "Error starting patrol");
  } catch (e) {
    alert("Error: " + e);
  }
};

window.deleteRoute = async (routeId) => {
  if (!confirm("Bạn có chắc chắn muốn xóa tuyến đường này không?")) return;
  try {
    await fetch(`/api/v1/routes/${routeId}`, { method: "DELETE" });
    fetchRoutes();
  } catch (e) {
    alert("Error deleting route: " + e);
  }
};

btnRefreshRoutes.onclick = fetchRoutes;

// Patrol Control Buttons
btnPausePatrol.onclick = async () => {
  if (activePatrolSessionId) {
    await fetch(`/api/v1/patrol/${activePatrolSessionId}/pause`, { method: "POST" });
  }
};

btnResumePatrol.onclick = async () => {
  if (activePatrolSessionId) {
    await fetch(`/api/v1/patrol/${activePatrolSessionId}/resume`, { method: "POST" });
  }
};

btnStopPatrol.onclick = async () => {
  if (activePatrolSessionId && confirm("Dừng phiên tuần tra hiện tại?")) {
    await fetch(`/api/v1/patrol/${activePatrolSessionId}/stop`, { method: "POST" });
  }
};

// --- Events ---
async function fetchEvents() {
  try {
    const res = await fetch("/api/v1/events?limit=20");
    const events = await res.json();
    renderEventsTable(events);
  } catch (err) {
    console.error("Error fetching events:", err);
  }
}

function renderEventsTable(events) {
  if (!events || events.length === 0) {
    eventsTbody.innerHTML = `<tr><td colspan="4" class="text-muted">Chưa có sự kiện an ninh nào.</td></tr>`;
    return;
  }
  eventsTbody.innerHTML = events.map(e => createEventRowHtml(e)).join("");
}

function prependEventRow(e) {
  const tr = document.createElement("tr");
  tr.innerHTML = createEventRowHtml(e, true);
  eventsTbody.prepend(tr);
}

function createEventRowHtml(e, innerOnly = false) {
  const dateStr = new Date(e.timestamp).toLocaleTimeString();
  let badgeClass = "badge-blue";
  if (e.event_type === "PERSON_DETECTED") badgeClass = "badge-red";
  else if (e.event_type === "OBSTACLE_BLOCKED") badgeClass = "badge-amber";
  else if (e.event_type === "OBSTACLE_CLEARED") badgeClass = "badge-green";

  const snapshotBtn = e.snapshot_url 
    ? `<button class="btn btn-outline-warning btn-sm" onclick="showSnapshot('${e.snapshot_url}', '${escapeHtml(e.description || '')}')">Xem Ảnh</button>`
    : `<span class="text-muted">-</span>`;

  const content = `
    <td><span class="badge ${badgeClass}">${e.event_type}</span></td>
    <td>${dateStr}</td>
    <td>${escapeHtml(e.description || "")}</td>
    <td>${snapshotBtn}</td>
  `;

  return innerOnly ? content : `<tr>${content}</tr>`;
}

btnRefreshEvents.onclick = fetchEvents;

window.showSnapshot = (url, desc) => {
  modalImg.src = url;
  modalDesc.textContent = desc;
  snapshotModal.classList.remove("hidden");
};

btnModalClose.onclick = () => snapshotModal.classList.add("hidden");
modalBackdrop.onclick = () => snapshotModal.classList.add("hidden");

// Flash notification on alert
function showFlashNotification(e) {
  if (e.event_type === "PERSON_DETECTED") {
    patrolPersonCount.textContent = parseInt(patrolPersonCount.textContent || 0) + 1;
  } else if (e.event_type === "OBSTACLE_BLOCKED") {
    patrolObsCount.textContent = parseInt(patrolObsCount.textContent || 0) + 1;
  }
}

// --- Simulator Triggers (from UI) ---
document.getElementById("sim-obstacle-btn").onclick = async () => {
  // Post obstacle blocked
  await fetch("/api/v1/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: "OBSTACLE_BLOCKED",
      severity: "WARNING",
      description: "Thử nghiệm giả lập: Phát hiện vật cản trước mặt 0.35m. Robot dừng khẩn cấp."
    })
  });
  setTimeout(async () => {
    // Clear obstacle after 3s
    await fetch("/api/v1/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: "OBSTACLE_CLEARED",
        severity: "INFO",
        description: "Thử nghiệm giả lập: Vật cản đã được dời đi. Robot tiếp tục tuần tra."
      })
    });
  }, 3500);
};

document.getElementById("sim-person-btn").onclick = async () => {
  await fetch("/api/v1/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: "PERSON_DETECTED",
      severity: "CRITICAL",
      confidence: 0.95,
      bounding_box: "[160, 260, 400, 370]",
      description: "Thử nghiệm giả lập: Computer Vision phát hiện 1 người trong vùng kiểm tra (độ tin cậy 95%)."
    })
  });
};

function escapeHtml(text) {
  if (!text) return "";
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Initial bootstrap
window.onload = () => {
  initWebSocket();
  fetchRoutes();
  fetchEvents();
};
