"""
R2-D2 Master — Point d'entrée.
Tourne sur Raspberry Pi 4B (dôme).

Séquence de boot:
1. Lecture config
2. Init logging
3. git pull si wlan1 disponible
4. Démarrage UARTController + TeecesController + DeployController
5. Phase 2: VescDriver + DomeMotorDriver + BodyServoDriver (décommenter)
6. Phase 3: ScriptEngine (décommenter)
7. Phase 4: API Flask sur port 5000 (décommenter)
"""

import logging
import configparser
import signal
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from master.uart_controller import UARTController
from master.teeces_controller import TeecesController
from master.deploy_controller import DeployController
from master.config.config_loader import load, is_auto_pull_enabled
import master.registry as reg

# ---- Phase 2 — Décommenter pour activer ----
# from master.drivers.vesc_driver        import VescDriver
# from master.drivers.dome_motor_driver  import DomeMotorDriver
from master.drivers.body_servo_driver  import BodyServoDriver
from master.drivers.dome_servo_driver  import DomeServoDriver

# ---- Phase 3 ----
from master.script_engine import ScriptEngine

# ---- Phase 4 — Décommenter pour activer ----
from master.flask_app import create_app
from master.motion_watchdog import motion_watchdog
from master.app_watchdog import app_watchdog

VERSION_FILE = "/home/artoo/r2d2/VERSION"


