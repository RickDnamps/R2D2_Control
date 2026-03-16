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

CENTER_X = 120
CENTER_Y = 120

# Fontes russhughes — 8x8 pour diagnostic (plus de lignes), 8x16 pour grands titres
try:
    import vga1_8x16 as _font16
except ImportError:
    _font16 = None

try:
    import vga1_8x8 as _font8
except ImportError:
    _font8 = None

# Police par defaut pour les petits textes
_font = _font8 if _font8 is not None else _font16

# Messages d'erreur lisibles
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

# Labels courts des items de boot (max ~11 chars pour tenir sur 1 ligne)
# Ordre = ordre d'affichage sur l'ecran
BOOT_LABELS = {
    'UART':   'UART MASTER',   # UART /dev/ttyAMA0 slipring → Master
    'VESC_G': 'VESC LEFT',     # FSESC /dev/ttyACM0 — left drive
    'VESC_D': 'VESC RIGHT',    # FSESC /dev/ttyACM1 — right drive
    'DOME':   'DOME MOTOR',    # Motor Driver HAT I2C 0x40 — dome rotation
    'SERVOS': 'SERVOS BODY',   # PCA9685 I2C 0x41 — panels + arms
    'AUDIO':  'AUDIO',         # 3.5mm jack — MP3 sounds
}

# Textes de statut par etat
STATUS_TEXT = {
    'pending':  'STANDBY',
    'progress': 'CHECKING',
    'ok':       'OK',
    'fail':     'ERROR',
}

STATUS_COLOR = {
    'pending':  GRAY,
    'progress': ORANGE,
    'ok':       GREEN,
    'fail':     RED,
}


def _text(tft, txt, x, y, color, font=None):
    """Texte — requiert font module russhughes."""
    f = font if font is not None else _font
    if f is not None:
        try:
            tft.text(f, txt, x, y, color)
        except Exception:
            pass


def _text_center(tft, txt, y, color, font=None):
    """Texte centre horizontalement."""
    f = font if font is not None else _font
    if f is None:
        return
    # vga1_8x8 → 8px par char, vga1_8x16 → 8px par char aussi
    char_w = 8
    x = CENTER_X - (len(txt) * char_w) // 2
    _text(tft, txt, x, y, color, f)


def _draw_ring(tft, cx, cy, r, thickness, color):
    """Anneau (bordure circulaire) via fill_rect."""
    r_inner = r - thickness
    for dy in range(-r, r + 1):
        r2 = r * r - dy * dy
        if r2 < 0:
            continue
        dx_outer = int(math.sqrt(r2))
        r2i = r_inner * r_inner - dy * dy
        dx_inner = int(math.sqrt(r2i)) if r2i >= 0 else 0
        if dx_outer > dx_inner:
            tft.fill_rect(cx - dx_outer, cy + dy, dx_outer - dx_inner, 1, color)
            tft.fill_rect(cx + dx_inner, cy + dy, dx_outer - dx_inner, 1, color)


def _progress_bar(tft, x, y, w, h, pct, color):
    """Barre de progression avec fond gris."""
    tft.fill_rect(x, y, w, h, DK_GRAY)
    filled = int(w * max(0.0, min(1.0, pct)))
    if filled > 0:
        tft.fill_rect(x, y, filled, h, color)
    # Contour
    tft.fill_rect(x,         y,         w, 1, GRAY)
    tft.fill_rect(x,         y + h - 1, w, 1, GRAY)
    tft.fill_rect(x,         y,         1, h, GRAY)
    tft.fill_rect(x + w - 1, y,         1, h, GRAY)


# ------------------------------------------------------------------
# Ecrans
# ------------------------------------------------------------------

