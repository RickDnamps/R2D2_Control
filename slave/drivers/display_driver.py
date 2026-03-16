"""
Display Driver — RP2040 Touch LCD 1.28 via USB serial.
Envoie les commandes DISP: au RP2040 sur /dev/ttyACM2.
"""

import logging
import serial
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.base_driver import BaseDriver

log = logging.getLogger(__name__)

DISPLAY_PORT = "/dev/ttyACM2"
DISPLAY_BAUD = 115200


class DisplayDriver(BaseDriver):
    def __init__(self, port: str = DISPLAY_PORT, baud: int = DISPLAY_BAUD):
        self._port = port
        self._baud = baud
        self._serial: serial.Serial | None = None
        self._ready = False

    def setup(self) -> bool:
        try:
            self._serial = serial.Serial(self._port, self._baud, timeout=1)
            self._ready = True
            log.info(f"DisplayDriver ouvert: {self._port}")
            return True
        except serial.SerialException as e:
            log.error(f"Impossible d'ouvrir display {self._port}: {e}")
            return False

    def shutdown(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready and self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    # Commandes d'état
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Séquence de boot diagnostic
    # ------------------------------------------------------------------

    def boot_start(self) -> bool:
        """Démarre la séquence de diagnostic — reset tous les items."""
        return self._send("DISP:BOOT:START")

    def boot_item(self, name: str) -> bool:
        """Item 'name' en cours de démarrage (orange)."""
        return self._send(f"DISP:BOOT:ITEM:{name}")

    def boot_ok(self, name: str) -> bool:
        """Item 'name' démarré avec succès (vert)."""
        return self._send(f"DISP:BOOT:OK:{name}")

    def boot_fail(self, name: str) -> bool:
        """Item 'name' en erreur (rouge)."""
        return self._send(f"DISP:BOOT:FAIL:{name}")

    def ready(self, version: str = "") -> bool:
        """Tout OK — affiche écran vert OPÉRATIONNEL 3s puis PRÊT."""
        if version:
            return self._send(f"DISP:READY:{version}")
        return self._send("DISP:READY")

    # ------------------------------------------------------------------
    # États opérationnels
    # ------------------------------------------------------------------

    def ok(self, version: str = "") -> bool:
        """Écran opérationnel normal (bordure verte)."""
        if version:
            return self._send(f"DISP:OK:{version}")
        return self._send("DISP:OK")

    def syncing(self, version: str = "") -> bool:
        """Synchronisation version en cours — reste sur l'écran de diagnostic."""
        return self._send("DISP:SYNCING")

    def error(self, code: str) -> bool:
        """
        Erreur avec code lisible (bordure rouge).
        Codes: MASTER_OFFLINE, VESC_TEMP_HIGH, VESC_FAULT, BATTERY_LOW,
               UART_ERROR, SYNC_FAILED, WATCHDOG, AUDIO_FAIL,
               SERVO_FAIL, VESC_L_FAIL, VESC_R_FAIL, I2C_ERROR
        """
        return self._send(f"DISP:ERROR:{code}")

    def telemetry(self, voltage: float, temp: float) -> bool:
        """Jauge batterie + température."""
        return self._send(f"DISP:TELEM:{voltage:.1f}V:{temp:.0f}C")

    def send_raw(self, cmd: str) -> bool:
        """Commande brute (ex: DISP: transférée depuis UART Master)."""
        return self._send(cmd)

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _send(self, cmd: str) -> bool:
        if not self.is_ready():
            log.debug(f"DisplayDriver non prêt, commande ignorée: {cmd}")
            return False
        try:
            self._serial.write(f"{cmd}\n".encode('utf-8'))
            log.debug(f"Display TX: {cmd}")
            return True
        except serial.SerialException as e:
            log.error(f"Erreur display send: {e}")
            self._ready = False
            return False
