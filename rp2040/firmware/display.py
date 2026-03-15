"""
Display renderer — écran rond GC9A01 240x240.
Dessine les différents états de l'interface R2-D2.
"""

import gc9a01
import framebuf
import math

# Couleurs RGB565
BLACK   = gc9a01.color565(0,   0,   0)
WHITE   = gc9a01.color565(255, 255, 255)
RED     = gc9a01.color565(220, 50,  50)
GREEN   = gc9a01.color565(50,  200, 80)
ORANGE  = gc9a01.color565(255, 150, 0)
BLUE    = gc9a01.color565(0,   120, 220)
GRAY    = gc9a01.color565(80,  80,  80)
YELLOW  = gc9a01.color565(255, 230, 0)

CENTER_X = 120
CENTER_Y = 120
RADIUS   = 120


def _clear(tft, color):
    tft.fill(color)


def _fill_circle(tft, cx, cy, r, color):
    """Cercle plein compatible tous drivers gc9a01 (fill_circle pas toujours dispo)."""
    if hasattr(tft, 'fill_circle'):
        tft.fill_circle(cx, cy, r, color)
        return
    # Fallback : lignes horizontales (Bresenham)
    for dy in range(-r, r + 1):
        dx = int(math.sqrt(r * r - dy * dy))
        tft.fill_rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)


def draw_boot(tft):
    """Splash boot : fond noir, logo R2-D2 simplifié."""
    _clear(tft, BLACK)
    # Dôme (demi-cercle haut)
    _fill_circle(tft, CENTER_X, CENTER_Y - 10, 55, WHITE)
    _fill_circle(tft, CENTER_X, CENTER_Y - 10, 45, BLACK)
    # Corps (rectangle)
    tft.fill_rect(CENTER_X - 30, CENTER_Y + 50, 60, 45, WHITE)
    tft.fill_rect(CENTER_X - 24, CENTER_Y + 56, 48, 33, BLACK)
    # Texte
    tft.text("R2-D2", CENTER_X - 25, CENTER_Y + 100, WHITE)
    tft.text("BOOT...", CENTER_X - 28, CENTER_Y + 115, GRAY)


def draw_syncing(tft, version: str, spinner_step: int = 0):
    """Spinner orange — synchronisation en cours."""
    _clear(tft, BLACK)
    # Anneau orange
    steps = 12
    for i in range(steps):
        angle = (i / steps) * 2 * math.pi + (spinner_step * math.pi / 6)
        x = int(CENTER_X + 80 * math.cos(angle))
        y = int(CENTER_Y + 80 * math.sin(angle))
        alpha = int(255 * (i / steps))
        color = gc9a01.color565(255, max(0, alpha // 2), 0)
        _fill_circle(tft, x, y, 8, color)
    tft.text("SYNCING", CENTER_X - 30, CENTER_Y - 10, ORANGE)
    tft.text(version[:10], CENTER_X - 30, CENTER_Y + 10, WHITE)


def draw_ok(tft, version: str):
    """Validation OK — fond vert, coche."""
    _clear(tft, BLACK)
    # Cercle vert
    _fill_circle(tft, CENTER_X, CENTER_Y - 20, 50, GREEN)
    # Coche simplifiée
    tft.line(CENTER_X - 20, CENTER_Y - 20, CENTER_X - 5, CENTER_Y - 5, WHITE)
    tft.line(CENTER_X - 5, CENTER_Y - 5, CENTER_X + 25, CENTER_Y - 40, WHITE)
    tft.text("OK", CENTER_X - 10, CENTER_Y + 45, GREEN)
    tft.text(version[:10], CENTER_X - 30, CENTER_Y + 65, GRAY)


def draw_error(tft, reason: str):
    """Alerte bloquante rouge."""
    _clear(tft, BLACK)
    _fill_circle(tft, CENTER_X, CENTER_Y - 20, 50, RED)
    tft.text("!", CENTER_X - 5, CENTER_Y - 35, WHITE)
    tft.text("ERREUR", CENTER_X - 27, CENTER_Y + 45, RED)
    # Affichage reason sur 2 lignes si besoin
    r = reason[:10]
    tft.text(r, CENTER_X - len(r) * 4, CENTER_Y + 65, WHITE)
    if len(reason) > 10:
        r2 = reason[10:20]
        tft.text(r2, CENTER_X - len(r2) * 4, CENTER_Y + 80, WHITE)


def draw_telemetry(tft, voltage: float, temp: float):
    """Jauge batterie + température. Fond bleu."""
    _clear(tft, BLACK)
    # Titre
    tft.text("TELEMETRY", CENTER_X - 38, 30, BLUE)

    # Jauge batterie (0-29.4V = 0-100%)
    v_pct = max(0.0, min(1.0, (voltage - 20.0) / (29.4 - 20.0)))
    bar_w = int(160 * v_pct)
    tft.fill_rect(CENTER_X - 80, CENTER_Y - 30, 160, 25, GRAY)
    bar_color = GREEN if v_pct > 0.3 else (ORANGE if v_pct > 0.15 else RED)
    tft.fill_rect(CENTER_X - 80, CENTER_Y - 30, bar_w, 25, bar_color)
    tft.text(f"{voltage:.1f}V", CENTER_X - 20, CENTER_Y - 50, WHITE)

    # Température
    temp_color = GREEN if temp < 60 else (ORANGE if temp < 75 else RED)
    tft.text(f"TEMP: {temp:.0f}C", CENTER_X - 38, CENTER_Y + 20, temp_color)
