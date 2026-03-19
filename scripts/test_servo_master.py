#!/usr/bin/env python3
"""
Test servo Master — PCA9685 @ 0x40, canal 0 (Servo Driver HAT dôme)
Tester AVANT d'activer Phase 2 dans main.py

Usage sur le Master Pi:
  python3 scripts/test_servo_master.py

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
    print("=== Test Servo Master — PCA9685 @ 0x40, canal 0 ===")
    print()

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pca = PCA9685(i2c, address=0x40)
        pca.frequency = 50
        print("PCA9685 @ 0x40 détecté OK")
    except Exception as e:
        print(f"ERREUR: impossible d'initialiser PCA9685 @ 0x40: {e}")
        print("Vérifier: i2cdetect -y 1  →  doit montrer '40'")
        sys.exit(1)

    print("Servo canal 0 — séquence: Centre → Max → Min → boucle")
    print("Ctrl+C pour arrêter")
    print()

    # Plage sécuritaire — évite de pousser contre la butée mécanique
    ANGLE_MIN = 60
    ANGLE_MAX = 120
    STEPS  = 50
    PERIOD = 2.0
    DELAY  = PERIOD / STEPS

    def set_angle(deg: float) -> None:
        pulse = 1000 + (deg / 180.0) * 1000
        pca.channels[0].duty_cycle = us_to_duty(pulse)

    print(f"Sweep {ANGLE_MIN}°→{ANGLE_MAX}° en boucle — Ctrl+C pour arrêter")

    try:
        set_angle(90)
        time.sleep(0.5)
        while True:
            for i in range(STEPS + 1):
                set_angle(ANGLE_MIN + i * (ANGLE_MAX - ANGLE_MIN) / STEPS)
                time.sleep(DELAY)
            for i in range(STEPS, -1, -1):
                set_angle(ANGLE_MIN + i * (ANGLE_MAX - ANGLE_MIN) / STEPS)
                time.sleep(DELAY)
    except KeyboardInterrupt:
        print("\nArrêt — servo en position neutre (90°)")
        set_angle(90)
        time.sleep(0.3)
        pca.deinit()
        print("OK")


if __name__ == "__main__":
    main()
