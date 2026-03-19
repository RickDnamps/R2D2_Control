#!/usr/bin/env python3
"""
Test servo Slave — PCA9685 @ 0x41, canal 0 (Breakout PCA9685 body)
Tester AVANT d'activer Phase 2 dans main.py

Usage sur le Slave Pi:
  python3 scripts/test_servo_slave.py

Prérequis:
  pip install adafruit-circuitpython-pca9685

Le servo sur le canal 0 va faire: Centre → Max → Min → Centre (boucle)
Ctrl+C pour arrêter proprement.
"""

import sys
import time

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
except ImportError:
    print("ERREUR: librairie manquante — installer:")
    print("  pip install adafruit-circuitpython-pca9685")
    sys.exit(1)


def us_to_duty(pulse_us: float) -> int:
    """Convertit µs en valeur 16-bit duty_cycle pour 50Hz (période 20000µs)."""
    return int((pulse_us / 20000.0) * 65535)


def main():
    print("=== Test Servo Slave — PCA9685 @ 0x41, canal 0 ===")
    print()

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=0x41)
        pca.frequency = 50
        print("PCA9685 @ 0x41 détecté OK")
    except Exception as e:
        print(f"ERREUR: impossible d'initialiser PCA9685 @ 0x41: {e}")
        print("Vérifier: i2cdetect -y 1  →  doit montrer '41'")
        sys.exit(1)

    print("Servo canal 0 — séquence: Centre → Max → Min → boucle")
    print("Ctrl+C pour arrêter")
    print()

    moves = [
        (1500, "Centre (1500µs)"),
        (2000, "Max ouvert (2000µs)"),
        (1500, "Centre (1500µs)"),
        (1000, "Min fermé (1000µs)"),
    ]

    try:
        while True:
            for pulse, label in moves:
                print(f"  → {label}")
                pca.channels[0].duty_cycle = us_to_duty(pulse)
                time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nArrêt — servo en position neutre (1500µs)")
        pca.channels[0].duty_cycle = us_to_duty(1500)
        time.sleep(0.5)
        pca.deinit()
        print("OK")


if __name__ == "__main__":
    main()
