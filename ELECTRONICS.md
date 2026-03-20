# R2D2_Control — Electronics & Wiring Reference

Complete wiring diagrams, power distribution, and communication architecture for the R2-D2 Master/Slave control system.

---

## Table of Contents

- [System Architecture](#1-system-architecture)
- [Power Distribution](#2-power-distribution)
- [Slip Ring Wiring](#3-slip-ring-wiring)
- [Network Topology](#4-network-topology)
- [3-Layer Safety System](#5-3-layer-safety-system)
- [I2C & GPIO Reference](#6-i2c--gpio-reference)
- [UART Protocol](#7-uart-protocol-reference)
- [Component Notes](#8-component-notes)

---

## 1. System Architecture

All hardware connections — software components, communication buses, and peripherals.

```mermaid
flowchart TB
    subgraph CTRL["📱 Control Interface"]
        direction LR
        BROWSER["Web Browser\nor Android App"]
    end

    subgraph MASTER["🎩 R2-MASTER — Raspberry Pi 4B 4GB  (Dome — rotates with slip ring)"]
        direction TB
        FLASK["🌐 Flask REST API\nport 5000"]
        ENGINE["🎬 Script Engine\n40 behavioral sequences"]
        UART_M["📡 UART Controller\nHeartbeat every 200ms"]
        DEPLOY["🔘 Deploy Controller\nDome button — git pull + rsync"]

        subgraph MASTER_HW["Master Hardware"]
            direction LR
            DOME_SRV["Dome Servo Driver\n11 panels\nPCA9685 @ I2C 0x40"]
            TEECES["Teeces32 LEDs\nFLD / RLD / PSI\n/dev/ttyUSB0"]
            CAM["Camera\nUSB — Phase 5"]
        end

        FLASK --> ENGINE
        FLASK --> UART_M
        FLASK --> DOME_SRV
        FLASK --> TEECES
    end

    subgraph SLIPRING["〰️  Slip Ring  (12 wires — dome rotates freely)"]
        SR_24V["24V Power\n3 wires ∥"]
        SR_GND["GND\n3 wires ∥"]
        SR_UART["UART TX/RX\n2 wires"]
        SR_SPARE["Spare\n4 wires"]
    end

    subgraph SLAVE["🤖 R2-SLAVE — Raspberry Pi 4B 2GB  (Body — fixed)"]
        direction TB
        UART_S["📡 UART Listener\n+ Watchdog 500ms"]
        WDG["🛑 Hardware Watchdog\nCuts VESCs if no heartbeat"]

        subgraph SLAVE_HW["Slave Hardware"]
            direction LR
            AUDIO["🔊 Audio Driver\naplay — 317 sounds\n3.5mm jack"]
            BODY_SRV["Body Servo Driver\n11 panels\nPCA9685 @ I2C 0x41"]
            DOME_MOT["Dome Motor Driver\nTB6612 @ I2C 0x40"]
            VESC["⚙️ VESC Driver\nPyVESC × 2\n/dev/ttyACM0+1"]
            RP2040["🖥️ RP2040 Display\n240×240 round LCD\n/dev/ttyACM2"]
        end

        UART_S --> WDG
        UART_S --> AUDIO
        UART_S --> BODY_SRV
        UART_S --> DOME_MOT
        UART_S --> VESC
        UART_S --> RP2040
    end

    BROWSER <-->|"Wi-Fi  REST/JSON"| FLASK
    UART_M <-->|"UART 115200 baud"| SR_UART
    SR_UART <-->|"UART 115200 baud"| UART_S
```

---

## 2. Power Distribution

Battery → fuses → switches → bucks → every powered component.

```mermaid
flowchart TD
    BAT["🔋 Battery\n6S LiPo 10 000mAh\n22–25V  XT90-S anti-spark"]

    FUSE80["⚡ Fuse 80A\n← closest possible to battery +"]
    SW_MAIN["🔴 Main Switch 30A+\nkills everything"]

    BAT --> FUSE80 --> SW_MAIN

    SW_MAIN --> XT90S
    SW_MAIN --> FUSE15

    subgraph PROP["⚙️ Propulsion  — 24V direct (high current)"]
        XT90S["XT90-S Connector\nanti-spark"]
        VESC1["FSESC Mini 6.7 PRO #1\n→ Left Hub Motor 250W"]
        VESC2["FSESC Mini 6.7 PRO #2\n→ Right Hub Motor 250W"]
        XT90S --> VESC1
        XT90S --> VESC2
    end

    subgraph ELEC["🔵 Electronics Branch"]
        FUSE15["⚡ Fuse 15A"]
        SW_ELEC["🔵 Electronics Switch 10A\npower on/off independently"]
        FUSE15 --> SW_ELEC

        subgraph BODY["📦 Body  (Slave Pi)"]
            BUCK_5V_BODY["Tobsun EA50-5V\n10–30V → 5V / 10A"]
            BUCK_12V_BODY["Tobsun EA120-12V\n18–32V → 12V / 10A"]

            PI_SLAVE["Raspberry Pi 4B Slave\n← 5V via GPIO pins 2 & 4"]
            SERVO_HAT_B["Body Servo HAT V+\nPCA9685 @ 0x41\n← 5V direct\n+ 1000µF + 100nF caps"]
            RP2040_B["RP2040 LCD\n← 5V via USB from Pi Slave"]

            MOTOR_HAT["Motor Driver HAT TB6612\n← 12V  (dome DC motor)"]
            AMPLIFIER["Audio Amplifier\n← 12V\n→ Speakers"]

            BUCK_5V_BODY --> PI_SLAVE
            BUCK_5V_BODY --> SERVO_HAT_B
            BUCK_5V_BODY --> RP2040_B
            BUCK_12V_BODY --> MOTOR_HAT
            BUCK_12V_BODY --> AMPLIFIER
        end

        subgraph SLIPRING_PWR["〰️ Slip Ring  (24V travels to dome)"]
            SR_PWR["24V  3 wires in parallel\n→ ~4–6A capacity"]
        end

        subgraph DOME["🎩 Dome  (Master Pi)"]
            BUCK_5V_DOME["Tobsun EA50-5V\n10–30V → 5V / 10A"]

            PI_MASTER["Raspberry Pi 4B Master\n← 5V via GPIO pins 2 & 4"]
            SERVO_HAT_D["Dome Servo HAT V+\nPCA9685 @ 0x40\n← 5V direct\n+ 1000µF + 100nF caps"]
            TEECES_LED["Teeces32 LEDs\nFLD / RLD / PSI\n← 5V direct"]
            TEECES_ESP["Teeces32 ESP32 logic\n← 5V via USB from Pi Master"]

            BUCK_5V_DOME --> PI_MASTER
            BUCK_5V_DOME --> SERVO_HAT_D
            BUCK_5V_DOME --> TEECES_LED
            BUCK_5V_DOME --> TEECES_ESP
        end

        SW_ELEC --> BUCK_5V_BODY
        SW_ELEC --> BUCK_12V_BODY
        SW_ELEC --> SR_PWR
        SR_PWR --> BUCK_5V_DOME
    end
```

> **Power-on sequence:**
> 1. Connect battery → plug XT90-S last (anti-spark for VESCs)
> 2. Flip main switch → Pi boots (~30s)
> 3. Plug XT90-S → VESCs power up safely

---

## 3. Slip Ring Wiring

The dome rotates freely. All signals and power pass through a 12-wire slip ring.

| Wire | Signal | Notes |
|------|--------|-------|
| 1, 2, 3 | **24V +** | 3 wires in parallel → ~4–6A total capacity |
| 4, 5, 6 | **GND** | 3 wires in parallel |
| 7 | **UART TX** | Slave (body) → Master (dome) |
| 8 | **UART RX** | Master (dome) → Slave (body) |
| 9–12 | **Spare** | Reserved for future use (camera USB, etc.) |

> **UART wiring rule — always cross TX↔RX:**
> ```
> Master BCM14 (TX) ──→  BCM15 (RX) Slave
> Master BCM15 (RX) ←──  BCM14 (TX) Slave
> Master GND        ───  GND         Slave
> ```

---

## 4. Network Topology

```mermaid
flowchart LR
    subgraph INTERNET["🌍 Internet"]
        GITHUB["GitHub\ngit pull / push"]
    end

    subgraph MASTER_NET["R2-Master Pi 4B (Dome)"]
        WLAN0["wlan0\n📡 Wi-Fi Hotspot AP\n192.168.4.1  (fixed)\nSSID: R2D2_Control"]
        WLAN1["wlan1\n🌐 Home Wi-Fi client\nDHCP — internet access"]
    end

    subgraph SLAVE_NET["R2-Slave Pi 4B (Body)"]
        WLAN0_S["wlan0\n📶 Client of Master hotspot\n192.168.4.x  (DHCP)"]
    end

    subgraph DEVICES["📱 Control Devices"]
        PHONE["Phone / Tablet\nAndroid App"]
        PC["PC / Laptop\nWeb Browser"]
    end

    PHONE <-->|"Wi-Fi  192.168.4.1:5000"| WLAN0
    PC    <-->|"Wi-Fi  192.168.4.1:5000"| WLAN0
    WLAN0_S <-->|"hotspot"| WLAN0
    WLAN1 <-->|"home Wi-Fi"| INTERNET
    WLAN1 -.->|"git pull on boot\nor dome button"| GITHUB
```

---

## 5. 3-Layer Safety System

Three independent watchdogs ensure motors stop even if any part of the system crashes.

```mermaid
flowchart TD
    subgraph WD1["🟡 Layer 1 — App Watchdog  (Master)"]
        APP_HB["App sends POST /heartbeat\nevery 200ms"]
        APP_WD["AppWatchdog\n600ms timeout"]
        APP_STOP["safe_stop()\nspeed ramp → 0"]
        APP_HB -->|"feeds"| APP_WD
        APP_WD -->|"timeout → triggers"| APP_STOP
    end

    subgraph WD2["🟠 Layer 2 — Motion Watchdog  (Master)"]
        DRIVE_CMD["App sends /motion/drive\ncommand"]
        MOTION_WD["MotionWatchdog\n800ms timeout"]
        MOTION_STOP["safe_stop()\nspeed ramp → 0"]
        DRIVE_CMD -->|"feeds"| MOTION_WD
        MOTION_WD -->|"no new cmd → triggers"| MOTION_STOP
    end

    subgraph WD3["🔴 Layer 3 — UART Watchdog  (Slave — hardware level)"]
        HB_UART["Master sends H:1 heartbeat\nevery 200ms via UART"]
        SLAVE_WD["Slave Watchdog\n500ms timeout"]
        VESC_KILL["Cut both VESCs\nimmediate hard stop"]
        HB_UART -->|"feeds"| SLAVE_WD
        SLAVE_WD -->|"no heartbeat → triggers"| VESC_KILL
    end

    MASTER_CRASH["Master crashes\nor Wi-Fi drops"]
    UART_CUT["UART cut\nor slip ring fault"]

    MASTER_CRASH --> APP_WD
    MASTER_CRASH --> MOTION_WD
    UART_CUT --> SLAVE_WD

    note1["⚠️ Layer 3 is the last resort\nIt operates on the Slave independently\nMaster crash cannot prevent it"]
```

---

## 6. I2C & GPIO Reference

### I2C Addresses

| Pi | Bus | Address | Component | Purpose |
|----|-----|---------|-----------|---------|
| Master (Dome) | I2C-1 | **0x40** | Waveshare Servo Driver HAT | 11 dome panel servos (ch 0–10) |
| Slave (Body) | I2C-1 | **0x40** | Waveshare Motor Driver HAT (TB6612) | Dome rotation DC motor |
| Slave (Body) | I2C-1 | **0x41** | PCA9685 Breakout | 11 body panel servos (ch 0–10) |

### GPIO Pins — both Pi 4B

| BCM | Function | Notes |
|-----|----------|-------|
| **2** | I2C SDA | I2C bus |
| **3** | I2C SCL | I2C bus |
| **14** | UART TX | → slip ring → other Pi RX |
| **15** | UART RX | ← slip ring ← other Pi TX |
| **2, 4** | 5V power in | GPIO header pins — Pi powered from buck (bypass USB-C) |
| **XX** | Dome button | BCM pin TBD — configure in `local.cfg [deploy] button_pin` |

### USB Ports — Slave Pi

| Port | Device | Driver |
|------|--------|--------|
| `/dev/ttyACM0` | FSESC Mini 6.7 PRO #1 | PyVESC |
| `/dev/ttyACM1` | FSESC Mini 6.7 PRO #2 | PyVESC |
| `/dev/ttyACM2` | RP2040 Touch LCD 1.28" | Serial → MicroPython |

### USB Ports — Master Pi

| Port | Device | Driver |
|------|--------|--------|
| `/dev/ttyUSB0` | Teeces32 ESP32 | JawaLite 9600 baud |

### Servo PWM Values — SG90 360° (current, temporary)

| Pulse | Effect |
|-------|--------|
| **1700µs** | STOP (actual neutral — non-standard) |
| **2000µs** | Open direction — slow (~300µs above stop) |
| **1000µs** | Close direction — fast (~700µs below stop, 2.3× faster) |

> ⚠️ SG90 360° asymmetry: close is 2.3× faster than open. Compensate via **Settings → Servo Calibration** — set `close_angle` ≈ `open_angle / 2.3`.
> This goes away when MG90S 180° standard servos are installed — they use direct angle control.

---

## 7. UART Protocol Reference

All messages follow this format over `/dev/ttyAMA0` at **115200 baud**:

```
TYPE:VALUE:CRC\n
```

CRC = XOR of all bytes in `TYPE:VALUE`.

### Message Types

| Type | Direction | Format | Description |
|------|-----------|--------|-------------|
| `H` | M→S | `H:1:CRC` | Heartbeat (every 200ms) |
| `H` | S→M | `H:OK:CRC` | Heartbeat ACK |
| `M` | M→S | `M:0.5,0.5:CRC` | Drive — left/right float [-1.0…1.0] |
| `D` | M→S | `D:0.3:CRC` | Dome motor speed float [-1.0…1.0] |
| `SRV` | M→S | `SRV:body_panel_1,1.0,500:CRC` | Servo — name, position, duration ms |
| `S` | M→S | `S:Happy001:CRC` | Play specific sound |
| `S` | M→S | `S:RANDOM:happy:CRC` | Play random sound by category |
| `S` | M→S | `S:STOP:CRC` | Stop audio |
| `V` | S→M | `V:?:CRC` | Version request |
| `V` | M→S | `V:abc123:CRC` | Version reply (git hash) |
| `T` | S→M | `T:VOLT:48.2:TEMP:32:CRC` | Telemetry |
| `DISP` | M→S | `DISP:OK:abc123:CRC` | RP2040 display command |
| `REBOOT` | M→S | `REBOOT:1:CRC` | Reboot Slave |

---

## 8. Component Notes

### Tobsun EA50-5V (5V / 10A Buck)
- Input: **10–30V** (covers 6S LiPo 22–25V)
- Output: 5V / 10A = 50W
- Used: one in body (Pi Slave + Servo HAT body), one in dome (Pi Master + Servo HAT dome)

### Tobsun EA120-12V (12V / 10A Buck)
- Input: **18–32V** (covers 6S LiPo 22–25V)
- Output: 12V / 10A = 120W
- Used: one in body (Motor HAT + Audio Amplifier)

### Capacitors on Servo HAT V+ input
- **1000µF 10V** (or 16V) electrolytic — absorbs current spikes at servo start/reverse
- **100nF** ceramic in parallel — filters high-frequency PWM noise
- Install as close as possible to the HAT V+ and GND terminals
- Only needed on servo HAT rails (shared with Pi 5V) — Motor HAT on 12V is isolated

### Pi 4B GPIO Power
The Pi 4B **is not powered by the HAT** — the HAT takes its logic power from the Pi.
Both Pi 4B units receive 5V directly from their respective buck converters via **GPIO pins 2 & 4** (bypassing USB-C).

### FSESC Mini 6.7 PRO
- Supports 4–13S LiPo — 6S 24V is well within spec
- Connect via XT90-S last (after main switch) to avoid spark on capacitor inrush
- Controlled via PyVESC over USB serial (`SetDutyCycle` commands)

### Hub Motors 250W / 24V
- Rated 250W peak — typical casual use ~20–30W each
- Double shaft — fits standard R2-D2 leg wheel mounts
- Requires soft speed ramps — hard stops risk tipping the robot

---

*For installation instructions, see [HOWTO.md](HOWTO.md).*
*For project overview and screenshots, see [README.md](README.md).*
