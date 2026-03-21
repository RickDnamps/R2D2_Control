/**
 * R2-D2 Control Dashboard — app.js
 * Holographic theme — Classes + REST polling
 * No external dependencies.
 */

'use strict';

// ================================================================
// Utilities
// ================================================================

function el(id) { return document.getElementById(id); }

function escapeHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

// ================================================================
// API Helper
// ================================================================

async function api(endpoint, method = 'GET', body = null) {
  try {
    const base = (typeof window.R2D2_API_BASE === 'string' && window.R2D2_API_BASE) ? window.R2D2_API_BASE : '';
    const url  = base + endpoint;
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const data = await res.json();
    return data;
  } catch (e) {
    console.error(`API ${method} ${endpoint}:`, e);
    return null;
  }
}

// ================================================================
// Toast Manager
// ================================================================

class ToastManager {
  constructor() {
    this._el = el('toast');
    this._timer = null;
  }

  show(msg, type = 'info') {
    const t = this._el;
    t.textContent = msg;
    t.className = `toast toast-${type} show`;
    clearTimeout(this._timer);
    this._timer = setTimeout(() => t.classList.remove('show'), 3000);
  }
}

const toastMgr = new ToastManager();
function toast(msg, type = 'info') { toastMgr.show(msg, type); }

// ================================================================
// Tab Navigation
// ================================================================

function switchTab(tabId) {
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const tabBtn = document.querySelector(`.tab[data-tab="${tabId}"]`);
  const tabContent = el(`tab-${tabId}`);
  if (tabBtn) tabBtn.classList.add('active');
  if (tabContent) tabContent.classList.add('active');

  if (tabId === 'config') { loadSettings(); loadServoSettings(); }
  if (tabId === 'sequences') loadScripts();
  if (tabId === 'audio') loadAudioCategories();
  if (tabId === 'vesc') vescPanel.refresh();
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ================================================================
// Battery Gauge
// ================================================================

class BatteryGauge {
  constructor() {
    this._arc      = el('battery-gauge-arc');
    this._arcMini  = el('battery-arc-path');
    this._text     = el('battery-gauge-text');
    this._pct      = el('battery-pct');
    this._TOTAL    = 170;   // full arc length (main)
    this._MINI     = 63;    // full arc length (mini header)
    this._MIN_V    = 20.0;
    this._MAX_V    = 29.4;
  }

  update(voltage) {
    if (!voltage || voltage < 1) return;
    const pct  = Math.max(0, Math.min(1, (voltage - this._MIN_V) / (this._MAX_V - this._MIN_V)));
    const color = pct > 0.5 ? '#00cc66' : pct > 0.25 ? '#ff8800' : '#ff2244';

    // Main arc
    if (this._arc) {
      const offset = this._TOTAL * (1 - pct);
      this._arc.style.strokeDashoffset = offset;
      this._arc.style.stroke = color;
    }
    if (this._text) {
      this._text.textContent = voltage.toFixed(1) + 'V';
      this._text.style.fill = color;
    }

    // Mini header arc
    if (this._arcMini) {
      const offsetMini = this._MINI * (1 - pct);
      this._arcMini.style.strokeDashoffset = offsetMini;
      this._arcMini.style.stroke = color;
    }
    if (this._pct) {
      this._pct.textContent = voltage.toFixed(1) + 'V';
      this._pct.style.color = color;
    }
  }
}

const batteryGauge = new BatteryGauge();

// ================================================================
// Virtual Joystick
// ================================================================

class VirtualJoystick {
  constructor(ringId, knobId, onMove, onStop, valXId = null, valYId = null) {
    this.ring   = el(ringId);
    this.knob   = el(knobId);
    this.onMove = onMove;
    this.onStop = onStop;
    this._valXId = valXId;
    this._valYId = valYId;
    this.active = false;
    this.x = 0;
    this.y = 0;
    this._keepAlive = null;  // timer keep-alive watchdog Master
    this._bind();
  }

  _bind() {
    const r = this.ring;
    r.addEventListener('touchstart',  e => { e.preventDefault(); this._start(e.touches[0]); }, { passive: false });
    r.addEventListener('touchmove',   e => { e.preventDefault(); this._move(e.touches[0]); },  { passive: false });
    r.addEventListener('touchend',    () => this._release());
    r.addEventListener('touchcancel', () => this._release());
    r.addEventListener('mousedown',   e => this._start(e));
    document.addEventListener('mousemove', e => { if (this.active) this._move(e); });
    document.addEventListener('mouseup',   () => { if (this.active) this._release(); });
  }

  _start(ptr) {
    this.active = true;
    this.ring.classList.add('active');
    this._move(ptr);
    // Keep-alive : renvoie la position courante toutes les 200ms pendant que
    // le joystick est tenu immobile — alimente le MotionWatchdog côté Master.
    this._keepAlive = setInterval(() => {
      if (this.active) this.onMove(this.x, this.y);
    }, 200);
  }

  _move(ptr) {
    if (!this.active) return;
    const rect   = this.ring.getBoundingClientRect();
    const cx     = rect.left + rect.width  / 2;
    const cy     = rect.top  + rect.height / 2;
    const radius = rect.width / 2;
    const dx     = ptr.clientX - cx;
    const dy     = ptr.clientY - cy;
    const maxR   = radius * 0.72;
    const dist   = Math.sqrt(dx * dx + dy * dy);
    const clamp  = Math.min(dist, maxR);
    const angle  = Math.atan2(dy, dx);
    const kx     = Math.cos(angle) * clamp;
    const ky     = Math.sin(angle) * clamp;

    this.x = Math.max(-1, Math.min(1, dx / maxR));
    this.y = Math.max(-1, Math.min(1, dy / maxR));

    this.knob.style.transform = `translate(calc(-50% + ${kx}px), calc(-50% + ${ky}px))`;
    this.onMove(this.x, this.y);

    // Android haptic feedback — light vibration when joystick moves significantly
    const nx = this.x;
    const ny = this.y;
    if (window.AndroidBridge && Math.abs(nx) + Math.abs(ny) > 0.1) {
      window.AndroidBridge.vibrate(20);
    }

    // Update value displays
    if (this._valXId) {
      const vx = el(this._valXId);
      if (vx) vx.textContent = this.x.toFixed(2);
    }
    if (this._valYId) {
      const vy = el(this._valYId);
      if (vy) vy.textContent = this.y.toFixed(2);
    }
  }

  _release() {
    this.active = false;
    clearInterval(this._keepAlive);
    this._keepAlive = null;
    this.x = 0;
    this.y = 0;
    this.ring.classList.remove('active');
    this.knob.style.transform = 'translate(-50%, -50%)';
    this.onStop();
    if (this._valXId) { const v = el(this._valXId); if (v) v.textContent = '0.00'; }
    if (this._valYId) { const v = el(this._valYId); if (v) v.textContent = '0.00'; }
  }
}

// ================================================================
// Propulsion & Dome
// ================================================================

let _speedLimit = 0.6;

function setSpeed(val) {
  _speedLimit = val / 100;
  el('speed-val').textContent = val + '%';
  // update slider gradient
  const slider = el('speed-slider');
  if (slider) slider.style.setProperty('--val', val + '%');
}

function driveStop()       { api('/motion/stop',      'POST'); }
function domeStop()        { api('/motion/dome/stop', 'POST'); }
function domeRandom(on)    { api('/motion/dome/random', 'POST', { enabled: on }); }

function emergencyStop() {
  driveStop();
  domeStop();
  api('/audio/stop', 'POST');
  api('/servo/dome/close_all', 'POST');
  api('/servo/body/close_all', 'POST');
  api('/system/estop', 'POST');
  toast('EMERGENCY STOP', 'error');
  audioBoard.setPlaying(false);
}

// Left joystick — Propulsion (arcade drive)
let _leftActive = false;
const jsLeft = new VirtualJoystick(
  'js-left-ring', 'js-left-knob',
  (x, y) => {
    _leftActive = true;
    const throttle = -y * _speedLimit;
    const steering =  x * _speedLimit * 0.55;
    api('/motion/arcade', 'POST', { throttle, steering });
    // update throttle/steer displays
    const t = el('js-left-t'); if (t) t.textContent = throttle.toFixed(2);
    const s = el('js-left-s'); if (s) s.textContent = steering.toFixed(2);
  },
  () => {
    _leftActive = false;
    driveStop();
    const t = el('js-left-t'); if (t) t.textContent = '0.00';
    const s = el('js-left-s'); if (s) s.textContent = '0.00';
  }
);

// Right joystick — Dome
let _domeActive = false;
const jsRight = new VirtualJoystick(
  'js-right-ring', 'js-right-knob',
  (x, y) => {
    const DEADZONE = 0.06;
    const vx = el('js-right-x'); if (vx) vx.textContent = x.toFixed(2);
    const vy = el('js-right-y'); if (vy) vy.textContent = y.toFixed(2);
    if (Math.abs(x) > DEADZONE) {
      api('/motion/dome/turn', 'POST', { speed: x * 0.85 });
      _domeActive = true;
    } else if (_domeActive) {
      domeStop();
      _domeActive = false;
    }
  },
  () => {
    domeStop();
    _domeActive = false;
    const vx = el('js-right-x'); if (vx) vx.textContent = '0.00';
    const vy = el('js-right-y'); if (vy) vy.textContent = '0.00';
  }
);

// ================================================================
// Keyboard Control (WASD / Arrows)
// ================================================================

const _keys = {};
const KBD_IDS = { 'KeyW': 'kbd-w', 'ArrowUp': 'kbd-w', 'KeyS': 'kbd-s', 'ArrowDown': 'kbd-s',
                  'KeyA': 'kbd-a', 'ArrowLeft': 'kbd-a', 'KeyD': 'kbd-d', 'ArrowRight': 'kbd-d' };

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
  if (e.code === 'Space') { e.preventDefault(); emergencyStop(); return; }
  if (_keys[e.code]) return;
  _keys[e.code] = true;
  _updateKbdUI();
  _handleKeys();
});

