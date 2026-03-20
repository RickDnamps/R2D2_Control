"""
Slave Body Servo Driver — Phase 2.
Reçoit les commandes SRV: du Master et pilote le PCA9685 I2C @ 0x41 via smbus2.

Servo continu : 1500µs=STOP, 1600µs=ouverture lente, 1400µs=fermeture lente.
open()  → envoie PULSE_OPEN_US  pendant duration_ms → STOP automatique
close() → envoie PULSE_CLOSED_US pendant duration_ms → STOP automatique

Formule 12-bit (registres PCA9685 hardware) :
    tick = int((pulse_us / 20000.0) * 4096)
"""

import logging
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.base_driver import BaseDriver

log = logging.getLogger(__name__)

PCA9685_ADDRESS  = 0x41
PCA9685_FREQ_HZ  = 50
MODE1_REG        = 0x00
PRE_SCALE_REG    = 0xFE
PRE_SCALE_50HZ   = 121

PULSE_STOP_US    = 1700   # point d'arrêt réel de ces SG90 (calibré sur bench)
# Vitesses asymétriques (inévitable avec SG90 CR dont le stop ≠ 1500µs) :
#   Open  : 2000µs → 300µs au-dessus du stop → vitesse lente
#   Close : 1000µs → 700µs en-dessous du stop → ~2.3× plus rapide
# → compenser via les angles open/close indépendants dans Settings → SERVO CALIBRATION
PULSE_OPEN_US    = 2000   # sens ouverture
PULSE_CLOSED_US  = 1000   # sens fermeture (plus rapide — compenser par close_angle)

SERVO_MAP: dict[str, int] = {
    'body_panel_1':   0,
    'body_panel_2':   1,
    'body_panel_3':   2,
    'body_panel_4':   3,
    'body_panel_5':   4,
    'body_panel_6':   5,
    'body_panel_7':   6,
    'body_panel_8':   7,
    'body_panel_9':   8,
    'body_panel_10':  9,
    'body_panel_11': 10,
}


def _pulse_to_tick(pulse_us: float) -> int:
    """Convertit µs en valeur 12-bit PCA9685 (registres hardware)."""
    return max(0, min(4095, int(pulse_us / 20000.0 * 4096)))


