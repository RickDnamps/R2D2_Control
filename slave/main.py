"""
R2-D2 Slave — Point d'entrée.
Tourne sur Raspberry Pi 4B 2GB (corps).

Séquence de boot:
1. Init display RP2040 — démarre séquence diagnostic (BOOT:START)
2. Init UART listener  → DISP:BOOT:OK:UART  ou FAIL
3. Init Watchdog (prioritaire — sécurité)
4. Init Audio          → DISP:BOOT:OK:AUDIO ou FAIL
5. Phase 2: Init VESC L/R, Dome, Servos → DISP:BOOT:OK/FAIL pour chaque
6. Vérification version avec Master
7. Si tout OK → DISP:READY (écran vert 3s puis PRET)
"""

import logging
import signal
import subprocess
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from slave.uart_listener import UARTListener
from slave.watchdog import WatchdogController
from slave.version_check import VersionChecker
from slave.drivers.display_driver import DisplayDriver
from slave.drivers.audio_driver   import AudioDriver

# ---- Phase 2 — Décommenter pour activer ----
# from slave.drivers.vesc_driver        import VescDriver
# from slave.drivers.body_servo_driver  import BodyServoDriver
# from slave.drivers.dome_motor_driver  import DomeMotorDriver  # à créer Phase 2

UART_PORT = "/dev/ttyAMA0"
UART_BAUD = 115200
LOG_LEVEL = "INFO"
VERSION_FILE = "/home/artoo/r2d2/VERSION"


def setup_logging(level_str: str) -> None:
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def emergency_stop_vesc() -> None:
    """Coupe d'urgence VESC — appelée par le watchdog."""
    log = logging.getLogger("watchdog.stop")
    log.error("COUPURE VESC — watchdog timeout")
    # Phase 2: vesc_g.stop() + vesc_d.stop()


def resume_vesc() -> None:
    """Réactivation VESC après retour heartbeat."""
    log = logging.getLogger("watchdog.resume")
    log.info("Réactivation VESC — heartbeat repris")
    # Phase 2: vesc_g.resume() + vesc_d.resume()


def handle_reboot(value: str) -> None:
    """Commande REBOOT reçue du Master — exécuté dans un thread pour ne pas bloquer l'UART."""
    logging.getLogger(__name__).info("Commande REBOOT reçue — reboot dans 3s")
    def _do_reboot():
        time.sleep(3)
        subprocess.run(['sudo', 'reboot'], check=False)
    threading.Thread(target=_do_reboot, daemon=True).start()


def main() -> None:
    setup_logging(LOG_LEVEL)
    log = logging.getLogger(__name__)
    log.info("=== R2-D2 Slave démarrage ===")

    # ------------------------------------------------------------------
    # Écran diagnostic RP2040 — démarre la séquence de boot
    # ------------------------------------------------------------------
    display = DisplayDriver()
    if not display.setup():
        log.warning("DisplayDriver indisponible — mode dégradé affichage")

    display.boot_start()   # RP2040 : reset tous les items → orange

    # ------------------------------------------------------------------
    # UART Listener — connexion au Master via slipring
    # ------------------------------------------------------------------
    display.boot_item('UART')
    uart = UARTListener(UART_PORT, UART_BAUD)
    if not uart.setup():
        log.error("UART init échoué — arrêt")
        display.boot_fail('UART')
        display.error("UART_ERROR")
        sys.exit(1)
    display.boot_ok('UART')

    # ------------------------------------------------------------------
    # Watchdog — CRITIQUE, démarrer immédiatement après UART
    # ------------------------------------------------------------------
    watchdog = WatchdogController()
    watchdog.register_stop_callback(emergency_stop_vesc)
    watchdog.register_resume_callback(resume_vesc)
    watchdog.start()

    uart.register_callback('H',      lambda v: watchdog.feed())
    uart.register_callback('REBOOT', handle_reboot)
    uart.register_callback('DISP',   lambda v: display.send_raw(f"DISP:{v}"))

    # ------------------------------------------------------------------
    # Audio — jack 3.5mm natif Pi 4B
    # ------------------------------------------------------------------
    display.boot_item('AUDIO')
    audio = AudioDriver()
    if audio.setup():
        uart.register_callback('S', audio.handle_uart)
        display.boot_ok('AUDIO')
    else:
        log.warning("AudioDriver indisponible — son désactivé")
        display.boot_fail('AUDIO')

    # ------------------------------------------------------------------
    # Phase 2 — VESC Gauche /dev/ttyACM0
    # ------------------------------------------------------------------
    # display.boot_item('VESC_G')
    # vesc_g = VescDriver(port='/dev/ttyACM0')
    # if vesc_g.setup():
    #     uart.register_callback('M', vesc_g.handle_uart)
    #     watchdog.register_stop_callback(vesc_g.stop)
    #     display.boot_ok('VESC_G')
    # else:
    #     log.warning("VESC Gauche indisponible")
    #     display.boot_fail('VESC_G')

    # ------------------------------------------------------------------
    # Phase 2 — VESC Droite /dev/ttyACM1
    # ------------------------------------------------------------------
    # display.boot_item('VESC_D')
    # vesc_d = VescDriver(port='/dev/ttyACM1')
    # if vesc_d.setup():
    #     display.boot_ok('VESC_D')
    # else:
    #     log.warning("VESC Droite indisponible")
    #     display.boot_fail('VESC_D')

    # ------------------------------------------------------------------
    # Phase 2 — Moteur dôme DC (Motor Driver HAT I2C 0x40)
    # ------------------------------------------------------------------
    # display.boot_item('DOME')
    # dome = DomeMotorDriver()
    # if dome.setup():
    #     uart.register_callback('D', dome.handle_uart)
    #     display.boot_ok('DOME')
    # else:
    #     log.warning("DomeMotorDriver indisponible")
    #     display.boot_fail('DOME')

    # ------------------------------------------------------------------
    # Phase 2 — Servos body (PCA9685 I2C 0x41)
    # ------------------------------------------------------------------
    # display.boot_item('SERVOS')
    # servo = BodyServoDriver()
    # if servo.setup():
    #     uart.register_callback('SRV', servo.handle_uart)
    #     display.boot_ok('SERVOS')
    # else:
    #     log.warning("BodyServoDriver indisponible")
    #     display.boot_fail('SERVOS')

    # ------------------------------------------------------------------
    # Démarrer UART listener (thread)
    # ------------------------------------------------------------------
    uart.start()

    # ------------------------------------------------------------------
    # Vérification version avec Master (affiche syncing sur RP2040)
    # ------------------------------------------------------------------
    checker = VersionChecker(uart, display)
    degraded = not checker.run()
    if degraded:
        log.warning("Mode dégradé — application démarrée avec version locale")
    else:
        log.info("Version validée — démarrage normal")

    log.info("Slave opérationnel")

    # ------------------------------------------------------------------
    # Gestion arrêt propre
    # ------------------------------------------------------------------
    def shutdown(sig, frame):
        log.info("Signal arrêt reçu")
        watchdog.stop()
        uart.stop()
        audio.shutdown()
        # Phase 2:
        # if vesc_g.is_ready():  vesc_g.shutdown()
        # if vesc_d.is_ready():  vesc_d.shutdown()
        # if dome.is_ready():    dome.shutdown()
        # if servo.is_ready():   servo.shutdown()
        display.shutdown()
        log.info("Slave arrêté proprement")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    signal.pause()


if __name__ == "__main__":
    main()
