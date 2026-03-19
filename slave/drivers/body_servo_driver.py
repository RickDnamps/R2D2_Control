"""
Slave Body Servo Driver — Phase 2.
Reçoit les commandes SRV: du Master et pilote le PCA9685 I2C.

Format UART reçu: SRV:NAME,POSITION,DURATION
  NAME     : nom du servo
  POSITION : float [0.0 … 1.0]
  DURATION : int millisecondes

Configuration des canaux PCA9685 dans SERVO_MAP ci-dessous.
Fréquence PWM: 50 Hz (standard servo).
Pulse: 1000µs (fermé) à 2000µs (ouvert) — ajuster par servo.

Activation Phase 2:
  1. Brancher PCA9685 sur I2C (GPIO 2/3, adresse 0x40)
  2. Décommenter l'import dans slave/main.py
  3. Appeler servo.setup() dans main()
  4. uart.register_callback('SRV', servo.handle_uart)
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

# Mapping nom → (channel, pulse_min_us, pulse_max_us)
# pulse_min = position fermée, pulse_max = position ouverte
SERVO_MAP: dict[str, tuple[int, int, int]] = {
    'utility_arm_left':   (0, 1000, 2000),
    'utility_arm_right':  (1, 1000, 2000),
    'panel_front_top':    (2, 1000, 2000),
    'panel_front_bottom': (3, 1000, 2000),
    'panel_rear_top':     (4, 1000, 2000),
    'panel_rear_bottom':  (5, 1000, 2000),
    'charge_bay':         (6, 1000, 2000),
    # Ajouter ici selon câblage réel
}


class BodyServoDriver(BaseDriver):
    """
    Pilote servos body via PCA9685 I2C.
    """

    def __init__(self, i2c_address: int = PCA9685_ADDRESS):
        self._address = i2c_address
        self._pca     = None
        self._ready   = False
        self._lock    = threading.Lock()

    def setup(self) -> bool:
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685

            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c, address=self._address)
            self._pca.frequency = PCA9685_FREQ_HZ
            self._ready = True
            log.info(f"BodyServoDriver prêt — PCA9685 @ 0x{self._address:02X}, "
                     f"{len(SERVO_MAP)} servos configurés")
            return True
        except ImportError:
            log.error("adafruit-circuitpython-pca9685 non installé")
            return False
        except Exception as e:
            log.error(f"Erreur init PCA9685: {e}")
            return False

    def shutdown(self) -> None:
        if self._pca:
            # Remettre tous les servos en position neutre
            for name in SERVO_MAP:
                self.move(name, 0.0, duration_ms=500)
            time.sleep(0.6)
            self._pca.deinit()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def move(self, name: str, position: float, duration_ms: int = 500) -> None:
        """
        Déplace un servo.

        Parameters
        ----------
        name       : nom du servo (dans SERVO_MAP)
        position   : float [0.0 … 1.0]
        duration_ms: durée du mouvement (ms) — 0 = instantané
        """
        if not self._ready:
            return
        if name not in SERVO_MAP:
            log.warning(f"Servo inconnu: {name!r}")
            return

        channel, pulse_min, pulse_max = SERVO_MAP[name]
        position = max(0.0, min(1.0, position))

        if duration_ms <= 0:
            self._set_pulse(channel, pulse_min, pulse_max, position)
        else:
            # Mouvement progressif dans un thread dédié
            threading.Thread(
                target=self._smooth_move,
                args=(channel, pulse_min, pulse_max, position, duration_ms),
                daemon=True
            ).start()

    def handle_uart(self, value: str) -> None:
        """
        Callback UART pour message SRV:NAME,POSITION,DURATION.
        """
        try:
            parts = value.split(',')
            name        = parts[0]
            position    = float(parts[1])
            duration_ms = int(parts[2])
            self.move(name, position, duration_ms)
        except (ValueError, IndexError) as e:
            log.error(f"Message SRV: invalide {value!r}: {e}")

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _set_pulse(self, channel: int, pulse_min: int,
                   pulse_max: int, position: float) -> None:
        """Envoie la valeur PWM au canal PCA9685."""
        pulse_us = pulse_min + (pulse_max - pulse_min) * position
        # Conversion µs → valeur 12-bit PCA9685 à 50Hz
        # Période = 20ms = 20000µs → 4096 ticks
        tick = int((pulse_us / 20000.0) * 4096)
        with self._lock:
            try:
                self._pca.channels[channel].duty_cycle = tick << 4  # 16-bit
            except Exception as e:
                log.error(f"Erreur PWM canal {channel}: {e}")

    def _smooth_move(self, channel: int, pulse_min: int, pulse_max: int,
                     target: float, duration_ms: int) -> None:
        """Interpolation linéaire sur duration_ms."""
        steps    = max(10, duration_ms // 20)  # ~50 fps
        interval = duration_ms / 1000.0 / steps
        for i in range(steps + 1):
            pos = i / steps * target
            self._set_pulse(channel, pulse_min, pulse_max, pos)
            time.sleep(interval)
