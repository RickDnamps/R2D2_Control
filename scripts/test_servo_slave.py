#!/usr/bin/env python3
"""
Test servo Slave — PCA9685 @ 0x41, canal 0
Supporte servo STANDARD et servo CONTINU.

Usage: python3 scripts/test_servo_slave.py [standard|continu]
Par défaut: continu

Servo standard  : 1000µs=0°  1500µs=90°  2000µs=180°
Servo continu   : 1500µs=STOP  <1500=sens1  >1500=sens2
"""

import sys, time

try:
    import board, busio
    from adafruit_pca9685 import PCA9685
except ImportError:
    print("ERREUR: pip install adafruit-circuitpython-pca9685")
    sys.exit(1)

MODE = sys.argv[1] if len(sys.argv) > 1 else "continu"

def us_to_duty(pulse_us):
    return int((pulse_us / 20000.0) * 65535)

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c, address=0x41)
pca.frequency = 50
print(f"PCA9685 @ 0x41 OK — mode: {MODE}")

def set_pulse(us):
    pca.channels[0].duty_cycle = us_to_duty(us)

def stop():
    set_pulse(1500)
    time.sleep(0.3)
    # Sleep mode direct via smbus2 — arrête l'oscillateur sans reset()
    import smbus2
    b = smbus2.SMBus(1)
    b.write_byte_data(0x41, 0x00, 0x10)
    b.close()
    print("STOP", flush=True)

try:
    if MODE == "continu":
        print("Servo continu — lent sens 1 → stop → lent sens 2 → stop (boucle)")
        print("Ctrl+C pour arrêter")
        while True:
            print("  → sens horaire lent (1600µs)")
            set_pulse(1600)
            time.sleep(2)
            print("  → STOP (1500µs)")
            set_pulse(1500)
            time.sleep(1)
            print("  → sens anti-horaire lent (1400µs)")
            set_pulse(1400)
            time.sleep(2)
            print("  → STOP (1500µs)")
            set_pulse(1500)
            time.sleep(1)
    else:
        # SG90 : 500µs=0°  1500µs=90°  2500µs=180°
        # Test safe : 45°→135° (±45° du centre)
        US_MIN = 1000   # ~45°
        US_MAX = 2000   # ~135°
        STEPS  = 50
        DELAY  = 0.04
        print(f"SG90 — sweep 45°→135° en boucle (Ctrl+C pour arrêter)")
        set_pulse(1500)  # centre d'abord
        time.sleep(0.5)
        while True:
            for i in range(STEPS + 1):
                set_pulse(US_MIN + i * (US_MAX - US_MIN) / STEPS)
                time.sleep(DELAY)
            for i in range(STEPS, -1, -1):
                set_pulse(US_MIN + i * (US_MAX - US_MIN) / STEPS)
                time.sleep(DELAY)

except KeyboardInterrupt:
    print("\nArrêt propre...")
    stop()
