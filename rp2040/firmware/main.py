"""
R2-D2 RP2040 Firmware — MicroPython.
Waveshare RP2040-LCD-1.28 / RP2040-Touch-LCD-1.28 (GC9A01, CST816S).

Ecran de diagnostic — demarre immediatement en mode BOOT_PROGRESS (orange).
Les items se mettent a jour au fur et a mesure que le Slave Pi demarre.
Si le timeout de boot expire sans reponse, les items non repondus passent en ERREUR.

Commandes DISP: recues depuis le Slave Pi via USB serial:
  DISP:BOOT:START            → reset items + debut sequence diagnostic
  DISP:BOOT:ITEM:NOM         → item NOM en cours (CHECKING)
  DISP:BOOT:OK:NOM           → item NOM OK
  DISP:BOOT:FAIL:NOM         → item NOM FAIL
  DISP:READY:version         → tout OK → ecran vert OPERATIONNEL (3s) → PRET
  DISP:OK:version            → operationnel normal
  DISP:ERROR:CODE            → erreur avec code (MASTER_OFFLINE, VESC_TEMP_HIGH, etc.)
  DISP:TELEM:24.5V:38C       → telemetrie batterie + temperature
"""

import sys
import select
import gc9a01
import time
from machine import SPI, Pin, I2C
import display as disp

# ------------------------------------------------------------------
# Config pins
# RST_PIN : 12 = RP2040-LCD-1.28 (sans touch)
#           13 = RP2040-Touch-LCD-1.28 (avec touch)
# ------------------------------------------------------------------
RST_PIN = 12

# Timeout boot — si le Slave ne repond pas dans ce delai,
# les items non OK passent automatiquement en ERREUR (rouge)
BOOT_TIMEOUT_MS = 90_000   # 90 secondes

# ------------------------------------------------------------------
# Init display — delai obligatoire au boot (RST pas LOW avant init)
# ------------------------------------------------------------------
time.sleep_ms(500)

Pin(25, Pin.OUT).value(1)  # backlight ON
spi = SPI(1, baudrate=40_000_000, sck=Pin(10), mosi=Pin(11))
tft = gc9a01.GC9A01(
    spi, 240, 240,
    dc=Pin(8,  Pin.OUT),
    cs=Pin(9,  Pin.OUT),
    reset=Pin(RST_PIN, Pin.OUT),
    backlight=Pin(25, Pin.OUT),
)
tft.init()

# ------------------------------------------------------------------
# Touch (optionnel — ignore si board sans touch)
# ------------------------------------------------------------------
touch = None
try:
    from touch import TouchHandler
    i2c = I2C(1, sda=Pin(6), scl=Pin(7), freq=400_000)
    touch = TouchHandler(i2c)
except Exception:
    pass

# ------------------------------------------------------------------
# Etats
# ------------------------------------------------------------------
STATE_BOOT_PROGRESS = "BOOT_PROGRESS"
STATE_OPERATIONAL   = "OPERATIONAL"
STATE_OK            = "OK"
STATE_ERROR         = "ERROR"
STATE_TELEM         = "TELEM"

# Cycle de navigation par swipe (apres le boot)
SCREENS = [STATE_BOOT_PROGRESS, STATE_OK, STATE_TELEM]

# Demarre directement sur l'ecran de diagnostic
state             = STATE_BOOT_PROGRESS
version           = ""
error_code        = ""
telem_voltage     = 0.0
telem_temp        = 0.0
screen_idx        = 0
operational_since = 0   # ticks pour auto-transition OPERATIONAL → OK
boot_timed_out    = False

# Items de boot et leur statut — tous en attente au demarrage
boot_items = {
    'UART':    'pending',
    'VERSION': 'pending',
    'AUDIO':   'pending',
    'VESC_L':  'pending',
    'VESC_R':  'pending',
    'SERVOS':  'pending',
}

_needs_redraw  = True              # forcer redraw au demarrage
_boot_start_ms = time.ticks_ms()   # reference pour le timeout boot


def apply_state():
    global state, _needs_redraw
    if state == STATE_BOOT_PROGRESS:
        disp.draw_boot_progress(tft, boot_items)
    elif state == STATE_OPERATIONAL:
        disp.draw_operational(tft, version)
        # Auto-transition vers OK apres 3 secondes
        if time.ticks_diff(time.ticks_ms(), operational_since) >= 3000:
            state = STATE_OK
            _needs_redraw = True
    elif state == STATE_OK:
        disp.draw_ok(tft, version)
    elif state == STATE_ERROR:
        disp.draw_error(tft, error_code)
    elif state == STATE_TELEM:
        disp.draw_telemetry(tft, telem_voltage, telem_temp)
    _needs_redraw = False


