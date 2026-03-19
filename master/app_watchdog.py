"""
App Watchdog — Heartbeat applicatif App → Master.

L'application (Android / navigateur web) envoie POST /heartbeat toutes les 200ms.
Si aucun heartbeat reçu pendant TIMEOUT secondes après qu'une connexion ait été
établie → arrêt d'urgence complet (propulsion + dôme).

Même principe que le watchdog UART Master→Slave, mais pour la couche applicative.

Protège contre :
  - Crash de l'app Android
  - Fermeture de l'onglet navigateur pendant une action
  - Perte WiFi de l'appareil de contrôle
  - Écran du téléphone éteint (WebView en pause)

Démarrage : app_watchdog.start() dans master/main.py
Alimentation : app_watchdog.feed() dans status_bp.py POST /heartbeat
"""

import logging
import threading
import time

import master.registry as reg
from master.safe_stop import stop_drive, stop_dome

log = logging.getLogger(__name__)

TIMEOUT_S   = 0.6   # 600ms — 3 HB manqués à 200ms = déconnexion
CHECK_HZ    = 0.1   # vérification toutes les 100ms


class AppWatchdog:
    """
    Surveille le heartbeat de l'application de contrôle.
    Si le heartbeat s'arrête après avoir été établi → arrêt d'urgence.
    """

    def __init__(self):
        self._lock          = threading.Lock()
        self._last_hb_time  = 0.0
        self._connected     = False   # True dès le premier HB reçu
        self._triggered     = False   # True après un timeout — reset au prochain HB
        self._running       = False

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="app-wdog").start()
        log.info("AppWatchdog démarré (timeout=%.1fs)", TIMEOUT_S)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def feed(self) -> None:
        """Appelé à chaque heartbeat reçu de l'application."""
        with self._lock:
            self._last_hb_time = time.monotonic()
            if self._triggered:
                log.info("AppWatchdog: connexion rétablie — watchdog réarmé")
                self._triggered = False
            self._connected = True

    @property
    def is_connected(self) -> bool:
        """True si une app envoie activement des heartbeats."""
        with self._lock:
            return self._connected and not self._triggered

    @property
    def last_hb_age_ms(self) -> float:
        """Âge du dernier heartbeat en millisecondes."""
        with self._lock:
            if not self._connected:
                return -1.0
            return (time.monotonic() - self._last_hb_time) * 1000.0

    # ------------------------------------------------------------------
    # Boucle interne
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            time.sleep(CHECK_HZ)
            with self._lock:
                if (not self._connected or
                        self._triggered or
                        time.monotonic() - self._last_hb_time <= TIMEOUT_S):
                    continue
                self._triggered = True
                self._connected = False

            # Hors du lock pour éviter deadlock sur les drivers
            self._emergency_stop()

    def _emergency_stop(self) -> None:
        log.warning(
            "AppWatchdog: heartbeat app perdu (>%.0fms) — arrêt progressif",
            TIMEOUT_S * 1000
        )
        stop_drive()   # ramp proportionnelle — pas de freinage brutal
        stop_dome()


# Singleton global
app_watchdog = AppWatchdog()
