const maxPoints = 34;
const history = {
  processor: Array(maxPoints).fill(0),
  ram: Array(maxPoints).fill(0),
  storage: Array(maxPoints).fill(0),
};

function cssColor(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

const colors = {
  processor: cssColor("--cpu", "#91abee"),
  ram: cssColor("--ram", "#ecbfe3"),
  storage: cssColor("--storage", "#b1d99c"),
};

function alphaColor(color, alpha) {
  if (!color.startsWith("#")) return color;
  const hex = color.slice(1);
  const fullHex = hex.length === 3 ? hex.split("").map((part) => part + part).join("") : hex;
  const value = Number.parseInt(fullHex, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

const ids = {
  usage: {
    processor: document.getElementById("processor-usage"),
    ram: document.getElementById("ram-usage"),
    storage: document.getElementById("storage-usage"),
  },
  bars: {
    processor: document.getElementById("processor-bar"),
    ram: document.getElementById("ram-bar"),
    storage: document.getElementById("storage-bar"),
  },
  uptime: {
    days: document.getElementById("days"),
    hours: document.getElementById("hours"),
    minutes: document.getElementById("minutes"),
    seconds: document.getElementById("seconds"),
  },
  sparks: {
    processor: document.getElementById("processor-spark"),
    ram: document.getElementById("ram-spark"),
    storage: document.getElementById("storage-spark"),
  },
};

const chart = document.getElementById("usage-chart");
const ctx = chart.getContext("2d");
const streamState = document.getElementById("stream-state");
const viewTabs = [...document.querySelectorAll(".view-tab")];
const performanceSections = [...document.querySelectorAll(".performance-section")];
const processesSection = document.querySelector(".processes-section");
const storageSection = document.querySelector(".storage-section");
const processRows = document.getElementById("process-rows");
const processFilter = document.getElementById("process-filter");
const filesystemRows = document.getElementById("filesystem-rows");
const fileRows = document.getElementById("file-rows");
const fileScanNote = document.getElementById("file-scan-note");
const refreshFilesystemsButton = document.getElementById("refresh-filesystems");
const refreshFilesButton = document.getElementById("refresh-files");
let currentView = "performance";
let processData = [];
let processTimer;
let hasLoadedFilesystems = false;

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function applyInfo(info) {
  setText("processor-name", info.processor.name);
  setText("processor-cores", info.processor.coreCount);
  setText("processor-clock", info.processor.clockSpeed);
  setText("processor-bit-depth", info.processor.bitDepth);
  setText("machine-os", info.machine.operatingSystem);
  setText("total-ram", info.machine.totalRam);
  setText("machine-bit-depth", info.machine.ramTypeOrOSBitDepth);
  setText("proc-count", info.machine.procCount);
  setText("main-storage", info.storage.mainStorage);
  setText("storage-total", info.storage.total);
  setText("disk-count", info.storage.diskCount);
  setText("swap-amount", info.storage.swapAmount);
}

function applyUptime(uptime) {
  Object.entries(uptime).forEach(([key, value]) => {
    ids.uptime[key].textContent = value;
  });
}

function pushUsage(usage) {
  Object.entries(usage).forEach(([key, value]) => {
    const clamped = Math.max(0, Math.min(100, Number(value) || 0));
    ids.usage[key].textContent = clamped;
    ids.bars[key].style.width = `${clamped}%`;
    history[key].push(clamped);
    history[key].shift();
  });

  drawSparklines();
  drawChart();
}

function resizeCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width: rect.width, height: rect.height };
}

function pointFor(value, index, length, width, height, padding) {
  const x = padding + (index / (length - 1)) * (width - padding * 2);
  const y = padding + (1 - value / 100) * (height - padding * 2);
  return { x, y };
}

function drawPath(context, points) {
  context.beginPath();
  points.forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point.x, point.y);
      return;
    }
    const previous = points[index - 1];
    const midpointX = (previous.x + point.x) / 2;
    context.bezierCurveTo(midpointX, previous.y, midpointX, point.y, point.x, point.y);
  });
}

function drawSparkline(canvas, series, color) {
  if (!canvas || canvas.offsetParent === null) return;
  const { context, width, height } = resizeCanvas(canvas);
  const padding = 5;
  const points = series.map((value, index) => pointFor(value, index, series.length, width, height, padding));

  context.clearRect(0, 0, width, height);
  context.strokeStyle = "rgba(255, 255, 255, 0.12)";
  context.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = padding + i * ((height - padding * 2) / 3);
    context.beginPath();
    context.moveTo(padding, y);
    context.lineTo(width - padding, y);
    context.stroke();
  }

  drawPath(context, points);
  context.shadowColor = color;
  context.shadowBlur = 12;
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.stroke();
  context.shadowBlur = 0;

  const last = points[points.length - 1];
  context.beginPath();
  context.arc(last.x, last.y, 3.2, 0, Math.PI * 2);
  context.fillStyle = "#f7fbff";
  context.fill();
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.stroke();
}

