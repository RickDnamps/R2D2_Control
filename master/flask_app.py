"""
Flask Application Factory — Phase 4.
Crée et configure l'app Flask R2-D2 avec tous les blueprints.

Usage dans master/main.py:
    from master.flask_app import create_app
    import master.registry as reg

    reg.uart   = uart
    reg.teeces = teeces
    reg.engine = engine
    # ... etc

    app = create_app()
    # Lancer dans un thread daemon:
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000,
                     use_reloader=False), daemon=True).start()
"""

import logging
import os
from flask import Flask, render_template, jsonify

log = logging.getLogger(__name__)


def create_app() -> Flask:
    """Crée et configure l'application Flask."""
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    static_dir   = os.path.join(os.path.dirname(__file__), 'static')

    app = Flask(__name__,
                template_folder=template_dir,
                static_folder=static_dir)

    app.config['JSON_SORT_KEYS'] = False

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    from master.api.audio_bp    import audio_bp
    from master.api.motion_bp   import motion_bp
    from master.api.servo_bp    import servo_bp
    from master.api.script_bp   import script_bp
    from master.api.status_bp   import status_bp
    from master.api.teeces_bp   import teeces_bp
    from master.api.settings_bp import settings_bp

    app.register_blueprint(audio_bp)
    app.register_blueprint(motion_bp)
    app.register_blueprint(servo_bp)
    app.register_blueprint(script_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(teeces_bp)
    app.register_blueprint(settings_bp)

    # ------------------------------------------------------------------
    # Route principale → dashboard web
    # ------------------------------------------------------------------
    @app.get('/')
    def index():
        return render_template('index.html')

    # ------------------------------------------------------------------
    # Gestion erreurs JSON
    # ------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error'}), 500

    log.info("Flask app créée — blueprints: audio, motion, servo, scripts, status, teeces, settings")
    return app
