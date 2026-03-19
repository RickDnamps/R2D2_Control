"""
Motion Watchdog — Sécurité contrôleur déconnecté.

Si aucune commande de mouvement (drive ou dome) n'est reçue pendant TIMEOUT secondes
ET que le robot est en mouvement → arrêt automatique via UART.

Protège contre :
  - Perte de connexion WiFi de l'app Android / navigateur
  - Crash de l'interface web
  - Déconnexion réseau pendant une action

Timeout : 800ms — suffisant pour absorber les latences HTTP normales,
          assez court pour stopper le robot rapidement.

Démarrage : motion_watchdog.start() dans master/main.py après UART init.
Alimentation : motion_watchdog.feed_drive(l, r) / feed_dome(s) dans motion_bp.py.
"""

import logging
import threading
import time

import master.registry as reg
from master.safe_stop import stop_drive, stop_dome, cancel_ramp

log = logging.getLogger(__name__)

TIMEOUT_S   = 0.8   # secondes sans commande → arrêt
CHECK_HZ    = 0.1   # intervalle de vérification (100ms)
DEADZONE    = 0.05  # seuil pour considérer "en mouvement"


class MotionWatchdog:
    """
    Watchdog de sécurité : arrête la propulsion et le dôme si le contrôleur
    ne répond plus.
    """

    def __init__(self):
        self._lock            = threading.Lock()
        self._last_drive_time = 0.0
        self._last_dome_time  = 0.0
        self._drive_active    = False
        self._dome_active     = False
        self._running         = False

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="motion-wdog").start()
        log.info("MotionWatchdog démarré (timeout=%.1fs)", TIMEOUT_S)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Alimentation — appelé à chaque commande de mouvement reçue
    # ------------------------------------------------------------------

    def feed_drive(self, left: float, right: float) -> None:
        """Signale une commande drive reçue."""
        cancel_ramp()   # annule tout arrêt progressif en cours
        with self._lock:
            self._last_drive_time = time.monotonic()
            self._drive_active    = abs(left) > DEADZONE or abs(right) > DEADZONE

    def feed_dome(self, speed: float) -> None:
        """Signale une commande dome reçue."""
        with self._lock:
            self._last_dome_time = time.monotonic()
            self._dome_active    = abs(speed) > DEADZONE

    def clear_drive(self) -> None:
        """Signale un stop propulsion explicite (pas un timeout)."""
        with self._lock:
            self._drive_active    = False
            self._last_drive_time = time.monotonic()

    def clear_dome(self) -> None:
        """Signale un stop dôme explicite."""
        with self._lock:
            self._dome_active    = False
            self._last_dome_time = time.monotonic()

    # ------------------------------------------------------------------
    # Boucle interne
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            time.sleep(CHECK_HZ)
            now = time.monotonic()
            with self._lock:
                drive_timeout = (self._drive_active and
                                 now - self._last_drive_time > TIMEOUT_S)
                dome_timeout  = (self._dome_active and
                                 now - self._last_dome_time  > TIMEOUT_S)

            if drive_timeout:
                self._stop_drive()
            if dome_timeout:
                self._stop_dome()

    def _stop_drive(self) -> None:
        with self._lock:
            self._drive_active = False
        log.warning("MotionWatchdog: timeout commande — arrêt progressif propulsion")
        stop_drive()   # ramp proportionnelle à la vitesse courante

    def _stop_dome(self) -> None:
        with self._lock:
            self._dome_active = False
        log.warning("MotionWatchdog: timeout commande — arrêt progressif dôme")
        stop_dome()


# Singleton global
motion_watchdog = MotionWatchdog()
