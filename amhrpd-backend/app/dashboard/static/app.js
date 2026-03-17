const STATUS_DOT = document.getElementById("status-dot");
const STATUS_TEXT = document.getElementById("status-text");
const SERVO_TABLE = document.getElementById("servo-table");
const DEVICE_STATUS = document.getElementById("device-status");
const AUDIO_LOG_TABLE = document.getElementById("audio-log-table");
const USER_REQUEST_TABLE = document.getElementById("user-request-table");
const SYSTEM_LOG_TABLE = document.getElementById("system-log-table");
const COMMAND_LOG_TABLE = document.getElementById("command-log-table");
const CONNECTION_EVENT_TABLE = document.getElementById("connection-event-table");
const CONNECTION_DEVICE_SELECT = document.getElementById("connection-device-select");

// ================== DEVICE IDS ==================

const DEVICES = {
  servo: { id: "servoscontroller", type: "esp32s3", name: "Servo Controller" },
  wheel: { id: "wheelcontroller", type: "esp32", name: "Wheel Controller" },
  cam: { id: "camcontroller", type: "esp32s3cam", name: "Camera Controller" }
};

// ================== STATE ==================

let servoStates = {};
let deviceStates = {};
let devicesList = [];

let serverSystemLogs = [];
const clientLogs = [];
const MAX_CLIENT_LOGS = 400;

const heartbeatState = {};
const heartbeatCanvases = {};

// ================== DEVICE STATUS ==================

async function pollDeviceStatus() {
  try {
    const res = await fetch("/api/devices");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    const devices = data.devices || [];
    devicesList = devices;
    
    // Update device states
    deviceStates = {};
    devices.forEach(d => { deviceStates[d.device_id] = d; });
    updateDeviceCount(devices.length);
    
    // Count online devices
    const onlineCount = devices.filter(d => d.is_online).length;
    
    if (onlineCount > 0) {
      setStatus(true, `${onlineCount}/${devices.length} devices online`);
    } else {
      setStatus(false, "No devices online");
    }
    
    renderDeviceStatus(devices);
    updateConnectionDeviceSelect(devices);
  } catch (e) {
    setStatus(false, `Backend unreachable (${e.message || e})`);
  }
}

function renderDeviceStatus(devices) {
  if (!DEVICE_STATUS) return;
  
  // Create status for known devices
  let html = '';
  Object.values(DEVICES).forEach(dev => {
    const found = devices.find(d => d.device_id === dev.id);
    const isOnline = found && found.is_online;
    const statusClass = isOnline ? 'online' : 'offline';
    const lastHeartbeatIso = found && found.last_heartbeat ? String(found.last_heartbeat) : null;
    const lastSeen = lastHeartbeatIso ? new Date(lastHeartbeatIso).toLocaleTimeString() : 'Never';
    const heartbeatAgeSec = lastHeartbeatIso ? Math.max(0, (Date.now() - new Date(lastHeartbeatIso).getTime()) / 1000) : null;
    const heartbeatAge = heartbeatAgeSec == null ? 'n/a' : `${heartbeatAgeSec.toFixed(1)}s`;

    if (!heartbeatState[dev.id]) {
      heartbeatState[dev.id] = { lastHeartbeatIso: null, lastBeatAt: 0, isOnline: false };
    }
    const prevIso = heartbeatState[dev.id].lastHeartbeatIso;
    if (isOnline && lastHeartbeatIso && lastHeartbeatIso !== prevIso) {
      heartbeatState[dev.id].lastBeatAt = performance.now();
      heartbeatState[dev.id].lastHeartbeatIso = lastHeartbeatIso;
    }
    heartbeatState[dev.id].isOnline = !!isOnline;
    
    html += `
      <div class="device-card ${statusClass}">
        <div class="device-indicator"></div>
        <div class="device-info">
          <strong>${dev.name}</strong>
          <span>${dev.type}</span>
          <small>Last: ${lastSeen} (${heartbeatAge})</small>
        </div>
        <canvas class="heartbeat-canvas" data-device-id="${dev.id}"></canvas>
      </div>
    `;
  });
  
  DEVICE_STATUS.innerHTML = html;
  bindHeartbeatCanvases();
}

