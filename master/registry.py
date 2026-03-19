"""
Registre des contrôleurs actifs — injection de dépendances pour Flask.
Les blueprints accèdent aux drivers via ce module.
Initialisé dans master/main.py avant le démarrage de Flask.
"""

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
