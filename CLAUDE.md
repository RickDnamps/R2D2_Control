# R2-D2 Project — Claude Code Context

## ⚙️ Instructions Claude Code
- **Toujours committer et pusher sur GitHub après chaque modification** — `git add ... && git commit && git push`
- Ne jamais laisser des changements non commités en fin de session
- **Toujours terminer avec le déploiement SSH direct** — Claude peut déployer lui-même via paramiko :
  ```python
  import paramiko, sys, io
  sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
  c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
  c.connect('r2-master.local', username='artoo', password='deetoo', timeout=10)
  stdin, stdout, stderr = c.exec_command('cd /home/artoo/r2d2 && bash scripts/update.sh 2>&1')
  for line in stdout: print(line, end='')
  c.close()
  ```
  > ⚠️ `sshpass` non disponible sur Windows Git Bash — toujours utiliser `paramiko`
  > ⚠️ Ne jamais git commit/push depuis le Pi (pas de credentials GitHub) — toujours depuis le PC de dev
  > ⚠️ Si git commit depuis le Pi est nécessaire : `git config user.email "artoo@r2d2.local" && git config user.name "R2-Master"` puis récupérer via SFTP et push depuis PC
- Si déploiement SSH impossible, donner UNE SEULE commande à rouler sur le Master :
  ```bash
  cd /home/artoo/r2d2 && git pull && bash scripts/update.sh
  ```

---

