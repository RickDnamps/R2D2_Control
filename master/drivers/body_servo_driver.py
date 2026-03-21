"""
Master Body Servo Driver — Phase 2 (MG90S 180°).
Envoie les commandes de servos body au Slave via UART (message SRV:).
Le Slave exécute sur le PCA9685 I2C.

Format UART: SRV:NAME,ANGLE_DEG
  NAME      : nom du servo (ex: body_panel_1)
  ANGLE_DEG : float — angle cible en degrés (10–170°)

Le Slave applique : pulse_us = 500 + (angle_deg / 180.0) * 2000
Le servo MG90S maintient la position — pas de timer d'arrêt.
"""

import logging

log = logging.getLogger(__name__)

DEFAULT_OPEN_DEG  = 110
DEFAULT_CLOSE_DEG =  20

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
        self._uart  = uart
        self._ready = False

    def setup(self) -> bool:
        self._ready = True
        log.info("BodyServoDriver prêt (%d servos connus)", len(KNOWN_SERVOS))
        return True

    def shutdown(self) -> None:
        self.close_all()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def open(self, name: str, angle_deg: float = DEFAULT_OPEN_DEG, speed: int = None) -> bool:
        return self._send(name, angle_deg)

    def close(self, name: str, angle_deg: float = DEFAULT_CLOSE_DEG, speed: int = None) -> bool:
        return self._send(name, angle_deg)

    def move(self, name: str, position: float,
             angle_open: float = DEFAULT_OPEN_DEG,
             angle_close: float = DEFAULT_CLOSE_DEG) -> bool:
        """position 0.0=fermé … 1.0=ouvert — interpolé entre angle_close et angle_open."""
        angle = angle_close + max(0.0, min(1.0, position)) * (angle_open - angle_close)
        return self._send(name, angle)

    def open_all(self, angle_deg: float = DEFAULT_OPEN_DEG) -> None:
        for name in KNOWN_SERVOS:
            self.open(name, angle_deg)

    def close_all(self, angle_deg: float = DEFAULT_CLOSE_DEG) -> None:
        for name in KNOWN_SERVOS:
            self.close(name, angle_deg)

    @property
    def state(self) -> dict:
        return {}

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _send(self, name: str, angle_deg: float) -> bool:
        if not self._ready:
            log.warning("BodyServoDriver non prêt — commande ignorée (%r)", name)
            return False
        if name not in KNOWN_SERVOS:
            log.warning("Servo inconnu: %r", name)
        ok = self._uart.send('SRV', f'{name},{angle_deg:.1f}')
        log.debug("Servo %s → %.1f°", name, angle_deg)
        return ok
