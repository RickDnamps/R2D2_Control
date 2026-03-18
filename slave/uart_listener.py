"""
Slave UART Listener.
Lit le bus UART depuis le Master et dispatche les commandes.
- H → watchdog feed + ACK
- M → propulsion (VESC)
- D → moteur dôme DC
- SRV → servos body
- S → audio
- V → version sync
- DISP → écran RP2040
- REBOOT → reboot Slave
"""

import logging
import threading
import time
import os
import sys

import serial

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.uart_protocol import parse_msg, build_msg

log = logging.getLogger(__name__)

MAX_INVALID_CRC_BEFORE_ALERT = 3
_MAX_BUFFER = 4096


class UARTListener:
    def __init__(self, port: str, baud: int):
        self._port = port
        self._baud = baud
        self._serial: serial.Serial | None = None
        self._running = False
        self._lock = threading.Lock()
        self._callbacks: dict[str, list] = {}
        self._invalid_crc_count = 0

    def setup(self) -> bool:
        try:
            self._serial = serial.Serial(self._port, self._baud, timeout=0.1)
            log.info(f"UART Slave ouvert: {self._port} @ {self._baud}")
            return True
        except serial.SerialException as e:
            log.error(f"Impossible d'ouvrir UART {self._port}: {e}")
            return False

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._read_loop, name="uart-slave-rx", daemon=True).start()
        log.info("UARTListener démarré")

    def stop(self) -> None:
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()

    def send(self, msg_type: str, value: str) -> bool:
        """Envoi d'un message vers le Master. Thread-safe."""
        msg = build_msg(msg_type, value)
        try:
            with self._lock:
                if self._serial and self._serial.is_open:
                    self._serial.write(msg.encode('utf-8'))
                    return True
        except serial.SerialException as e:
            log.error(f"Erreur envoi UART Slave: {e}")
        return False

    def register_callback(self, msg_type: str, callback) -> None:
        self._callbacks.setdefault(msg_type, []).append(callback)

    # ------------------------------------------------------------------
    # Thread interne
    # ------------------------------------------------------------------

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
                    log.warning(f"Buffer UART Slave overflow ({len(buffer)} bytes) — reset")
                    buffer = ""
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    self._process_line(line.strip())
            except serial.SerialException as e:
                log.error(f"Erreur lecture UART Slave: {e}")
                time.sleep(1)
            except Exception as e:
                log.error(f"Erreur inattendue read_loop Slave: {e}")

    def _process_line(self, line: str) -> None:
        if not line:
            return
        result = parse_msg(line)
        if result is None:
            self._invalid_crc_count += 1
            if self._invalid_crc_count >= MAX_INVALID_CRC_BEFORE_ALERT:
                log.warning(f"Alerte: {self._invalid_crc_count} messages CRC invalides consécutifs")
            return

        self._invalid_crc_count = 0
        msg_type, value = result
        log.debug(f"UART Slave RX: {msg_type}={value}")

        # Heartbeat: ACK immédiat
        if msg_type == 'H':
            self.send('H', 'OK')

        for cb in self._callbacks.get(msg_type, []):
            try:
                cb(value)
            except Exception as e:
                log.error(f"Erreur callback Slave {msg_type}: {e}")
