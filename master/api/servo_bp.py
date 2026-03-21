"""
Blueprint API Servo — Phase 4 (MG90S 180°).
Contrôle les servos body (via UART → Slave) et dôme (local Master).

Chaque panneau a son propre angle d'ouverture (open_angle) et de fermeture
(close_angle). Les angles sont passés directement aux drivers — plus de calcul
de durée (SG90 CR legacy supprimé).

Config dans local.cfg, section [servo_panels] :
    dome_panel_1_open  = 110      # angle ouverture (10–170°)
    dome_panel_1_close = 20       # angle fermeture (10–170°)
    body_panel_1_open  = 110
    body_panel_1_close = 20
    ...

Endpoints dôme (Master PCA9685 @ 0x40 direct):
  POST /servo/dome/open          {"name": "dome_panel_1"}
  POST /servo/dome/close         {"name": "dome_panel_1"}
  POST /servo/dome/open_all
  POST /servo/dome/close_all
  GET  /servo/dome/list
  GET  /servo/dome/state

Endpoints body (Slave PCA9685 @ 0x41 via UART):
  POST /servo/body/open          {"name": "body_panel_1"}
  POST /servo/body/close         {"name": "body_panel_1"}
  POST /servo/body/open_all
  POST /servo/body/close_all
  GET  /servo/body/list
  GET  /servo/body/state

Calibration:
  GET  /servo/settings           → {panels: {name: {open, close}}}
  POST /servo/settings           → {panels: {name: {open, close}}}
"""

import configparser
import json
import os
import subprocess

from flask import Blueprint, request, jsonify
import master.registry as reg

servo_bp = Blueprint('servo', __name__, url_prefix='/servo')

_MAIN_CFG          = '/home/artoo/r2d2/master/config/main.cfg'
_LOCAL_CFG         = '/home/artoo/r2d2/master/config/local.cfg'
_DOME_ANGLES_FILE  = '/home/artoo/r2d2/master/config/dome_angles.json'
_SLAVE_ANGLES_FILE = '/home/artoo/r2d2/slave/config/servo_angles.json'
_SLAVE_HOST        = 'artoo@r2-slave.local'

BODY_SERVOS = [f'body_panel_{i}' for i in range(1, 12)]
DOME_SERVOS = [f'dome_panel_{i}' for i in range(1, 12)]
_ALL_PANELS = DOME_SERVOS + BODY_SERVOS

_DEFAULT_OPEN  = 110
_DEFAULT_CLOSE =  20
_DEFAULT_SPEED =  10
_ANGLE_MIN     =  10
_ANGLE_MAX     = 170
_SPEED_MIN     =   1
_SPEED_MAX     =  10


# ================================================================
# Helpers config per-panel
# ================================================================

def _clamp(val: int) -> int:
    return max(_ANGLE_MIN, min(_ANGLE_MAX, val))

def _clamp_speed(val: int) -> int:
    return max(_SPEED_MIN, min(_SPEED_MAX, val))


def _read_panels_cfg() -> dict:
    """
    Retourne {'panels': {name: {'open': int, 'close': int}}}
    """
    cfg = configparser.ConfigParser()
    cfg.read([_MAIN_CFG, _LOCAL_CFG])
    panels = {}
    for name in _ALL_PANELS:
        open_a  = _clamp(cfg.getint('servo_panels', f'{name}_open',  fallback=_DEFAULT_OPEN))
        close_a = _clamp(cfg.getint('servo_panels', f'{name}_close', fallback=_DEFAULT_CLOSE))
        speed   = _clamp_speed(cfg.getint('servo_panels', f'{name}_speed', fallback=_DEFAULT_SPEED))
        panels[name] = {'open': open_a, 'close': close_a, 'speed': speed}
    return {'panels': panels}


def _write_panels_cfg(panels: dict) -> None:
    cfg = configparser.ConfigParser()
    if os.path.exists(_LOCAL_CFG):
        cfg.read(_LOCAL_CFG)
    if not cfg.has_section('servo_panels'):
        cfg.add_section('servo_panels')
    for name, vals in panels.items():
        if name not in _ALL_PANELS:
            continue
        if 'open'  in vals:
            cfg.set('servo_panels', f'{name}_open',  str(_clamp(int(vals['open']))))
        if 'close' in vals:
            cfg.set('servo_panels', f'{name}_close', str(_clamp(int(vals['close']))))
        if 'speed' in vals:
            cfg.set('servo_panels', f'{name}_speed', str(_clamp_speed(int(vals['speed']))))
    with open(_LOCAL_CFG, 'w', encoding='utf-8') as f:
        cfg.write(f)
    # Sync vers fichiers JSON dédiés
    _sync_angles_json(panels)


