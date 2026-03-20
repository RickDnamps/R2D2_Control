"""
Slave VESC Driver — Phase 2.
Reçoit les commandes M: du Master et pilote les VESC de propulsion via pyvesc.
Envoie la télémétrie TL:/TR: au Master toutes les 200ms.

Format UART reçu:
  M:LEFT,RIGHT:CRC      → propulsion différentielle (float [-1.0…+1.0])
  VCFG:scale:0.8:CRC   → power scale (0.1-1.0) — réduit le duty cycle max
  VINV:L:CRC            → inverse le sens du moteur gauche (software)
  VINV:R:CRC            → inverse le sens du moteur droit (software)
  CANSCAN:start:CRC     → lance un scan CAN bus, répond CANFOUND:id1,id2

Format UART envoyé (Slave → Master):
  TL:v_in:temp:curr:rpm:duty:fault:CRC  → télémétrie VESC gauche
  TR:v_in:temp:curr:rpm:duty:fault:CRC  → télémétrie VESC droit

Connexion VESC:
  Mode dual USB (défaut) :
    VESC gauche : /dev/ttyACM0
    VESC droit  : /dev/ttyACM1

Activation Phase 2:
  1. Brancher les VESC sur USB
  2. Décommenter l'import dans slave/main.py
  3. Appeler vesc.setup(uart) dans main()
  4. uart.register_callback('M',    vesc.handle_uart)
  5. uart.register_callback('VCFG', vesc.handle_config_uart)
  6. uart.register_callback('VINV', vesc.handle_invert_uart)
"""

import logging
import threading
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.base_driver import BaseDriver

log = logging.getLogger(__name__)

VESC_PORT_LEFT  = "/dev/ttyACM0"
VESC_PORT_RIGHT = "/dev/ttyACM1"
VESC_BAUD       = 115200

# Limite matérielle de sécurité — ne jamais dépasser
HARDWARE_SPEED_LIMIT = 0.85

# Intervalle télémétrie (secondes)
TELEM_INTERVAL = 0.2   # 5 Hz


