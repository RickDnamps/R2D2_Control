"""
Display renderer — ecran rond GC9A01 240x240.
"""

import gc9a01
import math

# Couleurs RGB565
BLACK   = gc9a01.color565(0,   0,   0)
WHITE   = gc9a01.color565(255, 255, 255)
RED     = gc9a01.color565(220, 50,  50)
GREEN   = gc9a01.color565(50,  200, 80)
ORANGE  = gc9a01.color565(255, 150, 0)
BLUE    = gc9a01.color565(0,   120, 220)
GRAY    = gc9a01.color565(80,  80,  80)
DK_GRAY = gc9a01.color565(40,  40,  40)
CYAN    = gc9a01.color565(0,   200, 200)

CENTER_X = 120
CENTER_Y = 120

_spin_frame = 0   # animation frame counter

# Fontes russhughes
try:
    import vga1_8x16 as _font16
except ImportError:
    _font16 = None

try:
    import vga1_8x8 as _font8
except ImportError:
    _font8 = None

_font = _font8 if _font8 is not None else _font16

ERROR_MESSAGES = {
    'MASTER_OFFLINE': ('Master',   'offline'),
    'VESC_TEMP_HIGH': ('VESC',     'overheat!'),
    'VESC_FAULT':     ('VESC',     'fault'),
    'BATTERY_LOW':    ('Battery',  'low!'),
    'UART_ERROR':     ('UART',     'error'),
    'SYNC_FAILED':    ('Sync',     'failed'),
    'WATCHDOG':       ('Watchdog', 'triggered'),
    'AUDIO_FAIL':     ('Audio',    'error'),
    'SERVO_FAIL':     ('Servos',   'error'),
    'VESC_L_FAIL':    ('VESC L',   'error'),
    'VESC_R_FAIL':    ('VESC R',   'error'),
    'I2C_ERROR':      ('I2C',      'error'),
}

BOOT_LABELS = {
    'UART':    'Pi4B MASTER',
    'VESC_G':  'VESC LEFT',
    'VESC_D':  'VESC RIGHT',
    'DOME':    'DOME MOTOR',
    'SERVOS':  'SERVOS BODY',
    'AUDIO':   'AUDIO',
    'BT_CTRL': 'BT CONTROL',
}

STATUS_TEXT = {
    'pending':  'STANDBY',
    'progress': 'CHECKING',
    'ok':       'OK',
    'fail':     'ERROR',
    'none':     'NO CTRL',
}

STATUS_COLOR = {
    'pending':  GRAY,
    'progress': ORANGE,
    'ok':       GREEN,
    'fail':     RED,
    'none':     BLUE,
}

# ------------------------------------------------------------------
# Pre-calcul des positions du spinner (evite math.cos/sin en boucle)
# ------------------------------------------------------------------
_SR      = 28
_SEG_LEN = 12
_SPIN_SEGS = []
for _i in range(8):
    _rad = _i * math.pi / 4.0
    _x1  = int(CENTER_X + math.cos(_rad) * _SR)
    _y1  = int(CENTER_Y + math.sin(_rad) * _SR)
    _x2  = int(CENTER_X + math.cos(_rad) * (_SR + _SEG_LEN))
    _y2  = int(CENTER_Y + math.sin(_rad) * (_SR + _SEG_LEN))
    _SPIN_SEGS.append((
        min(_x1, _x2), min(_y1, _y2),
        max(2, abs(_x2 - _x1)), max(2, abs(_y2 - _y1))
    ))

# Flags pour eviter le full-redraw a chaque frame d'animation
_booting_bg_drawn  = False
_locked_bg_drawn   = False
_ok_prev_bus_color = None   # suivi couleur pour draw_ok() incremental


def reset_animations():
    """Appeler quand on quitte un etat anime pour forcer un full redraw au retour."""
    global _booting_bg_drawn, _locked_bg_drawn
    _booting_bg_drawn = False
    _locked_bg_drawn  = False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _text(tft, txt, x, y, color, font=None):
    f = font if font is not None else _font
    if f is not None:
        try:
            tft.text(f, txt, x, y, color)
        except Exception:
            pass


def _text_center(tft, txt, y, color, font=None):
    f = font if font is not None else _font
    if f is None:
        return
    x = CENTER_X - (len(txt) * 8) // 2
    _text(tft, txt, x, y, color, f)


