"""
Master Dome Servo Driver — Phase 2.
Pilote directement le PCA9685 I2C @ 0x40 (Servo Driver HAT sur le Master).
11 servos pour les panneaux du dôme, canaux 0–10.

Pulse: 1000µs (fermé) → 1500µs (ouvert ≈ 45°).

Activation Phase 2:
  1. Brancher Servo Driver HAT sur I2C (GPIO 2/3, adresse 0x40)
  2. Décommenter l'import dans master/main.py
  3. Appeler dome_servo.setup() dans main()
  4. Enregistrer dans registry: reg.dome_servo = dome_servo
"""

import logging
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.base_driver import BaseDriver

log = logging.getLogger(__name__)

PCA9685_ADDRESS = 0x40
PCA9685_FREQ_HZ = 50

# Pulse fermé/ouvert — ~45° de débattement, safe pour SG90
PULSE_CLOSED_US = 1000  # ~45° (position fermée)
PULSE_OPEN_US   = 1500  # ~90° (position ouverte = +45°)

# 11 panneaux dôme, canaux 0–10
SERVO_MAP: dict[str, tuple[int, int, int]] = {
    'dome_panel_1':  (0,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_2':  (1,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_3':  (2,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_4':  (3,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_5':  (4,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_6':  (5,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_7':  (6,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_8':  (7,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_9':  (8,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_10': (9,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'dome_panel_11': (10, PULSE_CLOSED_US, PULSE_OPEN_US),
}


class DomeServoDriver(BaseDriver):
    """
    Pilote servos dôme via PCA9685 I2C @ 0x40 (local Master).
    """

    def __init__(self, i2c_address: int = PCA9685_ADDRESS):
        self._address  = i2c_address
        self._pca      = None
        self._ready    = False
        self._lock     = threading.Lock()
        self._positions: dict[str, float] = {n: 0.0 for n in SERVO_MAP}

    def setup(self) -> bool:
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685

            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c, address=self._address)
            self._pca.frequency = PCA9685_FREQ_HZ
            self._ready = True
            log.info(f"DomeServoDriver prêt — PCA9685 @ 0x{self._address:02X}, "
                     f"{len(SERVO_MAP)} panneaux dôme")
            return True
        except ImportError:
            log.error("adafruit-circuitpython-pca9685 non installé")
            return False
        except Exception as e:
            log.error(f"Erreur init PCA9685 dôme: {e}")
            return False

    def shutdown(self) -> None:
        if self._pca:
            for name in SERVO_MAP:
                self.close(name, duration_ms=300)
            time.sleep(0.4)
            try:
                import smbus2
                b = smbus2.SMBus(1)
                b.write_byte_data(self._address, 0x00, 0x10)  # SLEEP
                b.close()
            except Exception as e:
                log.warning(f"Erreur sleep PCA9685 dôme: {e}")
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def move(self, name: str, position: float,
             duration_ms: int = 500) -> bool:
        """
        Déplace un panneau dôme.

        Parameters
        ----------
        name       : nom du panneau (dans SERVO_MAP)
        position   : float [0.0=fermé … 1.0=ouvert]
        duration_ms: durée du mouvement (ms)
        """
        if not self._ready:
            return False
        if name not in SERVO_MAP:
            log.warning(f"Panneau dôme inconnu: {name!r}")
            return False

        position = max(0.0, min(1.0, position))
        self._positions[name] = position
        channel, pulse_min, pulse_max = SERVO_MAP[name]

        if duration_ms <= 0:
            self._set_pulse(channel, pulse_min, pulse_max, position)
        else:
            threading.Thread(
                target=self._smooth_move,
                args=(channel, pulse_min, pulse_max, position, duration_ms),
                daemon=True
            ).start()
        return True

    def open(self, name: str, duration_ms: int = 500) -> bool:
        """Ouvre un panneau dôme (position 1.0)."""
        return self.move(name, 1.0, duration_ms)

    def close(self, name: str, duration_ms: int = 500) -> bool:
        """Ferme un panneau dôme (position 0.0)."""
        return self.move(name, 0.0, duration_ms)

    def open_all(self, duration_ms: int = 500) -> None:
        """Ouvre tous les panneaux dôme."""
        for name in SERVO_MAP:
            self.open(name, duration_ms)

    def close_all(self, duration_ms: int = 500) -> None:
        """Ferme tous les panneaux dôme."""
        for name in SERVO_MAP:
            self.close(name, duration_ms)

    @property
    def state(self) -> dict:
        return dict(self._positions)

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _set_pulse(self, channel: int, pulse_min: int,
                   pulse_max: int, position: float) -> None:
        pulse_us = pulse_min + (pulse_max - pulse_min) * position
        tick = int((pulse_us / 20000.0) * 4096)
        with self._lock:
            try:
                self._pca.channels[channel].duty_cycle = tick << 4
            except Exception as e:
                log.error(f"Erreur PWM canal dôme {channel}: {e}")

    def _smooth_move(self, channel: int, pulse_min: int, pulse_max: int,
                     target: float, duration_ms: int) -> None:
        steps    = max(10, duration_ms // 20)
        interval = duration_ms / 1000.0 / steps
        for i in range(steps + 1):
            pos = i / steps * target
            self._set_pulse(channel, pulse_min, pulse_max, pos)
            time.sleep(interval)
