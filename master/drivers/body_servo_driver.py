"""
Master Body Servo Driver — Phase 2.
Envoie les commandes de servos body au Slave via UART (message SRV:).
Le Slave exécute sur le PCA9685 I2C.

Format UART: SRV:NAME,POSITION,DURATION
  NAME     : nom du servo (ex: utility_arm_left)
  POSITION : float [0.0 … 1.0] (0=fermé, 1=ouvert)
  DURATION : int millisecondes

Servos body R2-D2 typiques:
  utility_arm_left   — bras utilitaire gauche
  utility_arm_right  — bras utilitaire droit
  panel_front_top    — panneau avant haut
  panel_front_bottom — panneau avant bas
  panel_rear_top     — panneau arrière haut
  panel_rear_bottom  — panneau arrière bas
  charge_bay         — baie de charge

Activation Phase 2:
  1. Décommenter l'import dans master/main.py
  2. Appeler servo.setup() dans main()
  3. Configurer les canaux PCA9685 dans slave/config/servos.cfg
"""

import logging

log = logging.getLogger(__name__)

# Durée par défaut d'un mouvement servo (ms)
DEFAULT_DURATION_MS = 500

# Catalogue des servos body connus (envoyés via UART → Slave PCA9685 @ 0x41)
KNOWN_SERVOS = {
    'body_panel_1',  'body_panel_2',  'body_panel_3',
    'body_panel_4',  'body_panel_5',  'body_panel_6',
    'body_panel_7',  'body_panel_8',  'body_panel_9',
    'body_panel_10', 'body_panel_11',
}


class BodyServoDriver:
    """
    Couche d'abstraction servos body Master.
    Traduit les commandes haut niveau en messages UART SRV:.
    """

    def __init__(self, uart):
        self._uart = uart
        self._ready = False
        self._positions: dict[str, float] = {}

    def setup(self) -> bool:
        self._ready = True
        log.info(f"BodyServoDriver prêt ({len(KNOWN_SERVOS)} servos connus)")
        return True

    def shutdown(self) -> None:
        self.close_all()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def move(self, name: str, position: float,
             duration_ms: int = DEFAULT_DURATION_MS) -> bool:
        """
        Déplace un servo à une position donnée.

        Parameters
        ----------
        name       : nom du servo
        position   : float [0.0 … 1.0]
        duration_ms: durée du mouvement en ms
        """
        position = max(0.0, min(1.0, position))
        duration_ms = max(0, int(duration_ms))

        if name not in KNOWN_SERVOS:
            log.warning(f"Servo inconnu: {name!r}")

        self._positions[name] = position
        value = f"{name},{position:.3f},{duration_ms}"
        ok = self._uart.send('SRV', value)
        log.debug(f"Servo {name}: {position:.0%} en {duration_ms}ms")
        return ok

    def open(self, name: str, duration_ms: int = DEFAULT_DURATION_MS) -> bool:
        """Ouvre un servo (position 1.0)."""
        return self.move(name, 1.0, duration_ms)

    def close(self, name: str, duration_ms: int = DEFAULT_DURATION_MS) -> bool:
        """Ferme un servo (position 0.0)."""
        return self.move(name, 0.0, duration_ms)

    def open_all(self, duration_ms: int = DEFAULT_DURATION_MS) -> None:
        """Ouvre tous les servos connus."""
        for name in KNOWN_SERVOS:
            self.open(name, duration_ms)

    def close_all(self, duration_ms: int = DEFAULT_DURATION_MS) -> None:
        """Ferme tous les servos connus."""
        for name in KNOWN_SERVOS:
            self.close(name, duration_ms)

    @property
    def state(self) -> dict:
        return dict(self._positions)