document.addEventListener('keyup', e => {
  delete _keys[e.code];
  _updateKbdUI();
  _handleKeys();
});

function _updateKbdUI() {
  ['kbd-w','kbd-s','kbd-a','kbd-d'].forEach(id => {
    const k = el(id);
    if (k) k.classList.remove('active');
  });
  Object.keys(_keys).forEach(code => {
    const id = KBD_IDS[code];
    if (id) { const k = el(id); if (k) k.classList.add('active'); }
  });
}

function _handleKeys() {
  if (_leftActive) return; // joystick takes priority
  const fwd   = _keys['KeyW'] || _keys['ArrowUp'];
  const back  = _keys['KeyS'] || _keys['ArrowDown'];
  const left  = _keys['KeyA'] || _keys['ArrowLeft'];
  const right = _keys['KeyD'] || _keys['ArrowRight'];

  if (!fwd && !back && !left && !right) { driveStop(); return; }

  const throttle = (fwd ? 1 : back  ? -1 : 0) * _speedLimit;
  const steering = (right ? 1 : left ? -1 : 0) * _speedLimit * 0.5;
  api('/motion/arcade', 'POST', { throttle, steering });
}

// ================================================================
// Teeces Controller
// ================================================================

class TeecesController {
  constructor() {
    this._currentMode = 'random';
    this._initFLD();
    this._initPSI();
  }

  _initFLD() {
    const PSI_COLORS = [
      '#ff2244','#ff8800','#ffee00','#00cc66',
      '#00aaff','#8844ff','#ff44aa','#ffffff'
    ];

    // Build FLD dots (3 rows x 10 dots)
    for (let row = 0; row < 3; row++) {
      const rowEl = el(`fld-row-${row}`);
      if (!rowEl) continue;
      rowEl.innerHTML = '';
      for (let col = 0; col < 10; col++) {
        const dot = document.createElement('div');
        dot.className = 'fld-dot';
        rowEl.appendChild(dot);
      }
    }
    // Set initial mode
    this._applyFLDMode('random');

    // Build PSI swatches
    const swatches = el('psi-swatches');
    if (swatches) {
      swatches.innerHTML = PSI_COLORS.map((c, i) => `
        <div class="psi-swatch" style="background:${c};box-shadow:0 0 8px ${c}40"
             onclick="teecesController.setPSI(${i+1})" title="PSI mode ${i+1}"></div>
      `).join('');
    }
  }

  _initPSI() {
    // PSI dots start blue
    const pl = el('psi-left');
    const pr = el('psi-right');
    if (pl) { pl.style.background = '#00aaff'; pl.style.boxShadow = '0 0 10px #00aaff'; }
    if (pr) { pr.style.background = '#00aaff'; pr.style.boxShadow = '0 0 10px #00aaff'; }
  }

  _applyFLDMode(mode) {
    const preview = el('fld-preview');
    if (!preview) return;
    preview.className = `fld-preview mode-${mode}`;
  }

  setMode(mode) {
    this._currentMode = mode;
    api(`/teeces/${mode}`, 'POST').then(d => {
      if (d) toast(`Teeces: ${mode.toUpperCase()}`, 'ok');
    });
    document.querySelectorAll('[id^="teeces-btn-"]').forEach(b => b.classList.remove('btn-active'));
    const btn = el(`teeces-btn-${mode}`);
    if (btn) btn.classList.add('btn-active');
    this._applyFLDMode(mode);
  }