function updateConnectionDeviceSelect(devices) {
  if (!CONNECTION_DEVICE_SELECT) return;
  const selected = CONNECTION_DEVICE_SELECT.value;
  const ids = devices.map(d => d.device_id);
  const knownIds = Object.values(DEVICES).map(d => d.id);
  const merged = Array.from(new Set([...knownIds, ...ids]));
  CONNECTION_DEVICE_SELECT.innerHTML = "";
  merged.forEach(id => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = id;
    CONNECTION_DEVICE_SELECT.appendChild(opt);
  });
  if (selected && merged.includes(selected)) {
    CONNECTION_DEVICE_SELECT.value = selected;
  } else if (merged.includes(DEVICES.cam.id)) {
    CONNECTION_DEVICE_SELECT.value = DEVICES.cam.id;
  } else if (merged.length > 0) {
    CONNECTION_DEVICE_SELECT.value = merged[0];
  }
}

// ================== POSE COMMANDS ==================

async function sendPose(pose) {
  try {
    const res = await fetch(`/servo/pose/${pose}`, { method: "POST" });
    const data = await res.json().catch(() => null);
    
    if (!res.ok) {
      console.error("Pose failed:", res.status, data);
      return;
    }
    console.log("Pose command:", data);
  } catch (e) {
    console.error("Pose error:", e);
  }
}

// ================== MOVEMENT COMMANDS ==================

async function sendMovement(direction) {
  const speed = document.getElementById('speed-slider')?.value || 200;
  try {
    // Use generic command endpoint
    const deviceType = "esp32"; // Wheel Controller
    // Map direction to command name
    const commandName = direction; // forward, backward, left, right, stop
    
    const url = `/api/command?device_type=${encodeURIComponent(deviceType)}&command_name=${encodeURIComponent(commandName)}`;
    
    const res = await fetch(url, { 
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speed: parseInt(speed) }) 
    });
    
    const data = await res.json().catch(() => null);
    
    if (!res.ok) {
      console.error("Movement failed:", res.status, data);
      pushClientLog("error", `Movement failed: ${data?.error || res.statusText}`);
      return;
    }
    console.log("Movement command:", direction, data);
  } catch (e) {
    console.error("Movement error:", e);
    pushClientLog("error", `Movement error: ${e.message}`);
  }
}

// ================== AUDIO COMMANDS ==================

async function startManualRecording() {
  const btn = document.querySelector('.record-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Requesting...";
  }

  try {
    // Use the generic command endpoint which routes via WebSocket
    const deviceType = "esp32s3cam"; // Matches ESPCAM.ino DEVICE_TYPE
    const commandName = "start_recording";
    
    // Construct URL with query parameters
    const url = `/api/command?device_type=${encodeURIComponent(deviceType)}&command_name=${encodeURIComponent(commandName)}`;
    
    const res = await fetch(url, { 
      method: "POST",
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({}) // Empty payload
    });
    
    const data = await res.json().catch(() => null);
    
    if (!res.ok) {
      console.error("Audio recording request failed:", res.status, data);
      alert("Failed to start recording: " + (data?.error || res.statusText));
    } else {
      console.log("Audio recording requested:", data);
      // Visual feedback
      if (btn) btn.textContent = "Recording (4s)...";
      setTimeout(() => {
        if (btn) {
            btn.textContent = "Record Voice";
            btn.disabled = false;
        }
      }, 4500);
      return;
    }
  } catch (e) {
    console.error("Audio error:", e);
    alert("Error starting recording: " + e.message);
  }

  // Reset button on error
  if (btn) {
    btn.disabled = false;
    btn.textContent = "Record Voice";
  }
}

// ================== CAMERA COMMANDS ==================

async function sendCameraCmd(cmd) {
  try {
    const res = await fetch(`/camera/${cmd}`, { method: "POST" });
    const data = await res.json().catch(() => null);
    
    if (!res.ok) {
      console.error("Camera cmd failed:", res.status, data);
      return;
    }
    console.log("Camera command:", cmd, data);
  } catch (e) {
    console.error("Camera error:", e);
  }
}

// ================== SERVO STATE ==================

async function fetchAllServoStates() {
  try {
    const res = await fetch("/servo/all");
    if (!res.ok) return;

    const data = await res.json();
    servoStates = data || {};
    renderTable();
  } catch {
    // ignore
  }
}

async function fetchAudioLogs() {
  try {
    const res = await fetch("/api/audio/logs?limit=50");
    if (!res.ok) {
      pushClientLog("error", `fetchAudioLogs failed: HTTP ${res.status}`);
      return;
    }
    const data = await res.json();
    renderAudioLogs(data.logs || []);
  } catch {
    return;
  }
}

