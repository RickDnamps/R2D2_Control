# R2-D2 Project — Claude Code Context

> Hardware complet, câblage, alimentation, I2C/GPIO → **[ELECTRONICS.md](ELECTRONICS.md)**

---

## ⚙️ Instructions Claude Code
- **Toujours committer et pusher sur GitHub après chaque modification**
- Ne jamais laisser des changements non commités en fin de session
- **Toujours terminer avec le déploiement SSH direct** via paramiko :
  ```python
  import paramiko, sys, io
  sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
  c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  c.connect('192.168.2.104', username='artoo', password='deetoo', timeout=10)
  stdin, stdout, stderr = c.exec_command('cd /home/artoo/r2d2 && bash scripts/update.sh 2>&1')
  for line in stdout: print(line, end='')
  c.close()
  ```
  > ⚠️ `sshpass` non disponible sur Windows Git Bash — toujours utiliser `paramiko`
  > ⚠️ Ne jamais git commit/push depuis le Pi — toujours depuis le PC de dev
  > ⚠️ IPs réelles : Master=`192.168.2.104`, Slave=`192.168.4.171` — ne pas utiliser `.local` (mDNS capricieux sur Windows)

- Si déploiement SSH impossible, une seule commande sur le Master :
  ```bash
  cd /home/artoo/r2d2 && git pull && bash scripts/update.sh
  ```

---

