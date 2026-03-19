"""
Blueprint API Servo — Phase 4.
Contrôle les servos body (via UART → Slave) et dôme (local Master).

Endpoints body (Slave PCA9685 @ 0x41 via UART):
  POST /servo/body/move          {"name": "body_panel_1", "position": 1.0, "duration": 500}
  POST /servo/body/open          {"name": "body_panel_1"}
  POST /servo/body/close         {"name": "body_panel_1"}
  POST /servo/body/open_all
  POST /servo/body/close_all
  GET  /servo/body/list
  GET  /servo/body/state

Endpoints dôme (Master PCA9685 @ 0x40 direct):
  POST /servo/dome/move          {"name": "dome_panel_1", "position": 1.0, "duration": 500}
  POST /servo/dome/open          {"name": "dome_panel_1"}
  POST /servo/dome/close         {"name": "dome_panel_1"}
  POST /servo/dome/open_all
  POST /servo/dome/close_all
  GET  /servo/dome/list
  GET  /servo/dome/state
"""

from flask import Blueprint, request, jsonify
import master.registry as reg

servo_bp = Blueprint('servo', __name__, url_prefix='/servo')

BODY_SERVOS = [f'body_panel_{i}' for i in range(1, 12)]
DOME_SERVOS = [f'dome_panel_{i}' for i in range(1, 12)]


# ================================================================
# BODY SERVOS (via UART → Slave)
# ================================================================

@servo_bp.get('/body/list')
def body_list():
    return jsonify({'servos': BODY_SERVOS})


@servo_bp.get('/body/state')
def body_state():
    state = reg.servo.state if reg.servo else {}
    return jsonify(state)


@servo_bp.post('/body/move')
def body_move():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    position = float(body.get('position', 0.0))
    duration = int(body.get('duration', 500))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if reg.servo:
        reg.servo.move(name, position, duration)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},{position:.3f},{duration}')
    return jsonify({'status': 'ok', 'name': name, 'position': position})


@servo_bp.post('/body/open')
def body_open():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    duration = int(body.get('duration', 500))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if reg.servo:
        reg.servo.open(name, duration)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},1.000,{duration}')
    return jsonify({'status': 'ok', 'name': name})


@servo_bp.post('/body/close')
def body_close():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    duration = int(body.get('duration', 500))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if reg.servo:
        reg.servo.close(name, duration)
    elif reg.uart:
        reg.uart.send('SRV', f'{name},0.000,{duration}')
    return jsonify({'status': 'ok', 'name': name})


@servo_bp.post('/body/open_all')
def body_open_all():
    duration = int((request.get_json(silent=True) or {}).get('duration', 500))
    if reg.servo:
        reg.servo.open_all(duration)
    return jsonify({'status': 'ok'})


@servo_bp.post('/body/close_all')
def body_close_all():
    duration = int((request.get_json(silent=True) or {}).get('duration', 500))
    if reg.servo:
        reg.servo.close_all(duration)
    return jsonify({'status': 'ok'})


# ================================================================
# DOME SERVOS (direct PCA9685 @ 0x40 sur Master)
# ================================================================

@servo_bp.get('/dome/list')
def dome_list():
    return jsonify({'servos': DOME_SERVOS})


@servo_bp.get('/dome/state')
def dome_state():
    state = reg.dome_servo.state if reg.dome_servo else {}
    return jsonify(state)


@servo_bp.post('/dome/move')
def dome_move():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    position = float(body.get('position', 0.0))
    duration = int(body.get('duration', 500))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if reg.dome_servo:
        reg.dome_servo.move(name, position, duration)
    return jsonify({'status': 'ok', 'name': name, 'position': position})


@servo_bp.post('/dome/open')
def dome_open():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    duration = int(body.get('duration', 500))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    reg.dome_servo.open(name, duration)
    return jsonify({'status': 'ok', 'name': name})


@servo_bp.post('/dome/close')
def dome_close():
    body     = request.get_json(silent=True) or {}
    name     = body.get('name', '')
    duration = int(body.get('duration', 500))
    if not name:
        return jsonify({'error': 'Champ "name" requis'}), 400
    if not reg.dome_servo:
        return jsonify({'error': 'dome_servo driver non prêt — voir logs master'}), 503
    reg.dome_servo.close(name, duration)
    return jsonify({'status': 'ok', 'name': name})


@servo_bp.post('/dome/open_all')
def dome_open_all():
    duration = int((request.get_json(silent=True) or {}).get('duration', 500))
    if reg.dome_servo:
        reg.dome_servo.open_all(duration)
    return jsonify({'status': 'ok'})


@servo_bp.post('/dome/close_all')
def dome_close_all():
    duration = int((request.get_json(silent=True) or {}).get('duration', 500))
    if reg.dome_servo:
        reg.dome_servo.close_all(duration)
    return jsonify({'status': 'ok'})


# ================================================================
# Backward compatibility — ancien /servo/open|close|list|state
# ================================================================

@servo_bp.get('/list')
def servo_list():
    return jsonify({'servos': BODY_SERVOS + DOME_SERVOS})


@servo_bp.get('/state')
def servo_state():
    body_state = reg.servo.state if reg.servo else {}
    dome_state = reg.dome_servo.state if reg.dome_servo else {}
    return jsonify({**body_state, **dome_state})


@servo_bp.post('/open_all')
def servo_open_all():
    duration = int((request.get_json(silent=True) or {}).get('duration', 500))
    if reg.servo:
        reg.servo.open_all(duration)
    if reg.dome_servo:
        reg.dome_servo.open_all(duration)
    return jsonify({'status': 'ok'})


@servo_bp.post('/close_all')
def servo_close_all():
    duration = int((request.get_json(silent=True) or {}).get('duration', 500))
    if reg.servo:
        reg.servo.close_all(duration)
    if reg.dome_servo:
        reg.dome_servo.close_all(duration)
    return jsonify({'status': 'ok'})
