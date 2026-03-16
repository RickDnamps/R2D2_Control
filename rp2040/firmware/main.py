"""
R2-D2 RP2040 Firmware — MicroPython.
Waveshare RP2040-LCD-1.28 / RP2040-Touch-LCD-1.28 (GC9A01, CST816S).

Reçoit les commandes DISP: depuis le Slave Pi via USB serial.
Autonome — ne nécessite pas de MAJ fréquente.

Commandes reçues:
  DISP:BOOT
  DISP:SYNCING[:version]
  DISP:OK[:version]
  DISP:ERROR:RAISON
  DISP:TELEM:48.2V:32C

Gestes tactiles (si board Touch):
  SWIPE gauche/droite → changer d'écran
  DOUBLE TAP          → retour boot
  HOLD 2s             → arrêt d'urgence → envoie EMERGENCY:STOP au Slave
"""

import sys
import select
import gc9a01
import time
from machine import SPI, Pin, I2C
import display as disp

# ------------------------------------------------------------------
# Pins hardware — NE PAS créer en avance (RST LOW au boot casse init GC9A01)
# RST_PIN : 12 = RP2040-LCD-1.28 (sans touch) / 13 = RP2040-Touch-LCD-1.28
# ------------------------------------------------------------------
RST_PIN = 12   # ← changer à 13 si board avec touch

# ------------------------------------------------------------------
# Init hardware — délai boot obligatoire avant init display
# ------------------------------------------------------------------
time.sleep_ms(500)  # laisser le hardware se stabiliser

Pin(25, Pin.OUT).value(1)  # backlight ON immédiatement
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
# Touch (optionnel — ignoré si board sans touch ou chip absent)
# ------------------------------------------------------------------
touch = None
try:
    from touch import TouchHandler
    i2c = I2C(1, sda=Pin(6), scl=Pin(7), freq=400_000)
    touch = TouchHandler(i2c)
except Exception:
    pass  # board sans touch ou chip non détecté

# ------------------------------------------------------------------
# États
# ------------------------------------------------------------------
STATE_BOOT    = "BOOT"
STATE_SYNCING = "SYNCING"
STATE_OK      = "OK"
STATE_ERROR   = "ERROR"
STATE_TELEM   = "TELEM"

SCREENS = [STATE_BOOT, STATE_OK, STATE_TELEM]

state         = STATE_BOOT
version       = ""
telem_voltage = 0.0
telem_temp    = 0.0
screen_idx    = 0
spinner_step  = 0


def apply_state():
    global spinner_step
    if state == STATE_BOOT:
        disp.draw_boot(tft)
    elif state == STATE_SYNCING:
        disp.draw_syncing(tft, version, spinner_step)
        spinner_step = (spinner_step + 1) % 12
    elif state == STATE_OK:
        disp.draw_ok(tft, version)
    elif state == STATE_ERROR:
        disp.draw_error(tft, version)
    elif state == STATE_TELEM:
        disp.draw_telemetry(tft, telem_voltage, telem_temp)


def parse_command(line):
    global state, version, telem_voltage, telem_temp
    line = line.strip()
    if not line.startswith("DISP:"):
        return
    parts = line[5:].split(":")
    cmd = parts[0].upper()

    if cmd == "BOOT":
        state = STATE_BOOT
    elif cmd == "SYNCING":
        state   = STATE_SYNCING
        version = parts[1] if len(parts) > 1 else ""
    elif cmd == "OK":
        state   = STATE_OK
        version = parts[1] if len(parts) > 1 else ""
    elif cmd == "ERROR":
        state   = STATE_ERROR
        version = ":".join(parts[1:]) if len(parts) > 1 else "UNKNOWN"
    elif cmd == "TELEM" and len(parts) >= 3:
        state = STATE_TELEM
        try:
            telem_voltage = float(parts[1].rstrip("Vv"))
            telem_temp    = float(parts[2].rstrip("Cc"))
        except ValueError:
            pass


# ------------------------------------------------------------------
# Gestes touch
# ------------------------------------------------------------------
def on_swipe_left(x, y):
    global screen_idx, state
    screen_idx = (screen_idx + 1) % len(SCREENS)
    state = SCREENS[screen_idx]

def on_swipe_right(x, y):
    global screen_idx, state
    screen_idx = (screen_idx - 1) % len(SCREENS)
    state = SCREENS[screen_idx]

def on_double_tap(x, y):
    global state
    state = STATE_BOOT

def on_hold(x, y):
    sys.stdout.write("EMERGENCY:STOP\n")

if touch:
    touch.on('swipe_left',  on_swipe_left)
    touch.on('swipe_right', on_swipe_right)
    touch.on('double_tap',  on_double_tap)
    touch.on('hold',        on_hold)

# ------------------------------------------------------------------
# Stdin non-bloquant (commandes DISP: depuis Slave Pi)
# ------------------------------------------------------------------
_poller = select.poll()
_poller.register(sys.stdin, select.POLLIN)

# ------------------------------------------------------------------
# Boucle principale
# ------------------------------------------------------------------
apply_state()  # afficher état initial immédiatement

buf      = ""
last_draw = time.ticks_ms()
REFRESH_MS = 500  # refresh toutes les 500ms

while True:
    # Lecture stdin non-bloquante
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

    # Refresh affichage
    now = time.ticks_ms()
    if time.ticks_diff(now, last_draw) >= REFRESH_MS:
        apply_state()
        last_draw = now

    time.sleep_ms(20)
