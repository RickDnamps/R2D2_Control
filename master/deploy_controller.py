"""
Deploy Controller — Mise à jour et déploiement.
- git pull depuis wlan1 (internet)
- rsync /slave/ vers Pi Zero via SSH
- Bouton physique dôme (court=update, long=rollback, double=version)
- Reboot Slave via UART
"""

import logging
import subprocess
import threading
import time
import configparser
import sys
import os

log = logging.getLogger(__name__)

VERSION_FILE = "/home/artoo/r2d2/VERSION"
MAX_SYNC_RETRIES = 3
SYNC_RETRY_BACKOFF_S = [5, 15, 30]


class DeployController:
    def __init__(self, cfg: configparser.ConfigParser, uart_controller, teeces_controller):
        self._repo_path   = cfg.get('master', 'repo_path')
        self._slave_user  = cfg.get('deploy', 'slave_user')
        self._slave_host  = cfg.get('slave',  'host',             fallback=cfg.get('deploy', 'slave_host'))
        self._slave_path  = cfg.get('deploy', 'slave_path')
        self._button_pin  = cfg.getint('deploy', 'button_pin',    fallback=17)
        self._short_press_threshold = cfg.getfloat('deploy', 'button_short_press_s')
        self._internet_iface = cfg.get('network', 'internet_interface')
        self._github_url    = cfg.get('github', 'repo_url',   fallback='')
        self._github_branch = cfg.get('github', 'branch',     fallback='main')
        self._uart = uart_controller
        self._teeces = teeces_controller
        self._running = False

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._button_loop, name="deploy-btn", daemon=True).start()
        log.info("DeployController démarré")

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Bouton GPIO
    # ------------------------------------------------------------------

    def _button_loop(self) -> None:
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        except Exception as e:
            log.error(f"GPIO init échoué: {e} — bouton désactivé")
            return

        last_release = 0.0
        while self._running:
            try:
                if GPIO.input(self._button_pin) == GPIO.LOW:
                    press_start = time.monotonic()
                    # Attendre relâchement
                    while GPIO.input(self._button_pin) == GPIO.LOW:
                        time.sleep(0.05)
                    duration = time.monotonic() - press_start

                    now = time.monotonic()
                    if duration >= self._short_press_threshold:
                        # Appui long → rollback
                        log.info("Bouton: appui long → rollback")
                        self.rollback()
                    elif (now - last_release) < 0.5:
                        # Double appui → afficher version
                        log.info("Bouton: double appui → afficher version")
                        self._show_version()
                    else:
                        # Appui court → update
                        log.info("Bouton: appui court → update")
                        self.update_and_deploy()

                    last_release = now
                time.sleep(0.05)
            except Exception as e:
                log.error(f"Erreur button_loop: {e}")
                time.sleep(1)

    # ------------------------------------------------------------------
    # Actions principales
    # ------------------------------------------------------------------

    def update_and_deploy(self) -> bool:
        """Appui court: git pull (si internet) + rsync + reboot Slave."""
        if self._is_internet_available():
            self.git_pull()
        else:
            log.info("wlan1 absent — rsync version locale")
        success = self.rsync_to_slave()
        if success:
            self.reboot_slave()
        return success

    def rollback(self) -> bool:
        """Appui long: git checkout HEAD^ + rsync + reboot Slave."""
        log.info("Rollback: git checkout HEAD^")
        try:
            result = subprocess.run(
                ["git", "checkout", "HEAD^"],
                cwd=self._repo_path,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                log.error(f"git checkout HEAD^ échoué: {result.stderr}")
                return False
            self._update_version_file()
            log.info("Rollback git OK")
        except Exception as e:
            log.error(f"Erreur rollback: {e}")
            return False

        success = self.rsync_to_slave()
        if success:
            self.reboot_slave()
        return success

    def git_pull(self) -> bool:
        """
        git pull avec timeout.
        Utilise l'URL GitHub de local.cfg — supporte les forks.
        Met à jour le remote 'origin' si l'URL a changé.
        """
        try:
            # Synchroniser le remote origin avec local.cfg si nécessaire
            if self._github_url:
                self._sync_remote_url()

            result = subprocess.run(
                ["git", "pull", "origin", self._github_branch],
                cwd=self._repo_path,
                timeout=30,
                capture_output=True, text=True
            )
            if result.returncode == 0:
                self._update_version_file()
                log.info(f"git pull réussi (branch: {self._github_branch})")
                return True
            else:
                log.warning(f"git pull échoué: {result.stderr.strip()}")
                return False
        except subprocess.TimeoutExpired:
            log.warning("git pull timeout")
            return False
        except Exception as e:
            log.error(f"git pull erreur: {e}")
            return False

    def _sync_remote_url(self) -> None:
        """Met à jour git remote origin si l'URL dans local.cfg est différente."""
        url = self._github_url
        if not (url.startswith('https://') or url.startswith('http://') or url.startswith('git@')):
            log.warning(f"URL GitHub invalide ignorée: {url!r}")
            return
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self._repo_path,
                capture_output=True, text=True, timeout=5
            )
            current_url = result.stdout.strip()
            if current_url != url:
                subprocess.run(
                    ["git", "remote", "set-url", "origin", url],
                    cwd=self._repo_path, timeout=5, check=True
                )
                log.info(f"Remote origin mis à jour: {url}")
        except Exception as e:
            log.warning(f"Impossible de sync remote URL: {e}")

    def rsync_to_slave(self, retries: int = MAX_SYNC_RETRIES) -> bool:
        """rsync slave/ vers Pi Zero. Retry avec backoff."""
        slave_slave_path = f"{self._slave_user}@{self._slave_host}:{self._slave_path}/"
        local_path = os.path.join(self._repo_path, "slave/")

        for attempt in range(retries):
            try:
                log.info(f"rsync tentative {attempt + 1}/{retries}")
                result = subprocess.run(
                    [
                        "rsync", "-avz", "--delete",
                        "-e", "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10",
                        local_path, slave_slave_path
                    ],
                    timeout=120,
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    log.info("rsync réussi")
                    return True
                else:
                    log.warning(f"rsync échoué (code {result.returncode}): {result.stderr.strip()}")
            except subprocess.TimeoutExpired:
                log.warning("rsync timeout")
            except Exception as e:
                log.error(f"rsync erreur: {e}")

            if attempt < retries - 1:
                backoff = SYNC_RETRY_BACKOFF_S[attempt]
                log.info(f"Retry dans {backoff}s")
                time.sleep(backoff)

        log.error("rsync échoué après toutes les tentatives")
        if self._teeces:
            self._teeces.alert_error("SYNC")
        return False

    def reboot_slave(self) -> None:
        """Envoie commande REBOOT au Slave via UART."""
        if self._uart:
            self._uart.send('REBOOT', '1')
            log.info("Commande REBOOT envoyée au Slave")

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------

    def _show_version(self) -> None:
        version = self._read_version()
        if self._teeces:
            self._teeces.show_version(version)
        log.info(f"Version courante: {version}")

    def _update_version_file(self) -> None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self._repo_path,
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                with open(VERSION_FILE, 'w') as f:
                    f.write(version)
                log.info(f"VERSION mis à jour: {version}")
        except Exception as e:
            log.error(f"Erreur update VERSION: {e}")

    def _read_version(self) -> str:
        try:
            with open(VERSION_FILE) as f:
                return f.read().strip()
        except Exception:
            return "unknown"

    def _is_internet_available(self) -> bool:
        try:
            result = subprocess.run(
                ["ip", "addr", "show", self._internet_iface],
                capture_output=True, text=True, timeout=5
            )
            return "inet " in result.stdout
        except Exception:
            return False
