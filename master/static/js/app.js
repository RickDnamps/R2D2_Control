/**
 * R2-D2 Control Dashboard — app.js
 * Tabs + Virtual Joysticks + Settings + REST polling
 * Aucune dépendance externe.
 */

'use strict';

// ================================================================
// API Helper
// ================================================================

async function api(endpoint, method = 'GET', body = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(endpoint, opts);
    return await res.json();
  } catch (e) {
    console.error(`API ${method} ${endpoint}:`, e);
    return null;
  }
}

function el(id) { return document.getElementById(id); }

// ================================================================
// Toast notifications
// ================================================================

function toast(msg, type = 'info') {
  const t = el('toast');
  t.textContent = msg;
  t.className = `toast toast-${type} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.classList.remove('show'); }, 3000);
}

// ================================================================
// Tab navigation
// ================================================================

function switchTab(tabId) {
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector(`.tab[data-tab="${tabId}"]`).classList.add('active');
  el(`tab-${tabId}`).classList.add('active');

  if (tabId === 'settings') loadSettings();
  if (tabId === 'sequences') loadScripts();
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ================================================================
// Virtual Joystick
// ================================================================

class VirtualJoystick {
  /**
   * @param {string} ringId   - id de l'élément anneau
   * @param {string} knobId   - id du bouton central
   * @param {function} onMove - callback (x, y) normalisés [-1, 1]
   * @param {function} onStop - callback appelé au relâchement
   */
  constructor(ringId, knobId, onMove, onStop) {
    this.ring   = el(ringId);
    this.knob   = el(knobId);
    this.onMove = onMove;
    this.onStop = onStop;
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
    r.addEventListener('mousedown',   e => { this._start(e); });
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

    // Limiter au 75% du rayon pour garder le knob visible
    const maxR   = radius * 0.72;
    const dist   = Math.sqrt(dx * dx + dy * dy);
    const clamp  = Math.min(dist, maxR);
    const angle  = Math.atan2(dy, dx);
    const kx     = Math.cos(angle) * clamp;
    const ky     = Math.sin(angle) * clamp;

    // Valeurs normalisées [-1, 1]
    this.x = Math.max(-1, Math.min(1, dx / maxR));
    this.y = Math.max(-1, Math.min(1, dy / maxR));

    // Déplacer le knob visuellement
    this.knob.style.transform = `translate(calc(-50% + ${kx}px), calc(-50% + ${ky}px))`;
    this.onMove(this.x, this.y);
  }

  _release() {
    this.active = false;
    this.x = 0;
    this.y = 0;
    this.ring.classList.remove('active');
    this.knob.style.transform = 'translate(-50%, -50%)';
    this.onStop();
  }
}

// ================================================================
// Propulsion & Dôme
// ================================================================

let _speedLimit = 0.6;

function setSpeed(val) {
  _speedLimit = val / 100;
  el('speed-val').textContent = val + '%';
}

function driveStop()  { api('/motion/stop',      'POST'); }
function domeStop()   { api('/motion/dome/stop', 'POST'); }
function domeRandom(on) { api('/motion/dome/random', 'POST', { enabled: on }); }

function emergencyStop() {
  driveStop();
  domeStop();
  api('/audio/stop', 'POST');
}

// ----------------------------------------------------------------
// Joystick gauche — Propulsion (arcade drive)
// y négatif = vers le haut = avancer
// ----------------------------------------------------------------
const jsLeft = new VirtualJoystick(
  'js-left-ring', 'js-left-knob',
  (x, y) => {
    const throttle = -y * _speedLimit;          // up = forward
    const steering =  x * _speedLimit * 0.55;
    api('/motion/arcade', 'POST', { throttle, steering });
  },
  driveStop
);

// ----------------------------------------------------------------
// Joystick droit — Dôme (X) + Caméra future (Y)
// ----------------------------------------------------------------
let _domeActive = false;

const jsRight = new VirtualJoystick(
  'js-right-ring', 'js-right-knob',
  (x, y) => {
    const DEADZONE = 0.06;
    if (Math.abs(x) > DEADZONE) {
      api('/motion/dome/turn', 'POST', { speed: x * 0.85 });
      _domeActive = true;
    } else if (_domeActive) {
      domeStop();
      _domeActive = false;
    }
    // Phase 5: camera tilt with y
  },
  () => {
    domeStop();
    _domeActive = false;
  }
);

// ================================================================
// Clavier ZQSD / WASD (desktop)
// ================================================================

const _keys = {};

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (_keys[e.code]) return;
  _keys[e.code] = true;
  _handleKeys();
});

document.addEventListener('keyup', e => {
  delete _keys[e.code];
  _handleKeys();
});

function _handleKeys() {
  const fwd   = _keys['KeyW'] || _keys['ArrowUp'];
  const back  = _keys['KeyS'] || _keys['ArrowDown'];
  const left  = _keys['KeyA'] || _keys['ArrowLeft'];
  const right = _keys['KeyD'] || _keys['ArrowRight'];

  if (!fwd && !back && !left && !right) { driveStop(); return; }

  const throttle = (fwd ? 1 : (back ? -1 : 0)) * _speedLimit;
  const steering = (right ? 1 : (left ? -1 : 0)) * _speedLimit * 0.5;
  api('/motion/arcade', 'POST', { throttle, steering });
}

// ================================================================
// Teeces
// ================================================================

function teecesMode(mode) {
  api(`/teeces/${mode}`, 'POST');
  document.querySelectorAll('[id^="teeces-btn-"]').forEach(b => b.classList.remove('btn-active'));
  const btn = el(`teeces-btn-${mode}`);
  if (btn) btn.classList.add('btn-active');
}

function sendTeecesText() {
  const text = el('teeces-text').value.trim();
  if (text) api('/teeces/text', 'POST', { text });
}

// ================================================================
// Audio
// ================================================================

const AUDIO_ICONS = {
  alarm: '🚨', happy: '😄', hum: '🎵', misc: '🎲',
  proc: '⚙️', quote: '💬', razz: '🤪', sad: '😢',
  sent: '🤔', ooh: '😲', whistle: '🎶', scream: '😱',
  special: '⭐',
};

async function loadAudioCategories() {
  const data = await api('/audio/categories');
  if (!data || !data.categories) return;

  el('audio-categories').innerHTML = Object.entries(data.categories).map(([cat, count]) => `
    <button class="category-btn" onclick="api('/audio/random','POST',{category:'${cat}'})">
      ${AUDIO_ICONS[cat] || '🔊'} ${cat}
      <span class="count">${count} sons</span>
    </button>
  `).join('');
}

// ================================================================
// Servos
// ================================================================

const SERVOS = [
  'utility_arm_left', 'utility_arm_right',
  'panel_front_top',  'panel_front_bottom',
  'panel_rear_top',   'panel_rear_bottom',
  'charge_bay',
];

function loadServos() {
  el('servo-list').innerHTML = SERVOS.map(name => `
    <div class="servo-row">
      <label>${name.replace(/_/g, ' ')}</label>
      <button class="btn" onclick="api('/servo/open','POST',{name:'${name}'})">Ouvrir</button>
      <button class="btn btn-dark" onclick="api('/servo/close','POST',{name:'${name}'})">Fermer</button>
    </div>
  `).join('');
}

// ================================================================
// Scripts
// ================================================================

async function loadScripts() {
  const data = await api('/scripts/list');
  if (!data || !data.scripts) return;

  el('script-list').innerHTML = data.scripts.map(name => `
    <div class="script-item">
      <label>${name}</label>
      <button class="btn"        onclick="api('/scripts/run','POST',{name:'${name}',loop:false})">▶ Run</button>
      <button class="btn btn-active" onclick="api('/scripts/run','POST',{name:'${name}',loop:true})">↺ Loop</button>
    </div>
  `).join('');
}

// ================================================================
// Status polling
// ================================================================

async function pollStatus() {
  const data = await api('/status');
  if (!data) return;

  setPill('pill-heartbeat', data.heartbeat_ok, '● HB');
  setPill('pill-uart',      data.uart_ready,   '● UART');
  setPill('pill-teeces',    data.teeces_ready,  '● Teeces');
  setPill('pill-vesc',      data.vesc_ready,    '● VESC');

  el('uptime-label').textContent  = data.uptime  || '--';
  el('version-label').textContent = 'v' + (data.version || '?');

  // Scripts en cours dans la barre du tab séquences
  const running = data.scripts_running || [];
  el('running-scripts').textContent =
    running.length ? running.map(s => `${s.name}#${s.id}`).join(', ') : '—';

  // Version dans le panneau Système
  const sv = el('system-version');
  if (sv) sv.textContent = `Master: v${data.version || '?'}  |  Uptime: ${data.uptime || '--'}`;
}

