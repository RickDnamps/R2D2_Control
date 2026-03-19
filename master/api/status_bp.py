"""
Blueprint API Status — Phase 4.
Remonte l'état système R2-D2 en temps réel.

Endpoints:
  GET  /status              → état complet JSON
  GET  /status/version      → versions Master + Slave
  POST /system/reboot       → reboot Master
  POST /system/reboot_slave → reboot Slave (via UART)
"""

import datetime
import os
import subprocess
import threading
from flask import Blueprint, request, jsonify
import master.registry as reg
from master.app_watchdog import app_watchdog

status_bp = Blueprint('status', __name__)

VERSION_FILE = '/home/artoo/r2d2/VERSION'


def _read_version() -> str:
    try:
        with open(VERSION_FILE, encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return 'unknown'


def _uptime() -> str:
    try:
        with open('/proc/uptime', 'r') as f:
            seconds = float(f.readline().split()[0])
        return str(datetime.timedelta(seconds=int(seconds)))
    except Exception:
        return 'unknown'


def _cpu_temp() -> float | None:
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


@status_bp.get('/status')
def get_status():
    """État complet du système R2-D2."""
    _uart_serial = getattr(reg.uart, '_serial', None)
    uart_ready   = bool(_uart_serial and _uart_serial.is_open
                        and getattr(reg.uart, '_running', False))
    # HB  = heartbeat applicatif App ↔ Master (AppWatchdog)
    # UART = lien série Master ↔ Slave
    heartbeat_ok = app_watchdog.is_connected
    return jsonify({
        'version':      _read_version(),
        'uptime':       _uptime(),
        'temperature':  _cpu_temp(),
        'heartbeat_ok': heartbeat_ok,   # App ↔ Master
        'uart_ready':   uart_ready,     # Master ↔ Slave UART
        'app_hb_age_ms': app_watchdog.last_hb_age_ms,
        'teeces_ready':     bool(reg.teeces     and reg.teeces.is_ready()),
        'vesc_ready':       bool(reg.vesc       and reg.vesc.is_ready()),
        'dome_ready':       bool(reg.dome       and reg.dome.is_ready()),
        'servo_ready':      bool(reg.servo      and reg.servo.is_ready()),
        'dome_servo_ready': bool(reg.dome_servo and reg.dome_servo.is_ready()),
        'scripts_running': reg.engine.list_running() if reg.engine else [],
    })


@status_bp.get('/status/version')
def get_version():
    """Versions Master et Slave."""
    return jsonify({'master': _read_version()})


@status_bp.post('/system/reboot')
def system_reboot():
    """Reboot le Master (Pi dôme)."""
    threading.Thread(
        target=lambda: subprocess.run(['sudo', 'reboot'], check=False),
        daemon=True
    ).start()
    return jsonify({'status': 'rebooting'})


@status_bp.post('/system/reboot_slave')
def system_reboot_slave():
    """Envoie une commande reboot au Slave via UART."""
    if reg.uart:
        reg.uart.send('REBOOT', '1')
        return jsonify({'status': 'ok'})
    return jsonify({'error': 'UART non disponible'}), 503


@status_bp.post('/system/shutdown')
def system_shutdown():
    """Éteint le Master."""
    threading.Thread(
        target=lambda: subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=False),
        daemon=True
    ).start()
    return jsonify({'status': 'shutting_down'})


@status_bp.post('/heartbeat')
def app_heartbeat():
    """
    Heartbeat applicatif — App → Master, toutes les 200ms.
    Si ce heartbeat s'arrête pendant >600ms → arrêt d'urgence (AppWatchdog).
    Endpoint ultra-léger : juste un timestamp update.
    """
    app_watchdog.feed()
    return '', 204   # No Content — réponse minimale


@status_bp.post('/system/estop')
def system_estop():
    """Arrêt d'urgence servos — coupe PWM PCA9685 Master (0x40) + Slave (0x41) via smbus2."""
    # Coupe via drivers actifs si disponibles
    if reg.dome_servo:
        try:
            reg.dome_servo.shutdown()
        except Exception:
            pass
    if reg.servo:
        try:
            reg.servo.shutdown()
        except Exception:
            pass
    # Fallback garanti : estop.py direct via subprocess
    threading.Thread(
        target=lambda: subprocess.run(
            ['python3', '/home/artoo/r2d2/scripts/estop.py'], check=False
        ),
        daemon=True
    ).start()
    return jsonify({'status': 'estop_sent'})
