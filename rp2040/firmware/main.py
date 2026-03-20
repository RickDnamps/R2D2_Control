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
# Config pins
# RST_PIN : 12 = RP2040-LCD-1.28 (sans touch)
#           13 = RP2040-Touch-LCD-1.28 (avec touch)
# ------------------------------------------------------------------
RST_PIN = 12

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
STATE_BOOTING = "BOOTING"
STATE_OK      = "OK"
STATE_NET     = "NET"
STATE_LOCKED  = "LOCKED"
STATE_ERROR   = "ERROR"
STATE_TELEM   = "TELEM"

# Navigation swipe — seulement quand operationnel
SCREENS   = [STATE_OK, STATE_TELEM]
NAVIGABLE = {STATE_OK, STATE_TELEM}

# Demarre en mode BOOTING (spinner orange)
state           = STATE_BOOTING
version         = ""
error_code      = ""
telem_voltage   = 0.0
telem_temp      = 0.0
net_sub_state   = ""
bus_health_pct  = 100.0
screen_idx      = 0

_needs_redraw  = True
_last_anim_ms  = 0    # dernier tick animation pour BOOTING/LOCKED


def apply_state():
    global _needs_redraw
    if state == STATE_BOOTING:
        disp.draw_booting(tft)
    elif state == STATE_OK:
        disp.draw_ok(tft, version, bus_health_pct)
    elif state == STATE_NET:
        disp.draw_net(tft, net_sub_state)
    elif state == STATE_LOCKED:
        disp.draw_locked(tft)
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
    cmd = parts[0].upper()

    if cmd == "BOOT":
        # DISP:BOOT:START -> passe en BOOTING (spinner)
        # DISP:BOOT:ITEM/OK/FAIL sont silencieusement ignores (spinner continue)
        sub = parts[1].upper() if len(parts) > 1 else ""
        if sub == "START":
            state = STATE_BOOTING

    elif cmd in ("READY", "OK"):
        version = parts[1] if len(parts) > 1 else ""
        state = STATE_OK

    elif cmd == "SYNCING":
        state = STATE_BOOTING  # reste sur le spinner pendant la synchro

    elif cmd == "BUS":
        if len(parts) > 1:
            try:
                bus_health_pct = float(parts[1])
            except ValueError:
                pass
        # Ne change PAS l'etat — force redraw seulement si on est en STATE_OK
        if state == STATE_OK:
            _needs_redraw = True
        return  # pas de _needs_redraw global ici

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
    state = SCREENS[screen_idx]
    _needs_redraw = True

def on_swipe_right(x, y):
    global screen_idx, state, _needs_redraw
    if state not in NAVIGABLE:
        return
    screen_idx = (screen_idx - 1) % len(SCREENS)
    state = SCREENS[screen_idx]
    _needs_redraw = True

def on_double_tap(x, y):
    """Double tap — retour a STATE_OK depuis n'importe quel etat."""
    global state, screen_idx, _needs_redraw
    state = STATE_OK
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
apply_state()   # afficher etat initial immediatement

buf = ""
_ANIM_INTERVAL_MS = 200   # intervalle animation pour BOOTING et LOCKED

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

    # Animation periodique pour BOOTING et LOCKED
    now = time.ticks_ms()
    if state in (STATE_BOOTING, STATE_LOCKED):
        if time.ticks_diff(now, _last_anim_ms) >= _ANIM_INTERVAL_MS:
            _last_anim_ms = now
            _needs_redraw = True

    # Redessiner SEULEMENT si quelque chose a change
    if _needs_redraw:
        apply_state()

    time.sleep_ms(20)