def _draw_ring(tft, cx, cy, r, thickness, color):
    """Anneau via fill_rect — utilise isqrt pour eviter math.sqrt."""
    r_inner = r - thickness
    r2_outer = r * r
    r2_inner = r_inner * r_inner
    for dy in range(-r, r + 1):
        d2 = dy * dy
        ro2 = r2_outer - d2
        if ro2 < 0:
            continue
        dx_outer = int(math.sqrt(ro2))
        ri2 = r2_inner - d2
        dx_inner = int(math.sqrt(ri2)) if ri2 >= 0 else 0
        w = dx_outer - dx_inner
        if w > 0:
            tft.fill_rect(cx - dx_outer, cy + dy, w, 1, color)
            tft.fill_rect(cx + dx_inner, cy + dy, w, 1, color)


def _progress_bar(tft, x, y, w, h, pct, color):
    tft.fill_rect(x, y, w, h, DK_GRAY)
    filled = int(w * max(0.0, min(1.0, pct)))
    if filled > 0:
        tft.fill_rect(x, y, filled, h, color)
    tft.fill_rect(x,         y,         w, 1, GRAY)
    tft.fill_rect(x,         y + h - 1, w, 1, GRAY)
    tft.fill_rect(x,         y,         1, h, GRAY)
    tft.fill_rect(x + w - 1, y,         1, h, GRAY)


# ------------------------------------------------------------------
# Ecrans
# ------------------------------------------------------------------

def draw_booting(tft, full=False):
    """Spinner orange — full=True force un redraw complet (changement d'etat)."""
    global _spin_frame, _booting_bg_drawn
    prev_frame  = _spin_frame
    _spin_frame = (_spin_frame + 1) % 8

    if full or not _booting_bg_drawn:
        tft.fill(BLACK)
        _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, ORANGE)
        _text_center(tft, 'SYSTEM STATUS:', CENTER_Y - 66, ORANGE)
        _text_center(tft, 'STARTING UP',   CENTER_Y - 52, ORANGE)
        _text_center(tft, 'BOOT...',        CENTER_Y + 48, GRAY)
        for sx, sy, sw, sh in _SPIN_SEGS:
            tft.fill_rect(sx, sy, sw, sh, DK_GRAY)
        _booting_bg_drawn = True
        sx, sy, sw, sh = _SPIN_SEGS[_spin_frame]
        tft.fill_rect(sx, sy, sw, sh, ORANGE)
    else:
        px, py, pw, ph = _SPIN_SEGS[prev_frame]
        tft.fill_rect(px, py, pw, ph, DK_GRAY)
        sx, sy, sw, sh = _SPIN_SEGS[_spin_frame]
        tft.fill_rect(sx, sy, sw, sh, ORANGE)


def draw_locked(tft, full=False):
    """Cadenas rouge clignotant — full=True force redraw complet."""
    global _spin_frame, _locked_bg_drawn
    _spin_frame = (_spin_frame + 1) % 4
    visible     = _spin_frame < 2
    ring_color  = RED if visible else DK_GRAY

    if full or not _locked_bg_drawn:
        tft.fill(BLACK)
        _text_center(tft, 'SYSTEM STATUS:', 36, RED)
        # Corps cadenas
        tft.fill_rect(CENTER_X - 20, CENTER_Y - 8, 40, 30, RED)
        tft.fill_rect(CENTER_X - 13, CENTER_Y - 2, 26, 18, BLACK)
        # Trou de serrure
        tft.fill_rect(CENTER_X - 3, CENTER_Y + 2, 7, 10, RED)
        # Anse
        arc_r = 16
        for dy in range(-arc_r, 0):
            r2 = arc_r * arc_r - dy * dy
            if r2 >= 0:
                tft.fill_rect(CENTER_X - 22, CENTER_Y - 8 + dy, 5, 1, RED)
                tft.fill_rect(CENTER_X + 17, CENTER_Y - 8 + dy, 5, 1, RED)
        _text_center(tft, 'SYSTEM',             CENTER_Y + 28, RED)
        _text_center(tft, 'LOCKED',             CENTER_Y + 40, RED)
        tft.fill_rect(CENTER_X - 50, CENTER_Y + 54, 100, 1, DK_GRAY)
        _text_center(tft, 'WATCHDOG TRIGGERED', CENTER_Y + 60, GRAY)
        _text_center(tft, 'MOTORS STOPPED',     CENTER_Y + 72, GRAY)
        _locked_bg_drawn = True

    # Seul l'anneau clignote — mise a jour incrementale
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, ring_color)