## 🎯 Vision
Système de contrôle distribué pour une réplique R2-D2 grandeur nature.
**Master Pi** (dôme) — Flask API, séquences, servos dôme, Teeces32, déploiement.
**Slave Pi** (corps) — VESCs propulsion, servos body, audio, moteur dôme, RP2040 LCD.
Communication via UART physique 115200 baud à travers le slipring.
Inspiré de [r2_control by dpoulson](https://github.com/dpoulson/r2_control).

---

## 🏗️ Structure du repo

```
r2d2/
├── master/
│   ├── main.py                  ← boot + init services
│   ├── uart_controller.py       ← heartbeat 200ms + CRC
│   ├── teeces_controller.py     ← JawaLite (random/leia/off/text/psi)
│   ├── deploy_controller.py     ← git pull + rsync + bouton dôme
│   ├── script_engine.py         ← exécuteur séquences .scr
│   ├── app_watchdog.py          ← heartbeat App↔Master 600ms
│   ├── motion_watchdog.py       ← timeout drive 800ms
│   ├── safe_stop.py             ← ramp vitesse → 0
│   ├── registry.py              ← injection dépendances Flask
│   ├── flask_app.py             ← app factory
│   ├── drivers/
│   │   ├── dome_servo_driver.py ← PCA9685 @ 0x40, speed ramp, open/close par angle
│   │   ├── dome_motor_driver.py ← envoie D: via UART
│   │   └── body_servo_driver.py ← envoie SRV: via UART
│   ├── api/                     ← Flask blueprints (audio/motion/servo/script/teeces/status)
│   ├── sequences/               ← 40 séquences .scr (CSV)
│   ├── config/
│   │   ├── dome_angles.json     ← calibrations servos dôme (gitignored — propre au robot)
│   │   ├── main.cfg             ← config principale
│   │   └── local.cfg            ← credentials WiFi/hotspot (gitignored)
│   ├── templates/index.html     ← dashboard web (6 onglets)
│   └── static/                  ← CSS + JS
├── slave/
│   ├── main.py
│   ├── uart_listener.py         ← parse CRC + callbacks
│   ├── watchdog.py              ← coupe VESC si heartbeat >500ms
│   ├── drivers/
│   │   ├── audio_driver.py      ← mpg123 + sounds_index.json
│   │   ├── display_driver.py    ← RP2040 via /dev/ttyACM2
│   │   ├── vesc_driver.py       ← pyvesc propulsion
│   │   └── body_servo_driver.py ← PCA9685 @ 0x41
│   ├── config/
│   │   └── servo_angles.json    ← calibrations servos body (gitignored — propre au robot)
│   └── sounds/sounds_index.json ← 317 sons, 14 catégories (MP3 gitignorés)
├── shared/
│   └── uart_protocol.py         ← CRC somme mod 256, build_msg(), parse_msg()
├── rp2040/firmware/             ← MicroPython : GC9A01 display, écrans BOOT/OP/LOCKED
├── android/                     ← WebView app + APK compilé
└── scripts/                     ← setup_*.sh, deploy.sh, update.sh
```

---

## 📡 Protocole UART — Checksum (somme mod 256)

**Algorithme obligatoire sur tous les messages** — bus UART traverse slipring + parasites 24V.

```python
def calc_crc(payload: str) -> str:
    return format(sum(payload.encode('utf-8')) % 256, '02X')

def build_msg(type: str, value: str) -> str:
    payload = f"{type}:{value}"
    return f"{payload}:{calc_crc(payload)}\n"

def parse_msg(raw: str) -> tuple[str, str] | None:
    parts = raw.strip().split(":")
    if len(parts) < 3: return None
    *payload_parts, received_cs = parts
    payload = ":".join(payload_parts)
    if received_cs != calc_crc(payload): return None
    return (payload_parts[0], ":".join(payload_parts[1:]))

# Exemples : build_msg("H","1") → "H:1:B3\n"  |  build_msg("M","50") → "M:50:EC\n"
```

> ⚠️ Somme arithmétique mod 256 — PAS XOR (deux octets identiques s'annulent avec XOR)
> Messages sans checksum = rejetés. Hex majuscule 2 chars (`00`–`FF`).

**Types de messages :**
```
H:1:CRC          Master→Slave heartbeat (200ms)      H:OK:CRC  ACK
M:L,R:CRC        Drive float [-1.0…1.0]
D:SPEED:CRC      Dome motor [-1.0…1.0]
S:FILE:CRC       Audio play   S:RANDOM:CAT:CRC   S:STOP:CRC
V:?:CRC          Version request    V:hash:CRC   reply
DISP:CMD:CRC     RP2040 display (BOOT/OK/ERROR/TELEM)
REBOOT:1:CRC     Reboot Slave
```

---

## 🌐 API REST Flask — port 5000

```
GET  /status                    → état JSON complet
POST /heartbeat                 ← app JS toutes les 200ms (watchdog 600ms)

POST /audio/play                {"sound": "Happy001"}
POST /audio/random              {"category": "happy"}
POST /audio/stop
POST /audio/volume              {"volume": 79}

POST /motion/drive              {"left": 0.5, "right": 0.5}
POST /motion/stop
POST /motion/dome/turn          {"speed": 0.3}
POST /motion/dome/stop
POST /motion/dome/random        {"enabled": true}

POST /servo/open                {"name": "dome_panel_1"}
POST /servo/close               {"name": "dome_panel_1"}
POST /servo/open_all  /servo/close_all
GET  /servo/list
POST /servo/settings/save       {"panels": {"dome_panel_1": {"open":110,"close":20,"speed":10}}}

POST /scripts/run               {"name": "patrol", "loop": false}
POST /scripts/stop_all
GET  /scripts/list

POST /teeces/random  /teeces/leia  /teeces/off
POST /teeces/text               {"text": "HELLO"}
POST /teeces/psi                {"mode": 1}

POST /system/update             → git pull + rsync Slave + reboot
POST /system/reboot  /system/reboot_slave
```

---

## 🎵 Audio & Teeces — Gotchas

**ALSA sur Pi 4B :**
```bash
amixer -c 0 cset numid=1 <vol>%   # ✅ seule commande qui marche
# ❌ Ne PAS utiliser : amixer sset 'Master' / sset 'PCM Playback Volume'
```
Volume UI → courbe racine cubique (exposant 1/3) : slider 50% → ALSA 79%.
**Lecture MP3 :** `mpg123 -q` — `aplay` supporte uniquement WAV/PCM.

**JawaLite (Teeces32 via /dev/ttyUSB0 @ 9600 baud) :**
```python
"0T1\r"   # animations aléatoires    "0T20\r"  # tout éteint
"0T6\r"   # mode Leia                "1MTEXTE\r" # texte FLD (max ~20 chars)
"4S1\r"   # PSI random
```

**Sons spéciaux (catégorie `special`) :** `Theme001` `Theme002` `CANTINA` `LEIA` `FAILURE` `WOLFWSTL` `Gangnam` `SWDiscoShort` `birthday`

---

## 🦾 Servos — Calibration par panneau

Chaque panneau : **O°** open (10–170), **C°** close (10–170), **S** speed (1–10).
Config sauvegardée dans `dome_angles.json` / `servo_angles.json` (gitignorés).

```python
pulse_us = 500 + (angle / 180.0) * 2000   # MG90S 180°
# Speed ramp : step 2°, delay = (10 - speed) * 3ms/step
# speed 10 = instant | speed 1 ≈ 1.2s pour 90°
```

Commande séquence avec override angle+vitesse : `servo,dome_panel_1,open,40,8`

---

## 🛠️ Directives de codage

1. **Python 3.10+** — `try/except` sur tout I/O (UART, I2C, USB)
2. **Watchdog prioritaire** — ne jamais bloquer le thread watchdog
3. **Drivers isolés** — un fichier par périphérique, interface `BaseDriver`
4. **systemd** — `Restart=always`, `RestartSec=3`
5. **Logging** Python standard — INFO prod, DEBUG dev
6. **Config par .cfg** — jamais de hardcoding adresses/pins

---

## 📦 Réseau & Dépendances

**Hostnames / IPs :**
```
R2-Master → r2-master.local / 192.168.4.1 (hotspot) / 192.168.2.104 (WiFi maison)
R2-Slave  → r2-slave.local  / 192.168.4.171
SSH user  : artoo   Password : deetoo
```

**UART Pi 4B Trixie** — libérer ttyAMA0 du Bluetooth :
```bash
echo "dtoverlay=miniuart-bt" | sudo tee -a /boot/firmware/config.txt
# ✅ miniuart-bt = BT reste fonctionnel   ❌ disable-bt = BT coupé (plus de manettes)
```

**Dépendances Master :** `flask` `pyserial` `RPi.GPIO` `adafruit-pca9685` `paramiko`
**Dépendances Slave :** `pyserial` `pyvesc` `adafruit-pca9685` `RPi.GPIO` + `mpg123` (apt)

---

## 🚀 Phases — État actuel

| Phase | Description | État |
|-------|-------------|------|
| 1 | UART + watchdog + audio + Teeces + RP2040 + déploiement | ✅ Complet |
| 2 | VESCs + moteur dôme + servos MG90S | 🔧 Code prêt — hardware en assemblage |
| 3 | 40 séquences comportementales .scr | ✅ Actif |
| 4 | API REST + dashboard web (6 onglets) + Android | ✅ Actif |
| 5 | Caméra USB + suivi personne | 📋 Planifié |

**3 watchdogs actifs :** `app_watchdog.py` 600ms · `motion_watchdog.py` 800ms · `slave/watchdog.py` 500ms → coupe VESCs

**Backlog :** DiagnosticMonitor (Teeces Show↔Diagnostic) · Amélioration UI RP2040 (`rp2040/firmware/`)

---

## 🐙 GitHub & Déploiement

```
Repo : https://github.com/RickDnamps/R2D2_Control.git   Branch : main
```

**Workflow :** `git add <fichiers> && git commit -m "Phase X.Y: desc" && git push`
→ `scripts/update.sh` sur Master déploie automatiquement (rsync slave/ + reboot Slave)

**Bouton dôme :** court = git pull + rsync + reboot Slave | long = rollback HEAD^

**Conventions commit :** `Phase X.Y:` · `Fix:` · `Config:` · `Docs:` · `ci:`

---

## 📱 Build Android

```bash
# Build APK
powershell.exe -Command "& { \$env:JAVA_HOME='C:/Program Files/Android/Android Studio/jbr'; Set-Location 'J:/R2-D2_Build/software/android'; ./gradlew.bat assembleDebug }"
cp android/app/build/outputs/apk/debug/app-debug.apk android/compiled/R2-D2_Control.apk
git add android/compiled/R2-D2_Control.apk && git commit -m "ci: update APK [skip ci]" && git push

# Installer via ADB
"C:/Users/erict/AppData/Local/Android/Sdk/platform-tools/adb.exe" install -r android/compiled/R2-D2_Control.apk
```

> ⚠️ Sync assets Android si `master/static/` ou `templates/index.html` change :
> `cp master/static/js/app.js android/app/src/main/assets/js/app.js`
> `cp master/static/css/style.css android/app/src/main/assets/css/style.css`
> `index.html` : patcher `/static/` → chemins relatifs + désactiver Service Worker