function setPill(id, ok, label) {
  const p = el(id);
  if (!p) return;
  p.textContent = label;
  p.className   = 'status-pill ' + (ok ? 'ok' : 'error');
}

// ================================================================
// Système
// ================================================================

function confirmAction(msg, endpoint) {
  if (confirm(msg)) api(endpoint, 'POST');
}

// ================================================================
// Settings — chargement
// ================================================================

async function loadSettings() {
  const data = await api('/settings');
  if (!data) return;

  // WiFi
  el('wifi-ssid').value = data.wifi.ssid || '';
  const wifiStatus = el('wifi-status');
  if (data.wifi.connected) {
    wifiStatus.textContent = `✓ Connecté  |  SSID: ${data.wifi.connection}  |  IP: ${data.wifi.ip}`;
    wifiStatus.className = 'settings-status ok';
  } else {
    wifiStatus.textContent = 'Non connecté — wlan1 absent ou hotspot Master pas disponible';
    wifiStatus.className = 'settings-status error';
  }

  // Hotspot
  el('hotspot-ssid').value = data.hotspot.ssid || '';
  const hsStatus = el('hotspot-status');
  hsStatus.textContent = data.hotspot.active
    ? `✓ Actif  |  SSID: ${data.hotspot.ssid}  |  IP: ${data.hotspot.ip}`
    : `⚠ Hotspot inactif`;
  hsStatus.className = 'settings-status ' + (data.hotspot.active ? 'ok' : 'error');

  // GitHub / Deploy
  el('git-branch').value  = data.github.branch || 'main';
  el('slave-host').value  = data.slave.host    || 'r2-slave.local';
  el('auto-pull').checked = data.github.auto_pull_on_boot;
}

