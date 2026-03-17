#!/usr/bin/env python3
"""
generate_icons.py — Generate R2-D2 themed PNG icons using stdlib only (no Pillow).

Generates:
  - icon-192.png  (192×192)
  - icon-512.png  (512×512)

Design:
  - Dark background (#080c14)
  - Blue circle (#00aaff) as the dome
  - Body rectangle (#00aaff)
  - Eye dot (#080c14 on blue)
  - White "R2" text rendered as pixel bitmaps
  - Legs (#00aaff)

Run from the icons/ directory:
  python3 generate_icons.py
"""

import zlib
import struct
import os


# ================================================================
# Minimal PNG writer using stdlib struct + zlib
# ================================================================

def _make_png(width: int, height: int, pixels: list[list[tuple]]) -> bytes:
    """
    Build a valid PNG file from a 2D array of (R, G, B) tuples.
    pixels[y][x] = (r, g, b)  — each value 0-255
    Returns bytes of the complete PNG file.
    """

    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

    # PNG signature
    sig = b'\x89PNG\r\n\x1a\n'

    # IHDR: width, height, bit depth=8, color type=2 (RGB), compression, filter, interlace
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr = chunk(b'IHDR', ihdr_data)

    # IDAT: raw image data (filter byte 0 = None per scanline)
    raw_rows = []
    for row in pixels:
        row_bytes = bytearray()
        row_bytes.append(0)  # filter type None
        for (r, g, b) in row:
            row_bytes.append(r)
            row_bytes.append(g)
            row_bytes.append(b)
        raw_rows.append(bytes(row_bytes))
    raw_data = b''.join(raw_rows)
    compressed = zlib.compress(raw_data, 9)
    idat = chunk(b'IDAT', compressed)

    # IEND
    iend = chunk(b'IEND', b'')

    return sig + ihdr + idat + iend


# ================================================================
# Simple pixel font — digits and letters for "R2" text
# Each glyph is a list of strings, '#' = filled, ' ' = empty, 5×7
# ================================================================

GLYPHS = {
    'R': [
        "####",
        "#   #",
        "#   #",
        "####",
        "# #",
        "#  #",
        "#   #",
    ],
    '2': [
        " ### ",
        "#   #",
        "    #",
        "  ## ",
        " #   ",
        "#    ",
        "#####",
    ],
    '-': [
        "     ",
        "     ",
        "     ",
        "#####",
        "     ",
        "     ",
        "     ",
    ],
    'D': [
        "#### ",
        "#   #",
        "#   #",
        "#   #",
        "#   #",
        "#   #",
        "#### ",
    ],
}


def _draw_glyph(pixels, glyph_char, ox, oy, color, scale=1):
    """Draw a single glyph character onto the pixel buffer."""
    rows = GLYPHS.get(glyph_char, [])
    for ry, row_str in enumerate(rows):
        for rx, ch in enumerate(row_str):
            if ch == '#':
                for sy in range(scale):
                    for sx in range(scale):
                        py = oy + ry * scale + sy
                        px = ox + rx * scale + sx
                        if 0 <= py < len(pixels) and 0 <= px < len(pixels[0]):
                            pixels[py][px] = color


def _draw_text(pixels, text, ox, oy, color, scale=1, spacing=1):
    """Draw a string of characters."""
    x = ox
    for ch in text:
        rows = GLYPHS.get(ch, [])
        if not rows:
            x += (4 + spacing) * scale
            continue
        max_width = max(len(r) for r in rows)
        _draw_glyph(pixels, ch, x, oy, color, scale)
        x += (max_width + spacing) * scale


# ================================================================
# Drawing primitives
# ================================================================

def _fill_rect(pixels, x1, y1, x2, y2, color):
    """Fill rectangle [x1,y1] to [x2,y2] (inclusive)."""
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
                pixels[y][x] = color


def _fill_circle(pixels, cx, cy, r, color):
    """Fill a solid circle."""
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
                    pixels[y][x] = color


