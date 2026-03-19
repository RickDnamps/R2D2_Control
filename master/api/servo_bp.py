"""
Blueprint API Servo — Phase 4.
Contrôle les servos body (via UART → Slave) et dôme (local Master).

Chaque panneau a son propre angle d'ouverture (open_angle) et de fermeture
(close_angle). La durée envoyée au servo est calculée par :
    duration_ms = angle / 90.0 * ms_90deg

Config dans local.cfg, section [servo_panels] :
    ms_90deg           = 150      # durée moteur pour 90° — global
    dome_panel_1_open  = 70       # angle ouverture panneau 1 dôme
    dome_panel_1_close = 70       # angle fermeture panneau 1 dôme
    body_panel_1_open  = 70
    body_panel_1_close = 70
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
  GET  /servo/settings           → {ms_90deg, panels: {name: {open, close, open_ms, close_ms}}}
  POST /servo/settings           → {ms_90deg, panels: {name: {open, close}}}
"""

import configparser
import os

from flask import Blueprint, request, jsonify
import master.registry as reg

servo_bp = Blueprint('servo', __name__, url_prefix='/servo')

_MAIN_CFG  = '/home/artoo/r2d2/master/config/main.cfg'
_LOCAL_CFG = '/home/artoo/r2d2/master/config/local.cfg'

BODY_SERVOS = [f'body_panel_{i}' for i in range(1, 12)]
DOME_SERVOS = [f'dome_panel_{i}' for i in range(1, 12)]
_ALL_PANELS = DOME_SERVOS + BODY_SERVOS

_DEFAULT_OPEN  = 70
_DEFAULT_CLOSE = 70
_DEFAULT_MS90  = 150


# ================================================================
# Helpers config per-panel
# ================================================================

def _read_panels_cfg() -> dict:
    """
    Retourne {'ms_90deg': int, 'panels': {name: {'open': int, 'close': int,
                                                  'open_ms': int, 'close_ms': int}}}
    """
    cfg = configparser.ConfigParser()
    cfg.read([_MAIN_CFG, _LOCAL_CFG])
    ms90 = max(50, cfg.getint('servo_panels', 'ms_90deg', fallback=_DEFAULT_MS90))
    panels = {}
    for name in _ALL_PANELS:
        open_a  = max(0, min(90, cfg.getint('servo_panels', f'{name}_open',  fallback=_DEFAULT_OPEN)))
        close_a = max(0, min(90, cfg.getint('servo_panels', f'{name}_close', fallback=_DEFAULT_CLOSE)))
        panels[name] = {
            'open':     open_a,
            'close':    close_a,
            'open_ms':  max(50, int(open_a  / 90.0 * ms90)),
            'close_ms': max(50, int(close_a / 90.0 * ms90)),
        }
    return {'ms_90deg': ms90, 'panels': panels}


def _write_panels_cfg(ms90: int, panels: dict) -> None:
    cfg = configparser.ConfigParser()
    if os.path.exists(_LOCAL_CFG):
        cfg.read(_LOCAL_CFG)
    if not cfg.has_section('servo_panels'):
        cfg.add_section('servo_panels')
    cfg.set('servo_panels', 'ms_90deg', str(ms90))
    for name, vals in panels.items():
        if name not in _ALL_PANELS:
            continue
        if 'open'  in vals:
            cfg.set('servo_panels', f'{name}_open',  str(max(0, min(90, int(vals['open'])))))
        if 'close' in vals:
            cfg.set('servo_panels', f'{name}_close', str(max(0, min(90, int(vals['close'])))))
    with open(_LOCAL_CFG, 'w', encoding='utf-8') as f:
        cfg.write(f)


def _panel_ms(name: str, direction: str, cfg: dict) -> int:
    panel = cfg['panels'].get(name, {})
    key   = 'open_ms' if direction == 'open' else 'close_ms'
    return panel.get(key, max(50, int((_DEFAULT_OPEN / 90.0) * cfg['ms_90deg'])))


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
    cfg      = _read_panels_cfg()
    duration = int(body.get('duration') or _panel_ms(name, 'open' if position >= 0.5 else 'close', cfg))
    if reg.servo:
        reg.servo.move(name, position, duration)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},{position:.3f},{duration}')
    return jsonify({'status': 'ok', 'name': name, 'position': position})