class BodyServoDriver(BaseDriver):

    def __init__(self, i2c_address: int = PCA9685_ADDRESS):
        self._address        = i2c_address
        self._bus            = None
        self._ready          = False
        self._lock           = threading.Lock()
        self._cancel_events: dict[int, threading.Event] = {}

    def setup(self) -> bool:
        try:
            import smbus2
            self._bus = smbus2.SMBus(1)
            self._init_chip()
            self._ready = True
            log.info("BodyServoDriver prêt — smbus2 @ 0x%02X, %d servos",
                     self._address, len(SERVO_MAP))
            return True
        except Exception as e:
            log.error("Erreur init PCA9685 body: %s", e)
            return False

    def shutdown(self) -> None:
        for evt in self._cancel_events.values():
            evt.set()
        if self._bus:
            for ch in SERVO_MAP.values():
                self._set_pulse(ch, PULSE_STOP_US)
            time.sleep(0.3)
            try:
                self._bus.write_byte_data(self._address, MODE1_REG, 0x10)  # SLEEP
            except Exception:
                pass
            try:
                self._bus.close()
            except Exception:
                pass
        self._bus   = None
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def open(self, name: str, duration_ms: int = 300) -> None:
        self._move(name, PULSE_OPEN_US, duration_ms)

    def close(self, name: str, duration_ms: int = 300) -> None:
        self._move(name, PULSE_CLOSED_US, duration_ms)

    def open_all(self, duration_ms: int = 300) -> None:
        for name in SERVO_MAP:
            self.open(name, duration_ms)

    def close_all(self, duration_ms: int = 300) -> None:
        for name in SERVO_MAP:
            self.close(name, duration_ms)

    def move(self, name: str, position: float, duration_ms: int = 300) -> None:
        if position >= 0.5:
            self.open(name, duration_ms)
        else:
            self.close(name, duration_ms)

    def handle_uart(self, value: str) -> None:
        """Callback UART — SRV:NAME,POSITION,DURATION"""
        try:
            parts = value.split(',')
            self.move(parts[0], float(parts[1]), int(parts[2]))
        except (ValueError, IndexError) as e:
            log.error("Message SRV invalide %r: %s", value, e)

    @property
    def state(self) -> dict:
        return {n: 'open' if n in self._cancel_events else 'closed'
                for n in SERVO_MAP}

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _init_chip(self) -> None:
        """Initialise le PCA9685 : fréquence 50Hz + zéro tous les canaux."""
        self._bus.write_byte_data(self._address, MODE1_REG, 0x00)
        time.sleep(0.005)
        self._bus.write_byte_data(self._address, MODE1_REG, 0x10)
        time.sleep(0.005)
        self._bus.write_byte_data(self._address, PRE_SCALE_REG, PRE_SCALE_50HZ)
        self._bus.write_byte_data(self._address, MODE1_REG, 0x00)
        time.sleep(0.005)
        # RESTART bit (0x80) — réactive tous les canaux PWM (comme la lib adafruit)
        self._bus.write_byte_data(self._address, MODE1_REG, 0x80)
        time.sleep(0.005)
        for ch in range(16):
            self._full_off(ch)
        log.info("PCA9685 @ 0x%02X initialisé 50Hz + RESTART", self._address)

    def _ensure_awake(self) -> None:
        """Réveille le chip s'il est en sleep (ex: après estop.py)."""
        try:
            mode1 = self._bus.read_byte_data(self._address, MODE1_REG)
            if mode1 & 0x10:
                self._bus.write_byte_data(self._address, MODE1_REG, mode1 & ~0x10)
                time.sleep(0.002)
                log.info("PCA9685 @ 0x%02X réveillé (était en sleep)", self._address)
        except Exception as e:
            log.warning("_ensure_awake 0x%02X: %s", self._address, e)

    def _full_off(self, channel: int) -> None:
        base = 0x06 + 4 * channel
        self._bus.write_byte_data(self._address, base,     0x00)
        self._bus.write_byte_data(self._address, base + 1, 0x00)
        self._bus.write_byte_data(self._address, base + 2, 0x00)
        self._bus.write_byte_data(self._address, base + 3, 0x10)

    def _set_pulse(self, channel: int, pulse_us: float) -> None:
        tick = _pulse_to_tick(pulse_us)
        base = 0x06 + 4 * channel
        with self._lock:
            try:
                self._bus.write_byte_data(self._address, base,     0x00)
                self._bus.write_byte_data(self._address, base + 1, 0x00)
                self._bus.write_byte_data(self._address, base + 2, tick & 0xFF)
                self._bus.write_byte_data(self._address, base + 3, tick >> 8)
            except Exception as e:
                log.error("Erreur smbus2 canal body %d: %s", channel, e)

    def _move(self, name: str, pulse_us: int, duration_ms: int) -> None:
        if not self._ready:
            log.warning("BodyServoDriver non prêt — commande ignorée (%r)", name)
            return
        if name not in SERVO_MAP:
            log.warning("Servo inconnu: %r", name)
            return
        channel = SERVO_MAP[name]

        if channel in self._cancel_events:
            self._cancel_events[channel].set()
            # Stop immédiat avant nouvelle commande — évite la dérive de position
            self._set_pulse(channel, PULSE_STOP_US)
            time.sleep(0.05)

        cancel_evt = threading.Event()
        self._cancel_events[channel] = cancel_evt

        self._ensure_awake()
        self._set_pulse(channel, pulse_us)
        log.info("Body servo %r ch%d → %dµs (%dms)", name, channel, pulse_us, duration_ms)

        if duration_ms > 0:
            threading.Thread(
                target=self._timed_stop,
                args=(channel, duration_ms, cancel_evt),
                daemon=True
            ).start()

    def _timed_stop(self, channel: int, duration_ms: int,
                    cancel_evt: threading.Event) -> None:
        time.sleep(duration_ms / 1000.0)
        if not cancel_evt.is_set():
            self._set_pulse(channel, PULSE_STOP_US)
