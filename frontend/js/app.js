/* Tokyo Train Ticker — main app */

const API = window.location.origin;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

const app = (() => {
  let ws = null;
  let wsRetry = null;
  let mode = 'station';          // 'station' | 'line'
  let currentStation = 'shibuya';
  let currentLine = 'JY';
  let allStations = [];
  let allLines = [];
  let tickInterval = null;
  let clockInterval = null;
  let refreshTimeout = null;

  // ── Init ────────────────────────────────────────────────────────────────

  async function init() {
    startClock();
    await Promise.all([loadLines(), loadStations()]);
    checkStatus();
    connectWS();
    selectStation(currentStation);
    buildDevControls();
    setMode('station');
  }

  function startClock() {
    function tick() {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      document.getElementById('clock').textContent =
        `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    }
    tick();
    clockInterval = setInterval(tick, 1000);
  }

  async function checkStatus() {
    try {
      const res = await fetch(`${API}/api/status`);
      const data = await res.json();
      const badge = document.getElementById('demo-badge');
      if (data.demo_mode) badge.classList.remove('hidden');
      else badge.classList.add('hidden');
      setDevStatus(data.demo_mode ? 'DEMO MODE (no ODPT key)' : `LIVE · ${data.lines} lines · ${data.stations} stations`);
    } catch (e) {
      setDevStatus('Backend offline');
    }
  }

  // ── WebSocket ───────────────────────────────────────────────────────────

  function connectWS() {
    if (ws) { try { ws.close(); } catch (_) {} }
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setDevStatus('WS connected');
      refresh();
    };

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'tick') {
        refresh();
      } else if (msg.type === 'station_update') {
        renderStationBoard(msg.station_id, msg.trains);
      } else if (msg.type === 'line_update') {
        renderLineTracker(msg.line_code, msg.trains);
      }
    };

    ws.onclose = () => {
      setDevStatus('WS reconnecting…');
      wsRetry = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => { ws.close(); };
  }

  function wsSend(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    } else {
      // Fallback: REST poll
      restRefresh();
    }
  }

  function refresh() {
    if (mode === 'station') {
      wsSend({ mode: 'station', station_id: currentStation });
    } else {
      wsSend({ mode: 'line', line_code: currentLine });
    }
  }

  async function restRefresh() {
    if (mode === 'station') {
      const res = await fetch(`${API}/api/trains/station/${currentStation}`);
      const trains = await res.json();
      renderStationBoard(currentStation, trains);
    } else {
      const res = await fetch(`${API}/api/trains/line/${currentLine}`);
      const trains = await res.json();
      renderLineTracker(currentLine, trains);
    }
  }

  // ── Data loading ────────────────────────────────────────────────────────

  async function loadLines() {
    const res = await fetch(`${API}/api/lines`);
    allLines = await res.json();
  }

  async function loadStations() {
    const res = await fetch(`${API}/api/stations`);
    allStations = await res.json();
  }

  // ── Mode switching ──────────────────────────────────────────────────────

  function setMode(m, skipPicker = false) {
    mode = m;
    document.querySelectorAll('.mode-view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    // Close any open overlays
    closeStationPicker();
    closeLinePicker();

    if (m === 'station') {
      document.getElementById('station-board').classList.add('active');
      document.getElementById('btn-station').classList.add('active');
      document.getElementById('line-badges').style.display = 'flex';
      const devRow = document.getElementById('dev-line-row');
      if (devRow) devRow.style.display = 'none';
    } else {
      document.getElementById('line-tracker').classList.add('active');
      document.getElementById('btn-line').classList.add('active');
      document.getElementById('line-badges').style.display = 'none';
      const devRow = document.getElementById('dev-line-row');
      if (devRow) devRow.style.display = 'flex';
      // Open line picker so user can choose a line
      if (!skipPicker) openLinePicker();
    }
    refresh();
  }

  function selectStation(stationId) {
    currentStation = stationId;
    const station = allStations.find(s => s.id === stationId);
    if (station) {
      document.getElementById('station-en').textContent = station.name_en.toUpperCase();
      document.getElementById('station-ja').textContent = station.name_ja;
      renderLineBadges(station.lines);
    }
    const devSel = document.getElementById('dev-station-select');
    if (devSel) devSel.value = stationId;
    if (mode === 'station') refresh();
  }

  function selectLine(lineCode) {
    currentLine = lineCode;
    const devSel = document.getElementById('dev-line-select');
    if (devSel) devSel.value = lineCode;
    if (mode === 'line') refresh();
  }

  // ── Line badges strip ───────────────────────────────────────────────────

  function renderLineBadges(lineCodes) {
    const strip = document.getElementById('line-badges');
    strip.innerHTML = '';
    lineCodes.forEach(code => {
      const line = allLines.find(l => l.code === code);
      if (!line) return;
      const el = document.createElement('span');
      el.className = `line-badge shape-${line.shape}`;
      el.style.background = line.color;
      el.style.color = line.text_color;
      el.textContent = code;
      el.title = line.name;
      el.addEventListener('click', () => {
        setMode('line');
        selectLine(code);
      });
      strip.appendChild(el);
    });
  }

  // ── Station board renderer ──────────────────────────────────────────────

  function renderStationBoard(stationId, trains) {
    const list = document.getElementById('train-list');
    const noTrains = document.getElementById('no-trains');

    if (!trains || trains.length === 0) {
      list.innerHTML = '';
      noTrains.classList.remove('hidden');
      return;
    }
    noTrains.classList.add('hidden');

    const MAX_ROWS = 10;
    const rows = trains.slice(0, MAX_ROWS);

    list.innerHTML = rows.map(t => {
      const line = allLines.find(l => l.code === t.line_code) || t;
      const eta = t.eta_min;
      let timeClass = 'normal';
      let timeText = `${eta}`;
      let extraClass = '';
      if (eta <= 1) { timeClass = 'arriving'; timeText = 'NOW'; extraClass = 'arriving-blink'; }
      else if (eta <= 2) { timeClass = 'arriving'; }
      else if (eta <= 4) { timeClass = 'soon'; }

      const dest = truncate(t.destination, 11);
      const plat = t.platform || '–';
      const delayDot = t.delay_min > 0 ? `<span class="delay-dot" title="${t.delay_min}m delay"></span>` : '';
      const badgeShape = t.shape || line.shape || 'rect';

      return `<div class="board-row train-row ${extraClass}">
        <span class="col-line">
          <span class="inline-badge shape-${badgeShape}" style="background:${t.color};color:${t.text_color}">${t.line_code}</span>
        </span>
        <span class="col-dest" style="color:${brighten(t.color)}">${dest}${delayDot}</span>
        <span class="col-plat">${plat}</span>
        <span class="col-time"><span class="time-val ${timeClass}">${timeText}</span></span>
      </div>`;
    }).join('');
  }

  // ── Line tracker renderer ───────────────────────────────────────────────

  function renderLineTracker(lineCode, trains) {
    const line = allLines.find(l => l.code === lineCode);
    if (!line) return;

    const nameEl = document.getElementById('tracker-line-name');
    nameEl.innerHTML = `
      <span class="line-badge shape-${line.shape}" style="background:${line.color};color:${line.text_color};font-size:9px;height:14px;min-width:20px">${lineCode}</span>
      <span style="color:${line.color};text-shadow:0 0 8px ${line.color}40">${line.name.toUpperCase()}</span>
      <span style="font-size:9px;color:#444;margin-left:auto">${trains.length} TRAINS</span>
    `;

    const container = document.getElementById('tracker-trains');
    if (!trains || trains.length === 0) {
      container.innerHTML = '<div style="color:#444;font-size:10px;padding:10px 6px">No train data</div>';
      return;
    }

    container.innerHTML = trains.slice(0, 12).map(t => {
      const delayStr = t.delay_min > 0 ? `<span class="tracker-delay">+${t.delay_min}min</span>` : '';
      const progress = buildProgressBar(t, line);
      return `<div class="tracker-train">
        <div class="tracker-train-header">
          <span class="tracker-train-num">#${t.train_number}</span>
          <span class="tracker-dest" style="color:${brighten(t.color)}">&rarr; ${t.destination}</span>
          ${delayStr}
        </div>
        ${progress}
      </div>`;
    }).join('');
  }

  function buildProgressBar(train, line) {
    const from = train.from_station || '';
    const to = train.to_station || '';
    if (!from && !to) return '';

    // Show: [from] ──●──> [to] ──> [destination]
    const segments = [
      { label: truncate(from, 7), type: 'passed' },
      { label: '▶', type: 'current-marker' },
      { label: truncate(to, 7), type: 'next' },
      { label: '···', type: 'gap' },
      { label: truncate(train.destination, 7), type: 'dest' },
    ];

    return `<div class="station-progress">
      <span class="prog-station current" style="color:${brighten(line.color)}">${truncate(from, 7)}</span>
      <span class="prog-line passed" style="background:${line.color}40"></span>
      <span class="prog-dot current" style="background:${line.color};box-shadow:0 0 4px ${line.color}"></span>
      <span class="prog-line" style="background:${line.color}30"></span>
      <span class="prog-station next">${truncate(to, 7)}</span>
      <span class="prog-line" style="background:#1a1a1a"></span>
      <span class="prog-station" style="color:#555">${truncate(train.destination, 7)}</span>
    </div>`;
  }

  // ── Station picker ──────────────────────────────────────────────────────

  function openStationPicker() {
    const overlay = document.getElementById('station-picker');
    overlay.classList.remove('hidden');
    const input = document.getElementById('station-search');
    input.value = '';
    renderStationResults('');
    setTimeout(() => input.focus(), 50);

    input.oninput = () => renderStationResults(input.value);
    input.onkeydown = (e) => {
      if (e.key === 'Escape') closeStationPicker();
    };
  }

  function closeStationPicker() {
    document.getElementById('station-picker').classList.add('hidden');
  }

  function renderStationResults(query) {
    const q = query.toLowerCase();
    const results = allStations.filter(s =>
      !q || s.name_en.toLowerCase().includes(q) || s.name_ja.includes(q)
    ).slice(0, 20);

    const container = document.getElementById('station-results');
    container.innerHTML = results.map(s => {
      const badges = s.lines.map(lc => {
        const l = allLines.find(x => x.code === lc);
        if (!l) return '';
        return `<span class="inline-badge shape-${l.shape}" style="background:${l.color};color:${l.text_color}">${lc}</span>`;
      }).join('');
      return `<div class="picker-item" onclick="app._pickStation('${s.id}')">
        <span>${s.name_en}</span>
        <span class="item-ja">${s.name_ja}</span>
        <span class="picker-line-badges">${badges}</span>
      </div>`;
    }).join('');
  }

  function _pickStation(id) {
    closeStationPicker();
    selectStation(id);
    setMode('station');
  }

  // ── Line picker ──────────────────────────────────────────────────────────

  function openLinePicker() {
    const overlay = document.getElementById('line-picker');
    overlay.classList.remove('hidden');

    const container = document.getElementById('line-results');
    container.innerHTML = allLines.map(l =>
      `<div class="line-picker-item" onclick="app._pickLine('${l.code}')">
        <span class="line-badge shape-${l.shape}" style="background:${l.color};color:${l.text_color};font-size:9px;height:16px;min-width:22px">${l.code}</span>
        <span class="lp-code">${truncate(l.short, 8)}</span>
      </div>`
    ).join('');
  }

  function closeLinePicker() {
    document.getElementById('line-picker').classList.add('hidden');
  }

  function _pickLine(code) {
    closeLinePicker();
    selectLine(code);
    setMode('line', true);  // skip auto-opening picker again
  }

  // ── Dev controls ────────────────────────────────────────────────────────

  function buildDevControls() {
    const stSel = document.getElementById('dev-station-select');
    if (stSel) {
      stSel.innerHTML = allStations.map(s =>
        `<option value="${s.id}">${s.name_en} (${s.name_ja})</option>`
      ).join('');
      stSel.value = currentStation;
    }

    const lineSel = document.getElementById('dev-line-select');
    if (lineSel) {
      lineSel.innerHTML = allLines.map(l =>
        `<option value="${l.code}">[${l.code}] ${l.name}</option>`
      ).join('');
      lineSel.value = currentLine;
    }
  }

  function setDevStatus(msg) {
    const el = document.getElementById('dev-status');
    if (el) el.textContent = msg;
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  function truncate(str, n) {
    if (!str) return '';
    str = str.toUpperCase();
    return str.length > n ? str.slice(0, n - 1) + '…' : str;
  }

  function brighten(hex) {
    // Lighten a hex color for dark background readability
    if (!hex || !hex.startsWith('#')) return hex;
    let r = parseInt(hex.slice(1, 3), 16);
    let g = parseInt(hex.slice(3, 5), 16);
    let b = parseInt(hex.slice(5, 7), 16);
    // Boost luminance
    const factor = 1.4;
    r = Math.min(255, Math.round(r * factor + 40));
    g = Math.min(255, Math.round(g * factor + 40));
    b = Math.min(255, Math.round(b * factor + 40));
    return `rgb(${r},${g},${b})`;
  }

  // Public API
  return { init, setMode, selectStation, selectLine, openStationPicker, openLinePicker, _pickStation, _pickLine };
})();

document.addEventListener('DOMContentLoaded', () => app.init());