// ================================================================
// Settings — WiFi scan
// ================================================================

async function scanWifi() {
  const btn = el('btn-scan');
  btn.textContent = '⏳ Scan…';
  btn.disabled    = true;

  const data = await api('/settings/wifi/scan');

  btn.textContent = '🔍 Scan';
  btn.disabled    = false;

  const sel = el('wifi-scan-list');
  if (!data || !data.networks || data.networks.length === 0) {
    sel.innerHTML = '<option value="">Aucun réseau trouvé</option>';
    toast('Aucun réseau détecté sur wlan1', 'warn');
    return;
  }

  sel.innerHTML = '<option value="">— Sélectionner —</option>' +
    data.networks.map(n => {
      const bars = n.signal >= 75 ? '▰▰▰▰' : n.signal >= 50 ? '▰▰▰▱' : n.signal >= 25 ? '▰▰▱▱' : '▰▱▱▱';
      const sec  = n.security ? ` 🔒` : ' 🔓';
      return `<option value="${escapeHtml(n.ssid)}">${bars} ${escapeHtml(n.ssid)}${sec} (${n.signal}%)</option>`;
    }).join('');
}

function onScanSelect(ssid) {
  if (ssid) el('wifi-ssid').value = ssid;
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ================================================================
// Settings — Apply WiFi
// ================================================================

async function applyWifi() {
  const ssid     = el('wifi-ssid').value.trim();
  const password = el('wifi-password').value;

  if (!ssid) { toast('SSID requis', 'error'); return; }

  toast('Connexion en cours…');
  const data = await api('/settings/wifi', 'POST', { ssid, password });

  if (!data) { toast('Erreur réseau', 'error'); return; }
  if (data.error) { toast(data.error, 'error'); return; }

  toast(data.message || (data.connected ? 'wlan1 connecté ✓' : 'Config sauvegardée'), data.connected ? 'ok' : 'warn');
  await loadSettings();
}

// ================================================================
// Settings — Apply Hotspot
// ================================================================

async function applyHotspot() {
  const ssid     = el('hotspot-ssid').value.trim();
  const password = el('hotspot-password').value;

  if (!ssid) { toast('SSID requis', 'error'); return; }
  if (password && password.length < 8) {
    toast('Mot de passe : minimum 8 caractères', 'error');
    return;
  }
  if (!confirm(`Appliquer le hotspot SSID "${ssid}" ? Les clients seront déconnectés.`)) return;

  toast('Application du hotspot…');
  const data = await api('/settings/hotspot', 'POST', { ssid, password });

  if (!data) { toast('Erreur réseau', 'error'); return; }
  if (data.error) { toast(data.error, 'error'); return; }

  toast('Hotspot mis à jour ✓', 'ok');
  el('hotspot-password').value = '';
  await loadSettings();
}

// ================================================================
// Settings — Save config
// ================================================================

async function saveConfig() {
  const payload = {
    'github.branch':            el('git-branch').value.trim(),
    'github.auto_pull_on_boot': el('auto-pull').checked ? 'true' : 'false',
    'slave.host':               el('slave-host').value.trim(),
  };

  const data = await api('/settings/config', 'POST', payload);
  if (data && data.status === 'ok') {
    toast('Configuration sauvegardée ✓', 'ok');
  } else {
    toast('Erreur lors de la sauvegarde', 'error');
  }
}

// ================================================================
// Init
// ================================================================

async function init() {
  loadServos();
  await Promise.all([
    loadAudioCategories(),
    loadScripts(),
    pollStatus(),
  ]);

  setInterval(pollStatus, 2000);
  setInterval(loadScripts, 15000);
}

document.addEventListener('DOMContentLoaded', init);
