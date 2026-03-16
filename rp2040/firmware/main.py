"""
R2-D2 RP2040 Firmware — MicroPython.
Waveshare RP2040-Touch-LCD-1.28 (GC9A01, CST816S).

Reçoit les commandes DISP: depuis le Pi Zero via USB serial.
Autonome — ne nécessite pas de MAJ fréquente.

Commandes reçues:
  DISP:BOOT
  DISP:SYNCING[:version]
  DISP:OK[:version]
  DISP:ERROR:RAISON
  DISP:TELEM:48.2V:32C

Gestes tactiles:
  TAP          → action primaire
  SWIPE        → changer d'écran
  HOLD 2s      → arrêt d'urgence (envoi commande STOP vers Pi Zero)
  DOUBLE TAP   → retour accueil
"""

import sys
import gc9a01
import time
from machine import SPI, Pin, I2C
import display as disp
from touch import TouchHandler

# ------------------------------------------------------------------
# Pins hardware (Waveshare RP2040-Touch-LCD-1.28)
# ------------------------------------------------------------------
TFT_SCK  = Pin(10)
TFT_MOSI = Pin(11)
TFT_DC   = Pin(8,  Pin.OUT)
TFT_CS   = Pin(9,  Pin.OUT)
TFT_RST  = Pin(12, Pin.OUT)
TFT_BL   = Pin(25, Pin.OUT)

I2C_SDA  = Pin(6)
I2C_SCL  = Pin(7)
INT_PIN  = Pin(17, Pin.IN)  # CST816S interrupt


# ------------------------------------------------------------------
# Init hardware
# ------------------------------------------------------------------
def init_display():
    TFT_BL.value(1)  # allumer le backlight avant init
    spi = SPI(1, baudrate=40_000_000, sck=TFT_SCK, mosi=TFT_MOSI)
    tft = gc9a01.GC9A01(spi, 240, 240, dc=TFT_DC, cs=TFT_CS, reset=TFT_RST, backlight=TFT_BL)
    tft.init()
    return tft


def init_touch():
    i2c = I2C(1, sda=I2C_SDA, scl=I2C_SCL, freq=400_000)
    return TouchHandler(i2c)


# ------------------------------------------------------------------
# État courant
# ------------------------------------------------------------------
STATE_BOOT     = "BOOT"
STATE_SYNCING  = "SYNCING"
STATE_OK       = "OK"
STATE_ERROR    = "ERROR"
STATE_TELEM    = "TELEM"

current_state   = STATE_BOOT
current_version = ""
telem_data      = {"voltage": 0.0, "temp": 0.0}
spinner_step    = 0


def apply_state(tft):
    global spinner_step
    if current_state == STATE_BOOT:
        disp.draw_boot(tft)
    elif current_state == STATE_SYNCING:
        disp.draw_syncing(tft, current_version, spinner_step)
        spinner_step = (spinner_step + 1) % 12
    elif current_state == STATE_OK:
        disp.draw_ok(tft, current_version)
    elif current_state == STATE_ERROR:
        disp.draw_error(tft, current_version)
    elif current_state == STATE_TELEM:
        disp.draw_telemetry(tft, telem_data["voltage"], telem_data["temp"])


def parse_command(line: str) -> None:
    global current_state, current_version, telem_data
    line = line.strip()
    if not line.startswith("DISP:"):
        return
    parts = line[5:].split(":")
    cmd = parts[0].upper()

    if cmd == "BOOT":
        current_state = STATE_BOOT
    elif cmd == "SYNCING":
        current_state   = STATE_SYNCING
        current_version = parts[1] if len(parts) > 1 else ""
    elif cmd == "OK":
        current_state   = STATE_OK
        current_version = parts[1] if len(parts) > 1 else ""
    elif cmd == "ERROR":
        current_state   = STATE_ERROR
        current_version = ":".join(parts[1:]) if len(parts) > 1 else "UNKNOWN"
    elif cmd == "TELEM" and len(parts) >= 3:
        current_state = STATE_TELEM
        try:
            telem_data["voltage"] = float(parts[1].rstrip("Vv"))
            telem_data["temp"]    = float(parts[2].rstrip("Cc"))
        except ValueError:
            pass


# ------------------------------------------------------------------
# Gestes tactiles
# ------------------------------------------------------------------
SCREENS = [STATE_TELEM, STATE_OK, STATE_BOOT]
screen_idx = 0


def on_swipe_left(x, y):
    global screen_idx, current_state
    screen_idx = (screen_idx + 1) % len(SCREENS)
    current_state = SCREENS[screen_idx]


def on_swipe_right(x, y):
    global screen_idx, current_state
    screen_idx = (screen_idx - 1) % len(SCREENS)
    current_state = SCREENS[screen_idx]


def on_double_tap(x, y):
    global current_state
    current_state = STATE_BOOT


def on_hold(x, y):
    """Arrêt d'urgence — envoie STOP au Pi Zero."""
    sys.stdout.write("EMERGENCY:STOP\n")


# ------------------------------------------------------------------
# Boucle principale
# ------------------------------------------------------------------
def main():
    tft   = init_display()
    try:
        touch = init_touch()
    except Exception:
        touch = None

    touch.on('swipe_left',  on_swipe_left)
    touch.on('swipe_right', on_swipe_right)
    touch.on('double_tap',  on_double_tap)
    touch.on('hold',        on_hold)

    buf   = ""
    last_draw = time.ticks_ms()
    REFRESH_MS = 1000  # refresh toutes les 1s (évite tearing avec fallback circles)

    while True:
        # TODO: lecture commandes USB serial (DISP:) — à implémenter
        # quand le Slave sera connecté via USB

        # Touch polling
        if touch:
            touch.poll()

        # Refresh affichage
        now = time.ticks_ms()
        if time.ticks_diff(now, last_draw) >= REFRESH_MS:
            apply_state(tft)
            last_draw = now

        time.sleep_ms(20)


main()
