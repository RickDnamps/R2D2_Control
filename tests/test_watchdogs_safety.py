"""
Tests de sécurité — simulation de déconnexions App/Android/UART.

Vérifie les 3 watchdogs sans hardware :
  - AppWatchdog    (600ms) : crash app / perte WiFi contrôleur
  - MotionWatchdog (800ms) : commande drive sans suivi
  - WatchdogController Slave (500ms) : perte heartbeat UART

Usage : python -m pytest tests/test_watchdogs_safety.py -v
"""

import sys
import os
import time
import types
import unittest
from unittest.mock import MagicMock

# ── Mocks sys.modules AVANT tout import du code projet ───────────────────────
# Permet d'importer les watchdogs sans Flask / drivers hardware connectés.

_mock_stop_drive  = MagicMock(name='stop_drive')
_mock_stop_dome   = MagicMock(name='stop_dome')
_mock_cancel_ramp = MagicMock(name='cancel_ramp')

_registry_mod = types.ModuleType('master.registry')
_registry_mod.uart       = None
_registry_mod.vesc       = None
_registry_mod.dome       = None
_registry_mod.dome_servo = None
_registry_mod.servo      = None

_safe_stop_mod = types.ModuleType('master.safe_stop')
_safe_stop_mod.stop_drive  = _mock_stop_drive
_safe_stop_mod.stop_dome   = _mock_stop_dome
_safe_stop_mod.cancel_ramp = _mock_cancel_ramp

# Ne PAS mocker le package 'master' lui-même — laisser Python le résoudre
# comme namespace package. Mocker uniquement les sous-modules à dépendances hardware.
sys.modules.setdefault('master.registry',  _registry_mod)
sys.modules.setdefault('master.safe_stop', _safe_stop_mod)

# Ajouter la racine projet au path Python
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from master.app_watchdog    import AppWatchdog
from master.motion_watchdog import MotionWatchdog

# Slave watchdog — import direct pour éviter conflits de nommage
import importlib.util as _ilu
_slave_spec = _ilu.spec_from_file_location(
    'slave_watchdog',
    os.path.join(_PROJECT_ROOT, 'slave', 'watchdog.py')
)
_slave_mod = _ilu.module_from_spec(_slave_spec)
_slave_spec.loader.exec_module(_slave_mod)
WatchdogController = _slave_mod.WatchdogController


def _reset_mocks():
    _mock_stop_drive.reset_mock()
    _mock_stop_dome.reset_mock()
    _mock_cancel_ramp.reset_mock()


# ─────────────────────────────────────────────────────────────────────────────
# AppWatchdog — perte heartbeat applicatif (Android / navigateur)
# ─────────────────────────────────────────────────────────────────────────────

class TestAppWatchdog(unittest.TestCase):
    """
    Scénario : l'app Android ou le navigateur arrête d'envoyer POST /heartbeat.
    Causes possibles : crash app, WiFi coupé, écran éteint (WebView en pause).
    Attendu : arrêt d'urgence après 600ms.
    """

    def setUp(self):
        _reset_mocks()
        self.wdog = AppWatchdog()
        self.wdog.start()

    def tearDown(self):
        self.wdog.stop()

    def test_initial_not_connected(self):
        """Avant tout heartbeat, is_connected doit être False."""
        self.assertFalse(self.wdog.is_connected)

    def test_first_heartbeat_connects(self):
        """Dès le premier heartbeat, is_connected passe à True."""
        self.wdog.feed()
        self.assertTrue(self.wdog.is_connected)

    def test_no_emergency_stop_without_first_heartbeat(self):
        """
        CRITIQUE : si aucune app ne s'est jamais connectée,
        l'arrêt d'urgence NE doit PAS se déclencher (robot inerte au boot).
        """
        time.sleep(1.0)  # attendre > 600ms timeout
        _mock_stop_drive.assert_not_called()
        _mock_stop_dome.assert_not_called()

    def test_disconnect_triggers_emergency_stop(self):
        """
        CRITIQUE : app connectée → perte WiFi → arrêt d'urgence après 600ms.
        Simule : crash Android / fermeture onglet navigateur.
        """
        self.wdog.feed()
        self.assertTrue(self.wdog.is_connected)

        # Silence — plus aucun heartbeat
        time.sleep(1.0)  # 600ms timeout + 400ms marge

        _mock_stop_drive.assert_called_once()
        _mock_stop_dome.assert_called_once()
        self.assertFalse(self.wdog.is_connected)

    def test_continuous_heartbeats_no_stop(self):
        """
        Heartbeats réguliers (toutes les 150ms < 600ms timeout) → aucun arrêt.
        """
        for _ in range(6):
            self.wdog.feed()
            time.sleep(0.15)

        _mock_stop_drive.assert_not_called()
        _mock_stop_dome.assert_not_called()
        self.assertTrue(self.wdog.is_connected)

    def test_reconnect_rearms_watchdog(self):
        """
        Après un timeout, l'app se reconnecte → is_connected=True.
        Une deuxième déconnexion déclenche à nouveau l'arrêt.
        """
        # Cycle 1 : déconnexion
        self.wdog.feed()
        time.sleep(1.0)
        self.assertFalse(self.wdog.is_connected)

        _reset_mocks()

        # Reconnexion
        self.wdog.feed()
        self.assertTrue(self.wdog.is_connected)

        # Cycle 2 : deuxième déconnexion
        time.sleep(1.0)
        _mock_stop_drive.assert_called_once()

    def test_emergency_stop_triggered_only_once_per_disconnect(self):
        """
        L'arrêt d'urgence se déclenche exactement une fois par déconnexion,
        pas en boucle à chaque cycle watchdog.
        """
        self.wdog.feed()
        time.sleep(2.0)  # attendre 2+ cycles complets

        self.assertEqual(_mock_stop_drive.call_count, 1,
                         "stop_drive() doit être appelé exactement une fois")
        self.assertEqual(_mock_stop_dome.call_count, 1,
                         "stop_dome() doit être appelé exactement une fois")

    def test_hb_age_minus_one_before_first(self):
        """Avant le premier HB, last_hb_age_ms retourne -1 (pas de données)."""
        self.assertEqual(self.wdog.last_hb_age_ms, -1.0)

    def test_hb_age_positive_after_heartbeat(self):
        """Après un HB, l'âge est positif et inférieur au timeout."""
        self.wdog.feed()
        time.sleep(0.1)
        age = self.wdog.last_hb_age_ms
        self.assertGreater(age, 0, "L'âge doit être positif")
        self.assertLess(age, 600, "L'âge ne doit pas dépasser le timeout")