def draw_boot(tft):
    """Splash initial — logo R2-D2 + bordure orange."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 6, ORANGE)
    # Dome
    tft.fill_rect(CENTER_X - 55, CENTER_Y - 75, 110, 60, WHITE)
    tft.fill_rect(CENTER_X - 45, CENTER_Y - 65, 90,  45, BLACK)
    # Corps
    tft.fill_rect(CENTER_X - 35, CENTER_Y - 5,  70,  50, WHITE)
    tft.fill_rect(CENTER_X - 27, CENTER_Y + 3,  54,  34, BLACK)
    _text_center(tft, 'R2-D2',   CENTER_Y + 60, ORANGE)
    _text_center(tft, 'BOOT...', CENTER_Y + 72, GRAY)


def draw_boot_progress(tft, items):
    """
    Ecran de diagnostic boot — style reference image.
    Affiche: titre SYSTEM STATUS + etat, liste numerotee des items,
    barre de progression, pied GLOBAL STATUS.
    """
    # Determiner l'etat global
    statuses = list(items.values())
    has_fail     = any(s == 'fail'     for s in statuses)
    has_progress = any(s == 'progress' for s in statuses)
    all_ok       = all(s == 'ok'       for s in statuses)

    if has_fail:
        ring_color  = RED
        state_line  = 'BOOT ERROR'
        global_text = 'BOOT FAILED'
    elif all_ok:
        ring_color  = GREEN
        state_line  = 'OK'
        global_text = 'BOOT COMPLETE'
    else:
        ring_color  = ORANGE
        state_line  = 'IN PROGRESS'
        global_text = 'BOOTING...'

    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, ring_color)

    # --- Titre ---
    _text_center(tft, 'SYSTEM STATUS:', 20, ring_color)
    _text_center(tft, state_line,       30, ring_color)

    # --- Liste des items (vga1_8x8 → 8px/char × 8px tall) ---
    # Largeur utile ~170px centree (x=35..205), 8px/char → 21 chars max
    # Format: "N.LABEL.......STATUS" = ~21 chars
    ok_count = 0
    y = 46
    for i, (key, label) in enumerate(BOOT_LABELS.items()):
        status = items.get(key, 'pending')
        if status == 'ok':
            ok_count += 1
        color      = STATUS_COLOR[status]
        status_str = STATUS_TEXT[status]

        # Construire la ligne avec dots
        num_str = '{}.'.format(i + 1)          # "1."
        # Tronquer label a 11 chars
        short = label[:11].upper()
        left  = '{}{}'.format(num_str, short)   # "1.UART MASTER"
        # Total cible = 21 chars
        dot_count = max(1, 21 - len(left) - len(status_str))
        line = '{}{}{}'.format(left, '.' * dot_count, status_str)

        _text(tft, line, 34, y, color)
        y += 11  # 8px font + 3px espace

    # --- Barre de progression ---
    pct = ok_count / max(1, len(items))
    bar_y = y + 5
    _progress_bar(tft, 34, bar_y, 172, 10, pct, ring_color)

    # --- Pied de page ---
    _text_center(tft, 'GLOBAL STATUS:',  bar_y + 14, GRAY)
    _text_center(tft, global_text,       bar_y + 24, ring_color)


def draw_operational(tft, version):
    """Ecran 'tout OK' vert — affiche 3s puis transition automatique vers draw_ok."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, GREEN)
    _text_center(tft, 'SYSTEM STATUS:', 50, GREEN)
    _text_center(tft, 'OK',            62, GREEN)
    # Gros checkmark simple
    tft.fill_rect(CENTER_X - 38, CENTER_Y - 10, 76, 12, GREEN)
    tft.fill_rect(CENTER_X - 38, CENTER_Y + 2,  76, 12, GREEN)
    _text_center(tft, 'OPERATIONAL', CENTER_Y + 28, GREEN)
    if version:
        _text_center(tft, version[:14], CENTER_Y + 42, GRAY)


def draw_ok(tft, version):
    """Ecran operationnel normal — bordure verte fine."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 4, GREEN)
    _text_center(tft, 'SYSTEM STATUS:', 46, GREEN)
    _text_center(tft, 'OK',            58, GREEN)
    tft.fill_rect(CENTER_X - 40, CENTER_Y - 14, 80, 12, GREEN)
    tft.fill_rect(CENTER_X - 40, CENTER_Y +  2, 80, 12, GREEN)
    _text_center(tft, 'READY', CENTER_Y + 24, GREEN)
    if version:
        _text_center(tft, version[:14], CENTER_Y + 38, GRAY)


def draw_error(tft, code):
    """Ecran erreur — bordure rouge epaisse + description lisible."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, RED)
    _text_center(tft, 'SYSTEM STATUS:', 40, RED)
    _text_center(tft, 'CRITICAL ERROR', 52, RED)
    # Exclamation mark
    tft.fill_rect(CENTER_X - 6, CENTER_Y - 50, 12, 30, RED)
    tft.fill_rect(CENTER_X - 6, CENTER_Y - 12, 12, 12, RED)
    # Human-readable message
    msg = ERROR_MESSAGES.get(code, ('Error', code[:10]))
    _text_center(tft, msg[0], CENTER_Y + 20, RED)
    _text_center(tft, msg[1], CENTER_Y + 32, WHITE)
    _text_center(tft, 'GLOBAL STATUS:', CENTER_Y + 50, GRAY)
    _text_center(tft, 'BOOT FAILED',   CENTER_Y + 62, RED)


def draw_telemetry(tft, voltage, temp):
    """Jauge batterie + temperature — bordure bleue."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 4, BLUE)
    _text_center(tft, 'TELEMETRY', 28, BLUE)
    # Tension
    v_str = '{:.1f}V'.format(voltage)
    _text_center(tft, v_str, 48, WHITE)
    # Jauge batterie (20V-29.4V = 0-100%)
    v_pct = max(0.0, min(1.0, (voltage - 20.0) / 9.4))
    bar_color = GREEN if v_pct > 0.3 else (ORANGE if v_pct > 0.15 else RED)
    _progress_bar(tft, 34, 70, 172, 16, v_pct, bar_color)
    # Temperature
    temp_color = GREEN if temp < 60 else (ORANGE if temp < 75 else RED)
    t_str = 'TEMP: {:.0f}C'.format(temp)
    _text_center(tft, t_str, 100, temp_color)
    # Temp bar (0-100C)
    _progress_bar(tft, 34, 116, 172, 10, temp / 100.0, temp_color)