def _check_boot_timeout():
    """Apres BOOT_TIMEOUT_MS, marque les items non OK comme ERREUR."""
    global boot_timed_out, _needs_redraw
    if boot_timed_out:
        return
    if state != STATE_BOOT_PROGRESS:
        return
    if time.ticks_diff(time.ticks_ms(), _boot_start_ms) < BOOT_TIMEOUT_MS:
        return
    # Timeout atteint — marquer tout ce qui n'est pas OK en erreur
    changed = False
    for k in boot_items:
        if boot_items[k] != 'ok':
            boot_items[k] = 'fail'
            changed = True
    boot_timed_out = True
    if changed:
        _needs_redraw = True


def parse_command(line):
    global state, version, error_code, telem_voltage, telem_temp
    global operational_since, _needs_redraw, boot_timed_out

    line = line.strip()
    if not line.startswith("DISP:"):
        return

    parts = line[5:].split(":")
    cmd = parts[0].upper()

    if cmd == "BOOT":
        if parts[1].upper() == "START" if len(parts) > 1 else False:
            # Reset tous les items + timeout repart
            for k in boot_items:
                boot_items[k] = 'pending'
            boot_timed_out = False
            state = STATE_BOOT_PROGRESS
        elif parts[1].upper() in ("ITEM", "PROGRESS") if len(parts) > 1 else False:
            if len(parts) > 2:
                key = parts[2].upper()
                if key in boot_items:
                    boot_items[key] = 'progress'
            state = STATE_BOOT_PROGRESS
        elif parts[1].upper() == "OK" if len(parts) > 1 else False:
            if len(parts) > 2:
                key = parts[2].upper()
                if key in boot_items:
                    boot_items[key] = 'ok'
            state = STATE_BOOT_PROGRESS
        elif parts[1].upper() == "FAIL" if len(parts) > 1 else False:
            if len(parts) > 2:
                key = parts[2].upper()
                if key in boot_items:
                    boot_items[key] = 'fail'
            state = STATE_BOOT_PROGRESS

    elif cmd == "READY":
        version = parts[1] if len(parts) > 1 else version
        state = STATE_OPERATIONAL
        operational_since = time.ticks_ms()

    elif cmd == "OK":
        state = STATE_OK
        version = parts[1] if len(parts) > 1 else ""

    elif cmd == "SYNCING":
        # Afficher le diagnostic pendant la synchro version
        state = STATE_BOOT_PROGRESS

    elif cmd == "ERROR":
        error_code = ":".join(parts[1:]).upper() if len(parts) > 1 else "UNKNOWN"
        state = STATE_ERROR

    elif cmd == "TELEM" and len(parts) >= 3:
        try:
            telem_voltage = float(parts[1].rstrip("Vv"))
            telem_temp    = float(parts[2].rstrip("Cc"))
        except ValueError:
            pass
        state = STATE_TELEM

    _needs_redraw = True


# ------------------------------------------------------------------
# Gestes touch
# ------------------------------------------------------------------
def on_swipe_left(x, y):
    global screen_idx, state, _needs_redraw
    screen_idx = (screen_idx + 1) % len(SCREENS)
    state = SCREENS[screen_idx]
    _needs_redraw = True

def on_swipe_right(x, y):
    global screen_idx, state, _needs_redraw
    screen_idx = (screen_idx - 1) % len(SCREENS)
    state = SCREENS[screen_idx]
    _needs_redraw = True

def on_double_tap(x, y):
    """Double tap — revenir au diagnostic de boot."""
    global state, _needs_redraw
    state = STATE_BOOT_PROGRESS
    _needs_redraw = True

def on_hold(x, y):
    sys.stdout.write("EMERGENCY:STOP\n")

if touch:
    touch.on('swipe_left',  on_swipe_left)
    touch.on('swipe_right', on_swipe_right)
    touch.on('double_tap',  on_double_tap)
    touch.on('hold',        on_hold)

# ------------------------------------------------------------------
# Stdin non-bloquant
# ------------------------------------------------------------------
_poller = select.poll()
_poller.register(sys.stdin, select.POLLIN)

# ------------------------------------------------------------------
# Boucle principale
# ------------------------------------------------------------------
apply_state()  # afficher ecran diagnostic immediatement

buf       = ""
last_draw = time.ticks_ms()
REFRESH_MS = 500  # refresh toutes les 500ms

while True:
    # Lecture commandes DISP: depuis Slave — non-bloquant
    if _poller.poll(0):
        try:
            ch = sys.stdin.read(1)
            if ch:
                buf += ch
                if '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    parse_command(line)
        except Exception:
            pass

    # Touch
    if touch:
        try:
            touch.poll()
        except Exception:
            pass

    # Verifier timeout de boot
    _check_boot_timeout()

    # Refresh — seulement si changement d'etat ou timer
    now = time.ticks_ms()
    if _needs_redraw or time.ticks_diff(now, last_draw) >= REFRESH_MS:
        apply_state()
        last_draw = now

    time.sleep_ms(20)
