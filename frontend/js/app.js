/* Tokyo Train Ticker — main app */

const API = window.location.origin;
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

// ── Japanese lookup tables (mirrors pygame_display.py) ────────────────────────
const DEST_JA = {
  "IKEBUKURO":"池袋",    "SHIBUYA":"渋谷",      "SHINJUKU":"新宿",
  "UENO":"上野",          "TOKYO":"東京",         "TAKAO":"高尾",
  "TACHIKAWA":"立川",    "OGIKUBO":"荻窪",       "CHIBA":"千葉",
  "MITAKA":"三鷹",       "OMIYA":"大宮",          "OFUNA":"大船",
  "YOKOHAMA":"横浜",     "OSAKI":"大崎",          "UTSUNOMIYA":"宇都宮",
  "TAKASAKI":"高崎",     "KAMAKURA":"鎌倉",       "ZUSHI":"逗子",
  "SHINAGAWA":"品川",    "NARITA":"成田",
  "ASAKUSA":"浅草",      "GINZA":"銀座",           "HONANCHO":"方南町",
  "KITASENJU":"北千住",  "NAKAMEGURO":"中目黒",    "NAKA-MEGURO":"中目黒",
  "NAKANO":"中野",       "NISHIFUNABASHI":"西船橋","NISHI-FUNABASHI":"西船橋",
  "YOYOGI-UEHARA":"代々木上原","AYASE":"綾瀬",    "ABIKO":"我孫子",
  "WAKOSHI":"和光市",    "SHIN-KIBA":"新木場",     "SHINKIBA":"新木場",
  "OSHIAGE":"押上",      "NAGATSUTA":"長津田",     "TOCHOMAE":"都庁前",
  "MEGURO":"目黒",       "NISHI-TAKASHIMADAIRA":"西高島平",
  "MOTOMACHI-CHUKAGAI":"元町・中華街",
  "NISHI-MAGOME":"西馬込",        "HIKARIGAOKA":"光が丘",
  "NERIMA-KASUGACHO":"練馬春日町",
  "FUTAKO-TAMAGAWA":"二子玉川",   "MIZONOKUCHI":"溝の口",
  "MOTOSUMIYOSHI":"元住吉",       "CHOFU":"調布",
  "HASHIMOTO":"橋本",             "KEIO-HACHIOJI":"京王八王子",
  "KEIO-SAGAMIHARA":"京王相模原", "KICHIJOJI":"吉祥寺",
  "ODAWARA":"小田原",             "FUJISAWA":"藤沢",
  "KARAKIDA":"唐木田",            "KATASE-ENOSHIMA":"片瀬江ノ島",
  "HANNO":"飯能",                 "OGOSE":"越生",
  "KAWAGOE":"川越",               "TOBU-NIKKO":"東武日光",
  "AIZUWAKAMATSU":"会津若松",     "URAGA":"浦賀",
  "NARITA-SKYACCESS":"成田スカイアクセス",
  "HANEDA-AIRPORT":"羽田空港",    "NARITA-AIRPORT":"成田空港",
  "HANEDA-AIRPORT-T1":"羽田空港第1ターミナル",
  "TOYOSU":"豊洲",   "SHIMBASHI":"新橋",          "HAMAMATSUCHO":"浜松町",
  "URAWA-MISONO":"浦和美園",      "SHINOZAKIMACHI":"篠崎",
  "HANA-KOGANEI":"花小金井",      "NISHI-SHINJUKU":"西新宿",
  "MUSASHI-KYURYO":"武蔵丘",
};

