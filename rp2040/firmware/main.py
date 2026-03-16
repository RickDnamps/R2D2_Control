"""
R2-D2 RP2040 Firmware — MicroPython.
Waveshare RP2040-LCD-1.28 / RP2040-Touch-LCD-1.28 (GC9A01).
"""

import gc9a01
import time
from machine import SPI, Pin
import display as disp

# Pins hardware
TFT_SCK  = Pin(10)
TFT_MOSI = Pin(11)
TFT_DC   = Pin(8,  Pin.OUT)
TFT_CS   = Pin(9,  Pin.OUT)
TFT_RST  = Pin(12, Pin.OUT)   # 12 = sans touch / 13 = avec touch
TFT_BL   = Pin(25, Pin.OUT)

time.sleep_ms(500)  # laisser le hardware se stabiliser au boot
TFT_BL.value(1)
spi = SPI(1, baudrate=40_000_000, sck=TFT_SCK, mosi=TFT_MOSI)
tft = gc9a01.GC9A01(spi, 240, 240, dc=TFT_DC, cs=TFT_CS, reset=TFT_RST, backlight=TFT_BL)
tft.init()

disp.draw_boot(tft)

while True:
    time.sleep_ms(500)
