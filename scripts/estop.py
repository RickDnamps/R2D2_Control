#!/usr/bin/env python3
import board, busio
from adafruit_pca9685 import PCA9685
pca = PCA9685(busio.I2C(board.SCL, board.SDA), address=0x40)
pca.reset()
for ch in pca.channels:
    ch.duty_cycle = 0
pca.deinit()
print("STOP")
