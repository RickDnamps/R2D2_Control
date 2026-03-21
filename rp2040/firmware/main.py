"""
R2-D2 RP2040 Firmware — MicroPython.
Waveshare RP2040-LCD-1.28 / RP2040-Touch-LCD-1.28 (GC9A01, CST816S).

Ecran de diagnostic — "render what you're told".
L'etat est pilote entierement par les commandes DISP: recues du Slave Pi.

Commandes DISP: recues depuis le Slave Pi via USB serial:
  DISP:BOOT:START            -> spinner orange (BOOTING)
  DISP:READY:version         -> ecran vert OK
  DISP:OK:version            -> ecran vert OK
  DISP:NET:sub_state         -> ecran reseau
  DISP:LOCKED                -> ecran verrouille (animation)
  DISP:ERROR:CODE            -> erreur avec code
  DISP:TELEM:24.5V:38C      -> telemetrie batterie + temperature
  DISP:BUS:pct               -> sante bus UART (0-100)
  DISP:SYNCING               -> reste sur spinner BOOTING
"""

import sys
import select
import gc9a01
import time
from machine import SPI, Pin, I2C
import display as disp

# ------------------------------------------------------------------
# Init display
# ------------------------------------------------------------------
time.sleep_ms(500)

Pin(25, Pin.OUT).value(1)  # backlight ON
spi = SPI(1, baudrate=40_000_000, sck=Pin(10), mosi=Pin(11))
tft = gc9a01.GC9A01(
    spi, 240, 240,
    dc=Pin(8,  Pin.OUT),
    cs=Pin(9,  Pin.OUT),
    reset=Pin(12, Pin.OUT),
    backlight=Pin(25, Pin.OUT),
)
tft.init()

# ------------------------------------------------------------------
# Touch (optionnel)
# ------------------------------------------------------------------
touch = None
try:
    from touch import TouchHandler
    i2c   = I2C(1, sda=Pin(6), scl=Pin(7), freq=400_000)
    touch = TouchHandler(i2c)
except Exception:
    pass

# ------------------------------------------------------------------
# Etats
# ------------------------------------------------------------------
STATE_BOOTING = "BOOTING"
STATE_OK      = "OK"
STATE_NET     = "NET"
STATE_LOCKED  = "LOCKED"
STATE_ERROR   = "ERROR"
STATE_TELEM   = "TELEM"

SCREENS   = [STATE_OK, STATE_TELEM]
NAVIGABLE = {STATE_OK, STATE_TELEM}

state          = STATE_BOOTING
version        = ""
error_code     = ""
telem_voltage  = 0.0
telem_temp     = 0.0
net_sub_state  = ""
bus_health_pct = 100.0
screen_idx     = 0

_needs_redraw = True
_last_anim_ms = 0
_prev_state   = None   # detecte les changements d'etat pour forcer full-redraw


def apply_state():
    global _needs_redraw, _prev_state
    full = (state != _prev_state)   # True = changement d'etat = redraw complet
    _prev_state = state

    if state == STATE_BOOTING:
        disp.draw_booting(tft, full=full)
    elif state == STATE_OK:
        disp.draw_ok(tft, version, bus_health_pct)
    elif state == STATE_NET:
        disp.draw_net(tft, net_sub_state)
    elif state == STATE_LOCKED:
        disp.draw_locked(tft, full=full)
    elif state == STATE_ERROR:
        disp.draw_error(tft, error_code)
    elif state == STATE_TELEM:
        disp.draw_telemetry(tft, telem_voltage, telem_temp)

    _needs_redraw = False


def parse_command(line):
    global state, version, error_code, telem_voltage, telem_temp
    global net_sub_state, bus_health_pct, _needs_redraw

    line = line.strip()
    if not line.startswith("DISP:"):
        return

    parts = line[5:].split(":")
    cmd   = parts[0].upper()

    if cmd == "BOOT":
        sub = parts[1].upper() if len(parts) > 1 else ""
        if sub == "START":
            state = STATE_BOOTING

    elif cmd in ("READY", "OK"):
        version = parts[1] if len(parts) > 1 else ""
        state   = STATE_OK

    elif cmd == "SYNCING":
        state = STATE_BOOTING

    elif cmd == "BUS":
        if len(parts) > 1:
            try:
                bus_health_pct = float(parts[1])
            except ValueError:
                pass
        if state == STATE_OK:
            _needs_redraw = True
        return

    elif cmd == "NET":
        net_sub_state = ":".join(parts[1:]) if len(parts) > 1 else ""
        state = STATE_NET

    elif cmd == "LOCKED":
        state = STATE_LOCKED

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
    if state not in NAVIGABLE:
        return
    screen_idx = (screen_idx + 1) % len(SCREENS)
    state      = SCREENS[screen_idx]
    _needs_redraw = True

def on_swipe_right(x, y):
    global screen_idx, state, _needs_redraw
    if state not in NAVIGABLE:
        return
    screen_idx = (screen_idx - 1) % len(SCREENS)
    state      = SCREENS[screen_idx]
    _needs_redraw = True

def on_double_tap(x, y):
    global state, screen_idx, _needs_redraw
    state      = STATE_OK
    screen_idx = 0
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
apply_state()

buf              = ""
_ANIM_INTERVAL_MS = 80   # spinner plus fluide (etait 200ms)

while True:
    # Lecture UART — vider tout le buffer disponible en un seul passage
    while _poller.poll(0):
        try:
            ch = sys.stdin.read(1)
            if ch:
                buf += ch
                if '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    parse_command(line)
        except Exception:
            break

    # Touch
    if touch:
        try:
            touch.poll()
        except Exception:
            pass

    # Animation periodique (BOOTING et LOCKED uniquement)
    now = time.ticks_ms()
    if state in (STATE_BOOTING, STATE_LOCKED):
        if time.ticks_diff(now, _last_anim_ms) >= _ANIM_INTERVAL_MS:
            _last_anim_ms = now
            _needs_redraw = True

    if _needs_redraw:
        apply_state()

    time.sleep_ms(10)   # etait 20ms — plus reactif
