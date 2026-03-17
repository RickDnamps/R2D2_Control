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
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(endpoint, opts);
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

  if (tabId === 'config') loadSettings();
  if (tabId === 'sequences') loadScripts();
  if (tabId === 'audio') loadAudioCategories();
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
  constructor() {
    this._servos = [
      'utility_arm_left', 'utility_arm_right',
      'panel_front_top',  'panel_front_bottom',
      'panel_rear_top',   'panel_rear_bottom',
      'charge_bay',
    ];
    this._state = {}; // name → 'open'|'close'
    this._servos.forEach(n => this._state[n] = 'close');
    this.render();
  }

  render() {
    const grid = el('servo-list');
    if (!grid) return;
    grid.innerHTML = this._servos.map(name => {
      const label = name.replace(/_/g, ' ').toUpperCase();
      return `
        <div class="servo-row" id="servo-row-${name}">
          <span class="servo-name">${label}</span>
          <div class="servo-pos-bar">
            <div class="servo-pos-fill" id="servo-fill-${name}" style="width:0%"></div>
          </div>
          <button class="btn btn-sm" onclick="servoPanel.open('${name}')">OPEN</button>
          <button class="btn btn-sm btn-dark" onclick="servoPanel.close('${name}')">CLOSE</button>
        </div>
      `;
    }).join('');
  }

  open(name) {
    api('/servo/open', 'POST', { name }).then(d => {
      if (d) { toast(`${name}: OPEN`, 'ok'); this._setFill(name, 100); }
    });
    this._state[name] = 'open';
  }

  close(name) {
    api('/servo/close', 'POST', { name }).then(d => {
      if (d) { toast(`${name}: CLOSE`, 'ok'); this._setFill(name, 0); }
    });
    this._state[name] = 'close';
  }

  _setFill(name, pct) {
    const f = el(`servo-fill-${name}`);
    if (f) f.style.width = pct + '%';
  }
}

const servoPanel = new ServoPanel();

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
      this._setPill('pill-heartbeat', false, 'HB');
      return;
    }

    this._setPill('pill-heartbeat', data.heartbeat_ok, 'HB');
    this._setPill('pill-uart',      data.uart_ready,   'UART');

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
        status.textContent = `Connected | SSID: ${data.wifi.connection} | IP: ${data.wifi.ip}`;
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

// ================================================================
// Audio helpers exposed globally
// ================================================================

async function loadAudioCategories() {
  await audioBoard.loadCategories();
}

// ================================================================
// Init
// ================================================================

async function init() {
  // Render static UI components
  servoPanel.render();

  // Init speed slider gradient
  setSpeed(60);

  // Clock
  updateClock();
  setInterval(updateClock, 1000);

  // Load initial data
  await Promise.all([
    audioBoard.loadCategories(),
    scriptEngine.load(),
    poller.poll(),
  ]);

  // Start polling
  poller.start(2000);

  // Refresh scripts periodically
  setInterval(() => scriptEngine.load(), 15000);
}

document.addEventListener('DOMContentLoaded', init);