  sendText(text) {
    if (!text) return;
    api('/teeces/text', 'POST', { text }).then(d => {
      if (d) toast(`FLD: "${text}"`, 'ok');
    });
  }

  setPSI(modeNum) {
    api('/teeces/psi', 'POST', { mode: modeNum }).then(d => {
      if (d) toast(`PSI mode ${modeNum}`, 'ok');
    });
    const PSI_COLORS = ['#ff2244','#ff8800','#ffee00','#00cc66','#00aaff','#8844ff','#ff44aa','#ffffff'];
    const color = PSI_COLORS[modeNum - 1] || '#00aaff';
    ['psi-left','psi-right'].forEach(id => {
      const d = el(id);
      if (d) { d.style.background = color; d.style.boxShadow = `0 0 10px ${color}`; }
    });
    // highlight active swatch
    document.querySelectorAll('.psi-swatch').forEach((s, i) => {
      s.classList.toggle('active', i === modeNum - 1);
    });
  }
}

const teecesController = new TeecesController();

function teecesMode(mode)  { teecesController.setMode(mode); }
function sendTeecesText()  { teecesController.sendText(el('teeces-text').value.trim()); }

// ================================================================
// Servo Panel
// ================================================================

class ServoPanel {
  constructor(gridId, servos, apiPrefix) {
    this._gridId    = gridId;
    this._servos    = servos;
    this._apiPrefix = apiPrefix;  // e.g. '/servo/dome' or '/servo/body'
    this._state     = {};
    this._servos.forEach(n => this._state[n] = 'close');
    this.render();
  }

  render() {
    const grid = el(this._gridId);
    if (!grid) return;
    const varName = this._getVar();
    grid.innerHTML = this._servos.map(name => {
      const num      = name.split('_').pop();
      const panel    = (_servoCfg.panels || {})[name] || { open: 110, close: 20, speed: 10 };
      return `
        <div class="servo-row" id="servo-row-${name}">
          <span class="servo-name">P${num}</span>
          <div class="servo-calib-wrap">
            <label class="servo-calib-label">O<input type="number" id="sc-open-${name}"
              class="servo-angle-in" min="10" max="170" value="${panel.open}"></label>
            <label class="servo-calib-label">C<input type="number" id="sc-close-${name}"
              class="servo-angle-in" min="10" max="170" value="${panel.close}"></label>
            <label class="servo-calib-label">S<input type="number" id="sc-speed-${name}"
              class="servo-angle-in" min="1" max="10" value="${panel.speed ?? 10}"></label>
          </div>
          <button class="btn btn-sm" onclick="${varName}.open('${name}')">OPEN</button>
          <button class="btn btn-sm btn-dark" onclick="${varName}.close('${name}')">CLOSE</button>
        </div>
      `;
    }).join('');
  }

  updateInputs() {
    this._servos.forEach(name => {
      const panel = (_servoCfg.panels || {})[name];
      if (!panel) return;
      const oEl = el(`sc-open-${name}`);
      const cEl = el(`sc-close-${name}`);
      const sEl = el(`sc-speed-${name}`);
      if (oEl) oEl.value = panel.open;
      if (cEl) cEl.value = panel.close;
      if (sEl) sEl.value = panel.speed ?? 10;
    });
  }

  _getVar() {
    return this._apiPrefix.includes('dome') ? 'domeServoPanel' : 'bodyServoPanel';
  }

  open(name) {
    api(`${this._apiPrefix}/open`, 'POST', { name }).then(d => {
      if (d) { toast(`P${name.split('_').pop()}: OPEN`, 'ok'); this._setFill(name, 100); }
    });
    this._state[name] = 'open';
  }

  close(name) {
    api(`${this._apiPrefix}/close`, 'POST', { name }).then(d => {
      if (d) { toast(`P${name.split('_').pop()}: CLOSE`, 'ok'); this._setFill(name, 0); }
    });
    this._state[name] = 'close';
  }

  async saveAngles() {
    const panels = {};
    this._servos.forEach(name => {
      const oEl = el(`sc-open-${name}`);
      const cEl = el(`sc-close-${name}`);
      const sEl = el(`sc-speed-${name}`);
      if (oEl && cEl) {
        panels[name] = {
          open:  parseInt(oEl.value) || 110,
          close: parseInt(cEl.value) || 20,
          speed: parseInt(sEl?.value) || 10,
        };
      }
    });
    const data = await api('/servo/settings', 'POST', { panels });
    if (!data) { toast('Erreur réseau', 'error'); return; }
    _servoCfg = data;
    this.updateInputs();
    toast('Angles sauvegardés', 'ok');
  }

  _setFill(name, pct) {
    const f = el(`servo-fill-${name}`);
    if (f) f.style.width = pct + '%';
  }
}

// Servo calibration config (loaded from /servo/settings at init)
// Format : { ms_90deg: 150, panels: { dome_panel_1: { open: 70, close: 70, open_ms: 117, close_ms: 117 }, ... } }
let _servoCfg = { ms_90deg: 150, panels: {} };

async function loadServoSettings() {
  const data = await api('/servo/settings');
  if (!data) return;
  _servoCfg = data;
  if (el('servo-ms90')) el('servo-ms90').value = data.ms_90deg;
  updateServoDurationPreview();
  domeServoPanel.updateInputs();
  bodyServoPanel.updateInputs();
}

function updateServoDurationPreview() {
  const ms90 = parseInt(el('servo-ms90')?.value ?? _servoCfg.ms_90deg ?? 150);
  if (isNaN(ms90)) return;
  const dur  = Math.max(50, Math.round(70 / 90 * ms90));
  const prev = el('servo-duration-preview');
  if (prev) prev.textContent = `Exemple 70° = ${dur} ms`;
}

async function saveServoMs90() {
  const ms90 = parseInt(el('servo-ms90')?.value ?? 150);
  const data = await api('/servo/settings', 'POST', { ms_90deg: ms90, panels: {} });
  if (!data) { toast('Erreur réseau', 'error'); return; }
  _servoCfg = data;
  updateServoDurationPreview();
  domeServoPanel.updateInputs();
  bodyServoPanel.updateInputs();
  toast(`ms_90deg sauvegardé: ${ms90} ms`, 'ok');
}

async function testServoSettings(dir) {
  const endpoint = dir === 'open' ? '/servo/dome/open' : '/servo/dome/close';
  const data = await api(endpoint, 'POST', { name: 'dome_panel_1' });
  if (data) toast(`Test dome_panel_1 ${dir.toUpperCase()} — ${data.duration}ms`, 'ok');
}