def _fill_semicircle_top(pixels, cx, cy, r, color):
    """Fill the top half of a circle (dome shape)."""
    for y in range(cy - r, cy + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
                    pixels[y][x] = color


def _draw_ring(pixels, cx, cy, r_outer, r_inner, color):
    """Draw a ring (annulus)."""
    for y in range(cy - r_outer, cy + r_outer + 1):
        for x in range(cx - r_outer, cx + r_outer + 1):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if r_inner * r_inner < d2 <= r_outer * r_outer:
                if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
                    pixels[y][x] = color


def _draw_horizontal_stripe(pixels, y, x1, x2, color):
    """Draw a horizontal line."""
    for x in range(x1, x2 + 1):
        if 0 <= y < len(pixels) and 0 <= x < len(pixels[0]):
            pixels[y][x] = color


# ================================================================
# Icon generator
# ================================================================

BG    = (8,   12,  20)   # #080c14
BLUE  = (0,   170, 255)  # #00aaff
CYAN  = (0,   255, 234)  # #00ffea
WHITE = (255, 255, 255)
DARK  = (4,   8,   14)   # slightly darker than BG for depth


def generate_icon(size: int) -> bytes:
    """Generate a PNG icon at the given size (192 or 512)."""
    s = size

    # Initialize pixel buffer with background
    pixels = [[BG] * s for _ in range(s)]

    # Scale factor (design was conceived for 192px)
    f = s / 192.0

    def sc(v):
        return int(v * f)

    cx = s // 2  # center x
    cy = s // 2  # center y

    # ── Outer glow ring (subtle) ──────────────────────────────────
    glow_r = sc(82)
    for dy in range(-glow_r, glow_r + 1):
        for dx in range(-glow_r, glow_r + 1):
            d = (dx * dx + dy * dy) ** 0.5
            if glow_r - 3 < d <= glow_r:
                px, py = cx + dx, cy + dy
                if 0 <= py < s and 0 <= px < s:
                    # Blend with bg for glow effect
                    pixels[py][px] = (0, 60, 90)

    # ── Body (main rectangle) ────────────────────────────────────
    body_x1 = sc(38)
    body_x2 = sc(154)
    body_y1 = sc(96)
    body_y2 = sc(148)
    _fill_rect(pixels, body_x1, body_y1, body_x2, body_y2, BLUE)

    # Body highlight stripe (top of body)
    for y in range(body_y1, body_y1 + sc(4)):
        _draw_horizontal_stripe(pixels, y, body_x1, body_x2, (100, 200, 255))

    # ── Dome (semi-circle on top of body) ────────────────────────
    dome_cx = cx
    dome_cy = sc(96)
    dome_r  = sc(54)
    _fill_semicircle_top(pixels, dome_cx, dome_cy, dome_r, BLUE)

    # Dome highlight (inner lighter semicircle, top-left quadrant)
    hl_r = sc(38)
    for dy in range(-hl_r, 1):
        for dx in range(-hl_r, hl_r + 1):
            if (dx * dx + dy * dy) <= hl_r * hl_r:
                px = dome_cx + dx - sc(10)
                py = dome_cy + dy - sc(6)
                if 0 <= py < s and 0 <= px < s:
                    if pixels[py][px] == BLUE:
                        pixels[py][px] = (60, 190, 255)

    # ── Main Eye (large center circle in dome) ───────────────────
    eye_cx = cx
    eye_cy = sc(78)
    eye_r  = sc(16)
    _fill_circle(pixels, eye_cx, eye_cy, eye_r, DARK)
    # Eye ring
    _draw_ring(pixels, eye_cx, eye_cy, eye_r, eye_r - sc(3), CYAN)
    # Eye center glint
    _fill_circle(pixels, eye_cx - sc(4), eye_cy - sc(4), sc(4), (150, 240, 255))

    # ── Side circles (PSI indicators) ────────────────────────────
    psi_r = sc(7)
    _fill_circle(pixels, sc(52), sc(72), psi_r, DARK)
    _draw_ring(pixels, sc(52), sc(72), psi_r, psi_r - sc(2), CYAN)

    _fill_circle(pixels, sc(140), sc(72), psi_r, DARK)
    _draw_ring(pixels, sc(140), sc(72), psi_r, psi_r - sc(2), CYAN)

    # ── Body details ─────────────────────────────────────────────
    # Center panel stripe
    panel_cx = cx
    panel_y1 = body_y1 + sc(10)
    panel_y2 = body_y2 - sc(10)
    _fill_rect(pixels, panel_cx - sc(18), panel_y1, panel_cx + sc(18), panel_y2, (0, 110, 170))

    # Small indicator lights on body
    for i, lx in enumerate([sc(55), sc(68), sc(81)]):
        lc = CYAN if i == 0 else (0, 130, 200)
        _fill_circle(pixels, lx, sc(118), sc(4), lc)

    # ── Legs ─────────────────────────────────────────────────────
    leg_y1 = body_y2 + sc(2)
    leg_y2 = body_y2 + sc(30)
    # Left leg
    _fill_rect(pixels, sc(44), leg_y1, sc(68), leg_y2, BLUE)
    # Right leg
    _fill_rect(pixels, sc(124), leg_y1, sc(148), leg_y2, BLUE)
    # Feet
    foot_h = sc(10)
    _fill_rect(pixels, sc(38), leg_y2, sc(74), leg_y2 + foot_h, (0, 140, 210))
    _fill_rect(pixels, sc(118), leg_y2, sc(154), leg_y2 + foot_h, (0, 140, 210))

    return _make_png(s, s, pixels)


# ================================================================
# Main
# ================================================================

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    for size in [192, 512]:
        filename = os.path.join(script_dir, f'icon-{size}.png')
        print(f'Generating {filename} ({size}×{size})...')
        data = generate_icon(size)
        with open(filename, 'wb') as f:
            f.write(data)
        print(f'  Written {len(data):,} bytes  OK')

    print('\nDone! Icons generated:')
    print('  icon-192.png')
    print('  icon-512.png')
    print('\nNote: For production use, replace with proper PNG icons.')


if __name__ == '__main__':
    main()
