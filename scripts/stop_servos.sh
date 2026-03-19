#!/bin/bash
# Arrêt d'urgence servos — coupe PWM Master (0x40) + Slave (0x41)
REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local

pkill -9 -f test_servo 2>/dev/null
ssh $SLAVE "pkill -9 -f test_servo 2>/dev/null; true"

python3 -c "
import board, busio
from adafruit_pca9685 import PCA9685
pca = PCA9685(busio.I2C(board.SCL, board.SDA), address=0x40)
for ch in pca.channels: ch.duty_cycle = 0
pca.deinit()
print('Master servos OFF')
"

ssh $SLAVE "python3 -c \"
import board, busio
from adafruit_pca9685 import PCA9685
pca = PCA9685(busio.I2C(board.SCL, board.SDA), address=0x41)
for ch in pca.channels: ch.duty_cycle = 0
pca.deinit()
print('Slave servos OFF')
\""