const DOME_SERVOS = Array.from({length: 11}, (_, i) => `dome_panel_${i + 1}`);
const BODY_SERVOS = Array.from({length: 11}, (_, i) => `body_panel_${i + 1}`);

const domeServoPanel = new ServoPanel('dome-servo-list', DOME_SERVOS, '/servo/dome');
const bodyServoPanel = new ServoPanel('body-servo-list', BODY_SERVOS, '/servo/body');

// ================================================================
// Audio Board
// ================================================================

class AudioBoard {
  constructor() {
    this._currentCat = null;
    this._playing    = false;
    this._ICONS = {
      alarm:'🚨', happy:'😄', hum:'🎵', misc:'🎲', proc:'⚙️', quote:'💬',
      razz:'🤪', sad:'😢', sent:'🤔', ooh:'😲', whistle:'🎶', scream:'😱',
      special:'⭐', sent:'🗣️'
    };
    this._CAT_COLORS = {
      alarm:'#ff2244',  happy:'#ffcc00',  hum:'#00aaff',  misc:'#aa44ff',
      proc:'#00ffea',   quote:'#ff8800',  razz:'#ff44cc',  sad:'#4499ff',
      sent:'#00cc66',   ooh:'#ff6600',    whistle:'#44ffbb', scream:'#ff0055',
      special:'#ffaa00'
    };
    // Noms d'affichage propres pour chaque catégorie
    this._CAT_LABELS = {
      alarm:'Alarm',    happy:'Happy',    hum:'Hum',       misc:'Misc',
      proc:'Process',   quote:'Quote',    razz:'Razz',     sad:'Sad',
      sent:'Sentiment', ooh:'Ooh',        whistle:'Whistle', scream:'Scream',
      special:'Special'
    };
  }

  // Formate un nom de fichier pour l'affichage
  // "Happy001" → "001"  |  "Cantina" → "Cantina"
  _formatSound(filename) {
    const m = filename.match(/^[A-Za-z_]+?(\d+)$/);
    return m ? m[1].replace(/^0+/, '') || '1' : filename;
  }

  async loadCategories() {
    const data = await api('/audio/categories');
    if (!data || !data.categories) return;
    const wrap = el('audio-categories');
    if (!wrap) return;

    // Accepte les deux formats : [{name, count}] ou {name: count}
    const cats = Array.isArray(data.categories)
      ? data.categories
      : Object.entries(data.categories).map(([name, count]) => ({ name, count }));

    wrap.innerHTML = cats.map(({ name, count }) => {
      const color = this._CAT_COLORS[name] || '#00aaff';
      const label = this._CAT_LABELS[name] || name.charAt(0).toUpperCase() + name.slice(1);
      const icon  = this._ICONS[name] || '🔊';
      return `
        <div class="category-pill" id="cat-pill-${name}"
             onclick="audioBoard.selectCategory('${name}')"
             style="--cat-color:${color}">
          <span class="cat-icon">${icon}</span>
          <span class="cat-label">${label}</span>
          <span class="cat-count">${count}</span>
        </div>`;
    }).join('');

    // Sélectionner la première catégorie par défaut
    if (cats.length > 0) this.selectCategory(cats[0].name);
  }

