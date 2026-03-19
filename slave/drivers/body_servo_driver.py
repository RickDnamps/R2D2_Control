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

# Pulse fermé/ouvert — ~45° de débattement, safe pour SG90
PULSE_CLOSED_US = 1000  # ~45° (position fermée)
PULSE_OPEN_US   = 1500  # ~90° (position ouverte = +45°)

# 11 panneaux body, canaux 0–10
# Mapping nom → (channel, pulse_min_us, pulse_max_us)
# pulse_min = position fermée, pulse_max = position ouverte
SERVO_MAP: dict[str, tuple[int, int, int]] = {
    'body_panel_1':  (0,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_2':  (1,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_3':  (2,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_4':  (3,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_5':  (4,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_6':  (5,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_7':  (6,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_8':  (7,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_9':  (8,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_10': (9,  PULSE_CLOSED_US, PULSE_OPEN_US),
    'body_panel_11': (10, PULSE_CLOSED_US, PULSE_OPEN_US),
}


class BodyServoDriver(BaseDriver):
    """
    Pilote servos body via PCA9685 I2C.
    """

    def __init__(self, i2c_address: int = PCA9685_ADDRESS):
        self._address        = i2c_address
        self._pca            = None
        self._ready          = False
        self._lock           = threading.Lock()
        self._current_pulse: dict[int, float]           = {}
        self._cancel_events: dict[int, threading.Event] = {}

    def setup(self) -> bool:
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685

            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c, address=self._address)
            self._pca.frequency = PCA9685_FREQ_HZ

            # Initialiser tous les canaux en position fermée
            for name, (channel, pulse_min, pulse_max) in SERVO_MAP.items():
                self._current_pulse[channel] = float(pulse_min)
                self._set_pulse_raw(channel, float(pulse_min))

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
        # Annuler tous les mouvements en cours
        for evt in self._cancel_events.values():
            evt.set()
        if self._pca:
            for channel, pulse_min in [(SERVO_MAP[n][0], SERVO_MAP[n][1]) for n in SERVO_MAP]:
                self._set_pulse_raw(channel, float(pulse_min))
            time.sleep(0.3)
            try:
                import smbus2
                b = smbus2.SMBus(1)
                b.write_byte_data(self._address, 0x00, 0x10)  # MODE1 SLEEP
                b.close()
            except Exception as e:
                log.warning(f"Erreur sleep PCA9685 body: {e}")
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def move(self, name: str, position: float, duration_ms: int = 500) -> None:
        if not self._ready:
            return
        if name not in SERVO_MAP:
            log.warning(f"Servo inconnu: {name!r}")
            return

        channel, pulse_min, pulse_max = SERVO_MAP[name]
        position = max(0.0, min(1.0, position))

        # Annuler le mouvement en cours sur ce canal
        if channel in self._cancel_events:
            self._cancel_events[channel].set()

        target_pulse = pulse_min + (pulse_max - pulse_min) * position
        start_pulse  = self._current_pulse.get(channel, float(pulse_min))
        cancel_evt   = threading.Event()
        self._cancel_events[channel] = cancel_evt

        if duration_ms <= 0:
            self._set_pulse_raw(channel, target_pulse)
            self._current_pulse[channel] = target_pulse
        else:
            threading.Thread(
                target=self._smooth_move,
                args=(channel, start_pulse, target_pulse, duration_ms, cancel_evt),
                daemon=True
            ).start()

    def handle_uart(self, value: str) -> None:
        """Callback UART pour message SRV:NAME,POSITION,DURATION."""
        try:
            parts = value.split(',')
            self.move(parts[0], float(parts[1]), int(parts[2]))
        except (ValueError, IndexError) as e:
            log.error(f"Message SRV: invalide {value!r}: {e}")

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _set_pulse_raw(self, channel: int, pulse_us: float) -> None:
        tick = int((pulse_us / 20000.0) * 4096)
        with self._lock:
            try:
                self._pca.channels[channel].duty_cycle = tick << 4
            except Exception as e:
                log.error(f"Erreur PWM canal {channel}: {e}")

    def _smooth_move(self, channel: int, start_pulse: float, target_pulse: float,
                     duration_ms: int, cancel_evt: threading.Event) -> None:
        """Interpolation depuis position courante vers target — annulable."""
        steps    = max(10, duration_ms // 20)
        interval = duration_ms / 1000.0 / steps
        for i in range(steps + 1):
            if cancel_evt.is_set():
                return  # nouvelle commande reçue — abandonner
            pulse = start_pulse + (target_pulse - start_pulse) * (i / steps)
            self._set_pulse_raw(channel, pulse)
            self._current_pulse[channel] = pulse
            time.sleep(interval)
