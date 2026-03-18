"""
Teeces32 Controller — Protocole JawaLite via USB /dev/ttyUSB0.
Gère les LED logics FLD/RLD/PSI sur le dôme.
"""

import logging
import serial
import configparser
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.base_driver import BaseDriver

log = logging.getLogger(__name__)


class TeecesController(BaseDriver):
    def __init__(self, cfg: configparser.ConfigParser):
        self._port = cfg.get('teeces', 'port')
        self._baud = cfg.getint('teeces', 'baud')
        self._serial: serial.Serial | None = None
        self._ready = False

    def setup(self) -> bool:
        try:
            self._serial = serial.Serial(self._port, self._baud, timeout=1)
            self._ready = True
            log.info(f"Teeces32 ouvert: {self._port} @ {self._baud}")
            return True
        except serial.SerialException as e:
            log.error(f"Impossible d'ouvrir Teeces32 {self._port}: {e}")
            self._ready = False
            return False

    def shutdown(self) -> None:
        self.all_off()
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._ready = False
        log.info("Teeces32 arrêté")

    def is_ready(self) -> bool:
        return self._ready and self._serial is not None and self._serial.is_open

    def send_command(self, cmd: str) -> bool:
        """Envoie une commande JawaLite brute. Ex: '0T1\r'"""
        if not self.is_ready():
            log.warning(f"Teeces32 non prêt, commande ignorée: {cmd!r}")
            return False
        try:
            self._serial.write(cmd.encode('ascii'))
            log.debug(f"Teeces TX: {cmd!r}")
            return True
        except serial.SerialException as e:
            log.error(f"Erreur Teeces32 send: {e}")
            self._ready = False
            return False

    # ------------------------------------------------------------------
    # Commandes préfabriquées
    # ------------------------------------------------------------------

    def random_mode(self) -> bool:
        """Mode animations aléatoires (mode normal)."""
        return self.send_command("0T1\r")

    def all_off(self) -> bool:
        """Éteint toutes les LEDs."""
        return self.send_command("0T20\r")

    def leia_mode(self) -> bool:
        """Mode Leia."""
        return self.send_command("0T6\r")

    def psi_random(self) -> bool:
        """PSI animations aléatoires."""
        return self.send_command("4S1\r")

    def psi_mode(self, mode: int) -> bool:
        """Contrôle PSI avec mode spécifique. 1=aléatoire, 0=éteint."""
        mode = max(0, int(mode))
        return self.send_command(f"4S{mode}\r")

    def fld_text(self, text: str) -> bool:
        """Texte défilant sur Front Logic Display. Max ~20 chars."""
        text = text[:20].upper()
        return self.send_command(f"1M{text}\r")

    def alert_master_offline(self) -> bool:
        """Alerte visuelle Master hors ligne."""
        return self.send_command("1MMASTER OFFLINE\r")

    def alert_error(self, code: str = "") -> bool:
        """Alerte visuelle erreur."""
        msg = f"ERREUR {code}"[:20] if code else "ERREUR"
        return self.send_command(f"1M{msg}\r")

    def show_version(self, version: str) -> bool:
        """Affiche la version courante sur FLD."""
        return self.fld_text(f"VER {version}")