  async selectCategory(cat) {
    this._currentCat = cat;

    // Marquer la pill active
    document.querySelectorAll('.category-pill').forEach(p => p.classList.remove('active'));
    const pill = el(`cat-pill-${cat}`);
    if (pill) {
      pill.classList.add('active');
      pill.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    // Mettre à jour le titre de la section sons
    const label = this._CAT_LABELS[cat] || cat.toUpperCase();
    const color = this._CAT_COLORS[cat] || '#00aaff';
    const nameEl = el('audio-cat-name');
    if (nameEl) {
      nameEl.textContent = label;
      nameEl.style.color  = color;
    }

    // Afficher le spinner pendant le chargement
    const grid = el('audio-sounds-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="sounds-loading">Chargement...</div>';

    const data = await api(`/audio/sounds?category=${cat}`);

    if (data && data.sounds && data.sounds.length > 0) {
      // Bouton RANDOM en premier
      const randomBtn = `
        <button class="sound-btn sound-btn-random"
                onclick="audioBoard.playRandom('${cat}')"
                title="Son aléatoire de ${label}">
          🎲 RANDOM
        </button>`;

      const soundBtns = data.sounds.map(s => {
        const display = this._formatSound(s);
        return `<button class="sound-btn"
                  onclick="audioBoard.play('${escapeHtml(s)}')"
                  title="${escapeHtml(s)}">
                  ${escapeHtml(display)}
                </button>`;
      }).join('');

      grid.innerHTML = randomBtn + soundBtns;
    } else {
      grid.innerHTML = `
        <button class="sound-btn sound-btn-random" onclick="audioBoard.playRandom('${cat}')">
          🎲 RANDOM ${label}
        </button>`;
    }
  }

  play(sound) {
    api('/audio/play', 'POST', { sound }).then(d => {
      if (d && d.ok !== false) this.setPlaying(true, sound);
    });
  }

  playRandom(cat) {
    const c = cat || this._currentCat || 'happy';
    api('/audio/random', 'POST', { category: c }).then(d => {
      if (d) {
        const label = this._CAT_LABELS[c] || c;
        this.setPlaying(true, `🎲 ${label}`);
      }
    });
  }

  setPlaying(active, name = '') {
    this._playing = active;
    const waveform = el('waveform');
    const text     = el('now-playing-text');
    if (waveform) waveform.classList.toggle('playing', active);
    if (text) text.textContent = active ? name : 'IDLE';
  }
}

const audioBoard = new AudioBoard();

function audioStop() {
  api('/audio/stop', 'POST').then(d => {
    if (d) { audioBoard.setPlaying(false); toast('Audio stopped', 'ok'); }
  });
}

function audioRandom() {
  audioBoard.playRandom(null);
}

// ================================================================
// VESC Panel
// ================================================================

class VescPanel {
  constructor() {
    this._scaleDebounce = null;
  }

  // Called by StatusPoller on every refresh
  async refresh() {
    const d = await api('/vesc/telemetry');
    if (!d) return;
    this._updateStatus(d);
    this._updateCard('L', d.L);
    this._updateCard('R', d.R);
    this._updateScale(d.power_scale);
  }

  _updateStatus(d) {
    const pill  = el('vesc-conn-pill');
    const label = el('vesc-conn-label');
    if (!pill) return;
    if (d.connected) {
      pill.classList.add('online');
      label.textContent = 'ONLINE';
    } else {
      pill.classList.remove('online');
      label.textContent = 'OFFLINE';
    }
    // Battery voltage — use whichever side is available
    const src = d.L || d.R;
    const vEl  = el('vesc-voltage');
    const fill = el('vesc-battery-fill');
    if (src && vEl) {
      const v = src.v_in;
      vEl.textContent = v.toFixed(1);
      vEl.className = 'vesc-battery-value' + (v < 21 ? ' danger' : v < 22 ? ' warn' : '');
      // 6S LiPo: 19.2V empty → 25.2V full
      const pct = Math.max(0, Math.min(100, ((v - 19.2) / (25.2 - 19.2)) * 100));
      if (fill) {
        fill.style.width = pct + '%';
        fill.style.background = v < 21 ? '#ff4455' : v < 22 ? '#ffcc00' : '#00ff88';
      }
    } else if (vEl) {
      vEl.textContent = '--.-';
    }
  }

  _updateCard(side, data) {
    const s = side.toLowerCase();
    const fault = el(`v${s}-fault`);
    const card  = el(`vesc-card-${side}`);
    if (!data) {
      if (fault) { fault.textContent = 'OFFLINE'; fault.className = 'vesc-fault'; }
      if (card)  card.classList.remove('fault-active');
      ['temp','curr','rpm','duty'].forEach(k => {
        const e = el(`v${s}-${k}`);
        if (e) e.textContent = '--';
      });
      return;
    }
    // Metrics
    this._setMetric(`v${s}-temp`, data.temp.toFixed(1), data.temp > 80 ? 'danger' : data.temp > 60 ? 'hot' : '');
    this._setMetric(`v${s}-curr`, data.current.toFixed(1), '');
    this._setMetric(`v${s}-rpm`,  Math.abs(data.rpm), '');
    this._setMetric(`v${s}-duty`, Math.round(Math.abs(data.duty) * 100), '');
    // Fault
    if (fault) {
      const isFault = data.fault !== 0;
      fault.textContent = data.fault_str || 'NONE';
      fault.className = 'vesc-fault ' + (isFault ? 'error' : 'ok');
      if (card) card.classList.toggle('fault-active', isFault);
    }
  }

  _setMetric(id, val, cls) {
    const e = el(id);
    if (!e) return;
    e.textContent = val;
    e.className = 'vesc-metric-val' + (cls ? ' ' + cls : '');
  }

  _updateScale(scale) {
    const slider = el('vesc-scale-slider');
    const label  = el('vesc-scale-label');
    const info   = el('vesc-scale-pct');
    const pct = Math.round(scale * 100);
    if (slider && slider !== document.activeElement) slider.value = pct;
    if (label) label.textContent = pct + '%';
    if (info)  info.textContent  = pct;
  }

  initSlider() {
    const slider = el('vesc-scale-slider');
    const label  = el('vesc-scale-label');
    const info   = el('vesc-scale-pct');
    if (!slider) return;
    _updateSliderBg(slider);
    slider.addEventListener('input', () => {
      const pct = parseInt(slider.value, 10);
      if (label) label.textContent = pct + '%';
      if (info)  info.textContent  = pct;
      _updateSliderBg(slider);
      clearTimeout(this._scaleDebounce);
      this._scaleDebounce = setTimeout(() => {
        api('/vesc/config', 'POST', { scale: pct / 100 });
      }, 200);
    });
  }
}

const vescPanel = new VescPanel();

function vescInvert(side) {
  if (!confirm(`Invert ${side === 'L' ? 'LEFT' : 'RIGHT'} motor direction?`)) return;
  api('/vesc/invert', 'POST', { side }).then(d => {
    if (d) toast(`Motor ${side} direction inverted`, 'ok');
  });
}

function vescFocDetect(side) {
  if (!confirm(
    `⚡ FOC AUTODETECT — ${side === 'L' ? 'LEFT' : 'RIGHT'} motor\n\n` +
    `Motor must be FREE TO SPIN.\nDo NOT run this while R2-D2 is on the ground.\n\nContinue?`
  )) return;
  // FOC detect is done via VESC Tool directly — this just shows the reminder
  toast(`FOC Detect: connect via VESC Tool on /dev/ttyACM${side === 'L' ? '0' : '1'}`, 'info');
}

// ================================================================
// CAN Bus Wizard
// ================================================================

const canWizard = {
  _scanning: false,

  async scan() {
    if (this._scanning) return;
    this._scanning = true;

    const btn    = el('can-scan-btn');
    const result = el('can-scan-result');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin">⟳</span> SCANNING…'; }
    if (result) { result.textContent = ''; result.className = 'vesc-can-result'; }

    const d = await api('/vesc/can/scan');
    this._scanning = false;
    if (btn) { btn.disabled = false; btn.innerHTML = 'SCAN CAN BUS'; }

    if (!d || d.error) {
      const msg = (d && d.error) ? d.error : 'Connection failed';
      if (result) {
        result.innerHTML = `<span class="can-err">⚠ ${escapeHtml(msg)}</span>`;
        result.className = 'vesc-can-result show';
      }
      toast('CAN scan failed', 'warn');
      return;
    }
    this._displayResult(d.ids || []);
  },

  _displayResult(ids) {
    const result = el('can-scan-result');
    if (!result) return;

    let html = `<div class="can-found-header">FOUND ${ids.length} VESC${ids.length !== 1 ? 'S' : ''} ON CAN BUS</div>`;

    if (ids.length === 0) {
      html += `<p class="can-info">No VESCs found on CAN bus.<br>Check CAN H/L wiring between VESCs and ensure VESC 1 is connected via USB (/dev/ttyACM0).</p>`;
    } else {
      html += `<div class="can-id-list">`;
      ids.forEach(id => { html += `<span class="can-id-badge">CAN ID ${id}</span>`; });
      html += `</div>`;
      if (ids.length === 1) {
        html += `<p class="can-info">✓ VESC 2 found (CAN ID ${ids[0]}). VESC 1 (USB) is the gateway.</p>`;
      } else if (ids.filter(i => i === 0).length > 0 && ids.length > 1) {
        html += `<p class="can-warn">⚠ Multiple VESCs share CAN ID 0. Assign unique IDs via VESC Tool before operating.</p>`;
      } else {
        html += `<p class="can-info">✓ ${ids.length} VESCs found on CAN bus (IDs: ${ids.join(', ')}).</p>`;
      }
    }
    result.innerHTML = html;
    result.className = 'vesc-can-result show';
    toast(`CAN scan: ${ids.length} VESC${ids.length !== 1 ? 's' : ''} found`, ids.length > 0 ? 'ok' : 'warn');
  },
};

// ================================================================
// Script Engine
// ================================================================

class ScriptEngine {
  constructor() {
    this._scripts = [];
    this._running = new Set();
    this._DESCRIPTIONS = {
      patrol:    'R2-D2 patrols with sounds + dome movement',
      celebrate: 'Victory celebration with lights and sounds',
      cantina:   'Cantina dance routine with audio',
      leia:      'Help me Obi-Wan... holographic message',
    };
  }

  async load() {
    const data = await api('/scripts/list');
    if (!data || !data.scripts) return;
    this._scripts = data.scripts;
    this.render();
  }

  render() {
    const grid = el('script-list');
    if (!grid) return;
    grid.innerHTML = this._scripts.map(name => {
      const desc = this._DESCRIPTIONS[name] || 'Custom sequence script';
      const isRunning = this._running.has(name);
      return `
        <div class="script-card${isRunning ? ' running' : ''}" id="script-card-${name}">
          <div class="script-name">${name.toUpperCase()}</div>
          <div class="script-desc">${desc}</div>
          <div class="script-btns">
            <div class="running-indicator"></div>
            <button class="btn btn-sm btn-active" onclick="scriptEngine.run('${name}', false)">RUN</button>
            <button class="btn btn-sm" onclick="scriptEngine.run('${name}', true)">LOOP</button>
            <button class="btn btn-sm btn-danger" onclick="scriptEngine.stopName('${name}')">STOP</button>
          </div>
        </div>
      `;
    }).join('');
  }

  run(name, loop) {
    api('/scripts/run', 'POST', { name, loop }).then(d => {
      if (d) {
        this._running.add(name);
        const card = el(`script-card-${name}`);
        if (card) card.classList.add('running');
        toast(`${name.toUpperCase()} started${loop ? ' (loop)' : ''}`, 'ok');
      }
    });
  }

  stopName(name) {
    // We'd need the script ID — stop_all as fallback
    api('/scripts/stop_all', 'POST').then(d => {
      if (d) {
        this._running.clear();
        document.querySelectorAll('.script-card').forEach(c => c.classList.remove('running'));
        toast('Sequences stopped', 'ok');
      }
    });
  }

  updateRunning(running) {
    const names = new Set(running.map(s => s.name));
    this._running = names;

    document.querySelectorAll('.script-card').forEach(card => {
      const name = card.id.replace('script-card-', '');
      card.classList.toggle('running', names.has(name));
    });

    const count = el('running-count');
    if (count) count.textContent = names.size;

    const list = el('running-scripts');
    if (list) {
      list.textContent = running.length
        ? running.map(s => `${s.name}#${s.id}`).join(', ')
        : '—';
    }
  }
}

const scriptEngine = new ScriptEngine();

async function loadScripts() { await scriptEngine.load(); }

// ================================================================
// BT Controller
// ================================================================

class BTController {
  constructor() {
    this._connected = false;
    this._loadMappings();
  }

  updateStatus(data) {
    if (!data) return;
    const connected = data.bt_connected || false;
    const name = data.bt_name || '—';
    const pct  = data.bt_battery || 0;

    this._connected = connected;

    const icon = document.querySelector('.gamepad-icon');
    const statusText = el('bt-status-text');
    const deviceName = el('bt-device-name');
    const pillBt     = el('pill-bt');
    const fillEl     = el('bt-battery-fill');
    const pctEl      = document.querySelector('#bt-battery-pct') || el('bt-battery-pct');

    if (icon)       icon.classList.toggle('connected', connected);
    if (statusText) {
      statusText.textContent = connected ? 'CONNECTED' : 'NOT CONNECTED';
      statusText.classList.toggle('connected', connected);
    }
    if (deviceName) deviceName.textContent = name;
    if (pillBt)     pillBt.className = 'status-pill ' + (connected ? 'ok' : '');

    if (fillEl) {
      const bcolor = pct > 50 ? '#00cc66' : pct > 25 ? '#ff8800' : '#ff2244';
      fillEl.style.width    = pct + '%';
      fillEl.style.background = bcolor;
    }
    if (pctEl) pctEl.textContent = pct + '%';
  }

  _loadMappings() {
    try {
      const saved = localStorage.getItem('r2d2-bt-mappings');
      if (!saved) return;
      const m = JSON.parse(saved);
      if (m.throttle) { const e = el('bt-map-throttle'); if (e) { for (let o of e.options) if (o.value === m.throttle) { o.selected = true; break; } } }
      if (m.steer)    { const e = el('bt-map-steer');    if (e) { for (let o of e.options) if (o.value === m.steer)    { o.selected = true; break; } } }
      if (m.dome)     { const e = el('bt-map-dome');     if (e) { for (let o of e.options) if (o.value === m.dome)     { o.selected = true; break; } } }
      const dz = el('bt-deadzone');
      if (dz && m.deadzone) { dz.value = m.deadzone; el('bt-deadzone-val').textContent = m.deadzone + '%'; }
    } catch (e) { /* ignore */ }
  }

  saveMappings() {
    const m = {
      throttle: el('bt-map-throttle') ? el('bt-map-throttle').value : 'L_STICK_Y',
      steer:    el('bt-map-steer')    ? el('bt-map-steer').value    : 'L_STICK_X',
      dome:     el('bt-map-dome')     ? el('bt-map-dome').value     : 'R_STICK_X',
      panel1:   el('bt-map-panel1')   ? el('bt-map-panel1').value   : 'SQUARE',
      panel2:   el('bt-map-panel2')   ? el('bt-map-panel2').value   : 'TRIANGLE',
      audio:    el('bt-map-audio')    ? el('bt-map-audio').value    : 'CIRCLE',
      deadzone: el('bt-deadzone')     ? el('bt-deadzone').value     : '8',
    };
    localStorage.setItem('r2d2-bt-mappings', JSON.stringify(m));
    toast('BT mapping saved', 'ok');
  }
}

const btController = new BTController();
function saveBTConfig() { btController.saveMappings(); }

let _currentSpeedMode = 'normal';
function setSpeedMode(mode) {
  _currentSpeedMode = mode;
  document.querySelectorAll('.speed-mode-btn').forEach(b => {
    b.classList.toggle('btn-active', b.dataset.mode === mode);
  });
  const limits = { slow: 30, normal: 60, fast: 100 };
  const val = limits[mode] || 60;
  const slider = el('speed-slider');
  if (slider) { slider.value = val; setSpeed(val); }
  toast(`Speed mode: ${mode.toUpperCase()}`, 'ok');
}

// ================================================================
// Status Poller
// ================================================================

class StatusPoller {
  constructor() {
    this._interval = null;
  }

  start(intervalMs = 2000) {
    this.poll();
    this._interval = setInterval(() => this.poll(), intervalMs);
  }

  async poll() {
    const data = await api('/status');
    if (!data) {
      this._setOffline(true);
      return;
    }
    this._setOffline(false);

    this._setPill('pill-heartbeat', data.heartbeat_ok, 'HB');
    this._setUartPill(data.uart_ready, data.uart_health, data.uart_crc_errors ?? 0);

    const version = el('pill-version');
    if (version) version.textContent = 'v' + (data.version || '?');

    const uptime = el('uptime-label');
    if (uptime) uptime.textContent = 'up ' + (data.uptime || '--');

    const sysver = el('system-version');
    if (sysver) sysver.textContent =
      `Master: v${data.version || '?'}  |  Uptime: ${data.uptime || '--'}`;

    // Battery gauge
    if (data.battery_voltage) batteryGauge.update(data.battery_voltage);

    // Temperature
    if (data.temperature != null) {
      const temp = data.temperature;
      const tempLabel = el('temp-label');
      if (tempLabel) tempLabel.textContent = temp + '°C';
      const tempDrive = el('temp-val-drive');
      if (tempDrive) tempDrive.textContent = temp + '°C';
      const fill = el('temp-bar-fill');
      if (fill) {
        const pct = Math.min(100, temp);
        fill.style.height = pct + '%';
        fill.style.background = temp < 60 ? '#00cc66' : temp < 75 ? '#ff8800' : '#ff2244';
      }
      const tempHeader = el('temp-label');
      if (tempHeader) {
        tempHeader.textContent = temp + '°C';
        tempHeader.style.color = temp < 60 ? '#00cc66' : temp < 75 ? '#ff8800' : '#ff2244';
      }
    }

    // BT controller status
    btController.updateStatus(data);

    // Scripts running
    if (data.scripts_running) {
      scriptEngine.updateRunning(data.scripts_running);
    }

    // Teeces state
    if (data.teeces_mode) {
      teecesController._applyFLDMode(data.teeces_mode);
    }

    // VESC telemetry — refresh only if VESC tab is active
    if (el('tab-vesc') && el('tab-vesc').classList.contains('active')) {
      vescPanel.refresh();
    }
  }

  _setOffline(offline) {
    const wasOffline = this._offline;
    this._offline = offline;
    const pillOffline = el('pill-offline');
    if (pillOffline) pillOffline.style.display = offline ? '' : 'none';
    ['pill-heartbeat', 'pill-uart', 'pill-bt', 'pill-version'].forEach(id => {
      const p = el(id);
      if (p) p.style.display = offline ? 'none' : '';
    });
    // Reload data when coming back online
    if (wasOffline && !offline) {
      audioBoard.loadCategories();
      scriptEngine.load();
      loadServoSettings();
    }
  }

  _setUartPill(uartReady, health, masterCrcErrors) {
    const p = el('pill-uart');
    if (!p) return;
    const dot = p.querySelector('.pulse-dot');
    let cls, label, tooltip;

    if (!uartReady) {
      // Port série pas ouvert — erreur niveau OS
      cls     = 'status-pill error';
      label   = 'UART';
      tooltip = 'Port série non ouvert';
    } else if (health == null) {
      // Port ouvert mais Slave pas encore pollé / injoignable
      cls     = masterCrcErrors > 0 ? 'status-pill warn' : 'status-pill ok';
      label   = masterCrcErrors > 0 ? 'UART ERR' : 'UART';
      tooltip = masterCrcErrors > 0
        ? `Slave injoignable | Master CRC invalides: ${masterCrcErrors}`
        : 'Slave pas encore pollé';
    } else {
      // Port ouvert + données qualité disponibles — 3 niveaux
      const pct = health.health_pct;
      if      (pct >= 95) cls = 'status-pill ok';
      else if (pct >= 70) cls = 'status-pill warn';
      else                cls = 'status-pill error';
      label   = 'UART ' + pct.toFixed(0) + '%';
      tooltip = `${health.errors} erreurs / ${health.total} msg (${health.window_s}s)`
              + (masterCrcErrors > 0 ? ` | Master CRC invalides: ${masterCrcErrors}` : '');
    }

    p.className = cls;
    p.title     = tooltip;
    if (dot) {
      for (const node of p.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) node.textContent = label;
      }
    } else {
      p.textContent = label;
    }
  }

  _setPill(id, ok, label) {
    const p = el(id);
    if (!p) return;
    const dot = p.querySelector('.pulse-dot');
    const cls = 'status-pill ' + (ok ? 'ok' : 'error');
    p.className = cls;
    // label text node — update the text without removing the dot
    if (dot) {
      // Only update text nodes
      for (const node of p.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          node.textContent = label;
        }
      }
    } else {
      p.textContent = label;
    }
  }
}