def setup_logging(level_str: str) -> None:
    from logging.handlers import RotatingFileHandler
    level = getattr(logging, level_str.upper(), logging.INFO)
    fmt = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    root = logging.getLogger()
    root.setLevel(level)
    # Console (journald)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)
    # Fichier rotatif persistant — survit aux reboots, gitignored (debug/)
    log_dir = '/home/artoo/r2d2/debug'
    os.makedirs(log_dir, exist_ok=True)
    fh = RotatingFileHandler(
        os.path.join(log_dir, 'master.log'),
        maxBytes=5 * 1024 * 1024,   # 5 MB par fichier
        backupCount=3,               # master.log + master.log.1/2/3
        encoding='utf-8'
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _start_network_monitor() -> None:
    """Thread daemon — surveille wlan0/wlan1 toutes les 30s et log les changements."""
    import subprocess
    log_net = logging.getLogger('network')

    def _iface_state(iface: str) -> tuple[bool, str]:
        try:
            r = subprocess.run(['ip', 'addr', 'show', iface],
                               capture_output=True, text=True, timeout=3)
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.startswith('inet '):
                    return True, line.split()[1]
            return False, ''
        except Exception:
            return False, ''

    prev: dict[str, bool] = {}

    def _log_initial() -> None:
        for iface in ('wlan0', 'wlan1'):
            up, ip = _iface_state(iface)
            prev[iface] = up
            if up:
                log_net.info("%s connecté au boot — IP: %s", iface, ip)
            else:
                log_net.warning("%s non disponible au boot", iface)

    def _monitor() -> None:
        while True:
            time.sleep(30)
            for iface in ('wlan0', 'wlan1'):
                up, ip = _iface_state(iface)
                if prev.get(iface) != up:
                    if up:
                        log_net.info("%s reconnecté — IP: %s", iface, ip)
                    else:
                        log_net.warning("%s déconnecté !", iface)
                    prev[iface] = up

    _log_initial()
    threading.Thread(target=_monitor, name='network-monitor', daemon=True).start()


def try_git_pull(cfg: configparser.ConfigParser) -> bool:
    """Tentative de git pull au boot si wlan1 connecté et auto_pull activé."""
    import subprocess
    if not is_auto_pull_enabled(cfg):
        logging.info("auto_pull_on_boot désactivé — git pull ignoré")
        return False
    iface = cfg.get('network', 'internet_interface')
    repo = cfg.get('master', 'repo_path')

    try:
        result = subprocess.run(
            ["ip", "addr", "show", iface],
            capture_output=True, text=True, timeout=5
        )
        if "inet " not in result.stdout:
            logging.info(f"{iface} non disponible — git pull ignoré")
            return False
    except Exception:
        return False

    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=repo,
            timeout=30,
            capture_output=True, text=True
        )
        if result.returncode == 0:
            rev = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo, capture_output=True, text=True
            )
            if rev.returncode == 0:
                try:
                    with open(VERSION_FILE, 'w') as f:
                        f.write(rev.stdout.strip())
                except OSError as e:
                    logging.warning(f"Impossible d'écrire VERSION: {e}")
            logging.info("git pull réussi au démarrage")
            return True
        else:
            logging.warning(f"git pull échoué: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        logging.warning("git pull timeout — démarrage sans update")
        return False
    except Exception as e:
        logging.error(f"git pull erreur: {e}")
        return False


def main() -> None:
    cfg = load()
    setup_logging(cfg.get('master', 'log_level', fallback='INFO'))
    log = logging.getLogger(__name__)
    log.info("=== R2-D2 Master démarrage ===")
    _start_network_monitor()

    # Boot: tentative git pull
    try_git_pull(cfg)

    # Init composants Phase 1
    uart   = UARTController(cfg)
    teeces = TeecesController(cfg)
    deploy = DeployController(cfg, uart, teeces)

    # Registre partagé (accessible par Flask blueprints)
    reg.uart   = uart
    reg.teeces = teeces
    reg.deploy = deploy

    # ------------------------------------------------------------------
    # Phase 2 — Drivers propulsion / dôme / servos
    # ------------------------------------------------------------------
    # vesc = VescDriver(uart)
    # dome = DomeMotorDriver(uart)
    # if vesc.setup(): reg.vesc = vesc
    # if dome.setup(): reg.dome = dome

    servo      = BodyServoDriver(uart)
    dome_servo = DomeServoDriver()
    if servo.setup():      reg.servo      = servo
    if dome_servo.setup(): reg.dome_servo = dome_servo

    # ------------------------------------------------------------------
    # Phase 3 — Moteur de scripts
    # ------------------------------------------------------------------
    engine = ScriptEngine(
        uart=uart, teeces=teeces,
        vesc=reg.vesc, dome=reg.dome,
        servo=reg.servo, dome_servo=reg.dome_servo,
    )
    reg.engine = engine

    # Callbacks UART entrants
    def on_heartbeat_ack(value: str) -> None:
        log.debug(f"Heartbeat ACK Slave: {value}")

    def on_telemetry(value: str) -> None:
        log.info(f"Télémétrie Slave: {value}")

    def on_version(value: str) -> None:
        if value == '?':
            try:
                with open(VERSION_FILE) as f:
                    version = f.read().strip()
            except Exception:
                version = "unknown"
            uart.send('V', version)
            log.debug(f"Version demandée par Slave — réponse: {version}")
        else:
            log.info(f"Version Slave reçue: {value}")

    uart.register_callback('H', on_heartbeat_ack)
    uart.register_callback('T', on_telemetry)
    uart.register_callback('V', on_version)

    # Démarrage hardware
    if not uart.setup():
        log.error("UART init échoué — arrêt")
        sys.exit(1)

    if not teeces.setup():
        log.warning("Teeces32 init échoué — mode dégradé (LEDs indisponibles)")

    uart.start()
    teeces.random_mode()
    deploy.start()

    # ------------------------------------------------------------------
    # Phase 4 — Serveur Flask (API REST + Web UI)
    # ------------------------------------------------------------------
    app        = create_app()
    flask_port = cfg.getint('master', 'flask_port', fallback=5000)
    flask_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=flask_port,
                               use_reloader=False, threaded=True),
        name='flask', daemon=True
    )
    flask_thread.start()
    log.info(f"Flask démarré sur port {flask_port}")

    # Watchdogs sécurité — démarrer après Flask
    motion_watchdog.start()   # arrêt moteurs si plus de commande drive (800ms)
    app_watchdog.start()      # arrêt moteurs si heartbeat app absent (600ms)

    log.info("Master opérationnel")

    # Gestion arrêt propre
    def shutdown(sig, frame):
        log.info("Signal arrêt reçu")
        deploy.stop()
        uart.stop()
        teeces.shutdown()
        # Phase 2: if reg.vesc:  reg.vesc.shutdown()
        # Phase 2: if reg.dome:  reg.dome.shutdown()
        if reg.servo:      reg.servo.shutdown()
        if reg.dome_servo: reg.dome_servo.shutdown()
        if reg.engine: reg.engine.stop_all()
        log.info("Master arrêté proprement")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Maintien du processus
    signal.pause()


if __name__ == "__main__":
    main()
