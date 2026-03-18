"""
Blueprint API Settings — Configuration réseau et paramètres R2-D2.

Endpoints:
  GET  /settings              → lecture config actuelle (local.cfg + état NM)
  GET  /settings/wifi/scan    → scan réseaux WiFi disponibles sur wlan1
  POST /settings/wifi         → mise à jour wlan1 (local.cfg + nmcli reconnect)
  POST /settings/hotspot      → mise à jour credentials hotspot wlan0
  POST /settings/config       → mise à jour paramètres généraux (branch, slave, etc.)
"""

import configparser
import logging
import os
import subprocess
from flask import Blueprint, request, jsonify

settings_bp = Blueprint('settings', __name__)
log = logging.getLogger(__name__)

LOCAL_CFG    = '/home/artoo/r2d2/master/config/local.cfg'
INTERNET_CON = 'r2d2-internet'
HOTSPOT_CON  = 'r2d2-hotspot'


# =============================================================================
# Helpers
# =============================================================================

def _read_cfg() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if os.path.exists(LOCAL_CFG):
        cfg.read(LOCAL_CFG)
    return cfg


def _write_key(section: str, key: str, value: str) -> None:
    """Écrit ou met à jour une clé dans local.cfg."""
    cfg = _read_cfg()
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, key, value)
    with open(LOCAL_CFG, 'w', encoding='utf-8') as f:
        cfg.write(f)


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """Exécute une commande, retourne (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, '', 'timeout'
    except Exception as e:
        return 1, '', str(e)


def _nm_field(device: str, field: str) -> str:
    """Lit un champ nmcli pour un device."""
    rc, out, _ = _run(['nmcli', '-g', field, 'device', 'show', device])
    return out if rc == 0 else ''


# =============================================================================
# Endpoints
# =============================================================================

@settings_bp.get('/settings')
def get_settings():
    """Retourne la configuration complète (local.cfg + état réseau)."""
    cfg = _read_cfg()

    # État wlan1
    wlan1_state = _nm_field('wlan1', 'GENERAL.STATE')
    wlan1_conn  = _nm_field('wlan1', 'GENERAL.CONNECTION')
    wlan1_ip    = _nm_field('wlan1', 'IP4.ADDRESS[1]')

    # État wlan0 (hotspot)
    wlan0_state = _nm_field('wlan0', 'GENERAL.STATE')

    return jsonify({
        'wifi': {
            'ssid':       cfg.get('home_wifi', 'ssid',     fallback=''),
            'connected':  '100' in wlan1_state,
            'connection': wlan1_conn,
            'ip':         wlan1_ip.split('/')[0] if wlan1_ip else '',
        },
        'hotspot': {
            'ssid':         cfg.get('hotspot', 'ssid', fallback='R2D2_Control'),
            'password_set': bool(cfg.get('hotspot', 'password', fallback='')),
            'ip':           '192.168.4.1',
            'active':       '100' in wlan0_state,
        },
        'github': {
            'repo_url':          cfg.get('github', 'repo_url',          fallback=''),
            'branch':            cfg.get('github', 'branch',            fallback='main'),
            'auto_pull_on_boot': cfg.getboolean('github', 'auto_pull_on_boot', fallback=True),
        },
        'slave': {
            'host': cfg.get('slave', 'host', fallback='r2-slave.local'),
        },
        'deploy': {
            'button_pin': cfg.getint('deploy', 'button_pin', fallback=17),
        },
    })


@settings_bp.get('/settings/wifi/scan')
def wifi_scan():
    """Scanne les réseaux WiFi disponibles sur wlan1."""
    # Déclencher un rescan (non bloquant, erreur ignorée si wlan1 absent)
    _run(['nmcli', 'device', 'wifi', 'rescan', 'ifname', 'wlan1'], timeout=5)

    rc, out, _ = _run(
        ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', 'ifname', 'wlan1'],
        timeout=10
    )

    networks = []
    if rc == 0:
        for line in out.splitlines():
            # nmcli -t: escape les ':' dans le SSID en '\:'
            # on split depuis la droite pour isoler SIGNAL et SECURITY
            parts = line.rsplit(':', 2)
            if len(parts) == 3:
                ssid     = parts[0].replace('\\:', ':')
                signal   = int(parts[1]) if parts[1].isdigit() else 0
                security = parts[2]
                if ssid:
                    networks.append({'ssid': ssid, 'signal': signal, 'security': security})

        # Dédupliquer (garder le signal le plus fort) et trier
        seen: dict[str, dict] = {}
        for n in networks:
            if n['ssid'] not in seen or n['signal'] > seen[n['ssid']]['signal']:
                seen[n['ssid']] = n
        networks = sorted(seen.values(), key=lambda x: -x['signal'])

    return jsonify({'networks': networks})


@settings_bp.post('/settings/wifi')
def set_wifi():
    """Met à jour les credentials wlan1 et tente la connexion."""
    data = request.get_json() or {}
    ssid     = data.get('ssid', '').strip()
    password = data.get('password', '').strip()

    if not ssid:
        return jsonify({'error': 'SSID requis'}), 400

    # Sauvegarder dans local.cfg
    _write_key('home_wifi', 'ssid', ssid)
    if password:
        _write_key('home_wifi', 'password', password)

    # Reconfigurer NetworkManager
    _run(['nmcli', 'connection', 'delete', INTERNET_CON])

    cmd = ['nmcli', 'connection', 'add',
           'type', 'wifi', 'ifname', 'wlan1',
           'con-name', INTERNET_CON,
           'ssid', ssid,
           'connection.autoconnect', 'yes',
           'connection.autoconnect-priority', '10']
    if password:
        cmd += ['wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password]

    rc, _, err = _run(cmd)
    if rc != 0:
        log.error(f"nmcli add wlan1 failed: {err}")
        return jsonify({'error': f'Erreur nmcli: {err}'}), 500

    rc2, _, _ = _run(['nmcli', 'connection', 'up', INTERNET_CON])
    connected = rc2 == 0

    log.info(f"WiFi wlan1 mis à jour: ssid={ssid}, connected={connected}")
    return jsonify({'status': 'ok', 'connected': connected,
                    'message': 'Connecté ✓' if connected else 'Config sauvegardée — connexion au prochain boot'})


@settings_bp.post('/settings/hotspot')
def set_hotspot():
    """Met à jour les credentials du hotspot wlan0 et redémarre le hotspot."""
    data = request.get_json() or {}
    ssid     = data.get('ssid', '').strip()
    password = data.get('password', '').strip()

    if not ssid:
        return jsonify({'error': 'SSID requis'}), 400
    if password and len(password) < 8:
        return jsonify({'error': 'Mot de passe hotspot : minimum 8 caractères (WPA2)'}), 400

    # Sauvegarder
    _write_key('hotspot', 'ssid', ssid)
    if password:
        _write_key('hotspot', 'password', password)

    # Mettre à jour la connexion NM
    modify_cmd = ['nmcli', 'connection', 'modify', HOTSPOT_CON, 'ssid', ssid]
    if password:
        modify_cmd += ['wifi-sec.psk', password]
    _run(modify_cmd)

    # Redémarrer le hotspot (clients déconnectés puis reconnectés)
    _run(['nmcli', 'connection', 'down', HOTSPOT_CON])
    rc, _, err = _run(['nmcli', 'connection', 'up', HOTSPOT_CON])

    log.info(f"Hotspot mis à jour: ssid={ssid}")
    return jsonify({
        'status': 'ok' if rc == 0 else 'partial',
        'warning': 'Les clients WiFi doivent se reconnecter avec les nouveaux credentials',
    })


@settings_bp.post('/settings/config')
def set_config():
    """Met à jour les paramètres généraux dans local.cfg."""
    data = request.get_json() or {}

    # Clés autorisées (section.clé)
    allowed = {
        'github.branch', 'github.auto_pull_on_boot',
        'slave.host', 'deploy.button_pin',
    }

    updated = []
    for dotkey, value in data.items():
        if dotkey in allowed:
            section, key = dotkey.split('.', 1)
            _write_key(section, key, str(value))
            updated.append(dotkey)

    return jsonify({'status': 'ok', 'updated': updated})