def _update_angles_file(filepath: str, panels: dict, names: list) -> None:
    """Met à jour un fichier JSON d'angles avec les panneaux fournis."""
    subset = {k: v for k, v in panels.items() if k in names}
    if not subset:
        return
    existing = {}
    if os.path.exists(filepath):
        try:
            with open(filepath) as f:
                existing = json.load(f)
        except Exception:
            pass
    for name, vals in subset.items():
        existing[name] = {
            'open':  _clamp(int(vals.get('open',  existing.get(name, {}).get('open',  110)))),
            'close': _clamp(int(vals.get('close', existing.get(name, {}).get('close',  20)))),
            'speed': _clamp_speed(int(vals.get('speed', existing.get(name, {}).get('speed', 10)))),
        }
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(existing, f, indent=2)


def _sync_angles_json(panels: dict) -> None:
    """Écrit dome_angles.json (Master) et servo_angles.json (Slave via scp)."""
    import logging
    log = logging.getLogger(__name__)
    try:
        _update_angles_file(_DOME_ANGLES_FILE, panels, DOME_SERVOS)
    except Exception as e:
        log.warning("Écriture dome_angles.json échouée: %s", e)
    try:
        _update_angles_file(_SLAVE_ANGLES_FILE, panels, BODY_SERVOS)
        subprocess.run(
            ['scp', _SLAVE_ANGLES_FILE, f'{_SLAVE_HOST}:{_SLAVE_ANGLES_FILE}'],
            timeout=5, check=False, capture_output=True,
        )
    except Exception as e:
        log.warning("Sync servo_angles.json vers Slave échoué: %s", e)


def _panel_angle(name: str, direction: str, panels_cfg: dict) -> int:
    panel = panels_cfg['panels'].get(name, {})
    return panel.get('open' if direction == 'open' else 'close',
                     _DEFAULT_OPEN if direction == 'open' else _DEFAULT_CLOSE)

def _panel_speed(name: str, panels_cfg: dict) -> int:
    return panels_cfg['panels'].get(name, {}).get('speed', _DEFAULT_SPEED)


# ================================================================
# BODY SERVOS (via UART → Slave)
# ================================================================

@servo_bp.get('/body/list')
def body_list():
    return jsonify({'servos': BODY_SERVOS})


@servo_bp.get('/body/state')
def body_state():
    return jsonify(reg.servo.state if reg.servo else {})


@servo_bp.post('/body/move')
def body_move():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    position = float(body.get('position', 0.0))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    cfg         = _read_panels_cfg()
    open_angle  = _panel_angle(name, 'open',  cfg)
    close_angle = _panel_angle(name, 'close', cfg)
    if reg.servo:
        reg.servo.move(name, position, open_angle, close_angle)
    elif reg.uart:
        angle = close_angle + max(0.0, min(1.0, position)) * (open_angle - close_angle)
        reg.uart.send('SRV', f'{name},{angle:.1f}')
    return jsonify({'status': 'ok', 'name': name, 'position': position})


@servo_bp.post('/body/open')
def body_open():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    cfg   = _read_panels_cfg()
    angle = _panel_angle(name, 'open', cfg)
    speed = _panel_speed(name, cfg)
    if reg.servo:
        reg.servo.open(name, angle, speed)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},{angle}')
    return jsonify({'status': 'ok', 'name': name, 'angle': angle})


@servo_bp.post('/body/close')
def body_close():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    cfg   = _read_panels_cfg()
    angle = _panel_angle(name, 'close', cfg)
    speed = _panel_speed(name, cfg)
    if reg.servo:
        reg.servo.close(name, angle, speed)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},{angle}')
    return jsonify({'status': 'ok', 'name': name, 'angle': angle})


@servo_bp.post('/body/open_all')
def body_open_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        angle = _panel_angle(name, 'open', cfg)
        if reg.servo:
            reg.servo.open(name, angle)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},{angle}')
    return jsonify({'status': 'ok'})