@servo_bp.post('/body/open')
def body_open():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    cfg      = _read_panels_cfg()
    duration = int(body.get('duration') or _panel_ms(name, 'open', cfg))
    if reg.servo:
        reg.servo.open(name, duration)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},1.000,{duration}')
    return jsonify({'status': 'ok', 'name': name, 'duration': duration})


@servo_bp.post('/body/close')
def body_close():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    cfg      = _read_panels_cfg()
    duration = int(body.get('duration') or _panel_ms(name, 'close', cfg))
    if reg.servo:
        reg.servo.close(name, duration)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},0.000,{duration}')
    return jsonify({'status': 'ok', 'name': name, 'duration': duration})


@servo_bp.post('/body/open_all')
def body_open_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        dur = _panel_ms(name, 'open', cfg)
        if reg.servo:
            reg.servo.open(name, dur)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},1.000,{dur}')
    return jsonify({'status': 'ok'})


@servo_bp.post('/body/close_all')
def body_close_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        dur = _panel_ms(name, 'close', cfg)
        if reg.servo:
            reg.servo.close(name, dur)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},0.000,{dur}')
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
    cfg      = _read_panels_cfg()
    duration = int(body.get('duration') or _panel_ms(name, 'open' if position >= 0.5 else 'close', cfg))
    reg.dome_servo.move(name, position, duration)
    return jsonify({'status': 'ok', 'name': name, 'position': position})


@servo_bp.post('/dome/open')
def dome_open():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    cfg      = _read_panels_cfg()
    duration = int(body.get('duration') or _panel_ms(name, 'open', cfg))
    reg.dome_servo.open(name, duration)
    return jsonify({'status': 'ok', 'name': name, 'duration': duration})


@servo_bp.post('/dome/close')
def dome_close():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    cfg      = _read_panels_cfg()
    duration = int(body.get('duration') or _panel_ms(name, 'close', cfg))
    reg.dome_servo.close(name, duration)
    return jsonify({'status': 'ok', 'name': name, 'duration': duration})


@servo_bp.post('/dome/open_all')
def dome_open_all():
    if not reg.dome_servo:
        return jsonify({'status': 'ok'})
    cfg = _read_panels_cfg()
    for name in DOME_SERVOS:
        reg.dome_servo.open(name, _panel_ms(name, 'open', cfg))
    return jsonify({'status': 'ok'})


@servo_bp.post('/dome/close_all')
def dome_close_all():
    if not reg.dome_servo:
        return jsonify({'status': 'ok'})
    cfg = _read_panels_cfg()
    for name in DOME_SERVOS:
        reg.dome_servo.close(name, _panel_ms(name, 'close', cfg))
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
        dur = _panel_ms(name, 'open', cfg)
        if reg.servo:
            reg.servo.open(name, dur)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},1.000,{dur}')
    if reg.dome_servo:
        for name in DOME_SERVOS:
            reg.dome_servo.open(name, _panel_ms(name, 'open', cfg))
    return jsonify({'status': 'ok'})


@servo_bp.post('/close_all')
def servo_close_all():
    cfg = _read_panels_cfg()
    for name in BODY_SERVOS:
        dur = _panel_ms(name, 'close', cfg)
        if reg.servo:
            reg.servo.close(name, dur)
        elif reg.uart:
            reg.uart.send('SRV', f'{name},0.000,{dur}')
    if reg.dome_servo:
        for name in DOME_SERVOS:
            reg.dome_servo.close(name, _panel_ms(name, 'close', cfg))
    return jsonify({'status': 'ok'})


# ================================================================
# Calibration per-panel
# ================================================================

@servo_bp.get('/settings')
def servo_settings_get():
    return jsonify(_read_panels_cfg())


@servo_bp.post('/settings')
def servo_settings_save():
    data  = request.get_json(silent=True) or {}
    ms90  = max(50, min(2000, int(data.get('ms_90deg', _DEFAULT_MS90))))
    panels = {}
    for name, vals in (data.get('panels') or {}).items():
        if name in _ALL_PANELS and isinstance(vals, dict):
            panels[name] = {
                'open':  max(0, min(90, int(vals.get('open',  _DEFAULT_OPEN)))),
                'close': max(0, min(90, int(vals.get('close', _DEFAULT_CLOSE)))),
            }
    _write_panels_cfg(ms90, panels)
    return jsonify(_read_panels_cfg())
