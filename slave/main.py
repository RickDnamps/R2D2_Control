"""
R2-D2 Slave — Point d'entrée.
Tourne sur Raspberry Pi 4B 2GB (corps).

Séquence de boot:
1. Init display RP2040 (BOOT)
2. Init UART listener
3. Init Watchdog (prioritaire)
4. Vérification version (V:? → Master)
5. Si version OK → démarrage application principale
6. Si version KO → mode dégradé
"""

import logging
import signal
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from slave.uart_listener import UARTListener
from slave.watchdog import WatchdogController
from slave.version_check import VersionChecker
from slave.drivers.display_driver import DisplayDriver
from slave.drivers.audio_driver import AudioDriver

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
    # Phase 2: vesc_driver.stop() sera appelé ici


def resume_vesc() -> None:
    """Réactivation VESC après retour heartbeat."""
    log = logging.getLogger("watchdog.resume")
    log.info("Réactivation VESC — heartbeat repris")
    # Phase 2: vesc_driver.resume() sera appelé ici


def handle_reboot(value: str) -> None:
    """Commande REBOOT reçue du Master."""
    logging.getLogger(__name__).info("Commande REBOOT reçue — reboot dans 3s")
    time.sleep(3)
    os.system("sudo reboot")


def main() -> None:
    setup_logging(LOG_LEVEL)
    log = logging.getLogger(__name__)
    log.info("=== R2-D2 Slave démarrage ===")

    # Écran diagnostic — boot
    display = DisplayDriver()
    if display.setup():
        display.boot()
    else:
        log.warning("DisplayDriver indisponible — mode dégradé affichage")

    # UART Listener
    uart = UARTListener(UART_PORT, UART_BAUD)
    if not uart.setup():
        log.error("UART init échoué — arrêt")
        if display.is_ready():
            display.error("UART_FAIL")
        sys.exit(1)

    # Watchdog — CRITIQUE, démarrer avant tout
    watchdog = WatchdogController()
    watchdog.register_stop_callback(emergency_stop_vesc)
    watchdog.register_resume_callback(resume_vesc)
    watchdog.start()

    # Heartbeat → feed watchdog
    uart.register_callback('H', lambda v: watchdog.feed())

    # Reboot command
    uart.register_callback('REBOOT', handle_reboot)

    # Display command — transférer commandes DISP: vers le RP2040
    uart.register_callback('DISP', lambda v: display.send_raw(f"DISP:{v}"))

    # Audio
    audio = AudioDriver()
    if audio.setup():
        uart.register_callback('S', audio.handle_uart)
    else:
        log.warning("AudioDriver indisponible — son désactivé")

    # Démarrer UART
    uart.start()

    # Vérification version
    checker = VersionChecker(uart, display)
    degraded = not checker.run()
    if degraded:
        log.warning("Mode dégradé — application démarrée avec version locale")
    else:
        log.info("Version validée — démarrage normal")

    log.info("Slave opérationnel")

    # Gestion arrêt propre
    def shutdown(sig, frame):
        log.info("Signal arrêt reçu")
        watchdog.stop()
        uart.stop()
        audio.shutdown()
        display.shutdown()
        log.info("Slave arrêté proprement")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    signal.pause()


if __name__ == "__main__":
    main()