async function fetchUserRequests() {
  try {
    const res = await fetch("/api/audio/transcripts?limit=50");
    if (!res.ok) {
      pushClientLog("error", `fetchUserRequests failed: HTTP ${res.status}`);
      return;
    }
    const data = await res.json();
    renderUserRequests(data.logs || []);
  } catch {
    return;
  }
}

async function fetchSystemLogs() {
  try {
    const res = await fetch("/api/system/logs?limit=200");
    if (!res.ok) {
      pushClientLog("error", `fetchSystemLogs failed: HTTP ${res.status}`);
      return;
    }
    const data = await res.json();
    serverSystemLogs = Array.isArray(data.logs) ? data.logs : [];
    renderSystemLogs();
  } catch (e) {
    pushClientLog("error", `fetchSystemLogs error: ${e.message || e}`);
  }
}

async function fetchCommandLogs() {
  try {
    const res = await fetch("/api/command-logs?limit=50");
    if (!res.ok) {
      pushClientLog("error", `fetchCommandLogs failed: HTTP ${res.status}`);
      return;
    }
    const data = await res.json();
    renderCommandLogs(data.logs || []);
  } catch (e) {
    pushClientLog("error", `fetchCommandLogs error: ${e.message || e}`);
  }
}

async function fetchConnectionEvents() {
  const deviceId = CONNECTION_DEVICE_SELECT?.value;
  if (!deviceId) return;
  try {
    const res = await fetch(`/api/device-connection-history/${encodeURIComponent(deviceId)}?limit=50`);
    if (!res.ok) {
      pushClientLog("error", `fetchConnectionEvents failed: HTTP ${res.status}`);
      return;
    }
    const data = await res.json();
    renderConnectionEvents(data.events || []);
  } catch (e) {
    pushClientLog("error", `fetchConnectionEvents error: ${e.message || e}`);
  }
}

function renderAudioLogs(logs) {
  if (!AUDIO_LOG_TABLE) return;
  AUDIO_LOG_TABLE.innerHTML = "";
  logs
    .filter((log) => !["FEEDBACK", "WAKE_WORD"].includes(String(log.command_name || "")))
    .slice()
    .reverse()
    .forEach((log) => {
    const tr = document.createElement("tr");
    const ts = log.timestamp ? new Date(log.timestamp) : null;
    const time = ts ? ts.toLocaleTimeString() : "--";
    const level = log.level ?? "-";
    const threshold = log.threshold ?? "-";
    const text = log.text || "";
    const prefix = log.prefix_ok ? "Yes" : "No";
    const command = log.command_name || "-";
    const manual = log.manual ? "Yes" : "No";
    tr.innerHTML = `
      <td class="log-tight">${time}</td>
      <td class="log-tight">${log.device_id || "-"}</td>
      <td class="log-tight">${level}</td>
      <td class="log-tight">${threshold}</td>
      <td class="log-text">${text}</td>
      <td class="log-tight">${prefix}</td>
      <td class="log-tight">${command}</td>
      <td class="log-tight">${manual}</td>
    `;
    AUDIO_LOG_TABLE.appendChild(tr);
  });
}

function renderUserRequests(logs) {
  if (!USER_REQUEST_TABLE) return;
  USER_REQUEST_TABLE.innerHTML = "";
  logs.slice().reverse().forEach((log) => {
    const tr = document.createElement("tr");
    const ts = log.timestamp ? new Date(log.timestamp) : null;
    const time = ts ? ts.toLocaleTimeString() : "--";
    const text = log.text || "";
    const command = log.command_name || "-";
    const confidence = log.confidence == null ? "-" : Number(log.confidence).toFixed(2);
    const manual = log.manual ? "Yes" : "No";
    tr.innerHTML = `
      <td class="log-tight">${time}</td>
      <td class="log-tight">${log.device_id || "-"}</td>
      <td class="log-text">${escapeHtml(text)}</td>
      <td class="log-tight">${escapeHtml(command)}</td>
      <td class="log-tight">${confidence}</td>
      <td class="log-tight">${manual}</td>
    `;
    USER_REQUEST_TABLE.appendChild(tr);
  });
}