function drawSparklines() {
  drawSparkline(ids.sparks.processor, history.processor, colors.processor);
  drawSparkline(ids.sparks.ram, history.ram, colors.ram);
  drawSparkline(ids.sparks.storage, history.storage, colors.storage);
}

function drawGrid(width, height, padding) {
  ctx.save();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
  ctx.fillStyle = "rgba(133, 145, 167, 0.72)";
  ctx.lineWidth = 1;
  ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";

  for (let value = 0; value <= 100; value += 25) {
    const y = padding + (1 - value / 100) * (height - padding * 2);
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(width - padding, y);
    ctx.stroke();
    ctx.fillText(`${value}`, 10, y + 4);
  }
  ctx.restore();
}

function drawSeries(series, color, fill = false) {
  const width = chart.getBoundingClientRect().width;
  const height = chart.getBoundingClientRect().height;
  const padding = 28;
  const points = series.map((value, index) => pointFor(value, index, series.length, width, height, padding));

  if (fill) {
    drawPath(ctx, points);
    ctx.lineTo(width - padding, height - padding);
    ctx.lineTo(padding, height - padding);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, padding, 0, height - padding);
    gradient.addColorStop(0, alphaColor(color, 0.22));
    gradient.addColorStop(1, alphaColor(color, 0));
    ctx.fillStyle = gradient;
    ctx.fill();
  }

  drawPath(ctx, points);
  ctx.shadowColor = color;
  ctx.shadowBlur = 14;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.6;
  ctx.stroke();
  ctx.shadowBlur = 0;

  const last = points[points.length - 1];
  ctx.beginPath();
  ctx.arc(last.x, last.y, 4.2, 0, Math.PI * 2);
  ctx.fillStyle = "#f7fbff";
  ctx.fill();
  ctx.lineWidth = 2.4;
  ctx.strokeStyle = color;
  ctx.stroke();
}

function fitCanvas() {
  resizeCanvas(chart);
  drawSparklines();
  drawChart();
}

function drawChart() {
  const rect = chart.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  drawGrid(rect.width, rect.height, 28);
  drawSeries(history.storage, colors.storage, true);
  drawSeries(history.ram, colors.ram);
  drawSeries(history.processor, colors.processor);
}

function applySnapshot(snapshot) {
  applyInfo(snapshot.info);
  applyUptime(snapshot.uptime);
  pushUsage(snapshot.usage);
}

function setStreamState(text) {
  if (streamState) streamState.textContent = text;
}

async function pollSnapshot() {
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    applySnapshot(await response.json());
    setStreamState("Polling");
  } catch {
    setStreamState("Offline");
  }
}

function connectSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/metrics`);
  let fallback;

  socket.addEventListener("open", () => {
    setStreamState("Live Stream");
  });

  socket.addEventListener("message", (event) => {
    applySnapshot(JSON.parse(event.data));
  });

  socket.addEventListener("close", () => {
    setStreamState("Reconnecting");
    fallback = window.setInterval(pollSnapshot, 6000);
    window.setTimeout(() => {
      window.clearInterval(fallback);
      connectSocket();
    }, 15000);
  });

  socket.addEventListener("error", () => {
    socket.close();
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => (
    {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]
  ));
}

function renderProcesses() {
  if (!processRows) return;
  const query = processFilter ? processFilter.value.trim().toLowerCase() : "";
  const rows = processData.filter((process) => {
    if (!query) return true;
    return [process.name, process.user, process.pid].some((value) => String(value).toLowerCase().includes(query));
  });

  if (rows.length === 0) {
    processRows.innerHTML = '<tr><td colspan="6" class="process-empty">No matching processes.</td></tr>';
    return;
  }

  processRows.innerHTML = rows.map((process) => {
    const cpu = Number(process.cpu) || 0;
    const cpuWidth = Math.max(0, Math.min(100, cpu));
    return `
      <tr>
        <td>
          <div class="process-name">
            <span class="process-dot" aria-hidden="true"></span>
            <span>${escapeHtml(process.name)}</span>
          </div>
        </td>
        <td>
          <span class="process-cpu">
            <span>${cpu.toFixed(1)}%</span>
            <span class="process-cpu-bar" aria-hidden="true"><span style="width: ${cpuWidth}%"></span></span>
          </span>
        </td>
        <td>${escapeHtml(process.cpuTime)}</td>
        <td>${escapeHtml(process.threads)}</td>
        <td>${escapeHtml(process.pid)}</td>
        <td>${escapeHtml(process.user)}</td>
      </tr>
    `;
  }).join("");
}

async function fetchProcesses() {
  if (currentView !== "processes") return;
  try {
    const response = await fetch("/api/processes", { cache: "no-store" });
    const payload = await response.json();
    processData = payload.processes || [];
    renderProcesses();
  } catch {
    if (processRows) {
      processRows.innerHTML = '<tr><td colspan="6" class="process-empty">Unable to load processes.</td></tr>';
    }
  }
}

function loadingRow(target, columns, text) {
  if (!target) return;
  target.innerHTML = `<tr><td colspan="${columns}" class="process-empty loading-cell">${escapeHtml(text)}</td></tr>`;
}

function emptyRow(target, columns, text) {
  if (!target) return;
  target.innerHTML = `<tr><td colspan="${columns}" class="process-empty">${escapeHtml(text)}</td></tr>`;
}

function renderFilesystems(rows) {
  if (!filesystemRows) return;
  if (!rows.length) {
    emptyRow(filesystemRows, 6, "No filesystems found.");
    return;
  }

  filesystemRows.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.filesystem)}</td>
      <td>${escapeHtml(row.size)}</td>
      <td>${escapeHtml(row.used)}</td>
      <td>${escapeHtml(row.available)}</td>
      <td>
        <span class="process-cpu">
          <span>${escapeHtml(row.percent)}%</span>
          <span class="process-cpu-bar" aria-hidden="true"><span style="width: ${Math.max(0, Math.min(100, Number(row.percent) || 0))}%"></span></span>
        </span>
      </td>
      <td>${escapeHtml(row.mountedOn)}</td>
    </tr>
  `).join("");
}

