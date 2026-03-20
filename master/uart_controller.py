"""
Master UART Controller.
- Envoie heartbeat H:1:CS toutes les 200ms (CS = checksum somme mod 256)
- Lit les réponses du Slave et dispatche via callbacks
- Alerte si 3 checksums invalides consécutifs sur heartbeat
"""

import logging
import threading
import time
import configparser
import serial
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.uart_protocol import build_msg, parse_msg, HEARTBEAT_INTERVAL_MS

log = logging.getLogger(__name__)

MAX_INVALID_CRC_BEFORE_ALERT = 3
_MAX_BUFFER = 4096


class UARTController:
    def __init__(self, cfg: configparser.ConfigParser):
        self._port = cfg.get('master', 'uart_port')
        self._baud = cfg.getint('master', 'uart_baud')
        self._heartbeat_interval = cfg.getint('master', 'heartbeat_interval_ms') / 1000.0
        self._serial: serial.Serial | None = None
        self._running = False
        self._lock = threading.Lock()
        self._callbacks: dict[str, list] = {}
        self._invalid_crc_count = 0
        self._heartbeat_invalid_crc_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setup(self) -> bool:
        try:
            self._serial = serial.Serial(
                self._port, self._baud,
                timeout=0.1,
                exclusive=True,
                rtscts=False,
                dsrdtr=False
            )
            log.info(f"UART ouvert: {self._port} @ {self._baud}")
            return True
        except serial.SerialException as e:
            log.error(f"Impossible d'ouvrir UART {self._port}: {e}")
            return False

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._heartbeat_loop, name="uart-hb", daemon=True).start()
        threading.Thread(target=self._read_loop, name="uart-rx", daemon=True).start()
        log.info("UARTController démarré")

    def stop(self) -> None:
        self._running = False
        time.sleep(0.3)
        if self._serial and self._serial.is_open:
            self._serial.close()
        log.info("UARTController arrêté")

    def send(self, msg_type: str, value: str) -> bool:
        """Envoie un message avec CRC. Thread-safe."""
        msg = build_msg(msg_type, value)
        try:
            with self._lock:
                if self._serial and self._serial.is_open:
                    self._serial.write(msg.encode('utf-8'))
                    return True
        except serial.SerialException as e:
            log.error(f"Erreur envoi UART: {e}")
        return False

    def register_callback(self, msg_type: str, callback) -> None:
        """Enregistre un callback pour un type de message reçu."""
        self._callbacks.setdefault(msg_type, []).append(callback)

    # ------------------------------------------------------------------
    # Threads internes
    # ------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        while self._running:
            start = time.monotonic()
            ok = self.send('H', '1')
            if not ok:
                log.warning("Echec envoi heartbeat")
            elapsed = time.monotonic() - start
            sleep_time = self._heartbeat_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _read_loop(self) -> None:
        buffer = ""
        while self._running:
            try:
                if not self._serial or not self._serial.is_open:
                    time.sleep(0.1)
                    continue
                data = self._serial.read(256)
                if not data:
                    continue
                buffer += data.decode('utf-8', errors='replace')
                if len(buffer) > _MAX_BUFFER:
                    log.warning(f"Buffer UART overflow ({len(buffer)} bytes) — reset")
                    buffer = ""
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    self._process_line(line)
            except serial.SerialException as e:
                log.error(f"Erreur lecture UART: {e}")
                time.sleep(1)
            except Exception as e:
                log.error(f"Erreur inattendue read_loop: {e}")

    def _process_line(self, line: str) -> None:
        result = parse_msg(line)
        if result is None:
            self._invalid_crc_count += 1
            # Heartbeat checksum invalide = bus bruité (parasites moteurs / Tobsun)
            if line.startswith('H:'):
                self._heartbeat_invalid_crc_count += 1
                if self._heartbeat_invalid_crc_count >= MAX_INVALID_CRC_BEFORE_ALERT:
                    log.warning(
                        f"Bus UART bruité: {self._heartbeat_invalid_crc_count} "
                        "heartbeats checksum invalides consécutifs"
                    )
            if self._invalid_crc_count >= MAX_INVALID_CRC_BEFORE_ALERT:
                log.warning(f"Alerte: {self._invalid_crc_count} messages checksum invalides consécutifs")
            return

        self._invalid_crc_count = 0
        self._heartbeat_invalid_crc_count = 0
        msg_type, value = result
        log.debug(f"UART RX: {msg_type}={value}")

        for cb in self._callbacks.get(msg_type, []):
            try:
                cb(value)
            except Exception as e:
                log.error(f"Erreur callback {msg_type}: {e}")