## 🎯 Vision
Système de contrôle distribué pour une réplique R2-D2 grandeur nature.
Architecture Master/Slave sur deux Raspberry Pi communiquant via UART physique
et Wi-Fi local. Inspiré de [r2_control by dpoulson](https://github.com/dpoulson/r2_control)
pour l'API REST Flask et la structure modulaire.

---

## 🖥️ Hardware — Inventaire complet

### Master — Raspberry Pi 4B (Dôme, tourne avec le slipring)
| Composant | Interface | Détails |
|-----------|-----------|---------|
| Waveshare Servo Driver HAT | I2C 0x40 | PCA9685 16ch — servos dôme |
| Teeces32 (LEDs logics FLD/RLD/PSI) | USB `/dev/ttyUSB0` | Protocole JawaLite 9600 baud |
| Caméra | USB | Vision / suivi de personne |
| UART vers Pi 4B Slave | BCM 14/15 `/dev/ttyAMA0` | Via slipring 3.3V |

### Slave — Raspberry Pi 4B 2G (Corps, fixe)
| Composant | Interface | Détails |
|-----------|-----------|---------|
| Waveshare Motor Driver HAT | I2C 0x40 | TB6612 — moteur DC rotation dôme |
| Breakout PCA9685 | I2C 0x41 | 16ch PWM — servos body/bras/panneaux |
| FSESC Mini 6.7 PRO × 2 | USB `/dev/ttyACM0` `/dev/ttyACM1` | PyVESC — moteurs propulsion 24V |
| RP2040-Touch-LCD-1.28 (Waveshare) | USB `/dev/ttyACM2` | Écran rond 240x240 diagnostic |
| Jack audio 3.5mm intégré | Natif Pi 4B | Audio Mr Baddeley → Ampli → HP |
| UART vers Pi 4B dôme | BCM 14/15 `/dev/ttyAMA0` | Via slipring 3.3V |

> ✅ Plus besoin de MAX98357A DAC — le Pi 4B 2G a un jack 3.5mm natif
> ✅ Plus besoin de hub USB — 4 ports USB natifs suffisent
> ✅ BCM 18/19/21 libres pour usage futur

### Slipring — 12 fils (dôme tourne)
| Fils | Signal | Notes |
|------|--------|-------|
| 1-3 | 24V | 3 fils en parallèle → ~4-6A capacité totale |
| 4-6 | GND | 3 fils en parallèle |
| 7 | UART TX | R2-Slave (corps) → R2-Master (dôme) |
| 8 | UART RX | R2-Master (dôme) → R2-Slave (corps) |
| 9-12 | Spare | Réservé futur (caméra USB, etc.) |

> ✅ Seulement 24V + GND traversent le slipring — les bucks sont dans le dôme
> ✅ Fils en parallèle pour augmenter la capacité de courant sans changer le slipring

### Propulsion
- 2× Hub Motor 250W/24V (double shaft) — roues motrices (250W = pleine charge, usage réel ~20-30W chacun)
- 4× JayCreer 58mm Omni Wheels — stabilisation omnidirectionnelle
- Batterie 24V (XT60) — source principale

### Batterie recommandée
**6S LiPo 10000mAh — connecteur XT90-S**

| Spec | Valeur |
|------|--------|
| Tension nominale | 22.2V (6S × 3.7V) |
| Tension pleine charge | 25.2V (6S × 4.2V) |
| Capacité | 10 000mAh (10Ah) |
| Connecteur | **XT90-S** (anti-spark intégré — plus besoin de connecteur séparé) |
| Compatibilité VESC | ✅ FSESC Mini 6.7 PRO supporte 4-13S |
| Compatibilité bucks | ✅ 22-25V dans la plage d'entrée des bucks |

Usage prévu : maison + sorties courtes dans la rue (pas d'événements).

| Composant | Conso réelle estimée |
|-----------|---------------------|
| 2× Hub Motors 250W (usage casual ~20%) | ~50-100W |
| 2× Pi 4B + électronique | ~30W |
| Servos + LEDs + audio | ~15W |
| **Total moyen** | **~100-150W = 4-6A** |

Autonomie : **~1h30** — largement suffisant pour l'usage prévu.

> ✅ XT90-S = anti-spark intégré dans le connecteur batterie — supprime le besoin d'un connecteur XT90-S séparé dans le câblage
> ✅ 6S = standard communauté R2-D2 pour systèmes "24V"
> ❌ Éviter SLA (acide-plomb) — trop lourd pour un robot mobile
> ⚠️ Ne pas décharger sous 20% de capacité pour préserver la durée de vie

### Architecture d'alimentation
```
[BATTERIE 24V XT60]
        │
  [FUSIBLE 80A]  ← le plus proche possible du + batterie
        │
  [SWITCH PRINCIPAL]  ← interrupteur 30A+, tout couper d'un coup
        │
   ┌────┴─────────────────────────────────────────────────┐
   │                                                      │
[XT90-S]                                           [FUSIBLE 15A]
[VESC ×2]                                          [SWITCH ÉLECTRONIQUE]
(24V direct — propulsion)                                 │
                                    ┌─────────────────────┴──────────────────────┐
                                    │                                            │
                             [Corps — Slave]                       [Dôme — Master]
                                    │                           (via slipring 24V)
                   ┌────────────────┼────────────┐                      │
                   │                │            │              Buck 24V→5V/10A
            Buck 24V→5V/10A  Buck 24V→12V/5A   VESCs          → Pi Master (GPIO pins 2&4)
            → Pi Slave                →         24V direct     → Dome Servo HAT V+
              (GPIO pins 2&4)   Motor HAT TB6612               → Teeces32 LEDs (FLD/RLD/PSI)
            → Body Servo HAT V+   → Moteur dôme DC
            → RP2040 (USB Pi)   Ampli audio
                                   → HP
```

**Détail alimentation par composant :**

| Composant | Emplacement | Alimentation | Depuis |
|-----------|-------------|--------------|--------|
| Pi 4B Master | Dôme | 5V via GPIO pins 2&4 | Buck dôme 5V/10A |
| Dome Servo HAT V+ | Dôme | 5V direct | Buck dôme 5V/10A |
| Servos MG90S dôme (×11) | Dôme | 5V via HAT | Buck dôme 5V/10A |
| Teeces32 LEDs | Dôme | 5V direct | Buck dôme 5V/10A |
| Teeces32 ESP32 logique | Dôme | 5V via USB Pi Master | Pi Master |
| Pi 4B Slave | Corps | 5V via GPIO pins 2&4 | Buck corps 5V/10A |
| Body Servo HAT V+ | Corps | 5V direct | Buck corps 5V/10A |
| Servos body (bras/panneaux) | Corps | 5V via HAT | Buck corps 5V/10A |
| RP2040 display | Corps | 5V via USB Pi Slave | Pi Slave |
| Motor Driver HAT (TB6612) | Corps | 12V | Buck corps 12V/5A |
| Moteur DC rotation dôme | Corps | 12V via Motor HAT | Buck corps 12V/5A |
| Ampli audio | Corps | 12V | Buck corps 12V/5A |
| FSESC Mini 6.7 PRO ×2 | Corps | 24V direct | Batterie (via XT90-S) |

> ✅ Pi alimenté via GPIO pins 2&4 (bypass USB-C) — normal pour robot sur batterie
> ✅ Servo HAT V+ alimenté directement par le buck 5V — pas via le régulateur interne du HAT
> ✅ 24V traverse le slipring (3 fils en parallèle) → bucks dans le dôme pour le Pi Master
> ✅ Motor HAT et ampli audio dans le corps (côté Slave) sur le même buck 12V
> ⚠️ Le HAT servo a un régulateur interne — ne pas l'utiliser, alimenter V+ directement depuis le buck
> ⚠️ Pi NE s'alimente PAS depuis le HAT — le HAT prend sa logique du Pi (GPIO 3.3V/5V), pas l'inverse
> ⚠️ Ne jamais alimenter les servos MG90S en 12V — max 6V

### Sécurité électrique — composants requis

| Composant | Valeur | Emplacement | Rôle |
|-----------|--------|-------------|------|
| Fusible + holder | **80A** | Fil + batterie, le plus court possible | Protection court-circuit principal |
| Interrupteur principal | **30A+** | Après fusible 80A | Tout couper d'un coup |
| XT90-S | — | Connecteur batterie (intégré) | Anti-spark condensateurs VESC |
| Fusible + holder | **15A** | Branche électronique (bucks) | Protection Pi/servos |
| Interrupteur secondaire | **10A** | Branche électronique | Allumer électronique séparément |

### Bucks DC-DC — modèles retenus

| Buck | Modèle | I/O | Ampérage | Emplacement | Alimente |
|------|--------|-----|----------|-------------|---------|
| Corps 5V | Tobsun EA50-5V | 10-30V → 5V | 10A | Corps | Pi Slave (GPIO) + Body Servo HAT + RP2040 |
| Corps 12V | Tobsun EA120-12V | 18-32V → 12V | 10A | Corps | Motor Driver HAT (moteur dôme) + Ampli audio |
| Dôme 5V | Tobsun EA50-5V | 10-30V → 5V | 10A | Dôme | Pi Master (GPIO) + Dome Servo HAT + Teeces32 LEDs |

> ✅ 6S LiPo 22-25V dans la plage des deux modèles (EA50: 10-30V / EA120: 18-32V)

### Liste d'achat — composants en attente

| Composant | Qté | Spec | Usage |
|-----------|-----|------|-------|
| MG90S servo 180° | 10 | 4.8-6V, engrenages métal | Remplacement SG90 360° dôme + body |
| Condensateur électrolytique | 2 | **1000µF 10V** (ou 16V) | Filtrage rail 5V — entrée V+ Servo HAT dôme + body |
| Condensateur céramique | 2 | **100nF** | Filtrage HF en parallèle avec les 1000µF |

> ✅ Condensateurs sur entrée V+ Servo HAT uniquement (même rail que Pi) — Motor HAT sur 12V séparé, pas nécessaire
> ✅ 1000µF électrolytique : absorbe les pics de courant servo au démarrage/inversion
> ✅ 100nF céramique en parallèle : filtre les hautes fréquences générées par les PWM

### ⚠️ Procédure de mise sous tension (ordre obligatoire)
```
1. Switch principal OFF, XT90-S déconnecté
2. Brancher la batterie
3. Activer switch principal → Pi + servos s'allument
4. Attendre boot Pi (30s) — vérifier que tout est OK
5. Connecter XT90-S → VESCs s'alimentent sans arc (anti-spark intégré)
```

### ⚠️ Procédure d'arrêt
```
1. Couper les VESCs (logiciel ou déconnecter XT90-S)
2. Switch principal OFF
3. Déconnecter batterie si stockage
```

> ✅ XT90-S : anti-spark intégré (résistance interne charge les condensateurs avant contact complet)
> ✅ Motor Driver HAT (TB6612) : entrée 12V sur VIN, passe directement au moteur (pas de régulation)
> ✅ Servos MG90S : 4.8-6V, torque métal, remplacement des SG90 360° — commandes identiques
> ⚠️ Ne jamais connecter les VESCs sans XT90-S — risque d'arc et dommages condensateurs
> ⚠️ Fusible 80A le plus court possible du + batterie — en cas de court-circuit le fil fond avant le fusible si trop long
> ⚠️ Vérifier le voltage exact du moteur dôme DC avant de choisir 12V ou autre tension
> ⚠️ Ne jamais alimenter les servos MG90S en 12V directement — max 6V
> ⚠️ SG90 360° asymétrie vitesse : stop réel ≈1700µs (non-standard) → open (2000µs) 2.3× plus lent que close (1000µs)
>    Compenser via close_angle < open_angle dans Settings → SERVO CALIBRATION
>    MG90S standard 180° n'auront pas ce problème — contrôle par angle direct

---

## 📡 Protocole UART Master ↔ Slave

### Format des messages
```
TYPE:VALEUR\n          # message simple
TYPE:VALEUR:CRC\n      # message avec checksum (XOR des bytes)
```

### Types de messages définis
```python
# Heartbeat (Master → Slave, toutes les 200ms)
"H:1:CRC\n"           # Master envoie
"H:OK:CRC\n"          # Slave ACK immédiat

# Mouvement propulsion (Master → Slave)
"M:LEFT,RIGHT:CRC\n"  # float [-1.0…+1.0], ex: "M:0.500,0.500:CRC\n"
"M:0.000,0.000:CRC\n" # arrêt

# Moteur dôme DC (Master → Slave)
"D:SPEED:CRC\n"       # float [-1.0…+1.0], ex: "D:0.300:CRC\n"
"D:0.000:CRC\n"       # arrêt dôme

# Servos body (Master → Slave)
"SRV:NAME,POS,DUR:CRC\n"  # ex: "SRV:utility_arm_left,1.000,500:CRC\n"
                           # POS = float [0.0…1.0], DUR = int ms

# Audio (Master → Slave)
"S:FILENAME:CRC\n"         # ex: "S:Happy001:CRC\n"
"S:RANDOM:CATEGORY:CRC\n"  # ex: "S:RANDOM:happy:CRC\n"
"S:STOP:CRC\n"             # arrêt audio

# Version sync (bidirectionnel)
"V:?:CRC\n"           # Slave demande version au Master
"V:abc123:CRC\n"      # Réponse Master avec hash git

# Telemetry (Slave → Master, futur)
"T:VOLT:48.2:TEMP:32:CRC\n"

# Status display RP2040 (Master → Slave → RP2040)
"DISP:BOOT:CRC\n"
"DISP:SYNCING:abc123:CRC\n"
"DISP:OK:abc123:CRC\n"
"DISP:ERROR:MASTER_OFFLINE:CRC\n"
"DISP:TELEM:48.2V:32C:CRC\n"

# Reboot Slave (Master → Slave)
"REBOOT:1:CRC\n"
```

### Watchdog Slave (CRITIQUE — sécurité)
- Master envoie `H:1` toutes les **200ms**
- Slave coupe les VESC si aucun heartbeat reçu après **500ms**
- Slave envoie confirmation `H:OK\n` à chaque heartbeat reçu

---

## 🌐 API REST Flask (sur Master Pi 4B) — Phase 4
Inspirée de r2_control par dpoulson. Port **5000**.
Structure modulaire via **Flask Blueprints** dans `master/api/`.
Injection de dépendances via `master/registry.py`.

### Blueprints disponibles
| Fichier | Prefix | Description |
|---------|--------|-------------|
| `audio_bp.py`  | `/audio`   | Proxy audio → Slave via UART |
| `motion_bp.py` | `/motion`  | Propulsion + dôme |
| `servo_bp.py`  | `/servo`   | Servos body |
| `script_bp.py` | `/scripts` | Séquences .scr |
| `teeces_bp.py` | `/teeces`  | LEDs Teeces32 (local Master) |
| `status_bp.py` | —          | État système + commandes système |

### Endpoints
```
GET  /status                    → état complet JSON (heartbeat, version, uptime, drivers)
GET  /audio/categories          → liste catégories + nb sons
POST /audio/play                {"sound": "Happy001"}
POST /audio/random              {"category": "happy"}
POST /audio/stop

POST /motion/drive              {"left": 0.5, "right": 0.5}
POST /motion/arcade             {"throttle": 0.5, "steering": 0.0}
POST /motion/stop
GET  /motion/state
POST /motion/dome/turn          {"speed": 0.3}
POST /motion/dome/stop
POST /motion/dome/random        {"enabled": true}

POST /servo/move                {"name": "utility_arm_left", "position": 1.0, "duration": 500}
POST /servo/open                {"name": "utility_arm_left"}
POST /servo/close               {"name": "utility_arm_left"}
POST /servo/open_all
POST /servo/close_all
GET  /servo/list
GET  /servo/state

POST /scripts/run               {"name": "patrol", "loop": false}
POST /scripts/stop              {"id": 3}
POST /scripts/stop_all
GET  /scripts/list
GET  /scripts/running

POST /teeces/random
POST /teeces/leia
POST /teeces/off
POST /teeces/text               {"text": "HELLO"}
POST /teeces/psi                {"mode": 1}

POST /system/reboot             → reboot Master
POST /system/reboot_slave       → envoie REBOOT: via UART
POST /system/shutdown
```

### Dashboard Web
- URL : `http://192.168.4.1:5000` ou `http://r2-master.local:5000`
- Templates : `master/templates/index.html`
- CSS/JS : `master/static/css/style.css`, `master/static/js/app.js`
- Thème dark bleu R2-D2, responsive, compatible mobile
- Contrôles clavier WASD/flèches pour la propulsion
- Polling status toutes les 2s (pas de Socket.io — REST pur)

---

## 🔄 Système de déploiement (Single Source of Truth)

### Flow complet
```
1. Bouton dôme appui court  → Master: git pull
2. Master: rsync /slave/ → artoo@r2-slave.local via SSH/Wi-Fi local
3. Master: envoie "REBOOT\n" via UART
4. Slave reboot
5. Au boot Slave:
   a. Lire /home/artoo/r2d2/VERSION (git hash local)
   b. Envoyer "V:?\n" au Master via UART
   c. Master répond "V:abc123\n"
   d. Si identique → démarrer app principale
   e. Si différent  → re-déclencher rsync (max 3 tentatives)
   f. Si Master injoignable → mode dégradé (démarrer version actuelle)
                            → afficher erreur sur RP2040 et Teeces32
```

### Bouton physique dôme
```python
BUTTON_SHORT_PRESS = "git pull + rsync + reboot"   # < 2 secondes
BUTTON_LONG_PRESS  = "rollback git checkout HEAD^"  # > 2 secondes
```

### Fichier VERSION
```bash
# Généré automatiquement après chaque git pull
git rev-parse --short HEAD > /home/artoo/r2d2/VERSION
```

---

## 📺 RP2040 Écran Diagnostic (Waveshare Touch LCD 1.28)

### États affichés
| Commande UART | Affichage | Couleur |
|--------------|-----------|---------|
| `DISP:BOOT` | Splash R2-D2 | Blanc |
| `DISP:SYNCING:v1` | Spinner + versions | Orange |
| `DISP:OK:v1` | Libère vers écran principal | Vert |
| `DISP:ERROR:MASTER_OFFLINE` | Alerte bloquante | Rouge |
| `DISP:TELEM:48V:32C` | Jauge batterie + temp | Bleu |

### Navigation tactile
- TAP = action primaire
- SWIPE = changer d'écran
- HOLD 2s = action critique (arrêt d'urgence)
- Double TAP = retour accueil

### Firmware RP2040
- Language: **MicroPython** avec LVGL ou dessin direct GC9A01
- Reçoit commandes via USB serial depuis R2-Slave
- Autonome — ne nécessite pas de mise à jour fréquente

---

## 🎵 Audio & Teeces

### Teeces32 — Alertes visuelles sur logics dôme
```python
# Commandes JawaLite envoyées via /dev/ttyUSB0 à 9600 baud
"0T1\r"              # Animations aléatoires (mode normal)
"0T20\r"             # Tout éteint
"0T6\r"              # Mode Leia
"1MALERTE MASTER\r"  # Texte défilant sur FLD (max ~20 chars)
"4S1\r"              # PSI random
```

### Sons R2-D2 (issus de r2_control by dpoulson + extras)
- **317 sons MP3** stockés sur R2-Slave : `/home/artoo/r2d2/slave/sounds/`
- **Index** : `slave/sounds/sounds_index.json` — **14 catégories**
- Lecture : `aplay` via subprocess (jack 3.5mm natif Pi 4B)
- Driver : `slave/drivers/audio_driver.py`

| Catégorie | Nb sons | Prefix fichier |
|-----------|---------|----------------|
| alarm     | 11 | `ALARM` |
| happy     | 20 | `Happy` |
| hum       | 25 | `HUM__` |
| misc      | 36 | `MISC_` |
| proc      | 15 | `PROC_` |
| quote     | 47 | `Quote` |
| razz      | 23 | `RAZZ_` |
| sad       | 20 | `Sad__` |
| sent      | 20 | `SENT_` |
| ooh       | 7  | `OOH__` |
| whistle   | 25 | `WHIST` |
| scream    | 4  | `SCREA` |
| special   | 53 | (noms uniques) |
| extra     | 11 | `R2FREE` ← sons libres ajoutés manuellement sur le Pi |

> ⚠️ Catégorie `extra` : fichiers R2FREE001-011.mp3 présents physiquement sur le Pi uniquement (gitignorés)
> Si le Slave est réinstallé, re-télécharger :
> ```bash
> cd /tmp && wget -q -O r.zip 'https://www.orangefreesounds.com/wp-content/uploads/Zip/R2D2-sounds.zip'
> unzip r.zip && for i in $(seq 1 10); do cp "/tmp/r2d2_orange/r2d2 sound-${i}.mp3" ~/r2d2/slave/sounds/R2FREE00${i}.mp3; done
> wget -q -O ~/r2d2/slave/sounds/R2FREE011.mp3 'https://www.freesoundslibrary.com/wp-content/uploads/2021/06/r2-d2-sound.zip'
> ```

Sons spéciaux disponibles dans la catégorie `special` (noms exacts) :
`Theme001` `Theme002` `CANTINA` `LEIA` `FAILURE` `WOLFWSTL` `SCREA001` `Gangnam` `SWDiscoShort` `birthday` `ALARM003` `SCREA003`

Commandes UART audio :
```
S:Happy001:CRC        → joue le fichier spécifique
S:RANDOM:happy:CRC    → son aléatoire de la catégorie
S:STOP:CRC            → coupe le son en cours
```

---

## 🏗️ Structure du repo

```
r2d2/
├── CLAUDE.md                    ← CE FICHIER (contexte Claude Code)
├── HOWTO.md                     ← Guide installation phases 1-4
├── VERSION                      ← git hash courant
├── shared/
│   ├── uart_protocol.py         ← CRC XOR, build_msg, parse_msg
│   └── base_driver.py           ← interface BaseDriver
├── master/
│   ├── main.py                  ← boot + blocs Phase 2/3/4 commentés
│   ├── uart_controller.py       ← heartbeat 200ms + read loop + CRC
│   ├── teeces_controller.py     ← JawaLite (random/leia/off/text/psi)
│   ├── deploy_controller.py     ← git pull + rsync + bouton dôme
│   ├── registry.py              ← injection de dépendances Flask ← Phase 4
│   ├── flask_app.py             ← app factory Flask               ← Phase 4
│   ├── script_engine.py         ← exécuteur de scripts .scr       ← Phase 3
│   ├── drivers/                                                    ← Phase 2
│   │   ├── vesc_driver.py       ← envoie M: via UART
│   │   ├── dome_motor_driver.py ← envoie D: via UART + mode random
│   │   └── body_servo_driver.py ← envoie SRV: via UART
│   ├── api/                                                        ← Phase 4
│   │   ├── audio_bp.py          ← POST /audio/play|random|stop
│   │   ├── motion_bp.py         ← POST /motion/drive|arcade|dome/*
│   │   ├── servo_bp.py          ← POST /servo/move|open|close
│   │   ├── script_bp.py         ← POST /scripts/run|stop
│   │   ├── teeces_bp.py         ← POST /teeces/random|leia|text
│   │   └── status_bp.py         ← GET /status + POST /system/*
│   ├── scripts/                                                    ← Phase 3 — 40 scripts
│   │   ├── (26 scripts dpoulson fidèles)   ← theme, march, leia, evil, malfunction, cantina...
│   │   └── (14 scripts customs)            ← patrol, celebrate, startup, excited, scan, disco...
│   ├── templates/
│   │   └── index.html           ← dashboard web dark theme         ← Phase 4
│   ├── static/
│   │   ├── css/style.css        ← thème dark bleu R2-D2            ← Phase 4
│   │   └── js/app.js            ← contrôles + polling REST 2s      ← Phase 4
│   ├── config/
│   │   ├── main.cfg             ← config principale
│   │   ├── local.cfg.example    ← template config personnelle
│   │   └── config_loader.py     ← charge main.cfg + overlay local.cfg
│   └── services/
│       ├── r2d2-master.service  ← systemd
│       └── r2d2-monitor.service ← watchdog systemd
├── slave/
│   ├── main.py                  ← boot + blocs Phase 2 commentés
│   ├── uart_listener.py         ← parse CRC + dispatcher callbacks
│   ├── watchdog.py              ← coupe VESC si heartbeat >500ms
│   ├── version_check.py         ← V:? → compare → rsync si mismatch
│   ├── drivers/
│   │   ├── audio_driver.py      ← aplay MP3 + sounds_index.json   ← Phase 1
│   │   ├── display_driver.py    ← RP2040 via /dev/ttyACM2          ← Phase 1
│   │   ├── vesc_driver.py       ← pyvesc VESC propulsion           ← Phase 2
│   │   └── body_servo_driver.py ← PCA9685 I2C servos body          ← Phase 2
│   ├── sounds/
│   │   ├── sounds_index.json    ← 14 catégories, 317 sons (306 dpoulson + 11 R2FREE extras)
│   │   └── *.mp3                ← fichiers audio (gitignored — présents sur Pi uniquement)
│   └── services/
│       ├── r2d2-slave.service   ← systemd
│       └── r2d2-version.service ← validation version au boot
├── rp2040/
│   └── firmware/
│       ├── main.py              ← MicroPython firmware
│       ├── display.py           ← rendu GC9A01
│       └── touch.py             ← CST816S touch handler
└── scripts/
    ├── deploy.sh                    ← rsync Slave + install vendor + reboot
    ├── setup_master_network.sh      ← réseau Master : lit WiFi maison, configure hotspot wlan0 + wlan1
    ├── setup_slave_network.sh       ← réseau Slave : connecte wlan0 au hotspot Master
    ├── setup_ssh_keys.sh            ← génère + copie clés Ed25519
    └── vendor_deps.sh               ← pip download → slave/vendor/
```

---

## 🛠️ Directives de codage

### Règles absolues
1. **Python 3.10+** partout
2. **Gestion d'erreurs stricte** — try/except sur tout I/O (UART, I2C, USB)
3. **Watchdog prioritaire** — le watchdog ne peut jamais être bloqué
4. **Drivers isolés** — un fichier par périphérique, interface commune
5. **systemd** pour tous les services — `Restart=always`, `RestartSec=3`
6. **Logging** — `logging` Python standard, niveau INFO en prod, DEBUG en dev
7. **Config par fichiers .cfg** — jamais de hardcoding d'adresses/pins

### Interface commune des drivers
```python
class BaseDriver:
    def setup(self) -> bool: ...      # init hardware, retourne False si échec
    def shutdown(self) -> None: ...   # arrêt propre
    def is_ready(self) -> bool: ...   # état du driver
```

### Conventions UART
```python
MSG_TERMINATOR = "\n"
MSG_SEPARATOR  = ":"
HEARTBEAT_INTERVAL_MS = 200
WATCHDOG_TIMEOUT_MS   = 500
BAUD_RATE = 115200
```

### Protocole CRC — Checksum XOR obligatoire sur tous les messages

Le bus UART traverse un slipring — risque de bit flip. Chaque message
doit inclure un CRC (XOR de tous les bytes du payload avant le CRC).

**Format :**
```
TYPE:VALEUR:CRC\n
```

**Calcul du CRC (XOR de tous les bytes du payload) :**
```python
def calc_crc(payload: str) -> str:
    """
    payload = tout ce qui est avant le dernier ':'
    ex: pour "M:50:CRC"  → payload = "M:50"
    ex: pour "H:1:CRC"   → payload = "H:1"
    """
    crc = 0
    for byte in payload.encode("utf-8"):
        crc ^= byte
    return format(crc, '02X')  # retourne hex sur 2 chars ex: "3F"

def build_msg(type: str, value: str) -> str:
    payload = f"{type}:{value}"
    return f"{payload}:{calc_crc(payload)}\n"

def parse_msg(raw: str) -> tuple[str, str] | None:
    """
    Retourne (type, value) si CRC valide, None si invalide.
    Rejette silencieusement les messages corrompus.
    """
    raw = raw.strip()
    parts = raw.split(":")
    if len(parts) < 3:
        return None                          # format invalide
    *payload_parts, received_crc = parts
    payload = ":".join(payload_parts)
    expected_crc = calc_crc(payload)
    if received_crc != expected_crc:
        logging.warning(f"CRC mismatch: got {received_crc}, expected {expected_crc} for '{payload}'")
        return None                          # message corrompu, ignoré
    msg_type = payload_parts[0]
    msg_value = ":".join(payload_parts[1:])
    return (msg_type, msg_value)

# Exemples de messages valides générés
build_msg("M", "50")          # → "M:50:72\n"
build_msg("H", "1")           # → "H:1:43\n"
build_msg("S", "01")          # → "S:01:6C\n"
build_msg("V", "abc123")      # → "V:abc123:XX\n"

# Messages multi-valeurs (ex: drive différentiel)
build_msg("M", "LEFT:50:RIGHT:30")  # → "M:LEFT:50:RIGHT:30:XX\n"
# Note: parse_msg gère les valeurs composées correctement
# car seul le DERNIER segment est le CRC
```

**Règles :**
- Messages sans CRC = rejetés (sauf pendant la phase de boot initiale)
- CRC en hexadécimal majuscule sur 2 caractères (`00` à `FF`)
- En cas de 3 messages invalides consécutifs → logger une alerte
- Le Watchdog heartbeat `H:1:CRC\n` doit toujours passer — si 3 CRC
  invalides consécutifs sur heartbeat → considérer le bus comme bruité
  et loguer un warning (mais NE PAS couper les VESC pour un bus bruité,
  seulement pour un heartbeat absent)

### Gestion des versions
```python
VERSION_FILE = "/home/artoo/r2d2/VERSION"   # sur les deux Pi
VERSION_REQUEST = "V:?\n"
VERSION_RESPONSE_PREFIX = "V:"
MAX_SYNC_RETRIES = 3
SYNC_RETRY_BACKOFF_S = [5, 15, 30]  # backoff exponentiel
```

---

## 📦 Dépendances Python

### Hostnames et IPs
```
R2-Master  →  Pi 4B 4G  (Dôme)    →  r2-master.local  /  192.168.4.1 (fixe, hotspot)
R2-Slave   →  Pi 4B 2G  (Corps)   →  r2-slave.local   /  192.168.4.x (DHCP Master)
```

Configurer les hostnames via **Raspberry Pi Imager** (⚙️ Options) avant de graver la SD.
Résolution `.local` assurée par **avahi-daemon** (installé par les scripts réseau).

### UART sur Pi 4B Trixie — Libérer ttyAMA0

Par défaut sur Trixie, le Bluetooth occupe `/dev/ttyAMA0`. Ajouter dans `/boot/firmware/config.txt` :
```
dtoverlay=miniuart-bt
```
> ⚠️ Utiliser **`miniuart-bt`** et NON `disable-bt` — `miniuart-bt` déplace le BT sur le mini UART, ttyAMA0 est libéré pour GPIO 14/15, **le Bluetooth reste fonctionnel** (manettes Switch Pro, Xbox, etc.)
> `disable-bt` = BT complètement coupé → plus de manettes sans fil
> ⚠️ Ne pas avoir les deux lignes en même temps dans config.txt — si `disable-bt` et `miniuart-bt` sont présents, supprimer `disable-bt` :
> `sudo sed -i '/dtoverlay=disable-bt/d' /boot/firmware/config.txt`

```bash
# Sur les deux Pi (Master et Slave)
echo "dtoverlay=miniuart-bt" | sudo tee -a /boot/firmware/config.txt
sudo reboot
# Vérifier après reboot :
ls /dev/ttyAMA0   # doit exister
```

### Username
```
Username sur les deux Pi : artoo
Configurer via Raspberry Pi Imager → ⚙️ Options → Username: artoo
```

Utilisation dans les scripts :
```python
MASTER_HOST = "r2-master.local"
SLAVE_HOST  = "r2-slave.local"
MASTER_IP   = "192.168.4.1"   # IP fixe wlan0 Master (hotspot)
SLAVE_IP    = "192.168.4.x"   # DHCP attribué par NetworkManager Master
SSH_USER    = "artoo"
```

### SSH sans mot de passe — Clés SSH (obligatoire pour rsync automatique)
```
⚠️ NE PAS utiliser un mot de passe vide — utiliser des clés SSH
⚠️ NE PAS utiliser l'username 'pi' — utiliser 'artoo'

Principe :
  R2-Master génère une paire de clés Ed25519
  La clé publique est copiée sur R2-Slave
  R2-Master peut SSH/rsync vers R2-Slave sans mot de passe
  Nécessaire pour : rsync automatique au boot, bouton dôme,
                    reboot Slave depuis Master

Setup (une seule fois sur R2-Master) :
```bash
# 1. Générer la paire de clés sur R2-Master
ssh-keygen -t ed25519 -C "r2-master" -f ~/.ssh/id_ed25519 -N ""
# -N "" = passphrase vide sur la CLÉ (≠ mot de passe du compte artoo)
# La clé reste sécurisée — seul R2-Master peut s'en servir

# 2. Copier la clé publique vers R2-Slave (une seule fois manuellement)
ssh-copy-id artoo@r2-slave.local

# 3. Tester
ssh artoo@r2-slave.local
# → connexion sans mot de passe ✅

# 4. Après ça, le rsync est 100% automatique
rsync -av /home/artoo/r2d2/slave/ artoo@r2-slave.local:/home/artoo/r2d2/
```
```

### Réseau — Architecture finale

```
R2-MASTER (Pi 4B 4G — Dôme)
  wlan0  → Hotspot permanent          192.168.4.1   SSID dans local.cfg [hotspot]
  wlan1  → WiFi maison (clé USB)      DHCP          SSID dans local.cfg [home_wifi]

R2-SLAVE (Pi 4B 2G — Corps)
  wlan0  → Client du hotspot Master   192.168.4.x   (DHCP attribué par Master)
  (pas de wlan1 — le Slave n'a pas besoin d'internet directement)
```

### Configuration réseau — Outil : NetworkManager (Trixie)

Raspberry Pi OS Trixie utilise **NetworkManager** (pas wpa_supplicant + hostapd).
Toute la configuration réseau se fait via `nmcli`.

```bash
# Vérifier l'état réseau
nmcli device status
# wlan0  wifi  connecté  r2d2-hotspot      ← Master
# wlan1  wifi  connecté  r2d2-internet     ← Master

# Connexions NetworkManager créées par les scripts
nmcli connection show
# r2d2-hotspot       → wlan0, mode AP, ipv4.method shared, autoconnect prio 100
# r2d2-internet      → wlan1, client WiFi maison, autoconnect prio 10
# r2d2-master-hotspot → wlan0 Slave, client hotspot Master, autoconnect prio 100
```

### Scripts d'installation réseau

| Script | Exécuté sur | Ce qu'il fait |
|--------|-------------|---------------|
| `setup_master_network.sh` | R2-Master | Lit WiFi maison → demande SSID/password hotspot → sauvegarde local.cfg → configure wlan0 AP + wlan1 client |
| `setup_slave_network.sh`  | R2-Slave  | Demande SSID/password hotspot Master → configure wlan0 client hotspot |

> ⚠️ **Ordre obligatoire : Master TOUJOURS en premier.**
> Le hotspot Master doit exister avant de configurer le Slave.

### local.cfg — Sections réseau

```ini
[home_wifi]
ssid     = TON_WIFI_MAISON     # rempli automatiquement par setup_master_network.sh
password = TON_MOT_DE_PASSE    # lu depuis NetworkManager au moment du setup

[hotspot]
ssid     = R2D2_Control        # SSID du hotspot R2-D2 (personnalisable)
password = r2d2droid           # mot de passe WPA (min 8 chars, personnalisable)
```

Les deux sections sont remplies automatiquement par `setup_master_network.sh`.
Le password hotspot est demandé interactivement (défaut `r2d2droid`).
Le mot de passe hotspot doit ensuite être saisi manuellement sur le Slave.

### Séquence de boot Master
```
1. NetworkManager démarre wlan0 en mode AP (autoconnect prio 100 — toujours)
2. NetworkManager tente wlan1 → WiFi maison (autoconnect prio 10)
3. master/main.py : si wlan1 a une IP → git pull (timeout 30s, non bloquant)
4. Mettre à jour VERSION si pull réussi
5. Démarrer app principale (UART + Teeces + Flask si Phase 4 activée)
```

### Séquence de boot Slave
```
1. NetworkManager démarre wlan0 → connexion au hotspot Master (autoconnect prio 100)
2. Obtient IP 192.168.4.x via DHCP (géré par NetworkManager Master)
3. slave/main.py démarre : UART listener → Watchdog → Audio → ...
```

**Bouton dôme — logique complète :**
```python
BUTTON_PIN = XX  # BCM à définir (configuré dans local.cfg [deploy] button_pin)

# Appui court (< 2s) :
#   Si wlan1 dispo  → git pull + rsync + reboot Slave
#   Si wlan1 absent → rsync version locale + reboot Slave
#                     (utile pour forcer re-sync sans internet)

# Appui long (> 2s) :
#   → git checkout HEAD^ (rollback)
#   → rsync version précédente + reboot Slave

# Double appui :
#   → afficher version courante sur Teeces32 et RP2040
```

### Master (Pi 4B)
```
flask             # API REST + dashboard web (Phase 4)
flask-socketio    # (prévu — non utilisé Phase 4 actuelle, REST polling)
pyserial          # UART + Teeces32 USB
RPi.GPIO          # bouton dôme
adafruit-pca9685  # Servo Driver HAT dôme (Phase 2)
paramiko          # SSH pour rsync
```

### Slave (Pi 4B 2G corps)
```
pyserial          # UART Master + VESC USB + RP2040 USB
pyvesc            # contrôle VESC (Phase 2)
adafruit-pca9685  # PCA9685 body (I2C 0x41) (Phase 2)
RPi.GPIO          # GPIO général
# Audio : aplay out of the box — jack 3.5mm natif Pi 4B, pas de lib supplémentaire
```

---

## 🔌 Adresses I2C

| Bus | Adresse | Composant | Pi |
|-----|---------|-----------|-----|
| I2C-1 | 0x40 | Servo Driver HAT (servos dôme) | R2-Master Pi 4B 4G |
| I2C-1 | 0x40 | Motor Driver HAT (moteur DC dôme) | R2-Slave Pi 4B 2G |
| I2C-1 | 0x41 | Breakout PCA9685 (servos body) | R2-Slave Pi 4B 2G |

---

## 🔧 Pins GPIO

### Pi 4B 2G (Corps — Slave)
| BCM | Fonction |
|-----|----------|
| 2 | I2C SDA |
| 3 | I2C SCL |
| 14 | UART TX → slipring → Pi 4B dôme RX |
| 15 | UART RX ← slipring ← Pi 4B dôme TX |
| 18/19/21 | Libres (plus besoin I2S) |
| Jack 3.5mm | Audio natif → Ampli → Haut-parleurs |

### Pi 4B 4G (Dôme — Master)
| BCM | Fonction |
|-----|----------|
| 2 | I2C SDA |
| 3 | I2C SCL |
| 14 | UART TX → slipring → R2-Slave RX |
| 15 | UART RX ← slipring ← R2-Slave TX |
| XX | Bouton dôme (à définir) |

### ⚠️ CÂBLAGE UART — TOUJOURS CROISER TX→RX
```
CORRECT ✅
R2-Master BCM14 (TX) ──→ BCM15 (RX) R2-Slave
R2-Master BCM15 (RX) ←── BCM14 (TX) R2-Slave
R2-Master GND        ─── GND         R2-Slave

INCORRECT ❌ (ne fonctionnera jamais)
R2-Master BCM14 (TX) ──→ BCM14 (TX) R2-Slave
R2-Master BCM15 (RX) ──→ BCM15 (RX) R2-Slave
```
TX d'un côté = toujours sur RX de l'autre. Règle physique universelle.

---

## 🚀 Ordre de développement (Phases)

### Phase 1 — Infrastructure ✅ Code complet + validé sur bench
- [x] **1.1** Hotspot Wi-Fi Pi 4B (`wlan0`) + clé USB internet (`wlan1`)
- [x] **1.2** SSH sans mot de passe R2-Master → R2-Slave
- [x] **1.3** UART + Heartbeat 200ms + **Watchdog 500ms** — ✅ validé sur bench (BCM14/15 directement)
- [x] **1.4** Validation version au boot — Master répond à `V:?` avec hash git local
- [x] **1.5** Bouton dôme (update/rollback/double-appui)
- [x] **1.6** Écran RP2040 boot/sync/erreur/telemetry
- [x] **1.7** Teeces32 JawaLite (random/leia/off/text/psi)
- [x] **1.8** Audio 306 sons MP3 — `sounds_index.json` dans git, MP3 gitignorés
- [ ] Validation sur hardware réel (UART slipring physique)
> ⚠️ Slipring non encore reçu — tests UART à faire sur breadboard bench (connexion directe BCM14/15)
> ⚠️ Les services systemd `r2d2-master.service` et `r2d2-slave.service` sont `enabled` — les stopper manuellement avant `test_uart.sh` :
> ```bash
> sudo systemctl stop r2d2-master.service r2d2-monitor.service
> ssh artoo@r2-slave.local "sudo systemctl stop r2d2-slave.service"
> ```

### Sécurité — 3 couches indépendantes ✅ Actives dès Phase 4

| Fichier | Rôle | Timeout | Déclencheur |
|---------|------|---------|-------------|
| `master/app_watchdog.py` | Heartbeat App↔Master | **600ms** | App crash / perte WiFi / écran éteint |
| `master/motion_watchdog.py` | Timeout commande drive | **800ms** | Plus de cmd drive pendant mouvement |
| `slave/watchdog.py` | Heartbeat Master↔Slave | **500ms** | Master crash / UART coupé |

**Arrêt progressif (`master/safe_stop.py`) :**
- Ramp vitesse courante → 0 proportionnelle à la vitesse (max 400ms à vitesse 1.0)
- Vitesse 0.5 → 200ms / vitesse <0.08 → arrêt immédiat
- `cancel_ramp()` appelé à chaque nouvelle commande drive (reconnexion app)
- Tous les watchdogs utilisent `safe_stop` — jamais de `M:0,0` brut pendant le mouvement

**Heartbeat applicatif (`POST /heartbeat`) :**
- App JS envoie `fetch('/heartbeat', {method:'POST'})` toutes les **200ms**
- Android `onPause()` envoie stop natif HTTP (écran éteint → WebView figé)
- `beforeunload` envoie stop + dome/stop (fermeture onglet navigateur)
- `AppWatchdog.feed()` alimenté dans `status_bp.py`

**Joystick keep-alive :**
- `setInterval` 200ms pendant que joystick est tenu (doigt immobile = plus de touchmove)
- `clearInterval` sur `_release()` pour éviter fuites mémoire

**Pills dashboard :**
- **HB** = `app_watchdog.is_connected` → heartbeat **App ↔ Master**
- **UART** = serial `is_open` + `_running` → lien **Master ↔ Slave**

### ⚠️ Types de servos — VÉRIFIER AVANT D'ACHETER

Il existe deux types de SG90 **visuellement identiques** — se tromper de type est une erreur courante :

| | SG90 Standard 0-180° | SG90 360° / CR (rotation continue) |
|---|---|---|
| Butée mécanique | ✅ Oui (0° et 180°) | ❌ Non — tourne librement |
| Potentiomètre | Variable (mesure la position) | Remplacé par résistances fixes |
| Commande | Angle direct (`write(70)` → va à 70°) | Vitesse + durée (pas de position) |
| Pulse 1500µs | 90° (centre) | Stop (neutre) |
| Pulse 2000µs | ~165° | Tourne en sens A en continu |
| Pulse 1000µs | ~15° | Tourne en sens B en continu |
| Usage R2-D2 | ✅ Recommandé — précis et simple | Possible mais calibration par durée |

**Comment identifier son type :**
Essaie de tourner l'axe du servo à la main au-delà de 180° :
- **Résistance / blocage mécanique** → SG90 standard 0-180° ✅
- **Tourne librement à 360°** → SG90 rotation continue ⚠️

**Le "90" dans "SG90" :** désigne le point milieu (pulse 1500µs = position 90°), PAS la plage.
Un SG90 standard va de 0° à 180°. Le "SG90 360°" est un abus de nomenclature.

**Pour acheter les bons :** chercher "SG90 servo **180 degree**" ou "SG90 **standard**" — éviter "360°", "continuous rotation", "CR".

**Projet actuel :** Remplacement en cours — **10× MG90S commandés** (180° standard, engrenages métal).
- SG90 360° (rotation continue) encore en place pendant la transition
- SG90 360° : stop réel ≈1700µs (non-standard) → vitesse close 2.3× > vitesse open → compenser via `close_angle < open_angle` dans Settings
- MG90S 180° : contrôle par angle direct, symétrique, précis → le code passera à `pulse_us = 500 + (angle/180.0) * 2000`
- Le code actuel (durée par angle) fonctionne pour les deux types pendant la transition

**Config calibration par panneau (`master/config/main.cfg` ou `local.cfg`) :**
```ini
[servo_panels]
ms_90deg = 150          # durée base pour 90° (tous les panneaux)
dome_panel_1_open  = 70 # angle ouverture panneau 1 (0-90)
dome_panel_1_close = 70 # angle fermeture panneau 1
# ... dome_panel_2 à dome_panel_11, body_panel_1 à body_panel_11
```
> L'ancienne section `[servo]` avec `panel_angle` + `panel_ms_90deg` est remplacée par `[servo_panels]`
> `servo,dome_panel_N,open` dans les scripts utilise automatiquement l'angle `dome_panel_N_open` de la config

### Phase 2 — Propulsion & Actionneurs 🔧 Code prêt — décommenter
- [ ] **2.1** Brancher VESC USB `/dev/ttyACM0/1` → décommenter dans `slave/main.py`
- [ ] **2.2** Brancher Waveshare Motor Driver HAT #15364 (TB6612, I2C 0x40) → décommenter `DomeMotorDriver` dans `master/main.py`
- [ ] **2.3** Servos — **vérifier le type avant tout** (voir section ⚠️ Types de servos ci-dessus) puis tester avec scripts standalone :
  - Master : `python3 scripts/test_servo_master.py` → PCA9685 @ 0x40, canal 0
  - Slave  : `python3 scripts/test_servo_slave.py`  → PCA9685 @ 0x41, canal 0
  - Si OK → décommenter `BodyServoDriver` dans les deux main.py
- [ ] **2.4** Calibrer via Settings → SERVO CALIBRATION dans le dashboard web (`panel_angle` + `panel_ms_90deg`)
- [ ] **2.5** Tester watchdog VESC (arrêt si heartbeat perdu — critique sécurité)

### Phase 3 — Scripts de séquence ✅ 40 scripts disponibles
- [x] **3.1** `ScriptEngine` décommenté et actif dans `master/main.py`
- [x] **3.2** 40 scripts dans `master/scripts/` — 26 fidèles dpoulson + 14 customs

**Scripts dpoulson (fidèles) :**
`theme` `march` `leia` `evil` `failure` `alert` `malfunction` `cantina` `r2kt` `wolfwhistle`
`dome_dance` `dome_test1` `dome_test2` `test` `flap_dome` `flap_dome_fast` `flap_dome_side`
`ripple_dome` `ripple_dome_fast` `ripple_dome_side` `slow_open_close`
`looping_sounds` `looping_sounds_quick` `body_test` `dance` `hp_twitch`

**Scripts customs :**
`patrol` `celebrate` `panel_test` `startup` `excited` `scared` `angry` `curious`
`party` `birthday` `disco` `message` `taunt` `scan`

**Mapping dpoulson → notre système (pour créer de nouveaux scripts) :**
| dpoulson | Notre commande script |
|----------|-----------------------|
| `dome,P1,1,0` | `servo,dome_panel_1,open` |
| `dome,P1,0,0` | `servo,dome_panel_1,close` |
| `dome,P2/P3/P4` | `servo,dome_panel_2/3/4,open\|close` |
| `dome,PP1/PP2/PP5/PP6` | `servo,dome_panel_5/6/7/8,open\|close` |
| `dome,MP1/MP2/MP3` | `servo,dome_panel_9/10/11,open\|close` |
| `dome,all,open\|close` | `servo,all,open\|close` |
| `rseries,NNNN` | `teeces,random` + `sleep,N.N` + `teeces,off` |
| `sound,Theme001` | `sound,Theme001` (nom exact) |
| `sound,random,happy` | `sound,RANDOM,happy` |
| `body,LLD` | `servo,body_panel_1,open\|close` |
| `body,RLD` | `servo,body_panel_2,open\|close` |
| `body,BotArm` | `servo,body_panel_3,open\|close` |
| `flthy,XXXX` | *(non supporté — ignorer)* |
| `smoke,N` | *(non supporté — ignorer)* |

**Commandes script_engine complètes :**
```
sound,FILENAME           → son spécifique (ex: sound,Theme001)
sound,RANDOM,category    → son aléatoire (ex: sound,RANDOM,happy)
servo,dome_panel_N,open  → ouvre avec angle calibré de la config
servo,dome_panel_N,close → ferme avec angle calibré de la config
servo,dome_panel_N,1.0,300 → position float + durée ms (legacy)
servo,all,open|close     → tous les panneaux
teeces,random            → animations aléatoires (loop jusqu'à teeces,off)
teeces,leia              → mode Leia
teeces,off               → éteint
teeces,text,MESSAGE      → texte défilant FLD (max ~20 chars)
teeces,psi,0             → PSI random
teeces,psi,N             → PSI mode N
dome,turn,SPEED          → rotation dôme DC (float -1.0..1.0)
dome,stop                → arrêt dôme
dome,random,on|off       → mode aléatoire dôme
sleep,N                  → pause N secondes (float)
sleep,random,MIN,MAX     → pause aléatoire entre MIN et MAX secondes
motion,STOP              → arrêt propulsion
motion,LEFT,RIGHT,DUR    → drive différentiel (float, float, ms)
```

### Phase 4 — API REST + Dashboard Web 🔧 Code prêt — décommenter
- [ ] **4.1** Décommenter Flask dans `master/main.py` → `create_app()` + thread
- [ ] **4.2** Ajouter `flask_port = 5000` dans `master/config/main.cfg`
- [ ] **4.3** Tester dashboard sur `http://r2-master.local:5000`
- [ ] **4.4** Tester contrôle WASD depuis navigateur mobile (hotspot)
- [ ] **4.5** App Android (Phase 4+ — UDP joystick ou WebView dashboard)

### Phase 4.5 — App Android ✅ Implémentée + Connectivité fixée
- [x] WebView wrapper + assets bundlés (charge dashboard offline depuis `android/app/src/main/assets/`)
- [x] Bandeau natif **HORS LIGNE seulement** — slide down (offline) / slide up + hide (online) — animation 350ms
- [x] IP du Master cliquable dans le bandeau → dialog natif Android pour changer l'IP (hotspot ↔ WiFi maison)
- [x] `window.R2D2_API_BASE` injecté par `MainActivity.kt` via `evaluateJavascript` dans `onPageFinished`
- [x] `api()` dans `app.js` utilise `window.R2D2_API_BASE` comme préfixe — **critique pour Android** (`file://` → appels relatifs échouaient)
- [x] `startAppHeartbeat()` utilise aussi `R2D2_API_BASE` (fetch heartbeat + beforeunload)
- [x] `pollStatus()` global ajouté dans `app.js` — appelé par `MainActivity.kt` quand le serveur revient online
- [x] `StatusPoller._setOffline()` recharge scripts/servos/audio au retour online
- [x] Haptic feedback désactivé par défaut, contrôlable dans Settings
- [x] WebView plein écran (banner en overlay, ne vole plus 37dp en permanence)
- [x] Auto-découverte réseau : mDNS `r2-master.local` → IP sauvegardée → `192.168.4.1` → scan subnet /24 (50 threads, 500ms timeout)
- [x] Déclenchée automatiquement après 3 pings consécutifs en échec
- [x] Dialog IP : bouton RECHERCHER intégré avec spinner + résultat
- [x] Calibration servos par panneau : angles `open`/`close` individuels dans Settings → SERVO CALIBRATION
- [ ] Test sur hotspot R2D2_Control réel avec Master en ligne

> ⚠️ Assets Android — synchroniser manuellement si `master/static/` ou `master/templates/index.html` change :
> ```bash
> cp master/static/js/app.js android/app/src/main/assets/js/app.js
> cp master/static/css/style.css android/app/src/main/assets/css/style.css
> # Pour index.html : NE PAS copier directement — patcher les chemins :
> # /static/css/style.css → css/style.css
> # /static/js/app.js → js/app.js
> # {{ url_for(...) }} → chemin relatif
> # Désactiver le Service Worker (incompatible file:// origin)
> ```

> ⚠️ GitHub Actions workflow android-release.yml — utiliser `actions/checkout@v4` et `actions/setup-java@v4` (sans version patch) pour éviter dépréciation Node.js 20

> ⚠️ Bug critique résolu : `servoPanel.render()` dans `init()` → `servoPanel` n'existe pas (c'est `domeServoPanel`/`bodyServoPanel`)
> → tuait tout `init()` silencieusement (horloge, poller, pills jamais démarrés)

### Phase 5 — Vision (futur)
- [ ] **5.1** Caméra USB + flux vidéo MJPEG
- [ ] **5.2** Suivi de personne (OpenCV / TF Lite)

---

## 🐙 GitHub Repository

```
URL     : https://github.com/RickDnamps/R2D2_Control.git
Owner   : RickDnamps
Branch  : main
Licence : GNU GPL v3
```

### Setup initial (une seule fois sur le PC de développement)
```bash
# Cloner le repo
git clone https://github.com/RickDnamps/R2D2_Control.git
cd R2D2_Control

# Copier le CLAUDE.md dans le repo
# Puis premier commit
git add CLAUDE.md
git commit -m "Add project architecture and context"
git push
```

### Setup sur R2-Master (une seule fois)
```bash
# Cloner sur le Pi via wlan1 (Wi-Fi domestique)
cd /home/artoo
git clone https://github.com/RickDnamps/R2D2_Control.git r2d2
cd r2d2

# Générer le fichier VERSION initial
git rev-parse --short HEAD > VERSION
```

### Workflow git quotidien
```bash
# Sur le PC de dev — après avoir codé
git add .
git commit -m "Phase 1.3: UART watchdog implementation"
git push

# Sur R2-Master — via bouton dôme ou manuellement
git pull
git rev-parse --short HEAD > VERSION
# → rsync automatique vers R2-Slave déclenché
```

### Conventions de commit
```
Phase X.Y: description courte    # nouvelle fonctionnalité
Fix: description du bug          # correction de bug
Config: description              # changement de config
Docs: description                # documentation
```

### .gitignore — ne jamais committer
```
slave/sounds/            # sons trop lourds pour git
*.log                    # logs
master/config/local.cfg  # credentials WiFi maison + hotspot + GitHub URL personnelle
slave/vendor/            # dépendances pip pré-téléchargées
debug/                   # dossier généré automatiquement par le Master (logs de debug)
```

### local.cfg — sections complètes
```ini
[github]
repo_url           = https://github.com/RickDnamps/R2D2_Control.git
branch             = main
auto_pull_on_boot  = true

[home_wifi]           ← rempli par setup_master_network.sh
ssid               = TON_WIFI_MAISON
password           = TON_MOT_DE_PASSE

[hotspot]             ← rempli par setup_master_network.sh (demandé interactivement)
ssid               = R2D2_Control
password           = r2d2droid

[deploy]
button_pin         = 17

[slave]
host               = r2-slave.local
```

---

## 📚 Code de référence — r2_control by dpoulson

Le code source complet de r2_control est disponible localement :
```
J:\R2-D2_Build\software\others\r2_control-master\
```

### Ce qu'on a repris de r2_control
| Élément | Fichier r2_control | Notre équivalent |
|---------|-------------------|-----------------|
| 306 sons MP3 catégorisés | `Hardware/Audio/sounds/` | `slave/sounds/*.mp3` + `sounds_index.json` |
| Structure Blueprint Flask | `Hardware/Audio/AudioLibrary.py` | `master/api/*_bp.py` |
| Système de scripts .scr CSV | `Hardware/Scripts/ScriptThread.py` | `master/script_engine.py` |
| Catégories audio | `_Random_Sounds` list | `sounds_index.json` catégories |

### Ce qu'on adapte / remplace
- **Pas pygame** → `aplay` subprocess (Pi 4B jack 3.5mm natif)
- **Pas I2C depuis Master** → tout hardware body passe par UART → Slave
- **Pas contrôleur PS3/Xbox** → dashboard web WASD + API REST
- **Pas Flask URL-only** → POST JSON propre avec vrais codes HTTP
- **Watchdog UART** remplace la simple gestion d'erreurs de r2_control
- **Architecture Master/Slave** vs monolithique dans r2_control

### Notes importantes
- Le **Watchdog est non-négociable** — toujours tester en premier sur hardware réel (bench breadboard avant slipring)
- **Robot non assemblé** — pièces 3D encore en cours d'impression, tous les tests hardware se font sur bench/breadboard pour l'instant
- Le **slipring limite les fils** — ne jamais ajouter un signal sans valider le budget fils
- Le **RP2040 est autonome** — son firmware change rarement, ne pas l'inclure dans le pipeline rsync
- **Mode dégradé** = Slave démarre avec version locale si Master injoignable + alerte RP2040 + alerte Teeces32
- **Teeces32** = protocole JawaLite, compatible ESP32, USB `/dev/ttyUSB0` sur Pi 4B
- **FSESC Mini 6.7 PRO** = 4-13S LiPo, utiliser PyVESC avec commandes `SetDutyCycle`
- **Hub Motors 250W/24V double shaft** — prévoir rampes douces (risque basculement)
- **Phase 2/3/4** = code déjà écrit, décommenter les blocs dans `master/main.py` + `slave/main.py`
- **App Android** = charge dashboard depuis assets bundlés (`file:///android_asset/`) — API calls vers Pi via `window.R2D2_API_BASE`

---

## 📱 Build Android (Windows — PC de dev)

### Workflow — après chaque modif Android

```bash
# 1. Build APK debug (depuis J:/R2-D2_Build/software/)
powershell.exe -Command "& { \$env:JAVA_HOME='C:/Program Files/Android/Android Studio/jbr'; Set-Location 'J:/R2-D2_Build/software/android'; ./gradlew.bat assembleDebug }"

# 2. Copier l'APK dans android/compiled/
cp android/app/build/outputs/apk/debug/app-debug.apk android/compiled/R2-D2_Control.apk

# 3. Committer + pusher
git add android/compiled/R2-D2_Control.apk
git commit -m "ci: update R2-D2_Control.apk [skip ci]"
git push
```

L'APK est ensuite disponible directement sur GitHub :
`android/compiled/R2-D2_Control.apk`

> ⚠️ Le GitHub Actions workflow existe mais ne pas s'en fier — build local + copie manuelle est la méthode fiable
> ⚠️ Toujours synchroniser `android/app/src/main/assets/` si `master/static/` ou `master/templates/index.html` change

### Installer sur téléphone (ADB)

```bash
ADB="C:/Users/erict/AppData/Local/Android/Sdk/platform-tools/adb.exe"
"$ADB" install -r android/compiled/R2-D2_Control.apk
"$ADB" shell am start -n com.r2d2.control/.MainActivity

# Voir crashes
"$ADB" logcat -s AndroidRuntime:E
```

> ⚠️ Adaptive icons (`<adaptive-icon>`) doivent être dans `mipmap-anydpi-v26/` avec AGP 8.13+
> ⚠️ Réinstaller proprement (`uninstall` + `install`) pour réinitialiser les SharedPreferences
