"""
WiFi Watchdog — Slave Pi 4B.
Surveille la connectivité au hotspot Master (r2d2-master-hotspot).
Level 1 : jusqu'à 5 tentatives de reconnexion au hotspot.
Level 2 : fallback sur WiFi domestique (netplan-wlan0-mywifi2).
"""

import logging
import subprocess
import threading
import time
import re

log = logging.getLogger(__name__)

# Paramètres
PING_HOST           = "r2-master.local"
PING_RETRIES        = 3          # pings consécutifs avant de déclarer la perte
PING_TIMEOUT_S      = 2          # timeout par ping
CHECK_INTERVAL_S    = 30         # intervalle de vérification normal
L1_WAIT_S           = 15         # attente après nmcli connection up (Level 1)
L1_MAX_ATTEMPTS     = 5          # avant de passer Level 2
L2_WAIT_S           = 20         # attente après connexion home WiFi
HOME_CHECK_S        = 60         # intervalle de vérification en HOME_FALLBACK
AP_PROFILE          = "r2d2-master-hotspot"
HOME_PROFILE        = "netplan-wlan0-mywifi2"
IFACE               = "wlan0"

# États internes
CONNECTED     = "CONNECTED"
SCANNING      = "SCANNING"
HOME_FALLBACK = "HOME_FALLBACK"


class WiFiWatchdog:
    def __init__(self, display) -> None:
        """
        display : instance de DisplayDriver (déjà initialisé).
        Peut être None — les appels display sont silencieusement ignorés.
        """
        self._display  = display
        self._stop_evt = threading.Event()
        self._thread   = threading.Thread(
            target=self._run,
            name='wifi-watchdog',
            daemon=True,
        )

    def start(self) -> None:
        """Lance le thread de surveillance."""
        log.info("WiFiWatchdog démarré")
        self._thread.start()

    def stop(self) -> None:
        """Signal d'arrêt propre — retourne sans attendre la fin du thread."""
        self._stop_evt.set()

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _run(self) -> None:
        state          = CONNECTED
        l1_attempt     = 0

        while not self._stop_evt.is_set():
            # ---- Délai selon l'état courant ----
            wait = HOME_CHECK_S if state == HOME_FALLBACK else CHECK_INTERVAL_S
            if self._stop_evt.wait(wait):
                break  # arrêt demandé

            ping_ok = self._ping_master()

            if state == CONNECTED:
                if not ping_ok:
                    log.warning("WiFiWatchdog: Master injoignable — Level 1 démarre")
                    state      = SCANNING
                    l1_attempt = 0

            if state == SCANNING:
                if ping_ok:
                    log.info("WiFiWatchdog: Master joignable — CONNECTED")
                    state = CONNECTED
                    self._disp_net_ok()
                    continue

                l1_attempt += 1
                log.info(f"WiFiWatchdog: Level 1 tentative {l1_attempt}/{L1_MAX_ATTEMPTS}")
                self._disp_net_scanning(l1_attempt)

                # Déconnecter + reconnecter
                self._nmcli_disconnect()
                self._disp_net_ap(l1_attempt)
                self._nmcli_up(AP_PROFILE)

                # Attendre puis re-pinger
                if self._stop_evt.wait(L1_WAIT_S):
                    break
                if self._ping_master():
                    log.info("WiFiWatchdog: Level 1 reconnexion OK")
                    state = CONNECTED
                    self._disp_net_ok()
                    continue

                # Tentative échouée
                if l1_attempt >= L1_MAX_ATTEMPTS:
                    log.warning("WiFiWatchdog: Level 1 épuisé — Level 2 (home fallback)")
                    state = HOME_FALLBACK
                    self._level2_connect()

            elif state == HOME_FALLBACK:
                if ping_ok:
                    log.info("WiFiWatchdog: Master de retour — reconnexion AP")
                    self._nmcli_up(AP_PROFILE)
                    if self._stop_evt.wait(L1_WAIT_S):
                        break
                    if self._ping_master():
                        state = CONNECTED
                        self._disp_net_ok()
                    else:
                        log.warning("WiFiWatchdog: retour AP échoué — reste HOME_FALLBACK")
                        self._level2_connect()  # re-tenter home

    def _level2_connect(self) -> None:
        """Connecte au WiFi domestique et affiche l'état."""
        self._disp_net_home_try()
        self._nmcli_up(HOME_PROFILE)
        if self._stop_evt.wait(L2_WAIT_S):
            return
        ip = self._get_wlan0_ip()
        if ip:
            log.info(f"WiFiWatchdog: HOME_FALLBACK actif — IP {ip}")
            self._disp_net_home_ok(ip)
        else:
            log.warning("WiFiWatchdog: home WiFi connecté mais pas d'IP")

    # ------------------------------------------------------------------
    # Helpers réseau
    # ------------------------------------------------------------------

    def _ping_master(self) -> bool:
        """Retourne True si au moins un ping réussit parmi PING_RETRIES tentatives."""
        for _ in range(PING_RETRIES):
            if self._stop_evt.is_set():
                return False
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', str(PING_TIMEOUT_S), PING_HOST],
                    capture_output=True,
                    timeout=PING_TIMEOUT_S + 1,
                )
                if result.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    def _nmcli_disconnect(self) -> None:
        try:
            subprocess.run(
                ['nmcli', 'device', 'disconnect', IFACE],
                capture_output=True, timeout=10,
            )
        except Exception as e:
            log.warning(f"nmcli disconnect: {e}")

    def _nmcli_up(self, profile: str) -> None:
        try:
            subprocess.run(
                ['nmcli', 'connection', 'up', profile],
                capture_output=True, timeout=15,
            )
        except Exception as e:
            log.warning(f"nmcli connection up {profile}: {e}")

    def _get_wlan0_ip(self) -> str | None:
        """Retourne l'IP courante de wlan0, ou None."""
        try:
            result = subprocess.run(
                ['ip', '-4', 'addr', 'show', IFACE],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
            return m.group(1) if m else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Helpers display (silencieux si _display est None)
    # ------------------------------------------------------------------

    def _disp_net_scanning(self, attempt: int) -> None:
        if self._display:
            try:
                self._display.net_scanning(attempt)
            except Exception:
                pass

    def _disp_net_ap(self, attempt: int) -> None:
        if self._display:
            try:
                self._display.net_connecting_ap(attempt)
            except Exception:
                pass

    def _disp_net_home_try(self) -> None:
        if self._display:
            try:
                self._display.net_home_try()
            except Exception:
                pass

    def _disp_net_home_ok(self, ip: str) -> None:
        if self._display:
            try:
                self._display.net_home_ok(ip)
            except Exception:
                pass

    def _disp_net_ok(self) -> None:
        if self._display:
            try:
                self._display.net_ok()
            except Exception:
                pass
