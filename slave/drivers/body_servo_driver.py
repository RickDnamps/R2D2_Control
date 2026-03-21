"""
Slave Body Servo Driver — Phase 2 (MG90S 180°).
Reçoit les commandes SRV: du Master et pilote le PCA9685 I2C @ 0x41 via smbus2.

Servo MG90S 180° : pulse_us = 500 + (angle_deg / 180.0) * 2000
open()  → va à open_angle_deg et maintient la position (pas de timer)
close() → va à close_angle_deg et maintient la position

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

PCA9685_ADDRESS = 0x41
PCA9685_FREQ_HZ = 50
MODE1_REG       = 0x00
PRE_SCALE_REG   = 0xFE
PRE_SCALE_50HZ  = 121

DEFAULT_OPEN_DEG  = 110   # angle ouverture MG90S (0–180°)
DEFAULT_CLOSE_DEG =  20   # angle fermeture MG90S (0–180°)
ANGLE_MIN_DEG     =  10   # sécurité matérielle
ANGLE_MAX_DEG     = 170   # sécurité matérielle

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


def _angle_to_pulse(angle_deg: float) -> float:
    """Convertit un angle MG90S en µs pour PCA9685."""
    angle_deg = max(ANGLE_MIN_DEG, min(ANGLE_MAX_DEG, angle_deg))
    return 500.0 + (angle_deg / 180.0) * 2000.0


def _pulse_to_tick(pulse_us: float) -> int:
    """Convertit µs en valeur 12-bit PCA9685 (registres hardware)."""
    return max(0, min(4095, int(pulse_us / 20000.0 * 4096)))


class BodyServoDriver(BaseDriver):

    def __init__(self, i2c_address: int = PCA9685_ADDRESS):
        self._address = i2c_address
        self._bus     = None
        self._ready   = False
        self._lock    = threading.Lock()

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
        if self._bus:
            close_pulse = _angle_to_pulse(DEFAULT_CLOSE_DEG)
            for ch in SERVO_MAP.values():
                self._set_pulse(ch, close_pulse)
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

    def open(self, name: str, angle_deg: float = DEFAULT_OPEN_DEG) -> None:
        self._move(name, angle_deg)

    def close(self, name: str, angle_deg: float = DEFAULT_CLOSE_DEG) -> None:
        self._move(name, angle_deg)

    def move(self, name: str, position: float,
             angle_open: float = DEFAULT_OPEN_DEG,
             angle_close: float = DEFAULT_CLOSE_DEG) -> None:
        """position 0.0=fermé … 1.0=ouvert — interpolé entre angle_close et angle_open."""
        angle = angle_close + max(0.0, min(1.0, position)) * (angle_open - angle_close)
        self._move(name, angle)

    def open_all(self, angle_deg: float = DEFAULT_OPEN_DEG) -> None:
        for name in SERVO_MAP:
            self.open(name, angle_deg)

    def close_all(self, angle_deg: float = DEFAULT_CLOSE_DEG) -> None:
        for name in SERVO_MAP:
            self.close(name, angle_deg)

    def handle_uart(self, value: str) -> None:
        """Callback UART — SRV:NAME,ANGLE_DEG"""
        try:
            parts = value.split(',')
            self._move(parts[0], float(parts[1]))
        except (ValueError, IndexError) as e:
            log.error("Message SRV invalide %r: %s", value, e)

    @property
    def state(self) -> dict:
        return {n: 'unknown' for n in SERVO_MAP}

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
        self._bus.write_byte_data(self._address, MODE1_REG, 0x80)
        time.sleep(0.005)
        for ch in range(16):
            self._full_off(ch)
        # Position fermée dès l'init — jamais de position 90° parasite
        close_pulse = _angle_to_pulse(DEFAULT_CLOSE_DEG)
        for ch in SERVO_MAP.values():
            self._set_pulse(ch, close_pulse)
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

    def _move(self, name: str, angle_deg: float) -> None:
        if not self._ready:
            log.warning("BodyServoDriver non prêt — commande ignorée (%r)", name)
            return
        if name not in SERVO_MAP:
            log.warning("Servo inconnu: %r", name)
            return
        channel  = SERVO_MAP[name]
        pulse_us = _angle_to_pulse(angle_deg)
        self._ensure_awake()
        self._set_pulse(channel, pulse_us)
        log.info("Body servo %r ch%d → %.1f° (%.0fµs)", name, channel, angle_deg, pulse_us)