# ─────────────────────────────────────────────────────────────────────────────
# MotionWatchdog — déconnexion pendant un mouvement actif
# ─────────────────────────────────────────────────────────────────────────────

class TestMotionWatchdog(unittest.TestCase):
    """
    Scénario : l'app envoie une commande drive/dôme, puis se déconnecte.
    Attendu : arrêt automatique après 800ms sans nouvelle commande.
    """

    def setUp(self):
        _reset_mocks()
        self.wdog = MotionWatchdog()
        self.wdog.start()

    def tearDown(self):
        self.wdog.stop()

    def test_no_command_no_stop(self):
        """Sans commande drive, aucun arrêt ne doit être déclenché."""
        time.sleep(1.2)
        _mock_stop_drive.assert_not_called()

    def test_drive_timeout_triggers_stop(self):
        """
        CRITIQUE : commande drive reçue, puis silence > 800ms → arrêt propulsion.
        Simule : crash app Android en cours de marche.
        """
        self.wdog.feed_drive(0.5, 0.5)
        time.sleep(1.2)
        _mock_stop_drive.assert_called()

    def test_dome_timeout_triggers_stop(self):
        """
        CRITIQUE : commande dôme active, puis silence > 800ms → arrêt dôme.
        """
        self.wdog.feed_dome(0.3)
        time.sleep(1.2)
        _mock_stop_dome.assert_called()

    def test_continuous_drive_no_stop(self):
        """Commandes drive continues (toutes les 150ms) → aucun arrêt."""
        for _ in range(6):
            self.wdog.feed_drive(0.5, 0.5)
            time.sleep(0.15)
        _mock_stop_drive.assert_not_called()

    def test_explicit_stop_no_watchdog_trigger(self):
        """
        Stop explicite via clear_drive() → le watchdog ne se déclenche pas.
        Le stop vient de l'app, pas d'un timeout.
        """
        self.wdog.feed_drive(0.5, 0.5)
        self.wdog.clear_drive()
        time.sleep(1.2)
        _mock_stop_drive.assert_not_called()

    def test_explicit_dome_stop_no_trigger(self):
        """Stop explicite dôme → pas de trigger watchdog."""
        self.wdog.feed_dome(0.3)
        self.wdog.clear_dome()
        time.sleep(1.2)
        _mock_stop_dome.assert_not_called()

    def test_zero_speed_no_timeout(self):
        """
        Commande drive avec vitesse 0 (dans la deadzone) → pas de timeout.
        Le robot est déjà à l'arrêt.
        """
        self.wdog.feed_drive(0.0, 0.0)
        time.sleep(1.2)
        _mock_stop_drive.assert_not_called()

    def test_cancel_ramp_on_new_drive_command(self):
        """
        Nouvelle commande drive → cancel_ramp() appelé pour interrompre
        tout arrêt progressif en cours (ex: app reconnectée).
        """
        self.wdog.feed_drive(0.5, 0.5)
        _mock_cancel_ramp.assert_called()

    def test_drive_timeout_only_once(self):
        """Timeout propulsion déclenché exactement une fois, pas en boucle."""
        self.wdog.feed_drive(0.8, 0.8)
        time.sleep(2.0)
        self.assertEqual(_mock_stop_drive.call_count, 1)

    def test_dome_drive_independent_timeouts(self):
        """
        Timeout dôme et timeout propulsion sont indépendants.
        Stop propulsion explicite n'affecte pas le timeout dôme.
        """
        self.wdog.feed_drive(0.5, 0.5)
        self.wdog.clear_drive()       # stop propulsion explicite
        self.wdog.feed_dome(0.3)      # dôme actif

        time.sleep(1.2)

        _mock_stop_drive.assert_not_called()   # propulsion : stop explicite
        _mock_stop_dome.assert_called()        # dôme : timeout

    def test_reverse_drive_timeout(self):
        """Commande drive en marche arrière déclenche aussi le timeout."""
        self.wdog.feed_drive(-0.6, -0.6)
        time.sleep(1.2)
        _mock_stop_drive.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# WatchdogController (Slave) — perte heartbeat UART Master→Slave