function renderFileUsage(rows, skipped) {
  if (!fileRows) return;
  if (!rows.length) {
    emptyRow(fileRows, 2, "No file usage data found.");
    return;
  }

  fileRows.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.path)}</td>
      <td>${escapeHtml(row.size)}</td>
    </tr>
  `).join("");

  if (fileScanNote) {
    fileScanNote.hidden = !skipped;
    fileScanNote.textContent = skipped ? `${skipped} paths could not be read and were skipped.` : "";
  }
}

async function fetchFilesystems() {
  loadingRow(filesystemRows, 6, "Loading filesystems...");
  if (refreshFilesystemsButton) refreshFilesystemsButton.disabled = true;
  try {
    const response = await fetch("/api/storage/filesystems", { cache: "no-store" });
    const payload = await response.json();
    renderFilesystems(payload.filesystems || []);
    hasLoadedFilesystems = true;
  } catch {
    emptyRow(filesystemRows, 6, "Unable to load filesystems.");
  } finally {
    if (refreshFilesystemsButton) refreshFilesystemsButton.disabled = false;
  }
}

async function fetchFileUsage() {
  loadingRow(fileRows, 2, "Scanning largest paths...");
  if (fileScanNote) fileScanNote.hidden = true;
  if (refreshFilesButton) refreshFilesButton.disabled = true;
  try {
    const response = await fetch("/api/storage/files", { cache: "no-store" });
    const payload = await response.json();
    renderFileUsage(payload.files || [], payload.skipped || 0);
  } catch {
    emptyRow(fileRows, 2, "Unable to scan files.");
  } finally {
    if (refreshFilesButton) refreshFilesButton.disabled = false;
  }
}

function setView(view) {
  currentView = view;
  const showingProcesses = view === "processes";
  const showingStorage = view === "storage";

  performanceSections.forEach((section) => {
    section.hidden = showingProcesses || showingStorage;
  });
  if (processesSection) processesSection.hidden = !showingProcesses;
  if (storageSection) storageSection.hidden = !showingStorage;

  viewTabs.forEach((tab) => {
    const selected = tab.dataset.view === view;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
  });

  if (showingProcesses) {
    fetchProcesses();
    window.clearInterval(processTimer);
    processTimer = window.setInterval(fetchProcesses, 10000);
  } else {
    window.clearInterval(processTimer);
    if (!showingStorage) fitCanvas();
  }

  if (showingStorage && !hasLoadedFilesystems) {
    fetchFilesystems();
  }
}

viewTabs.forEach((tab) => {
  tab.addEventListener("click", () => setView(tab.dataset.view));
});

if (processFilter) {
  processFilter.addEventListener("input", renderProcesses);
}

if (refreshFilesystemsButton) {
  refreshFilesystemsButton.addEventListener("click", fetchFilesystems);
}

if (refreshFilesButton) {
  refreshFilesButton.addEventListener("click", fetchFileUsage);
}

window.addEventListener("resize", fitCanvas);
fitCanvas();
pollSnapshot();
connectSocket();
