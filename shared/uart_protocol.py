"""
Protocole UART partagé Master ↔ Slave.
Checksum = somme arithmétique de tous les bytes du payload, modulo 256.
Format: TYPE:VALEUR:CS\n  (CS = 2 hex chars, ex: "B3")

Pourquoi somme mod 256 plutôt que XOR ?
  - XOR : deux octets identiques s'annulent → aveugle à la répétition de bruit périodique
    ex: moteurs 24V + convertisseurs Tobsun génèrent des rafales d'impulsions identiques
  - Somme mod 256 : chaque octet s'accumule → détecte les rafales, les bits flippés,
    les octets dupliqués et les insertions de zéros
  - Suffisant pour des paquets courts (<64 bytes) sur UART 115200 avec slipring
"""

import logging

MSG_TERMINATOR = "\n"
MSG_SEPARATOR  = ":"
HEARTBEAT_INTERVAL_MS = 200
WATCHDOG_TIMEOUT_MS   = 500
BAUD_RATE = 115200


def calc_crc(payload: str) -> str:
    """
    Calcule le checksum (somme des bytes mod 256) du payload.
    Retourne 2 caractères hex majuscules, ex: 'B3'.
    Appelé 'calc_crc' pour compatibilité avec le reste du code.
    """
    return format(sum(payload.encode('utf-8')) % 256, '02X')


def build_msg(msg_type: str, value: str) -> str:
    """Construit un message avec checksum. Ex: build_msg('H', '1') → 'H:1:B3\\n'"""
    payload = f"{msg_type}:{value}"
    return f"{payload}:{calc_crc(payload)}\n"


def parse_msg(raw: str) -> tuple[str, str] | None:
    """
    Parse et valide un message UART avec checksum.
    Retourne (type, value) si checksum valide, None sinon (paquet ignoré).
    Le dernier segment séparé par ':' est toujours le checksum.
    """
    raw = raw.strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) < 3:
        return None
    *payload_parts, received_cs = parts
    payload = ":".join(payload_parts)
    expected_cs = calc_crc(payload)
    if received_cs != expected_cs:
        logging.warning(f"Checksum mismatch: got {received_cs}, expected {expected_cs} for '{payload}'")
        return None
    msg_type = payload_parts[0]
    msg_value = ":".join(payload_parts[1:])
    return (msg_type, msg_value)