const LINE_NAME_JA = {
  "JY":"山手線",       "JC":"中央線",         "JB":"中央・総武線",
  "JK":"京浜東北線",   "JA":"埼京線",          "JH":"横須賀線",
  "JU":"宇都宮・高崎線","JE":"京葉線",         "JO":"横須賀・総武線",
  "G":"銀座線",        "M":"丸ノ内線",         "H":"日比谷線",
  "T":"東西線",        "C":"千代田線",         "Y":"有楽町線",
  "Z":"半蔵門線",      "N":"南北線",            "F":"副都心線",
  "A":"浅草線",        "I":"三田線",            "S":"新宿線",
  "E":"大江戸線",
  "TY":"東横線",       "DT":"田園都市線",      "OM":"大井町線",
  "MG":"目黒線",       "KK":"空港線",
  "KO":"京王線",       "KL":"京王相模原線",    "KI":"井の頭線",
  "OH":"小田原線",     "OE":"江ノ島線",
  "SI":"池袋線",       "SS":"新宿線",
  "TJ":"東上線",       "TS":"スカイツリーライン",
  "KS":"本線",         "KE":"本線",
  "MM":"みなとみらい線","SR":"埼玉高速鉄道線",
  "RI":"りんかい線",   "YU":"ゆりかもめ",
  "MO":"東京モノレール",
};

const CARS = {
  "JY":10,"JC":10,"JB":10,"JK":10,"JA":10,"JH":15,"JU":15,"JE":10,
  "G":6,"M":6,"H":8,"T":10,"C":10,"Y":10,"Z":8,"N":6,"F":10,
  "A":5,"I":6,"S":10,"E":12,
  "TY":8,"DT":8,"OM":6,"MG":6,"KK":6,
  "KO":8,"KL":8,"KI":7,
  "OH":10,"OE":8,
  "SI":10,"SS":10,"TJ":8,"TS":8,
  "KS":8,"KE":8,"MM":6,"SR":6,"RI":10,
};

// ── Operator icon (small secondary image below line badge) ────────────────────
const OPERATOR_LOGO_IMG = {
  'JR-East':    '/logos/jr-east.svg',
  'TokyoMetro': '/logos/tokyo-metro.png',
  'Tokyu':      '/logos/tokyu.png',
  'Tobu':       '/logos/tobu.png',
  'Seibu':      '/logos/seibu.png',
  'Odakyu':     '/logos/odakyu.png',
  'Keio':       '/logos/keio.png',
  'Keisei':     '/logos/keisei.png',
  'Keikyu':     '/logos/keikyu.png',
};

function operatorIconHTML(operator) {
  const src = OPERATOR_LOGO_IMG[operator];
  return src ? `<img src="${src}" class="op-icon" alt="${operator}">` : '';
}

function carDiagramHTML(code, color) {
  const n = CARS[code] || 8;
  const blocks = Array.from({length: n}, () =>
    `<span class="car-block" style="background:${color}"></span>`
  ).join('');
  return `<span class="car-diagram">${blocks}<span class="car-count">${n}c</span></span>`;
}

function destJaPrefix(destKey) {
  const ja = DEST_JA[destKey.replace(/^→\s*/, '').trim().toUpperCase()];
  return ja ? `<span class="dest-ja">${ja}</span>` : '';
}

