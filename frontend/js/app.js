/* Tokyo Train Ticker — main app */

const API = window.location.origin;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

const app = (() => {
  let ws = null;
  let wsRetry = null;
  let mode = 'station';          // 'station' | 'line'
  let currentStation = 'shibuya';
  let currentLine = 'JY';
  let currentPlatform = 'ALL';   // 'ALL' or platform label string
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
      const devRow = document.getElementById('dev-line-row');
      if (devRow) devRow.style.display = 'none';
    } else {
      document.getElementById('line-tracker').classList.add('active');
      document.getElementById('btn-line').classList.add('active');
      const strip = document.getElementById('platform-strip');
      if (strip) strip.classList.add('hidden');
      const devRow = document.getElementById('dev-line-row');
      if (devRow) devRow.style.display = 'flex';
      if (!skipPicker) openLinePicker();
    }
    refresh();
  }

  function selectStation(stationId) {
    currentStation = stationId;
    currentPlatform = 'ALL';
    const station = allStations.find(s => s.id === stationId);
    if (station) {
      document.getElementById('station-en').textContent = station.name_en.toUpperCase();
      document.getElementById('station-ja').textContent = station.name_ja;
    }
    renderPlatformStrip([]);
    const devSel = document.getElementById('dev-station-select');
    if (devSel) devSel.value = stationId;
    if (mode === 'station') refresh();
  }

  function selectPlatform(plt) {
    currentPlatform = plt;
    // Full re-render so hero card also updates to the right platform's next train
    refresh();
  }

  function selectLine(lineCode) {
    currentLine = lineCode;
    const devSel = document.getElementById('dev-line-select');
    if (devSel) devSel.value = lineCode;
    if (mode === 'line') refresh();
  }

  // ── Hero card ── renders the next train prominently ────────────────────

  function renderHeroCard(train) {
    if (!train) {
      document.getElementById('next-badge').textContent = '?';
      document.getElementById('next-badge').style.cssText = 'background:#1a1a1a;border-radius:4px;';
      document.getElementById('next-line-name').textContent = '';
      document.getElementById('next-dest').textContent = 'NO SERVICE';
      document.getElementById('next-eta').textContent = '–';
      document.getElementById('next-delay').textContent = '';
      document.getElementById('next-platform').textContent = '';
      return;
    }
    const line = allLines.find(l => l.code === train.line_code) || train;
    const shape = train.shape || line.shape || 'rect';
    const borderRadius = shape === 'circle' ? '50%' : shape === 'square' ? '4px' : '8px';
    const glow = `0 0 18px ${train.color}99, 0 0 36px ${train.color}44`;

    const badge = document.getElementById('next-badge');
    badge.textContent = train.line_code;
    badge.style.cssText = `background:${train.color};color:${train.text_color};border-radius:${borderRadius};box-shadow:${glow};`;

    document.getElementById('next-line-name').textContent = line.name || line.short || '';

    const destEl = document.getElementById('next-dest');
    const bright = brighten(train.color);
    destEl.textContent = `→ ${train.destination}`;
    destEl.style.color = bright;
    destEl.style.textShadow = `0 0 10px ${train.color}99, 0 0 20px ${train.color}44`;

    const eta = train.eta_min;
    const etaEl = document.getElementById('next-eta');
    if (eta <= 1) {
      etaEl.textContent = 'NOW';
      etaEl.style.color = '#ff6020';
      etaEl.style.textShadow = '0 0 12px #ff6020';
      etaEl.classList.add('eta-arriving');
    } else {
      etaEl.classList.remove('eta-arriving');
      etaEl.textContent = `${eta} MIN`;
      etaEl.style.color = eta <= 4 ? '#ffd700' : '#9acd32';
      etaEl.style.textShadow = eta <= 4
        ? '0 0 10px #ffd70099'
        : '0 0 8px #9acd3266';
    }

    const delayEl = document.getElementById('next-delay');
    delayEl.textContent = train.delay_min > 0 ? `+${train.delay_min}m delay` : '';

    document.getElementById('next-platform').textContent =
      train.platform ? `PLATFORM ${train.platform}` : '';
  }

  // ── Platform filter strip ───────────────────────────────────────────────

  function renderPlatformStrip(trains) {
    const strip = document.getElementById('platform-strip');
    const buttons = document.getElementById('platform-buttons');

    // Collect unique platform labels, sorted numerically then alpha
    const seen = new Set();
    trains.forEach(t => { if (t.platform && t.platform !== '–') seen.add(t.platform); });
    const platforms = [...seen].sort((a, b) => {
      const na = parseFloat(a), nb = parseFloat(b);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return a.localeCompare(b);
    });

    if (platforms.length <= 1) {
      // Nothing useful to filter — hide strip
      strip.classList.add('hidden');
      return;
    }

    strip.classList.remove('hidden');

    // Ensure currentPlatform is still valid; reset if the data no longer has it
    if (currentPlatform !== 'ALL' && !platforms.includes(currentPlatform)) {
      currentPlatform = 'ALL';
    }

    buttons.innerHTML = [
      `<button class="plt-btn all-btn ${currentPlatform === 'ALL' ? 'active' : ''}" data-plt="ALL" onclick="app.selectPlatform('ALL')">ALL</button>`,
      ...platforms.map(p =>
        `<button class="plt-btn ${currentPlatform === p ? 'active' : ''}" data-plt="${p}" onclick="app.selectPlatform('${p}')">${p}</button>`
      )
    ].join('');
  }

  // ── Station board renderer ──────────────────────────────────────────────

  function renderStationBoard(stationId, trains) {
    const list = document.getElementById('train-list');
    const noTrains = document.getElementById('no-trains');

    if (!trains || trains.length === 0) {
      renderHeroCard(null);
      list.innerHTML = '';
      noTrains.textContent = 'No service data';
      noTrains.classList.remove('hidden');
      renderPlatformStrip([]);
      return;
    }
    noTrains.classList.add('hidden');

    // Filter by platform if active, then pick hero from filtered set
    const visible = currentPlatform === 'ALL'
      ? trains
      : trains.filter(t => (t.platform || '–') === currentPlatform);

    // Hero card — always the next train (respects platform filter)
    renderHeroCard(visible[0] || trains[0]);

    // Update platform strip
    renderPlatformStrip(trains);

    // Upcoming list — skip the very first train (it's in the hero card)
    const upcoming = visible.slice(1);

    // Time buckets for section dividers (in minutes)
    const BUCKETS = [
      { max: 2,  label: 'ARRIVING' },
      { max: 10, label: 'NEXT 10 MIN' },
      { max: 20, label: '20 MIN' },
      { max: 30, label: '30 MIN' },
      { max: 45, label: '45 MIN' },
      { max: 60, label: '1 HOUR' },
    ];

    let html = '';
    let lastBucket = -1;

    upcoming.forEach(t => {
      const eta = t.eta_min;
      const bucketIdx = BUCKETS.findIndex(b => eta <= b.max);
      const bucket = bucketIdx >= 0 ? BUCKETS[bucketIdx] : null;

      if (bucket && bucketIdx !== lastBucket) {
        html += `<div class="time-divider">
          <span class="time-divider-label">${bucket.label}</span>
          <span class="time-divider-line"></span>
        </div>`;
        lastBucket = bucketIdx;
      }

      const line = allLines.find(l => l.code === t.line_code) || t;
      let timeClass = 'normal';
      let timeText = `${eta}`;
      if (eta <= 2) { timeClass = 'arriving'; timeText = eta <= 1 ? 'NOW' : `${eta}`; }
      else if (eta <= 5) { timeClass = 'soon'; }

      const dest = truncate(t.destination, 11);
      const plat = t.platform || '–';
      const delayDot = t.delay_min > 0 ? `<span class="delay-dot" title="${t.delay_min}m delay"></span>` : '';
      const badgeShape = t.shape || line.shape || 'rect';

      html += `<div class="board-row train-row" data-platform="${plat}">
        <span class="col-line">
          <span class="inline-badge shape-${badgeShape}" style="background:${t.color};color:${t.text_color}">${t.line_code}</span>
        </span>
        <span class="col-dest" style="color:${brighten(t.color)}">${dest}${delayDot}</span>
        <span class="col-plat" style="font-size:8px;color:#555">${plat}</span>
        <span class="col-time"><span class="time-val ${timeClass}">${timeText}</span></span>
      </div>`;
    });

    list.innerHTML = html;

    if (upcoming.length === 0 && currentPlatform !== 'ALL') {
      noTrains.textContent = `No more trains\non platform ${currentPlatform}`;
      noTrains.classList.remove('hidden');
    }
  }

  // ── Line tracker renderer ───────────────────────────────────────────────

  function renderLineTracker(lineCode, trains) {
    const line = allLines.find(l => l.code === lineCode);
    if (!line) return;

    const nameEl = document.getElementById('tracker-line-name');
    const shape = line.shape || 'rect';
    const br = shape === 'circle' ? '50%' : shape === 'square' ? '2px' : '4px';
    nameEl.innerHTML = `
      <span style="background:${line.color};color:${line.text_color};font-family:'Press Start 2P',monospace;font-size:7px;padding:2px 4px;border-radius:${br};box-shadow:0 0 8px ${line.color}88">${lineCode}</span>
      <span style="font-family:'Press Start 2P',monospace;font-size:7px;color:${line.color};text-shadow:0 0 8px ${line.color}66">${line.short.toUpperCase()}</span>
      <span style="font-size:8px;color:#333;margin-left:auto;font-family:'Share Tech Mono',monospace">${trains.length} trains</span>
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
  return { init, setMode, selectStation, selectLine, selectPlatform, openStationPicker, openLinePicker, _pickStation, _pickLine };
})();

document.addEventListener('DOMContentLoaded', () => app.init());
