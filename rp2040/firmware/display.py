"""
Display renderer — écran rond GC9A01 240x240.
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

CENTER_X = 120
CENTER_Y = 120

# Font russhughes (requis pour tft.text)
try:
    import vga1_8x16 as _font
except ImportError:
    try:
        import vga1_8x8 as _font
    except ImportError:
        _font = None

# Messages d'erreur lisibles
ERROR_MESSAGES = {
    'MASTER_OFFLINE': ('Master',    'hors ligne'),
    'VESC_TEMP_HIGH': ('VESC',      'surchauffe!'),
    'VESC_FAULT':     ('Erreur',    'VESC'),
    'BATTERY_LOW':    ('Batterie',  'faible!'),
    'UART_ERROR':     ('Erreur',    'UART'),
    'SYNC_FAILED':    ('Sync',      'echouee'),
    'WATCHDOG':       ('Watchdog',  'declenche'),
    'AUDIO_FAIL':     ('Audio',     'erreur'),
    'SERVO_FAIL':     ('Servos',    'erreur'),
    'VESC_L_FAIL':    ('VESC G',    'erreur'),
    'VESC_R_FAIL':    ('VESC D',    'erreur'),
    'I2C_ERROR':      ('I2C',       'erreur'),
}

# Labels des items de boot
BOOT_LABELS = {
    'UART':    'UART Master',
    'VERSION': 'Sync version',
    'AUDIO':   'Audio',
    'VESC_L':  'VESC Gauche',
    'VESC_R':  'VESC Droit',
    'SERVOS':  'Servos',
}


def _text(tft, txt, x, y, color):
    """Texte — requiert font module russhughes."""
    if _font is not None:
        try:
            tft.text(_font, txt, x, y, color)
        except Exception:
            pass


def _draw_ring(tft, cx, cy, r, thickness, color):
    """Anneau (bordure circulaire) via fill_rect — compatible tous drivers."""
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


# ------------------------------------------------------------------
# Écrans
# ------------------------------------------------------------------

def draw_boot(tft):
    """Splash initial — logo R2-D2 + bordure orange."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 5, ORANGE)
    # Dôme
    tft.fill_rect(CENTER_X - 55, CENTER_Y - 75, 110, 60, WHITE)
    tft.fill_rect(CENTER_X - 45, CENTER_Y - 65, 90,  45, BLACK)
    # Corps
    tft.fill_rect(CENTER_X - 35, CENTER_Y - 5,  70,  50, WHITE)
    tft.fill_rect(CENTER_X - 27, CENTER_Y + 3,  54,  34, BLACK)
    _text(tft, 'R2-D2',  CENTER_X - 28, CENTER_Y + 60, ORANGE)
    _text(tft, 'BOOT...', CENTER_X - 32, CENTER_Y + 78, GRAY)


def draw_boot_progress(tft, items):
    """
    Séquence de boot avec liste d'items et statuts.
    items = dict { 'UART': 'pending'|'progress'|'ok'|'fail', ... }
    Bordure orange — items orange en cours, vert OK, rouge FAIL, gris en attente.
    """
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 5, ORANGE)
    _text(tft, 'DEMARRAGE', CENTER_X - 40, 18, ORANGE)

    y = 52
    for key, label in BOOT_LABELS.items():
        status = items.get(key, 'pending')
        if status == 'ok':
            indicator = '+'
            color = GREEN
        elif status == 'progress':
            indicator = '>'
            color = ORANGE
        elif status == 'fail':
            indicator = '!'
            color = RED
        else:
            indicator = '-'
            color = GRAY
        _text(tft, '{} {}'.format(indicator, label), CENTER_X - 55, y, color)
        y += 22


def draw_operational(tft, version):
    """Écran 'tout OK' vert — affiché 3s puis transition automatique."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, GREEN)
    # Gros OK centré
    tft.fill_rect(CENTER_X - 40, CENTER_Y - 25, 80, 15, GREEN)  # barre haute checkmark
    tft.fill_rect(CENTER_X - 40, CENTER_Y - 10, 80, 15, GREEN)  # barre basse
    _text(tft, 'OPERATIONNEL', CENTER_X - 50, CENTER_Y + 25, GREEN)
    _text(tft, version[:10],   CENTER_X - 40, CENTER_Y + 48, GRAY)


def draw_ok(tft, version):
    """Écran opérationnel normal — bordure verte fine."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 3, GREEN)
    tft.fill_rect(CENTER_X - 45, CENTER_Y - 20, 90, 40, GREEN)
    tft.fill_rect(CENTER_X - 38, CENTER_Y - 13, 76, 26, BLACK)
    _text(tft, 'PRET',       CENTER_X - 18, CENTER_Y - 8, GREEN)
    _text(tft, version[:10], CENTER_X - 40, CENTER_Y + 28, GRAY)


def draw_error(tft, code):
    """Écran erreur — bordure rouge épaisse + description lisible."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 8, RED)
    # Point d'exclamation
    tft.fill_rect(CENTER_X - 7, CENTER_Y - 60, 14, 38, RED)
    tft.fill_rect(CENTER_X - 7, CENTER_Y - 14, 14, 14, RED)
    # Message lisible
    msg = ERROR_MESSAGES.get(code, ('Erreur', code[:10]))
    _text(tft, msg[0], CENTER_X - len(msg[0]) * 4, CENTER_Y + 20, RED)
    _text(tft, msg[1], CENTER_X - len(msg[1]) * 4, CENTER_Y + 42, WHITE)


def draw_telemetry(tft, voltage, temp):
    """Jauge batterie + température — bordure bleue."""
    tft.fill(BLACK)
    _draw_ring(tft, CENTER_X, CENTER_Y, 115, 3, BLUE)
    _text(tft, 'TELEMETRY', CENTER_X - 38, 28, BLUE)
    # Jauge batterie (20V-29.4V = 0-100%)
    v_pct = max(0.0, min(1.0, (voltage - 20.0) / 9.4))
    bar_w = int(160 * v_pct)
    tft.fill_rect(CENTER_X - 80, CENTER_Y - 32, 160, 28, GRAY)
    bar_color = GREEN if v_pct > 0.3 else (ORANGE if v_pct > 0.15 else RED)
    if bar_w > 0:
        tft.fill_rect(CENTER_X - 80, CENTER_Y - 32, bar_w, 28, bar_color)
    _text(tft, '{:.1f}V'.format(voltage), CENTER_X - 22, CENTER_Y - 58, WHITE)
    # Température
    temp_color = GREEN if temp < 60 else (ORANGE if temp < 75 else RED)
    _text(tft, 'TEMP: {:.0f}C'.format(temp), CENTER_X - 42, CENTER_Y + 10, temp_color)