# ─────────────────────────────────────────────────────────────────────────────

class TestSlaveWatchdog(unittest.TestCase):
    """
    Scénario : le lien UART entre Master et Slave est coupé.
    Causes : câble slipring débranché, crash Master, alimentation dôme perdue.
    Attendu : VESC coupé après 500ms sans heartbeat UART.
    """

    def setUp(self):
        self.stop_cb   = MagicMock(name='stop_callback')
        self.resume_cb = MagicMock(name='resume_callback')
        self.wdog = WatchdogController(timeout_s=0.5)
        self.wdog.register_stop_callback(self.stop_cb)
        self.wdog.register_resume_callback(self.resume_cb)
        self.wdog.start()

    def tearDown(self):
        self.wdog.stop()

    def test_no_immediate_stop_at_startup(self):
        """
        Au démarrage, le watchdog initialise le timer à now().
        Pas de déclenchement immédiat — laisser le temps au Master de booter.
        """
        time.sleep(0.2)
        self.stop_cb.assert_not_called()

    def test_no_hb_triggers_vesc_cutoff(self):
        """
        CRITIQUE : aucun heartbeat UART depuis le démarrage → coupure VESC.
        Simule : câble slipring débranché avant boot, ou Master planté.
        """
        time.sleep(0.8)
        self.stop_cb.assert_called_once()

    def test_regular_hb_prevents_cutoff(self):
        """Heartbeats réguliers (toutes les 150ms < 500ms) → aucune coupure."""
        for _ in range(6):
            self.wdog.feed()
            time.sleep(0.15)
        self.stop_cb.assert_not_called()

    def test_resume_callback_on_uart_recovery(self):
        """
        UART coupé → coupure VESC → UART reprend → réactivation VESC.
        Simule : reconnexion slipring à chaud.
        """
        time.sleep(0.8)  # trigger coupure
        self.stop_cb.assert_called_once()

        # Reprise UART
        self.wdog.feed()
        time.sleep(0.1)
        self.resume_cb.assert_called_once()

    def test_stop_triggered_only_once_per_cutoff(self):
        """
        La coupure VESC se déclenche exactement une fois par timeout,
        pas en boucle (éviter flicker des VESCs).
        """
        time.sleep(1.5)
        self.assertEqual(self.stop_cb.call_count, 1,
                         "stop_callback doit être appelé exactement une fois")

    def test_multiple_disconnect_reconnect_cycles(self):
        """
        Plusieurs cycles déconnexion/reconnexion → chaque déconnexion
        déclenche une coupure, chaque reconnexion déclenche une reprise.
        """
        # Cycle 1 : coupure
        time.sleep(0.8)
        self.assertEqual(self.stop_cb.call_count, 1)

        # Reconnexion
        self.wdog.feed()
        time.sleep(0.1)
        self.assertEqual(self.resume_cb.call_count, 1)

        # Cycle 2 : coupure
        time.sleep(0.8)
        self.assertEqual(self.stop_cb.call_count, 2)

        # Reconnexion 2
        self.wdog.feed()
        time.sleep(0.1)
        self.assertEqual(self.resume_cb.call_count, 2)

    def test_feed_clears_triggered_state(self):
        """Après un trigger, feed() remet triggered à False."""
        time.sleep(0.8)
        self.assertTrue(self.wdog._triggered)
        self.wdog.feed()
        time.sleep(0.1)
        self.assertFalse(self.wdog._triggered)

    def test_callback_exception_does_not_crash_watchdog(self):
        """
        Un callback qui lève une exception ne doit pas crasher le watchdog.
        Le watchdog doit rester fonctionnel.
        """
        crash_cb = MagicMock(side_effect=RuntimeError("driver crash simulé"))
        safe_cb  = MagicMock()

        wdog = WatchdogController(timeout_s=0.3)
        wdog.register_stop_callback(crash_cb)
        wdog.register_stop_callback(safe_cb)
        wdog.start()

        time.sleep(0.6)

        crash_cb.assert_called()
        safe_cb.assert_called()   # doit être appelé malgré l'exception précédente
        wdog.stop()

    def test_custom_timeout_respected(self):
        """Le timeout personnalisé est bien respecté."""
        fast_wdog = WatchdogController(timeout_s=0.2)
        fast_cb = MagicMock()
        fast_wdog.register_stop_callback(fast_cb)
        fast_wdog.start()

        time.sleep(0.4)
        fast_cb.assert_called_once()
        fast_wdog.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