const poller = new StatusPoller();

// Called by MainActivity.kt (Android) when R2D2_API_BASE is updated
// and the server becomes reachable — reloads all dynamic data
function pollStatus() {
  audioBoard.loadCategories();
  scriptEngine.load();
  loadServoSettings();
  poller.poll();
}

// ================================================================
// Clock
// ================================================================

function updateClock() {
  const c = el('clock-label');
  if (!c) return;
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  c.textContent = `${h}:${m}:${s}`;
}

// ================================================================
// Settings
// ================================================================

async function loadSettings() {
  const data = await api('/settings');
  if (!data) return;

  if (data.wifi) {
    const ssid = el('wifi-ssid');
    if (ssid) ssid.value = data.wifi.ssid || '';
    const status = el('wifi-status');
    if (status) {
      if (data.wifi.connected) {
        status.textContent = `Connected | SSID: ${data.wifi.ssid || data.wifi.connection} | IP: ${data.wifi.ip}`;
        status.className = 'settings-status ok';
      } else {
        status.textContent = 'Not connected — wlan1 absent or Master hotspot not available';
        status.className = 'settings-status error';
      }
    }
  }

  if (data.hotspot) {
    const ssid = el('hotspot-ssid');
    if (ssid) ssid.value = data.hotspot.ssid || '';
    const status = el('hotspot-status');
    if (status) {
      status.textContent = data.hotspot.active
        ? `Active | SSID: ${data.hotspot.ssid} | IP: ${data.hotspot.ip}`
        : 'Hotspot inactive';
      status.className = 'settings-status ' + (data.hotspot.active ? 'ok' : 'error');
    }
  }

  if (data.github) {
    const branch = el('git-branch');
    if (branch) branch.value = data.github.branch || 'main';
    const autoPull = el('auto-pull');
    if (autoPull) autoPull.checked = data.github.auto_pull_on_boot;
  }

  if (data.slave) {
    const host = el('slave-host');
    if (host) host.value = data.slave.host || 'r2-slave.local';
  }
}

