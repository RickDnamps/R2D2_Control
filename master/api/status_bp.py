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


@status_bp.get('/status')
def get_status():
    """État complet du système R2-D2."""
    heartbeat_ok = True  # Phase 4: brancher sur uart.last_heartbeat_age()
    return jsonify({
        'version':      _read_version(),
        'uptime':       _uptime(),
        'heartbeat_ok': heartbeat_ok,
        'uart_ready':   bool(reg.uart),
        'teeces_ready': bool(reg.teeces and reg.teeces.is_ready()),
        'vesc_ready':   bool(reg.vesc   and reg.vesc.is_ready()),
        'dome_ready':   bool(reg.dome   and reg.dome.is_ready()),
        'servo_ready':  bool(reg.servo  and reg.servo.is_ready()),
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