def draw_ok(tft, version, bus_pct=100.0, full=False):
    """Redraw complet si full=True (changement d'etat), sinon incremental (bus update)."""
    global _ok_prev_bus_color
    bus_color     = GREEN if bus_pct >= 80.0 else ORANGE
    color_changed = (bus_color != _ok_prev_bus_color)
    _ok_prev_bus_color = bus_color

    if full:
        # Redraw complet — changement d'etat (pas de flicker, appel rare)
        tft.fill(BLACK)
        _draw_ring(tft, CENTER_X, CENTER_Y, 115, 4, bus_color)
        _text_center(tft, 'SYSTEM STATUS:', 50, GREEN)
        _text_center(tft, 'OPERATIONAL',   64, GREEN)
        tft.fill_rect(CENTER_X - 50, 78, 100, 1, DK_GRAY)
        if version:
            _text_center(tft, 'v' + version[:11], 88, GREEN)
        _text_center(tft, 'UART BUS HEALTH', 106, bus_color)
        tft.fill_rect(CENTER_X - 50, 156, 100, 1, DK_GRAY)
        _text_center(tft, '< swipe >  TELEM', 164, GRAY)
    elif color_changed:
        # Couleur franchit le seuil 80% : redessiner anneau + label uniquement
        _draw_ring(tft, CENTER_X, CENTER_Y, 115, 4, bus_color)
        tft.fill_rect(0, 106, 240, 9, BLACK)
        _text_center(tft, 'UART BUS HEALTH', 106, bus_color)

    # Parties dynamiques : toujours mises a jour sans effacer tout l'ecran
    _progress_bar(tft, 34, 118, 172, 10, bus_pct / 100.0, bus_color)
    tft.fill_rect(CENTER_X - 24, 133, 48, 9, BLACK)
    _text_center(tft, '{:.0f}%'.format(bus_pct), 133, bus_color)
    if bus_pct < 80.0:
        _text_center(tft, 'PARASITES DETECTES', 147, ORANGE)
    elif not full:
        tft.fill_rect(0, 147, 240, 9, BLACK)   # efface avertissement si recupere

    reset_animations()