async function scanWifi() {
  const btn = el('btn-scan');
  if (btn) { btn.textContent = 'SCANNING...'; btn.disabled = true; }
  const data = await api('/settings/wifi/scan');
  if (btn) { btn.textContent = 'SCAN'; btn.disabled = false; }

  const sel = el('wifi-scan-list');
  if (!sel) return;

  if (!data || !data.networks || data.networks.length === 0) {
    sel.innerHTML = '<option value="">No networks found</option>';
    toast('No networks detected on wlan1', 'warn');
    return;
  }

  sel.innerHTML = '<option value="">— Select network —</option>' +
    data.networks.map(n => {
      const bars = n.signal >= 75 ? '++++ ' : n.signal >= 50 ? '+++  ' : n.signal >= 25 ? '++   ' : '+    ';
      const sec  = n.security ? ' [WPA]' : '';
      return `<option value="${escapeHtml(n.ssid)}">${bars}${escapeHtml(n.ssid)}${sec} (${n.signal}%)</option>`;
    }).join('');
}

function onScanSelect(ssid) {
  if (ssid) { const f = el('wifi-ssid'); if (f) f.value = ssid; }
}

async function applyWifi() {
  const ssid     = (el('wifi-ssid')?.value || '').trim();
  const password = el('wifi-password')?.value || '';
  if (!ssid) { toast('SSID required', 'error'); return; }
  toast('Connecting...', 'info');
  const data = await api('/settings/wifi', 'POST', { ssid, password });
  if (!data)       { toast('Network error', 'error'); return; }
  if (data.error)  { toast(data.error, 'error'); return; }
  toast(data.message || (data.connected ? 'wlan1 connected' : 'Config saved'), data.connected ? 'ok' : 'warn');
  await loadSettings();
}