// ── App ────────────────────────────────────────────────────────────────────────
const app = (() => {
  let ws = null;
  let wsRetry = null;
  let mode = 'station';
  let currentStation = 'shibuya';
  let currentLine = 'JY';
  let currentPlatform = 'ALL';
  let selectedLineTrain = null;
  let _lineTrainsCache = [];
  let allStations = [];
  let allLines = [];
  let clockInterval = null;

  // ── Init ─────────────────────────────────────────────────────────────────────

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

  // ── WebSocket ─────────────────────────────────────────────────────────────────

  function connectWS() {
    if (ws) { try { ws.close(); } catch (_) {} }
    ws = new WebSocket(WS_URL);

    ws.onopen = () => { setDevStatus('WS connected'); refresh(); };

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'tick') refresh();
      else if (msg.type === 'station_update') renderStationBoard(msg.station_id, msg.trains);
      else if (msg.type === 'line_update') renderLineTracker(msg.line_code, msg.trains);
    };

    ws.onclose = () => {
      setDevStatus('WS reconnecting…');
      wsRetry = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => { ws.close(); };
  }

  function wsSend(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    else restRefresh();
  }

  function refresh() {
    if (mode === 'station') wsSend({ mode: 'station', station_id: currentStation });
    else wsSend({ mode: 'line', line_code: currentLine });
  }

  async function restRefresh() {
    if (mode === 'station') {
      const trains = await fetch(`${API}/api/trains/station/${currentStation}`).then(r => r.json());
      renderStationBoard(currentStation, trains);
    } else {
      const trains = await fetch(`${API}/api/trains/line/${currentLine}`).then(r => r.json());
      renderLineTracker(currentLine, trains);
    }
  }

  // ── Data loading ──────────────────────────────────────────────────────────────

  async function loadLines() {
    allLines = await fetch(`${API}/api/lines`).then(r => r.json());
  }

  async function loadStations() {
    allStations = await fetch(`${API}/api/stations`).then(r => r.json());
  }

  // ── Mode switching ────────────────────────────────────────────────────────────

  function setMode(m, skipPicker = false) {
    mode = m;
    document.querySelectorAll('.mode-view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
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
    closePltPopup();
    refresh();
  }

  function togglePltPopup() {
    const popup = document.getElementById('plt-popup');
    popup.classList.toggle('hidden');
  }

  function closePltPopup() {
    document.getElementById('plt-popup').classList.add('hidden');
  }

  function selectLine(lineCode) {
    currentLine = lineCode;
    renderLineHero(null, null);
    const devSel = document.getElementById('dev-line-select');
    if (devSel) devSel.value = lineCode;
    if (mode === 'line') refresh();
  }

  // ── Hero card ─────────────────────────────────────────────────────────────────

  function renderHeroCard(train) {
    const badgeWrap = document.getElementById('next-badge-wrap');
    if (!train) {
      badgeWrap.innerHTML = `<svg viewBox="0 0 68 68" class="op-logo">
        <rect width="68" height="68" rx="5" fill="#1a1a1a"/>
        <text x="34" y="38" font-size="24" fill="#333" text-anchor="middle" dominant-baseline="middle" font-family="monospace">?</text>
      </svg>`;
      document.getElementById('next-line-name').innerHTML = '';
      document.getElementById('next-dest').innerHTML = 'NO SERVICE';
      document.getElementById('next-dest').style.cssText = 'color:#333';
      document.getElementById('next-eta').textContent = '–';
      document.getElementById('next-eta').style.cssText = '';
      document.getElementById('next-delay').textContent = '';
      document.getElementById('next-platform').textContent = '';
      return;
    }

    const line = allLines.find(l => l.code === train.line_code) || {};
    const operator = line.operator || '';
    const bright = brighten(train.color);

    // Line badge (primary) + small operator icon (secondary)
    const shape = train.shape || line.shape || 'rect';
    const br = shape === 'circle' ? '50%' : shape === 'square' ? '4px' : '8px';
    const glow = `0 0 16px ${train.color}99, 0 0 32px ${train.color}44`;
    const badge = document.getElementById('next-badge');
    badge.textContent = train.line_code;
    badge.style.cssText = `background:${train.color};color:${train.text_color};border-radius:${br};box-shadow:${glow};`;

    // Swap out any old op-icon, add new one
    const oldIcon = badgeWrap.querySelector('.op-icon');
    if (oldIcon) oldIcon.remove();
    const iconHtml = operatorIconHTML(operator);
    if (iconHtml) badgeWrap.insertAdjacentHTML('beforeend', iconHtml);

    // Line name row: kanji + english + car diagram (right-aligned)
    const lineJa = LINE_NAME_JA[train.line_code] || '';
    const lineName = (line.name || line.short || train.line_code).toUpperCase();
    const jaHtml = lineJa ? `<span class="line-name-ja">${lineJa}</span>` : '';
    document.getElementById('next-line-name').innerHTML =
      `${jaHtml}<span class="line-name-en">${lineName}</span>${carDiagramHTML(train.line_code, train.color)}`;

    // Destination with kanji
    const destKey = train.destination.toUpperCase();
    const destEl = document.getElementById('next-dest');
    destEl.innerHTML = `${destJaPrefix(destKey)}<span>→ ${train.destination}</span>`;
    destEl.style.color = bright;
    destEl.style.textShadow = `0 0 10px ${train.color}99, 0 0 20px ${train.color}44`;

    // ETA
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
      etaEl.style.textShadow = eta <= 4 ? '0 0 10px #ffd70099' : '0 0 8px #9acd3266';
    }

    document.getElementById('next-delay').textContent =
      train.delay_min > 0 ? `+${train.delay_min}m delay` : '';
    document.getElementById('next-platform').textContent =
      train.platform ? `PLT ${train.platform}` : '';
  }

  // ── Platform popup ────────────────────────────────────────────────────────────

  function renderPlatformStrip(trains) {
    const buttons = document.getElementById('platform-buttons');
    const trigger = document.getElementById('plt-trigger');

    const seen = new Set();
    trains.forEach(t => { if (t.platform && t.platform !== '–') seen.add(String(t.platform)); });
    const platforms = [...seen].sort((a, b) => {
      const na = parseFloat(a), nb = parseFloat(b);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return a.localeCompare(b);
    });

    if (currentPlatform !== 'ALL' && !platforms.includes(currentPlatform)) currentPlatform = 'ALL';

    trigger.textContent = currentPlatform !== 'ALL' ? `P${currentPlatform}` : 'PLT';
    trigger.classList.toggle('active', currentPlatform !== 'ALL');

    if (platforms.length <= 1) { buttons.innerHTML = ''; return; }

    buttons.innerHTML = ['ALL', ...platforms].map(p =>
      `<button class="plt-btn ${currentPlatform === p ? 'active' : ''}" onclick="app.selectPlatform('${p}')">${p}</button>`
    ).join('');
  }

  // ── Station board ─────────────────────────────────────────────────────────────

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

    const visible = currentPlatform === 'ALL'
      ? trains
      : trains.filter(t => String(t.platform || '–') === currentPlatform);

    renderHeroCard(visible[0] || trains[0]);
    renderPlatformStrip(trains);

    const upcoming = visible.slice(1);
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

      if (bucketIdx >= 0 && bucketIdx !== lastBucket) {
        html += `<div class="time-divider">
          <span class="time-divider-label">${BUCKETS[bucketIdx].label}</span>
          <span class="time-divider-line"></span>
        </div>`;
        lastBucket = bucketIdx;
      }

      const line = allLines.find(l => l.code === t.line_code) || t;
      const timeClass = eta <= 2 ? 'arriving' : eta <= 5 ? 'soon' : 'normal';
      const timeText = eta <= 1 ? 'NOW' : String(eta);
      const plat = String(t.platform || '–');
      const badgeShape = t.shape || line.shape || 'rect';
      const delayDot = t.delay_min > 0 ? `<span class="delay-dot"></span>` : '';
      const jaPrefix = destJaPrefix(t.destination);

      html += `<div class="board-row train-row" style="border-left:3px solid ${t.color}">
        <span class="col-line">
          <span class="inline-badge shape-${badgeShape}" style="background:${t.color};color:${t.text_color}">${t.line_code}</span>
        </span>
        <span class="col-dest" style="color:${brighten(t.color)}">${jaPrefix}${truncate(t.destination, 11)}${delayDot}</span>
        <span class="col-plat">${plat}</span>
        <span class="col-time"><span class="time-val ${timeClass}">${timeText}</span></span>
      </div>`;
    });

    list.innerHTML = html;

    if (upcoming.length === 0 && currentPlatform !== 'ALL') {
      noTrains.textContent = `No more trains on platform ${currentPlatform}`;
      noTrains.classList.remove('hidden');
    }
  }

  // ── Line tracker ──────────────────────────────────────────────────────────────

  function renderLineTracker(lineCode, trains) {
    const line = allLines.find(l => l.code === lineCode);
    if (!line) return;

    const nameEl = document.getElementById('tracker-line-name');
    const shape = line.shape || 'rect';
    const br = shape === 'circle' ? '50%' : shape === 'square' ? '2px' : '4px';
    const lineJa = LINE_NAME_JA[lineCode] || '';
    const jaHtml = lineJa
      ? `<span style="font-family:'Noto Sans JP',sans-serif;font-size:9px;color:#8b6c2a;margin-right:4px">${lineJa}</span>`
      : '';

    nameEl.innerHTML = `
      <span style="background:${line.color};color:${line.text_color};font-family:'Press Start 2P',monospace;font-size:7px;padding:2px 4px;border-radius:${br};box-shadow:0 0 8px ${line.color}88">${lineCode}</span>
      ${jaHtml}
      <span style="font-family:'Press Start 2P',monospace;font-size:7px;color:${line.color};text-shadow:0 0 8px ${line.color}66">${line.short.toUpperCase()}</span>
      <span style="font-size:8px;color:#333;margin-left:auto;font-family:'Share Tech Mono',monospace">${trains.length} trains</span>
    `;

    _lineTrainsCache = trains;

    // Keep hero in sync on data refresh
    if (selectedLineTrain) {
      const updated = trains.find(t => t.train_number === selectedLineTrain.train_number);
      renderLineHero(updated || null, line);
    }

    const container = document.getElementById('tracker-trains');
    if (!trains || trains.length === 0) {
      container.innerHTML = '<div style="color:#444;font-size:10px;padding:10px 6px">No train data</div>';
      return;
    }

    container.innerHTML = trains.slice(0, 12).map((t, i) => {
      const delayStr = t.delay_min > 0 ? `<span class="tracker-delay">+${t.delay_min}min</span>` : '';
      const destKey = (t.destination || '').toUpperCase();
      const jaSpan = DEST_JA[destKey] ? `<span class="tracker-dest-ja">${DEST_JA[destKey]}</span>` : '';
      const progress = buildProgressBar(t, line);
      const isSelected = selectedLineTrain && selectedLineTrain.train_number === t.train_number;
      return `<div class="tracker-train${isSelected ? ' selected' : ''}" onclick="app._selectLineTrain(${i})" style="${isSelected ? `border-left:3px solid ${line.color}` : ''}">
        <div class="tracker-train-header">
          <span class="tracker-train-num">#${t.train_number}</span>
          <span class="tracker-dest" style="color:${brighten(t.color)}">${jaSpan}&rarr; ${t.destination}</span>
          ${delayStr}
        </div>
        ${progress}
      </div>`;
    }).join('');
  }

  function _selectLineTrain(idx) {
    const line = allLines.find(l => l.code === currentLine);
    if (!line) return;
    const train = _lineTrainsCache[idx];
    if (!train) return;
    if (selectedLineTrain && selectedLineTrain.train_number === train.train_number) {
      renderLineHero(null, line);
    } else {
      renderLineHero(train, line);
    }
  }

  function renderLineHero(train, line) {
    const hero = document.getElementById('tracker-hero');
    selectedLineTrain = train;
    if (!train || !line) {
      hero.classList.add('hidden');
      hero.innerHTML = '';
      return;
    }
    const shape = line.shape || 'rect';
    const br = shape === 'circle' ? '50%' : shape === 'square' ? '2px' : '5px';
    const opIcon = operatorIconHTML(line.operator);
    const jaPrefix = destJaPrefix(train.destination);
    const from = (train.from_station || '').toUpperCase();
    const to   = (train.to_station   || '').toUpperCase();
    const posHtml = (from || to)
      ? `<div style="font-family:'Share Tech Mono',monospace;font-size:9px;color:#555;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${from} → ${to}</div>`
      : '';
    const delayHtml = train.delay_min > 0
      ? `<span style="font-family:'Share Tech Mono',monospace;font-size:10px;color:#e87722">+${train.delay_min}min</span>`
      : '';

    hero.innerHTML = `
      <div style="width:90px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;padding:6px;flex-shrink:0">
        <div style="width:58px;height:58px;display:flex;align-items:center;justify-content:center;
                    background:${line.color};color:${line.text_color};
                    font-family:'Press Start 2P',monospace;font-size:18px;border-radius:${br};
                    box-shadow:0 0 10px ${line.color}66">
          ${line.code}
        </div>
        ${opIcon}
      </div>
      <div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:6px 8px 6px 0;gap:3px;overflow:hidden;min-width:0">
        <div style="font-family:'Share Tech Mono',monospace;font-size:9px;color:#444">#${train.train_number || '—'}</div>
        <div style="display:flex;align-items:baseline;gap:3px;overflow:hidden">
          ${jaPrefix}<span style="font-family:'Press Start 2P',monospace;font-size:11px;color:${brighten(line.color)};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">→ ${truncate(train.destination, 10)}</span>
        </div>
        ${posHtml}
        ${delayHtml}
      </div>
    `;
    hero.classList.remove('hidden');
  }

  function buildProgressBar(train, line) {
    const from = train.from_station || '';
    const to = train.to_station || '';
    if (!from && !to) return '';
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

  // ── Station picker ────────────────────────────────────────────────────────────

  function openStationPicker() {
    const overlay = document.getElementById('station-picker');
    overlay.classList.remove('hidden');
    const input = document.getElementById('station-search');
    input.value = '';
    renderStationResults('');
    setTimeout(() => input.focus(), 50);
    input.oninput = () => renderStationResults(input.value);
    input.onkeydown = e => { if (e.key === 'Escape') closeStationPicker(); };
  }

  function closeStationPicker() {
    document.getElementById('station-picker').classList.add('hidden');
  }

  function renderStationResults(query) {
    const q = query.toLowerCase();
    const results = allStations.filter(s =>
      !q || s.name_en.toLowerCase().includes(q) || s.name_ja.includes(q)
    ).slice(0, 20);

    document.getElementById('station-results').innerHTML = results.map(s => {
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

  function _pickStation(id) { closeStationPicker(); selectStation(id); setMode('station'); }

  // ── Line picker ───────────────────────────────────────────────────────────────

  function openLinePicker() {
    document.getElementById('line-picker').classList.remove('hidden');
    document.getElementById('line-results').innerHTML = allLines.map(l =>
      `<div class="line-picker-item" onclick="app._pickLine('${l.code}')">
        <span class="line-badge shape-${l.shape}" style="background:${l.color};color:${l.text_color};font-size:9px;height:16px;min-width:22px">${l.code}</span>
        <span class="lp-code">${truncate(l.short, 8)}</span>
      </div>`
    ).join('');
  }

  function closeLinePicker() { document.getElementById('line-picker').classList.add('hidden'); }
  function _pickLine(code) { closeLinePicker(); selectLine(code); setMode('line', true); }

  // ── Dev controls ──────────────────────────────────────────────────────────────

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

  // ── Helpers ───────────────────────────────────────────────────────────────────

  function truncate(str, n) {
    if (!str) return '';
    str = str.toUpperCase();
    return str.length > n ? str.slice(0, n - 1) + '…' : str;
  }

  function brighten(hex) {
    if (!hex || !hex.startsWith('#')) return hex;
    let r = parseInt(hex.slice(1,3), 16);
    let g = parseInt(hex.slice(3,5), 16);
    let b = parseInt(hex.slice(5,7), 16);
    r = Math.min(255, Math.round(r * 1.4 + 40));
    g = Math.min(255, Math.round(g * 1.4 + 40));
    b = Math.min(255, Math.round(b * 1.4 + 40));
    return `rgb(${r},${g},${b})`;
  }

  return { init, setMode, selectStation, selectLine, selectPlatform, togglePltPopup, openStationPicker, openLinePicker, _pickStation, _pickLine, _selectLineTrain };
})();

document.addEventListener('DOMContentLoaded', () => {
  app.init();
  document.addEventListener('click', e => {
    const popup = document.getElementById('plt-popup');
    const trigger = document.getElementById('plt-trigger');
    if (popup && !popup.classList.contains('hidden') &&
        !popup.contains(e.target) && e.target !== trigger) {
      popup.classList.add('hidden');
    }
  });
});
