"""
Master Dome Servo Driver — Phase 2.
Pilote directement le PCA9685 I2C @ 0x40 (Servo Driver HAT).
11 servos panneaux dôme, canaux 0–10.

Servo continu : 1500µs=STOP, 1600µs=ouverture lente, 1400µs=fermeture lente.
open()  → envoie PULSE_OPEN_US  pendant duration_ms → STOP automatique
close() → envoie PULSE_CLOSED_US pendant duration_ms → STOP automatique

Formule duty_cycle identique au script de test validé :
    duty = int((pulse_us / 20000.0) * 65535)
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

# Servo continu — valeurs calquées sur test_servo_master.py validé
PULSE_STOP_US   = 1500  # STOP absolu
PULSE_OPEN_US   = 1600  # ouverture lente (ajuster vers 1550 si trop vite)
PULSE_CLOSED_US = 1400  # fermeture lente (ajuster vers 1450 si trop vite)

# Canaux 0–10 → dome_panel_1..11
SERVO_MAP: dict[str, int] = {
    'dome_panel_1':   0,
    'dome_panel_2':   1,
    'dome_panel_3':   2,
    'dome_panel_4':   3,
    'dome_panel_5':   4,
    'dome_panel_6':   5,
    'dome_panel_7':   6,
    'dome_panel_8':   7,
    'dome_panel_9':   8,
    'dome_panel_10':  9,
    'dome_panel_11': 10,
}


def _us_to_duty(pulse_us: float) -> int:
    """Même formule que test_servo_master.py — confirmée fonctionnelle."""
    return int((pulse_us / 20000.0) * 65535)


class DomeServoDriver(BaseDriver):

    def __init__(self, i2c_address: int = PCA9685_ADDRESS):
        self._address       = i2c_address
        self._pca           = None
        self._ready         = False
        self._lock          = threading.Lock()
        self._cancel_events: dict[int, threading.Event] = {}

    def setup(self) -> bool:
        try:
            import board, busio
            from adafruit_pca9685 import PCA9685

            # Réveiller le chip explicitement (peut être en sleep après estop.py)
            try:
                import smbus2
                b = smbus2.SMBus(1)
                b.write_byte_data(self._address, 0x00, 0x00)  # MODE1 = normal
                b.close()
                time.sleep(0.005)
            except Exception:
                pass

            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c, address=self._address)
            self._pca.frequency = PCA9685_FREQ_HZ

            # FULL OFF sur tous les canaux — efface valeurs résiduelles du chip
            for ch in range(16):
                self._pca.channels[ch].duty_cycle = 0

            self._ready = True
            log.info("DomeServoDriver prêt — PCA9685 @ 0x%02X, %d panneaux",
                     self._address, len(SERVO_MAP))
            return True
        except ImportError:
            log.error("adafruit-circuitpython-pca9685 non installé")
            return False
        except Exception as e:
            log.error("Erreur init PCA9685 dôme: %s", e)
            return False

    def shutdown(self) -> None:
        for evt in self._cancel_events.values():
            evt.set()
        if self._pca:
            for ch in SERVO_MAP.values():
                self._set_pulse(ch, PULSE_STOP_US)
            time.sleep(0.3)
            try:
                import smbus2
                b = smbus2.SMBus(1)
                b.write_byte_data(self._address, 0x00, 0x10)  # SLEEP
                b.close()
            except Exception as e:
                log.warning("Erreur sleep PCA9685 dôme: %s", e)
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def open(self, name: str, duration_ms: int = 500) -> bool:
        return self._move(name, PULSE_OPEN_US, duration_ms)

    def close(self, name: str, duration_ms: int = 500) -> bool:
        return self._move(name, PULSE_CLOSED_US, duration_ms)

    def open_all(self, duration_ms: int = 500) -> None:
        for name in SERVO_MAP:
            self.open(name, duration_ms)

    def close_all(self, duration_ms: int = 500) -> None:
        for name in SERVO_MAP:
            self.close(name, duration_ms)

    def move(self, name: str, position: float, duration_ms: int = 500) -> bool:
        """position 1.0 = open, 0.0 = close."""
        if position >= 0.5:
            return self.open(name, duration_ms)
        return self.close(name, duration_ms)

    @property
    def state(self) -> dict:
        return {n: 'open' if n in self._cancel_events else 'closed'
                for n in SERVO_MAP}

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _ensure_awake(self) -> None:
        """Réveille le chip si en sleep (ex: après estop.py ou test_servos.sh)."""
        try:
            import smbus2
            b = smbus2.SMBus(1)
            mode1 = b.read_byte_data(self._address, 0x00)
            if mode1 & 0x10:  # bit SLEEP actif
                b.write_byte_data(self._address, 0x00, mode1 & ~0x10)
                time.sleep(0.001)
                log.info("PCA9685 @ 0x%02X réveillé (était en sleep)", self._address)
            b.close()
        except Exception:
            pass

    def _move(self, name: str, pulse_us: int, duration_ms: int) -> bool:
        if not self._ready:
            return False
        if name not in SERVO_MAP:
            log.warning("Panneau dôme inconnu: %r", name)
            return False
        channel = SERVO_MAP[name]

        # Annuler mouvement précédent sur ce canal
        if channel in self._cancel_events:
            self._cancel_events[channel].set()

        cancel_evt = threading.Event()
        self._cancel_events[channel] = cancel_evt

        self._ensure_awake()
        self._set_pulse(channel, pulse_us)

        if duration_ms > 0:
            threading.Thread(
                target=self._timed_stop,
                args=(channel, duration_ms, cancel_evt),
                daemon=True
            ).start()
        return True

    def _set_pulse(self, channel: int, pulse_us: float) -> None:
        """Formule identique à test_servo_master.py."""
        duty = _us_to_duty(pulse_us)
        with self._lock:
            try:
                self._pca.channels[channel].duty_cycle = duty
            except Exception as e:
                log.error("Erreur PWM canal dôme %d: %s", channel, e)

    def _timed_stop(self, channel: int, duration_ms: int,
                    cancel_evt: threading.Event) -> None:
        """Attend duration_ms puis envoie STOP — servo continu."""
        time.sleep(duration_ms / 1000.0)
        if not cancel_evt.is_set():
            self._set_pulse(channel, PULSE_STOP_US)