@servo_bp.post('/body/close_all')
def body_close_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        angle = _panel_angle(name, 'close', cfg)
        if reg.servo:
            reg.servo.close(name, angle)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},{angle}')
    return jsonify({'status': 'ok'})


# ================================================================
# DOME SERVOS (direct PCA9685 @ 0x40 sur Master)
# ================================================================

@servo_bp.get('/dome/list')
def dome_list():
    return jsonify({'servos': DOME_SERVOS})


@servo_bp.get('/dome/state')
def dome_state():
    return jsonify(reg.dome_servo.state if reg.dome_servo else {})


@servo_bp.post('/dome/move')
def dome_move():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    position = float(body.get('position', 0.0))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    cfg         = _read_panels_cfg()
    open_angle  = _panel_angle(name, 'open',  cfg)
    close_angle = _panel_angle(name, 'close', cfg)
    reg.dome_servo.move(name, position, open_angle, close_angle)
    return jsonify({'status': 'ok', 'name': name, 'position': position})


@servo_bp.post('/dome/open')
def dome_open():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    cfg   = _read_panels_cfg()
    angle = _panel_angle(name, 'open', cfg)
    speed = _panel_speed(name, cfg)
    reg.dome_servo.open(name, angle, speed)
    return jsonify({'status': 'ok', 'name': name, 'angle': angle})


@servo_bp.post('/dome/close')
def dome_close():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    cfg   = _read_panels_cfg()
    angle = _panel_angle(name, 'close', cfg)
    speed = _panel_speed(name, cfg)
    reg.dome_servo.close(name, angle, speed)
    return jsonify({'status': 'ok', 'name': name, 'angle': angle})


@servo_bp.post('/dome/open_all')
def dome_open_all():
    if not reg.dome_servo:
        return jsonify({'status': 'ok'})
    cfg = _read_panels_cfg()
    for name in DOME_SERVOS:
        reg.dome_servo.open(name, _panel_angle(name, 'open', cfg))
    return jsonify({'status': 'ok'})


@servo_bp.post('/dome/close_all')
def dome_close_all():
    if not reg.dome_servo:
        return jsonify({'status': 'ok'})
    cfg = _read_panels_cfg()
    for name in DOME_SERVOS:
        reg.dome_servo.close(name, _panel_angle(name, 'close', cfg))
    return jsonify({'status': 'ok'})


# ================================================================
# Backward compat — /servo/open_all|close_all (script_bp, anciens appels)
# ================================================================

@servo_bp.get('/list')
def servo_list():
    return jsonify({'servos': BODY_SERVOS + DOME_SERVOS})


@servo_bp.get('/state')
def servo_state():
    body_st = reg.servo.state      if reg.servo      else {}
    dome_st = reg.dome_servo.state if reg.dome_servo else {}
    return jsonify({**body_st, **dome_st})


@servo_bp.post('/open_all')
def servo_open_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        angle = _panel_angle(name, 'open', cfg)
        if reg.servo:
            reg.servo.open(name, angle)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},{angle}')
    if reg.dome_servo:
        for name in DOME_SERVOS:
            reg.dome_servo.open(name, _panel_angle(name, 'open', cfg))
    return jsonify({'status': 'ok'})


@servo_bp.post('/close_all')
def servo_close_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        angle = _panel_angle(name, 'close', cfg)
        if reg.servo:
            reg.servo.close(name, angle)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},{angle}')
    if reg.dome_servo:
        for name in DOME_SERVOS:
            reg.dome_servo.close(name, _panel_angle(name, 'close', cfg))
    return jsonify({'status': 'ok'})


# ================================================================
# Calibration per-panel
# ================================================================

@servo_bp.get('/settings')
def servo_settings_get():
    return jsonify(_read_panels_cfg())


@servo_bp.post('/settings')
def servo_settings_save():
    data   = request.get_json(silent=True) or {}
    panels = {}
    for name, vals in (data.get('panels') or {}).items():
        if name in _ALL_PANELS and isinstance(vals, dict):
            panels[name] = {
                'open':  _clamp(int(vals.get('open',  _DEFAULT_OPEN))),
                'close': _clamp(int(vals.get('close', _DEFAULT_CLOSE))),
                'speed': _clamp_speed(int(vals.get('speed', _DEFAULT_SPEED))),
            }
    _write_panels_cfg(panels)
    return jsonify(_read_panels_cfg())
