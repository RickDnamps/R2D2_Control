"""
Pilote audio Slave.
Joue les sons MP3 via aplay (jack 3.5mm natif Pi 4B).
Commandes UART:
  S:Happy001          → joue le fichier spécifique
  S:RANDOM:happy      → joue un son aléatoire de la catégorie
  S:STOP              → coupe le son en cours
"""

import json
import logging
import os
import random
import subprocess
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from shared.base_driver import BaseDriver

log = logging.getLogger(__name__)

_SOUNDS_DIR  = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'sounds'))
_INDEX_FILE  = os.path.join(_SOUNDS_DIR, 'sounds_index.json')


class AudioDriver(BaseDriver):
    def __init__(self, sounds_dir: str = _SOUNDS_DIR):
        self._sounds_dir = os.path.abspath(sounds_dir)
        self._index: dict[str, list[str]] = {}
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ready = False

    # ------------------------------------------------------------------
    # BaseDriver
    # ------------------------------------------------------------------

    def setup(self) -> bool:
        if not os.path.isfile(_INDEX_FILE):
            log.error(f"sounds_index.json introuvable: {_INDEX_FILE}")
            return False
        try:
            with open(_INDEX_FILE, encoding='utf-8') as f:
                data = json.load(f)
            self._index = data.get('categories', {})
            total = sum(len(v) for v in self._index.values())
            log.info(f"AudioDriver prêt — {total} sons dans {len(self._index)} catégories")
            self._ready = True
            return True
        except Exception as e:
            log.error(f"Erreur chargement sounds_index.json: {e}")
            return False

    def shutdown(self) -> None:
        self.stop()
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def play(self, filename: str) -> bool:
        """Joue un fichier MP3 par nom (sans extension)."""
        if not filename or any(c in filename for c in ('/', '\\', '..')):
            log.warning(f"Nom de fichier audio refusé (path traversal): {filename!r}")
            return False
        path = os.path.join(self._sounds_dir, filename + '.mp3')
        if not os.path.isfile(path):
            log.warning(f"Son introuvable: {path}")
            return False
        self._launch(path)
        return True

    def play_random(self, category: str) -> bool:
        """Joue un son aléatoire de la catégorie donnée."""
        sounds = self._index.get(category.lower())
        if not sounds:
            log.warning(f"Catégorie audio inconnue: {category!r}")
            return False
        filename = random.choice(sounds)
        return self.play(filename)

    def stop(self) -> None:
        """Coupe le son en cours de lecture."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                log.debug("Son arrêté")
            self._proc = None

    def handle_uart(self, value: str) -> None:
        """
        Callback pour les messages UART S:.
        Formats attendus:
          - 'Happy001'          → play specific
          - 'RANDOM:happy'      → play random category
          - 'STOP'              → stop
        """
        if value == 'STOP':
            self.stop()
            return
        if value.startswith('RANDOM:'):
            category = value[7:]
            self.play_random(category)
        else:
            self.play(value)

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _launch(self, path: str) -> None:
        """Lance aplay en arrière-plan, coupe le son précédent."""
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            try:
                self._proc = subprocess.Popen(
                    ['aplay', path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.info(f"Audio: {os.path.basename(path)}")
            except FileNotFoundError:
                log.error("aplay introuvable — installer alsa-utils sur le Slave")
            except Exception as e:
                log.error(f"Erreur lancement audio: {e}")