function renderSystemLogs() {
  if (!SYSTEM_LOG_TABLE) return;
  const combined = [...serverSystemLogs, ...clientLogs]
    .filter(x => x && x.timestamp)
    .sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)))
    .slice(-200);

  SYSTEM_LOG_TABLE.innerHTML = "";
  combined.slice().reverse().forEach((log) => {
    const tr = document.createElement("tr");
    const ts = log.timestamp ? new Date(log.timestamp) : null;
    const time = ts ? ts.toLocaleTimeString() : "--";
    const levelRaw = (log.level || "info").toString().toLowerCase();
    const level = levelRaw === "warn" ? "warning" : levelRaw;
    const src = log.logger || log.source || "-";
    const msg = log.message || "";
    tr.innerHTML = `
      <td class="log-tight">${time}</td>
      <td class="log-tight"><span class="log-level ${level}">${(log.level || "INFO").toString()}</span></td>
      <td class="log-tight">${escapeHtml(src)}</td>
      <td class="log-text">${escapeHtml(msg)}</td>
    `;
    SYSTEM_LOG_TABLE.appendChild(tr);
  });
}

function renderCommandLogs(logs) {
  if (!COMMAND_LOG_TABLE) return;
  COMMAND_LOG_TABLE.innerHTML = "";
  logs.slice().reverse().forEach((log) => {
    const tr = document.createElement("tr");
    const ts = log.created_at ? new Date(log.created_at) : null;
    const time = ts ? ts.toLocaleTimeString() : "--";
    const status = log.status || "-";
    const targets = log.target_device_count ?? "-";
    const success = log.success_count ?? "-";
    tr.innerHTML = `
      <td class="log-tight">${time}</td>
      <td class="log-tight">${escapeHtml(log.device_type || "-")}</td>
      <td class="log-tight">${escapeHtml(log.command_name || "-")}</td>
      <td class="log-tight">${escapeHtml(status)}</td>
      <td class="log-tight">${targets}</td>
      <td class="log-tight">${success}</td>
    `;
    COMMAND_LOG_TABLE.appendChild(tr);
  });
}

function renderConnectionEvents(events) {
  if (!CONNECTION_EVENT_TABLE) return;
  CONNECTION_EVENT_TABLE.innerHTML = "";
  events.slice().reverse().forEach((ev) => {
    const tr = document.createElement("tr");
    const ts = ev.timestamp ? new Date(ev.timestamp) : null;
    const time = ts ? ts.toLocaleTimeString() : "--";
    const details = ev.details ? JSON.stringify(ev.details) : "";
    tr.innerHTML = `
      <td class="log-tight">${time}</td>
      <td class="log-tight">${escapeHtml(ev.event || "-")}</td>
      <td class="log-text">${escapeHtml(details)}</td>
    `;
    CONNECTION_EVENT_TABLE.appendChild(tr);
  });
}

