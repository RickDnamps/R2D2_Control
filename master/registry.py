"""
Registre des contrôleurs actifs — injection de dépendances pour Flask.
Les blueprints accèdent aux drivers via ce module.
Initialisé dans master/main.py avant le démarrage de Flask.
"""

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from master.uart_controller      import UARTController
    from master.teeces_controller    import TeecesController
    from master.deploy_controller    import DeployController
    from master.script_engine        import ScriptEngine
    from master.drivers.vesc_driver  import VescDriver
    from master.drivers.dome_motor_driver  import DomeMotorDriver
    from master.drivers.body_servo_driver  import BodyServoDriver
    from master.drivers.dome_servo_driver  import DomeServoDriver

# Ces variables sont assignées dans main.py avant app.run()
uart:        'UARTController | None'    = None
teeces:      'TeecesController | None'  = None
deploy:      'DeployController | None'  = None
engine:      'ScriptEngine | None'      = None
vesc:        'VescDriver | None'        = None
dome:        'DomeMotorDriver | None'   = None
servo:       'BodyServoDriver | None'   = None
dome_servo:  'DomeServoDriver | None'   = None

# Télémétrie VESC — mise à jour par les callbacks TL/TR du Master
# Format: {'v_in': 23.5, 'temp': 35.2, 'current': 8.5, 'rpm': 1200, 'duty': 0.45, 'fault': 0, 'ts': 1234567890.0}
vesc_telem: dict = {'L': None, 'R': None}
vesc_power_scale: float = 1.0

# Résultat du scan CAN bus — mis à jour par callback CANFOUND dans main.py
# None = pas encore de résultat, [] = aucun VESC trouvé, [...] = IDs trouvés
vesc_can_scan_result: list | None = None
vesc_can_scan_event: threading.Event = threading.Event()

# Santé UART Slave — mis à jour par le thread slave-health-poll dans main.py
# None = Slave injoignable ou pas encore pollé
# dict: {'total': N, 'errors': E, 'health_pct': 98.1, 'window_s': 60}
slave_uart_health: dict | None = None
