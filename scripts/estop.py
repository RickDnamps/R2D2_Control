#!/usr/bin/env python3
# Arrêt d'urgence — coupe PWM via I2C direct (sans adafruit)
import smbus2, sys

ADDRESSES = [0x40, 0x41]
bus = smbus2.SMBus(1)

MODE1 = 0x00
SLEEP_BIT = 0x10

for addr in ADDRESSES:
    try:
        mode1 = bus.read_byte_data(addr, MODE1)
        bus.write_byte_data(addr, MODE1, mode1 | SLEEP_BIT)
        print(f"PCA9685 @ 0x{addr:02X} — SLEEP OK")
    except Exception as e:
        print(f"PCA9685 @ 0x{addr:02X} — {e}")

bus.close()
print("Tous les servos coupés")