class VescDriver(BaseDriver):
    """
    Pilote VESC pour la propulsion différentielle R2-D2.
    - Contrôle moteurs gauche/droit via pyvesc
    - Télémétrie GET_VALUES envoyée au Master via UART toutes les 200ms
    - Power scale et invert configurables depuis le dashboard
    """

    def __init__(self, port_left: str = VESC_PORT_LEFT,
                 port_right: str = VESC_PORT_RIGHT):
        self._port_left   = port_left
        self._port_right  = port_right
        self._serial_left  = None
        self._serial_right = None
        self._pyvesc       = None
        self._ready        = False
        self._uart         = None          # référence UARTListener pour télémétrie
        self._lock         = threading.Lock()

        # Config modifiable depuis le dashboard
        self._power_scale   = 1.0          # 0.1 – 1.0 — réduit duty max
        self._invert_left   = False
        self._invert_right  = False

        self._telem_thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # BaseDriver
    # ------------------------------------------------------------------

    def setup(self, uart=None) -> bool:
        """
        Initialise les connexions VESC.
        uart : UARTListener — optionnel, active l'envoi télémétrie vers Master.
        """
        self._uart = uart
        try:
            import pyvesc
            import serial as _serial

            self._serial_left  = _serial.Serial(self._port_left,  VESC_BAUD, timeout=0.05)
            self._serial_right = _serial.Serial(self._port_right, VESC_BAUD, timeout=0.05)
            self._pyvesc = pyvesc
            self._ready  = True
            log.info(f"VescDriver prêt: L={self._port_left} R={self._port_right}")

            # Démarrer la boucle télémétrie
            self._running = True
            self._telem_thread = threading.Thread(
                target=self._telem_loop, name='vesc-telem', daemon=True
            )
            self._telem_thread.start()
            return True

        except ImportError:
            log.error("pyvesc non installé — sudo pip install pyvesc")
            return False
        except Exception as e:
            log.error(f"Erreur init VESC: {e}")
            return False

    def shutdown(self) -> None:
        self._running = False
        self._stop_motors()
        if self._serial_left  and self._serial_left.is_open:
            self._serial_left.close()
        if self._serial_right and self._serial_right.is_open:
            self._serial_right.close()
        self._ready = False
        log.info("VescDriver arrêté")

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def drive(self, left: float, right: float) -> None:
        """Commande différentielle : left/right ∈ [-1.0, +1.0]."""
        if not self._ready:
            return
        # Appliquer power scale + limites hardware
        lim = HARDWARE_SPEED_LIMIT * self._power_scale
        left  = max(-lim, min(lim, left))
        right = max(-lim, min(lim, right))
        # Inversion software si configurée
        if self._invert_left:  left  = -left
        if self._invert_right: right = -right
        with self._lock:
            self._set_duty(self._serial_left,  left)
            self._set_duty(self._serial_right, right)

    def stop(self) -> None:
        """Arrêt d'urgence — coupe les deux VESC."""
        self._stop_motors()

    # ------------------------------------------------------------------
    # Callbacks UART (appelés par uart_listener)
    # ------------------------------------------------------------------

    def handle_uart(self, value: str) -> None:
        """M:LEFT,RIGHT — commande propulsion."""
        try:
            parts = value.split(',')
            self.drive(float(parts[0]), float(parts[1]))
        except (ValueError, IndexError) as e:
            log.error(f"Message M: invalide {value!r}: {e}")

    def handle_config_uart(self, value: str) -> None:
        """
        VCFG:param:val — configuration depuis le dashboard.
        Paramètres supportés :
          scale:0.8   → power scale (0.1-1.0)
        """
        try:
            parts = value.split(':')
            param, val = parts[0], parts[1]
            if param == 'scale':
                self._power_scale = max(0.1, min(1.0, float(val)))
                log.info(f"VESC power scale: {self._power_scale:.2f}")
            else:
                log.warning(f"Paramètre VCFG inconnu: {param!r}")
        except (ValueError, IndexError) as e:
            log.error(f"Message VCFG invalide {value!r}: {e}")

    def handle_invert_uart(self, value: str) -> None:
        """VINV:L ou VINV:R — inverse le sens d'un moteur."""
        side = value.strip().upper()
        if side == 'L':
            self._invert_left = not self._invert_left
            log.info(f"Invert gauche: {self._invert_left}")
        elif side == 'R':
            self._invert_right = not self._invert_right
            log.info(f"Invert droit: {self._invert_right}")
        else:
            log.warning(f"VINV: côté inconnu {value!r}")

    def handle_can_scan_uart(self, value: str) -> None:
        """
        CANSCAN:start — scanne le CAN bus via VESC 1 USB et envoie CANFOUND: au Master.
        Lancé dans un thread pour ne pas bloquer l'UART listener.
        """
        if not self._ready or not self._serial_left:
            log.warning("CAN scan demandé mais VESC gauche non prêt")
            if self._uart:
                self._uart.send('CANFOUND', 'ERR')
            return

        def _do_scan():
            try:
                from slave.drivers.vesc_can import scan_can_bus
                log.info("Démarrage scan CAN bus...")
                with self._lock:
                    found = scan_can_bus(self._serial_left)
                ids_str = ','.join(str(i) for i in found) if found else ''
                log.info(f"CAN scan terminé: {found}")
                if self._uart:
                    self._uart.send('CANFOUND', ids_str)
            except Exception as e:
                log.error(f"CAN scan échoué: {e}")
                if self._uart:
                    self._uart.send('CANFOUND', 'ERR')

        threading.Thread(target=_do_scan, name='can-scan', daemon=True).start()

    # ------------------------------------------------------------------
    # Télémétrie
    # ------------------------------------------------------------------

    def _get_values(self, ser) -> dict | None:
        """Lit MC_VALUES depuis un VESC via pyvesc. Retourne dict ou None."""
        try:
            req = self._pyvesc.encode_request(self._pyvesc.GetValues)
            ser.reset_input_buffer()
            ser.write(req)
            time.sleep(0.04)   # attendre la réponse
            raw = ser.read(ser.in_waiting or 100)
            if not raw:
                return None
            msg, _ = self._pyvesc.decode(raw)
            if msg is None:
                return None
            return {
                'v_in':    round(float(msg.v_in),              2),
                'temp':    round(float(msg.temp_fet),          1),
                'current': round(float(msg.avg_motor_current), 2),
                'rpm':     int(msg.rpm),
                'duty':    round(float(msg.duty_cycle_now),    3),
                'fault':   int(msg.fault_code),
            }
        except Exception as e:
            log.debug(f"Télémétrie VESC indisponible: {e}")
            return None

    def _telem_loop(self) -> None:
        """Lit la télémétrie des deux VESC et l'envoie au Master via UART."""
        while self._running:
            if self._ready and self._uart:
                with self._lock:
                    vl = self._get_values(self._serial_left)
                    vr = self._get_values(self._serial_right)
                if vl:
                    self._uart.send('TL',
                        f"{vl['v_in']}:{vl['temp']}:{vl['current']}"
                        f":{vl['rpm']}:{vl['duty']}:{vl['fault']}"
                    )
                if vr:
                    self._uart.send('TR',
                        f"{vr['v_in']}:{vr['temp']}:{vr['current']}"
                        f":{vr['rpm']}:{vr['duty']}:{vr['fault']}"
                    )
            time.sleep(TELEM_INTERVAL)

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _set_duty(self, ser, duty: float) -> None:
        try:
            msg = self._pyvesc.encode(self._pyvesc.SetDutyCycle(duty))
            ser.write(msg)
        except Exception as e:
            log.error(f"Erreur commande VESC: {e}")

    def _stop_motors(self) -> None:
        if not self._ready:
            return
        try:
            with self._lock:
                self._set_duty(self._serial_left,  0.0)
                self._set_duty(self._serial_right, 0.0)
        except Exception:
            pass