def _draw_antenna(tft, cx, cy, color):
    """Antenne avec 3 ondes — dessin en primitives."""
    # Mat vertical
    tft.fill_rect(cx - 1, cy - 28, 3, 28, color)
    # 3 arcs d'onde (approximes par des arcs de cercle horizontaux)
    for r, dy_offset in [(10, -28), (17, -32), (24, -36)]:
        for dy in range(-r // 3, r // 3 + 1):
            dx = int((r * r - dy * dy * 9) ** 0.5) if r * r >= dy * dy * 9 else 0
            if dx > 0:
                tft.fill_rect(cx - dx, cy + dy_offset + r // 3 + dy, dx * 2, 1, color)
                break
        # Approche plus simple : juste des barres horizontales etagees
    tft.fill_rect(cx -  8, cy - 22, 16, 2, color)
    tft.fill_rect(cx - 14, cy - 28, 28, 2, color)
    tft.fill_rect(cx - 20, cy - 34, 40, 2, color)
    # Point base
    tft.fill_rect(cx - 3, cy, 7, 3, color)


def draw_net(tft, sub_state):
    tft.fill(BLACK)
    parts = sub_state.split(':') if sub_state else []
    cmd   = parts[0].upper() if parts else ''
    # Couleur selon etat
    if cmd == 'HOME':
        net_color = BLUE
        ring_w    = 5
    elif cmd in ('SCANNING', 'AP'):
        net_color = BLUE
        ring_w    = 6
    else:
        net_color = BLUE
        ring_w    = 5
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, ring_w, net_color)
    _text_center(tft, 'NETWORK', 36, net_color)
    _draw_antenna(tft, CENTER_X, CENTER_Y + 10, net_color)
    if cmd == 'SCANNING':
        n = parts[1] if len(parts) > 1 else '?'
        _text_center(tft, 'SCANNING...',              CENTER_Y + 46, net_color)
        _text_center(tft, 'MASTER AP NOT FOUND',      CENTER_Y + 58, GRAY)
        _text_center(tft, 'ATTEMPT {}/5'.format(n),   CENTER_Y + 70, GRAY)
    elif cmd == 'AP':
        n = parts[1] if len(parts) > 1 else '?'
        _text_center(tft, 'CONNECTING',               CENTER_Y + 46, net_color)
        _text_center(tft, 'R2D2_Control',             CENTER_Y + 58, net_color)
        _text_center(tft, 'ATTEMPT {}/5'.format(n),   CENTER_Y + 70, GRAY)
    elif cmd == 'HOME_TRY':
        _text_center(tft, 'HOME WIFI',                CENTER_Y + 46, ORANGE)
        _text_center(tft, 'CONNECTING...',            CENTER_Y + 58, GRAY)
    elif cmd == 'HOME':
        ip = ':'.join(parts[1:]) if len(parts) > 1 else '?'
        _text_center(tft, 'HOME WIFI ACTIVE',         CENTER_Y + 46, ORANGE)
        _text_center(tft, ip[:16],                    CENTER_Y + 58, GRAY)
        _text_center(tft, 'SSH DEBUG OK',             CENTER_Y + 70, GRAY)
    elif cmd == 'OK':
        _text_center(tft, 'RECONNECTED',              CENTER_Y + 46, GREEN)
    else:
        _text_center(tft, sub_state[:16] if sub_state else 'NET EVENT', CENTER_Y + 46, net_color)
    reset_animations()


def draw_error(tft, code):
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, RED)
    _text_center(tft, 'SYSTEM STATUS:', 40, RED)
    _text_center(tft, 'CRITICAL ERROR', 52, RED)
    tft.fill_rect(CENTER_X - 6, CENTER_Y - 50, 12, 30, RED)
    tft.fill_rect(CENTER_X - 6, CENTER_Y - 12, 12, 12, RED)
    msg = ERROR_MESSAGES.get(code, ('Error', code[:10]))
    _text_center(tft, msg[0], CENTER_Y + 20, RED)
    _text_center(tft, msg[1], CENTER_Y + 32, WHITE)
    _text_center(tft, 'GLOBAL STATUS:', CENTER_Y + 50, GRAY)
    _text_center(tft, 'BOOT FAILED',   CENTER_Y + 62, RED)
    reset_animations()


def draw_telemetry(tft, voltage, temp):
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 4, BLUE)
    _text_center(tft, 'TELEMETRY', 34, BLUE)
    # Tension
    v_str     = '{:.1f}V'.format(voltage)
    _text_center(tft, v_str, 52, WHITE)
    v_pct     = max(0.0, min(1.0, (voltage - 20.0) / 9.4))
    bar_color = GREEN if v_pct > 0.3 else (ORANGE if v_pct > 0.15 else RED)
    _progress_bar(tft, 34, 66, 172, 14, v_pct, bar_color)
    lipo_pct  = '{:.0f}%'.format(v_pct * 100)
    _text_center(tft, '6S LiPo  ' + lipo_pct, 85, bar_color)
    tft.fill_rect(CENTER_X - 50, 98, 100, 1, DK_GRAY)
    # Temperature
    temp_color = GREEN if temp < 60 else (ORANGE if temp < 75 else RED)
    t_str      = 'TEMP: {:.0f}C'.format(temp)
    _text_center(tft, t_str, 108, temp_color)
    _progress_bar(tft, 34, 122, 172, 10, temp / 100.0, temp_color)
    tft.fill_rect(CENTER_X - 50, 142, 100, 1, DK_GRAY)
    _text_center(tft, '< swipe  BACK TO OK', 150, GRAY)
    reset_animations()


def draw_boot(tft):
    """Splash initial legacy."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 6, ORANGE)
    tft.fill_rect(CENTER_X - 55, CENTER_Y - 75, 110, 60, WHITE)
    tft.fill_rect(CENTER_X - 45, CENTER_Y - 65, 90,  45, BLACK)
    tft.fill_rect(CENTER_X - 35, CENTER_Y - 5,  70,  50, WHITE)
    tft.fill_rect(CENTER_X - 27, CENTER_Y + 3,  54,  34, BLACK)
    _text_center(tft, 'R2-D2',   CENTER_Y + 60, ORANGE)
    _text_center(tft, 'BOOT...', CENTER_Y + 72, GRAY)
    reset_animations()
