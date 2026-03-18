"""
Blueprint API Audio — Phase 4.
Proxy les commandes audio vers le Slave via UART.

Endpoints:
  POST /audio/play          {"sound": "Happy001"}
  POST /audio/random        {"category": "happy"}
  POST /audio/stop
  GET  /audio/categories    → liste des catégories
"""

import json
import os
from flask import Blueprint, request, jsonify
import master.registry as reg

audio_bp = Blueprint('audio', __name__, url_prefix='/audio')

_INDEX_FILE = os.path.join(
    os.path.dirname(__file__), '..', '..', 'slave', 'sounds', 'sounds_index.json'
)

# Index chargé une seule fois au démarrage
_INDEX_CACHE: dict = {}


def _get_index() -> dict:
    global _INDEX_CACHE
    if not _INDEX_CACHE:
        try:
            with open(_INDEX_FILE, encoding='utf-8') as f:
                _INDEX_CACHE = json.load(f)
        except Exception:
            _INDEX_CACHE = {}
    return _INDEX_CACHE


def _valid_sound(sound: str) -> bool:
    cats = _get_index().get('categories', {})
    return any(sound in sounds for sounds in cats.values())


def _valid_category(cat: str) -> bool:
    return cat in _get_index().get('categories', {})


@audio_bp.get('/categories')
def get_categories():
    """Liste des catégories avec nombre de sons."""
    try:
        cats = _get_index().get('categories', {})
        return jsonify({
            'categories': [{'name': k, 'count': len(v)} for k, v in cats.items()],
            'total': sum(len(v) for v in cats.values())
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audio_bp.get('/sounds')
def get_sounds():
    """Liste des sons d'une catégorie. Query: ?category=happy"""
    category = request.args.get('category', '').strip().lower()
    if not category:
        return jsonify({'error': 'Paramètre "category" requis'}), 400
    sounds = _get_index().get('categories', {}).get(category)
    if sounds is None:
        return jsonify({'error': f'Catégorie inconnue: {category}'}), 404
    return jsonify({'category': category, 'sounds': sounds})


@audio_bp.post('/play')
def play_sound():
    """Joue un son spécifique. Body: {"sound": "Happy001"}"""
    body = request.get_json(silent=True) or {}
    sound = body.get('sound', '').strip()
    if not sound:
        return jsonify({'error': 'Champ "sound" requis'}), 400
    if not _valid_sound(sound):
        return jsonify({'error': f'Son inconnu: {sound}'}), 404
    if reg.uart:
        reg.uart.send('S', sound)
    return jsonify({'status': 'ok', 'sound': sound})


@audio_bp.post('/random')
def play_random():
    """Joue un son aléatoire. Body: {"category": "happy"}"""
    body = request.get_json(silent=True) or {}
    category = body.get('category', 'happy').strip().lower()
    if not _valid_category(category):
        return jsonify({'error': f'Catégorie inconnue: {category}'}), 404
    if reg.uart:
        reg.uart.send('S', f'RANDOM:{category}')
    return jsonify({'status': 'ok', 'category': category})


@audio_bp.post('/stop')
def stop_audio():
    """Coupe le son en cours."""
    if reg.uart:
        reg.uart.send('S', 'STOP')
    return jsonify({'status': 'ok'})
