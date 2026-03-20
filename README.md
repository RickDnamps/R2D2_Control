# R2D2_Control

Full-scale R2-D2 replica control system running on two Raspberry Pi 4B in a Master/Slave architecture, communicating over physical UART (through the dome slip ring) and local Wi-Fi.

> **Alpha Phase** — Software is functional and actively tested on bench hardware. Physical assembly (3D-printed parts, slip ring, final wiring) is still in progress. No camera stream yet.

---

## Screenshots

### Drive Interface
Dual joystick control with WASD keyboard support, emergency stop, and battery gauge.

![Drive Interface](Screenshots/Drive_web_interface.jpg)

### Audio
317 R2-D2 sounds across 14 categories — play specific sounds or trigger random ones by mood.

![Audio Interface](Screenshots/Audio_web_interface.jpg)

### Sequences
40 pre-built behavioral scripts (patrol, celebrate, Cantina, Leia, evil, malfunction…) — run once or loop.

![Sequences Interface](Screenshots/Sequences_web_interface.jpg)

### Systems & Servo Control
Teeces32 LED logic control, independent dome panel servos (×11) and body panel servos (×11), Bluetooth controller mapping.

![Systems Interface](Screenshots/Systems_TemporaryServos_web_interface.jpg)

### Configuration
Wi-Fi, hotspot, GitHub/auto-deploy settings, per-panel servo calibration, and system controls.

![Config Interface](Screenshots/Config_web_interface.jpg)

---

## Features

- **Distributed architecture** — Master Pi (dome, rotates with slip ring) + Slave Pi (body, fixed)
- **UART heartbeat watchdog** — Slave cuts drive motors within 500ms if Master goes offline (safety-critical)
- **Web dashboard** — Dark theme, mobile-friendly, WASD/arrow key drive control, REST polling
- **Android app** — WebView wrapper with offline asset bundling, native connectivity banner, auto-discovery
- **317 R2-D2 sounds** in 14 categories (sourced from dpoulson/r2_control + extras)
- **40 behavior scripts** (.scr CSV format) — 26 faithful dpoulson ports + 14 custom sequences
- **Dome servos** — 11 panels via PCA9685 I2C on Master (0x40)
- **Body servos** — 11 panels via PCA9685 I2C on Slave (0x41)
- **Per-panel servo calibration** — individual open/close angles in web Settings
- **Teeces32 LED logics** — random, Leia, off, scrolling text, PSI modes via JawaLite protocol
- **Auto-deploy** — dome button triggers git pull + rsync to Slave + reboot
- **RP2040 diagnostic display** — boot/sync/error/telemetry states on round 240×240 LCD
- **3-layer motion safety** — app heartbeat watchdog (600ms) + drive timeout watchdog (800ms) + UART watchdog (500ms)
- **Graceful deceleration** — speed ramp to 0 on watchdog trip (no hard stops at speed)

---

## Hardware Overview

### Master — Raspberry Pi 4B 4GB (Dome, rotates with slip ring)

| Component | Interface | Details |
|-----------|-----------|---------|
| Waveshare Servo Driver HAT | I2C 0x40 | PCA9685 16ch — dome panel servos |
| Teeces32 LED logics (FLD/RLD/PSI) | USB `/dev/ttyUSB0` | JawaLite protocol, 9600 baud |
| Camera | USB | Vision / person tracking (Phase 5) |
| UART to Slave Pi | BCM 14/15 `/dev/ttyAMA0` | Through slip ring, 3.3V |

### Slave — Raspberry Pi 4B 2GB (Body, fixed)

| Component | Interface | Details |
|-----------|-----------|---------|
| Waveshare Motor Driver HAT | I2C 0x40 | TB6612 — dome rotation DC motor |
| PCA9685 Breakout | I2C 0x41 | 16ch PWM — body/arm/panel servos |
| FSESC Mini 6.7 PRO × 2 | USB `/dev/ttyACM0/1` | PyVESC — 24V drive motors |
| RP2040 Touch LCD 1.28" | USB `/dev/ttyACM2` | 240×240 diagnostic display |
| 3.5mm audio jack | Native Pi 4B | R2-D2 sounds → amp → speakers |
| UART to Master Pi | BCM 14/15 `/dev/ttyAMA0` | Through slip ring, 3.3V |