function escapeHtml(input) {
  return String(input)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pushClientLog(level, message) {
  const entry = {
    timestamp: new Date().toISOString(),
    level: (level || "info").toString().toUpperCase(),
    logger: "browser",
    message: String(message)
  };
  clientLogs.push(entry);
  if (clientLogs.length > MAX_CLIENT_LOGS) {
    clientLogs.splice(0, clientLogs.length - MAX_CLIENT_LOGS);
  }
  renderSystemLogs();
}

function bindHeartbeatCanvases() {
  const canvases = document.querySelectorAll("canvas.heartbeat-canvas");
  canvases.forEach((c) => {
    const deviceId = c.getAttribute("data-device-id");
    if (!deviceId) return;
    heartbeatCanvases[deviceId] = c;
  });
}

function resizeCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(10, Math.floor(canvas.clientWidth * dpr));
  const h = Math.max(10, Math.floor(canvas.clientHeight * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  return { w, h, dpr };
}

function drawHeartbeat() {
  const now = performance.now();
  Object.entries(heartbeatCanvases).forEach(([deviceId, canvas]) => {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { w, h } = resizeCanvas(canvas);

    const st = heartbeatState[deviceId] || { lastBeatAt: 0, isOnline: false };
    const pad = 8;
    const baseline = Math.floor(h * 0.58);
    const stepPx = 2;
    const samples = Math.max(20, Math.floor((w - pad * 2) / stepPx));

    if (!st.points || st.points.length !== samples) {
      st.points = new Array(samples).fill(baseline);
      st.lastUpdateAt = now;
      heartbeatState[deviceId] = st;
    }

    const dt = Math.max(0, now - (st.lastUpdateAt || now));
    const steps = Math.min(12, Math.max(1, Math.floor(dt / 16)));
    const beatMs = st.isOnline ? (now - (st.lastBeatAt || 0)) : 1e9;

    for (let i = 0; i < steps; i++) {
      const t = beatMs + (i - steps) * 16;
      let amp = 0;
      if (st.isOnline && t >= 0 && t <= 420) {
        const p = t / 420;
        if (p < 0.12) amp = p / 0.12;
        else if (p < 0.2) amp = 1 - (p - 0.12) / 0.08;
        else if (p < 0.34) amp = -0.55 * ((p - 0.2) / 0.14);
        else if (p < 0.55) amp = -0.55 + 0.55 * ((p - 0.34) / 0.21);
        else amp = 0;
      }
      const noise = st.isOnline ? (Math.sin((now + i * 10) / 90) * 0.06 + Math.cos((now + i * 7) / 120) * 0.04) : 0;
      const y = baseline - (amp + noise) * (h * 0.42);
      st.points.shift();
      st.points.push(y);
    }
    st.lastUpdateAt = now;

    ctx.clearRect(0, 0, w, h);
    const glow = st.isOnline ? "rgba(0, 240, 255, 0.25)" : "rgba(255, 51, 102, 0.18)";
    const line = st.isOnline ? "rgba(0, 240, 255, 0.95)" : "rgba(148, 163, 184, 0.65)";

    ctx.lineWidth = 2;
    ctx.strokeStyle = glow;
    ctx.beginPath();
    ctx.moveTo(0, baseline);
    ctx.lineTo(w, baseline);
    ctx.stroke();

    ctx.strokeStyle = line;
    ctx.beginPath();
    for (let idx = 0; idx < st.points.length; idx++) {
      const x = pad + idx * stepPx;
      const y = st.points[idx];
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  });
  requestAnimationFrame(drawHeartbeat);
}

function renderTable() {
  if (!SERVO_TABLE) return;
  SERVO_TABLE.innerHTML = "";

  Object.values(servoStates).forEach((s) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.channel}</td>
      <td>${Number(s.current_angle).toFixed(1)} deg</td>
      <td>${Number(s.target_angle).toFixed(1)} deg</td>
      <td>${s.is_moving ? "Moving" : "Stable"}</td>
    `;
    SERVO_TABLE.appendChild(tr);
  });
}

// ================== STATUS UI ==================

function setStatus(online, text) {
  if (STATUS_DOT) STATUS_DOT.style.background = online ? "#22c55e" : "#ef4444";
  if (STATUS_TEXT) STATUS_TEXT.textContent = text || (online ? "Online" : "Offline");
}
// ================== CLOCK & COUNTS ==================

function updateClock() {
  const clockEl = document.getElementById("current-time");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString("en-US", { hour12: false });
  }
}

function updateDeviceCount(count) {
  const countEl = document.getElementById("device-count");
  if (countEl) countEl.textContent = count ?? 0;
}

// ================== SPEED SLIDER ==================

const speedSlider = document.getElementById('speed-slider');
const speedValue = document.getElementById('speed-value');
if (speedSlider && speedValue) {
  speedSlider.addEventListener('input', () => {
    speedValue.textContent = speedSlider.value;
  });
}

if (CONNECTION_DEVICE_SELECT) {
  CONNECTION_DEVICE_SELECT.addEventListener("change", () => {
    fetchConnectionEvents();
  });
}

// ================== INIT ==================
pollDeviceStatus();
setInterval(pollDeviceStatus, 1000);
updateClock();
setInterval(updateClock, 1000);
fetchAudioLogs();
setInterval(fetchAudioLogs, 3000);
fetchUserRequests();
setInterval(fetchUserRequests, 3000);
fetchSystemLogs();
setInterval(fetchSystemLogs, 2000);
fetchCommandLogs();
setInterval(fetchCommandLogs, 3000);
fetchConnectionEvents();
setInterval(fetchConnectionEvents, 4000);

window.addEventListener("error", (ev) => {
  pushClientLog("error", ev.message || "Unhandled error");
});

window.addEventListener("unhandledrejection", (ev) => {
  pushClientLog("error", ev.reason?.message || String(ev.reason || "Unhandled rejection"));
});

const _consoleError = console.error.bind(console);
console.error = (...args) => {
  pushClientLog("error", args.map(a => (typeof a === "string" ? a : JSON.stringify(a))).join(" "));
  _consoleError(...args);
};

const _consoleWarn = console.warn.bind(console);
console.warn = (...args) => {
  pushClientLog("warning", args.map(a => (typeof a === "string" ? a : JSON.stringify(a))).join(" "));
  _consoleWarn(...args);
};

requestAnimationFrame(drawHeartbeat);