async function applyHotspot() {
  const ssid     = (el('hotspot-ssid')?.value || '').trim();
  const password = el('hotspot-password')?.value || '';
  if (!ssid) { toast('SSID required', 'error'); return; }
  if (password && password.length < 8) { toast('Password: minimum 8 characters', 'error'); return; }
  if (!confirm(`Apply hotspot SSID "${ssid}"? Clients will be disconnected.`)) return;
  toast('Applying hotspot...', 'info');
  const data = await api('/settings/hotspot', 'POST', { ssid, password });
  if (!data)      { toast('Network error', 'error'); return; }
  if (data.error) { toast(data.error, 'error'); return; }
  toast('Hotspot updated', 'ok');
  const pw = el('hotspot-password');
  if (pw) pw.value = '';
  await loadSettings();
}

async function saveConfig() {
  if (!confirm('Save config? (git branch, slave host — restart required to take effect)')) return;
  const payload = {
    'github.branch':            (el('git-branch')?.value || '').trim(),
    'github.auto_pull_on_boot': el('auto-pull')?.checked ? 'true' : 'false',
    'slave.host':               (el('slave-host')?.value || '').trim(),
  };
  const data = await api('/settings/config', 'POST', payload);
  if (data && data.status === 'ok') {
    toast('Config saved', 'ok');
  } else {
    toast('Error saving config', 'error');
  }
}

function confirmAction(msg, endpoint) {
  if (confirm(msg)) {
    api(endpoint, 'POST').then(d => {
      if (d) toast('Command sent', 'ok');
    });
  }
}

async function systemUpdate() {
  if (!confirm('Force update?\n\ngit pull + rsync Slave + reboot Slave')) return;
  toast('Update started…', 'info');
  const d = await api('/system/update', 'POST');
  if (d) toast('Update in progress — Slave will reboot', 'ok');
}

// ================================================================
// Volume slider
// ================================================================

// ALSA bcm2835 maps 0-100% linearly onto ~-102dB..+4dB,
// so 50% ALSA ≈ -49dB (nearly inaudible).
// Square-root curve makes slider 50% → ALSA 71% (≈-28dB, usable).
function _sliderToAlsa(v) { return Math.round(Math.pow(v / 100, 1 / 3) * 100); }
function _alsaToSlider(v) { return Math.round(Math.pow(v / 100, 3) * 100); }

function initVolume() {
  const slider = document.getElementById('volume-slider');
  const label  = document.getElementById('volume-label');
  if (!slider) return;

  // Load current ALSA volume → convert back to slider position
  api('/audio/volume').then(d => {
    if (d && d.volume !== undefined) {
      slider.value = _alsaToSlider(d.volume);
      label.textContent = slider.value + '%';
      _updateSliderBg(slider);
    }
  });

  let _debounceTimer = null;

  slider.addEventListener('input', () => {
    const sliderVal = parseInt(slider.value, 10);
    label.textContent = sliderVal + '%';
    _updateSliderBg(slider);
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      api('/audio/volume', 'POST', { volume: _sliderToAlsa(sliderVal) }).catch(() => {});
    }, 150);
  });
}

function _updateSliderBg(slider) {
  const pct = ((slider.value - slider.min) / (slider.max - slider.min)) * 100;
  slider.style.background = `linear-gradient(to right, var(--blue) ${pct}%, var(--border) ${pct}%)`;
}

// ================================================================
// Audio helpers exposed globally
// ================================================================

async function loadAudioCategories() {
  await audioBoard.loadCategories();
}

// ================================================================
// Init
// ================================================================

// ================================================================
// App Heartbeat — alimente l'AppWatchdog côté Master
// ================================================================

function startAppHeartbeat() {
  const base = () => (typeof window.R2D2_API_BASE === 'string' && window.R2D2_API_BASE) ? window.R2D2_API_BASE : '';

  // Envoi POST /heartbeat toutes les 200ms tant que la page est active
  setInterval(() => {
    fetch(base() + '/heartbeat', { method: 'POST' }).catch(() => {});
  }, 200);

  // Stop d'urgence si l'onglet / l'app se ferme
  window.addEventListener('beforeunload', () => {
    fetch(base() + '/motion/stop', { method: 'POST', keepalive: true }).catch(() => {});
    fetch(base() + '/motion/dome/stop', { method: 'POST', keepalive: true }).catch(() => {});
  });
}

// ================================================================
// Init
// ================================================================

async function init() {
  // Init speed slider gradient
  setSpeed(60);

  // Clock
  updateClock();
  setInterval(updateClock, 1000);

  // Heartbeat applicatif vers Master (sécurité watchdog)
  startAppHeartbeat();

  // Volume slider + VESC scale slider
  initVolume();
  vescPanel.initSlider();

  // Load initial data
  await Promise.all([
    audioBoard.loadCategories(),
    scriptEngine.load(),
    poller.poll(),
    loadServoSettings(),
  ]);

  // Start polling
  poller.start(2000);

  // Refresh scripts periodically
  setInterval(() => scriptEngine.load(), 15000);
}

document.addEventListener('DOMContentLoaded', init);