### Propulsion

- 2× 250W/24V hub motors (double shaft) — drive wheels
- 4× 58mm omni wheels — omnidirectional stabilization
- 2× FSESC Mini 6.7 PRO (4–13S LiPo) — motor controllers
- 6S LiPo 10 000mAh, XT90-S connector (anti-spark)

---

## Architecture

```
[PC / Phone]  ←WiFi→  [R2-Master Pi 4B — Dome]  ←UART slip ring→  [R2-Slave Pi 4B — Body]
                              │                                              │
                         Flask :5000                                   UART listener
                         Dome servos (I2C 0x40)                        Watchdog (500ms)
                         Teeces32 (USB)                                 Body servos (I2C 0x41)
                         Script engine                                  Drive VESCs (USB)
                         Deploy controller                              Dome motor (I2C 0x40)
                                                                        Audio (3.5mm jack)
                                                                        RP2040 display (USB)
```

### Network

```
R2-Master  wlan0 → Wi-Fi hotspot (AP)  192.168.4.1   SSID: R2D2_Control
           wlan1 → Home Wi-Fi (client) DHCP           (for git pull / updates)
R2-Slave   wlan0 → Client of Master hotspot  192.168.4.x
```

---

## Repository Structure

```
r2d2/
├── master/          — Master Pi code (dome)
│   ├── main.py
│   ├── drivers/     — VescDriver, DomeMotorDriver, DomeServoDriver, BodyServoDriver
│   ├── api/         — Flask blueprints (audio, motion, servo, scripts, teeces, status)
│   ├── scripts/     — 40 behavioral scripts (.scr)
│   ├── templates/   — Web dashboard HTML
│   └── static/      — CSS + JS
├── slave/           — Slave Pi code (body)
│   ├── main.py
│   ├── drivers/     — AudioDriver, DisplayDriver, VescDriver, BodyServoDriver
│   └── sounds/      — sounds_index.json (MP3 files gitignored — too large)
├── shared/          — uart_protocol.py (CRC), base_driver.py
├── rp2040/          — MicroPython firmware for diagnostic display
├── android/         — Android app (WebView wrapper)
│   └── compiled/    — R2-D2_Control.apk (ready to install)
├── scripts/         — deploy.sh, setup_master_network.sh, setup_slave_network.sh
├── Screenshots/     — Web interface screenshots
└── HOWTO.md         — Installation guide (French)
```

---

## Installation

See [HOWTO.md](HOWTO.md) for the full step-by-step installation guide (French).

Quick overview:
1. Flash two Pi 4B SD cards (username: `artoo`) using Raspberry Pi Imager
2. Run `scripts/setup_master_network.sh` on Master → configures Wi-Fi hotspot + internet
3. Run `scripts/setup_slave_network.sh` on Slave → connects to Master hotspot
4. Run `scripts/setup_ssh_keys.sh` → passwordless SSH Master → Slave
5. Enable systemd services on both Pis
6. Access dashboard at `http://r2-master.local:5000` or `http://192.168.4.1:5000`

### Android App

Download `android/compiled/R2-D2_Control.apk`, enable "Install from unknown sources", install and launch. The app auto-discovers the Master Pi on the network.

---

## Development Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Infrastructure: UART, heartbeat watchdog, audio, Teeces32, RP2040, deploy button | ✅ Code complete, bench tested |
| 2 | Propulsion: VESCs, dome motor, body/dome servo panels | 🔧 Code ready — hardware assembly pending |
| 3 | Script engine: 40 behavioral sequences | ✅ Active |
| 4 | REST API + Web dashboard + Android app | ✅ Active |
| 5 | Vision: USB camera, person tracking | 📋 Planned |

> Physical assembly is in progress — 3D-printed parts printing, slip ring not yet received.
> All current testing is done on bench/breadboard with direct BCM14/15 UART connection.

---

## Credits

- Sound library and script format inspired by [r2_control by dpoulson](https://github.com/dpoulson/r2_control)
- 306 R2-D2 sounds sourced from dpoulson's collection

## License

GNU GPL v3 — see [LICENSE](LICENSE)
