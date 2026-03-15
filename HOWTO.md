# R2-D2 — Guide d'installation complet

| Phase | Contenu | État |
|-------|---------|------|
| **1** | Infrastructure UART / Heartbeat / Watchdog / Version / Hotspot | ✅ Prêt |
| **2** | Propulsion VESC / Moteur dôme / Servos body | 🔧 Décommenter |
| **3** | Scripts de séquence comportementale (.scr) | 🔧 Décommenter |
| **4** | API REST Flask + Dashboard Web | 🔧 Décommenter |

---

## ⚠️ Ordre d'installation obligatoire

```
1. R2-Master  (étapes 0 → 2)   ← TOUJOURS EN PREMIER
2. R2-Slave   (étapes 1b → 2b) ← seulement après le reboot Master
3. Suite commune (étapes 3 → 7)
```

> Le Slave doit se connecter au **hotspot du Master**.
> Ce hotspot n'existe pas avant que le Master soit configuré et redémarré.
> Configurer le Slave avant le Master = impossible de le joindre en SSH.

---

## Prérequis matériel

| Composant | Master (dôme) | Slave (corps) |
|-----------|--------------|---------------|
| Pi 4B | 4G | 2G |
| OS | Raspberry Pi OS Lite 64-bit Trixie | idem |
| WiFi | wlan0 intégré + **clé USB WiFi** (wlan1) | wlan0 intégré suffit |
| Réseau initial | connecté à ton WiFi maison | connecté à ton WiFi maison |

**Avant de commencer — graver les cartes SD avec Raspberry Pi Imager :**
- Cliquer ⚙️ Options dans l'Imager pour les deux cartes :
  - Username : `artoo`
  - Password : (ton choix, même des deux côtés recommandé)
  - WiFi : ton réseau maison (SSID + mot de passe)
  - SSH : activé
  - Hostname Master : `r2-master`
  - Hostname Slave  : `r2-slave`

---

## Vue d'ensemble

```
─── PHASE 1 ────────────────────────────────────────────────
── Sur le R2-Master (PREMIER) ──
ÉTAPE 0 — local.cfg (GitHub, hotspot souhaité)
ÉTAPE 1 — Paquets + repo git
ÉTAPE 2 — Réseau Master : hotspot wlan0 + wlan1 internet
           → noter le SSID/password du hotspot créé
           → sudo reboot

── Sur le R2-Slave (après reboot Master) ──
ÉTAPE 1b — Paquets sur Slave
ÉTAPE 2b — Réseau Slave : connecter wlan0 au hotspot Master
            → sudo reboot

── Suite commune ──
ÉTAPE 3 — SSH sans mot de passe Master → Slave
ÉTAPE 4 — Déploiement du code (rsync initial)
ÉTAPE 5 — Services systemd
ÉTAPE 6 — RP2040 firmware
ÉTAPE 7 — Tests de validation Phase 1

─── PHASE 2 ────────────────────────────────────────────────
ÉTAPE 8 — Câblage VESC (propulsion)
ÉTAPE 9 — Câblage moteur dôme (Syren10/Sabertooth)
ÉTAPE 10 — Câblage servos body (PCA9685 I2C)
ÉTAPE 11 — Activation des drivers Phase 2

─── PHASE 3 ────────────────────────────────────────────────
ÉTAPE 12 — Scripts de séquence (.scr)
ÉTAPE 13 — Activation du ScriptEngine

─── PHASE 4 ────────────────────────────────────────────────
ÉTAPE 14 — API REST Flask
ÉTAPE 15 — Dashboard Web
ÉTAPE 16 — Tests de validation Phase 4
```

---

## ÉTAPE 0 — Configurer local.cfg (à faire une seule fois)

`local.cfg` est le fichier de **configuration personnelle** de ton R2-D2.
Il n'est **jamais écrasé par git pull** — c'est là que vivent ton WiFi et ton GitHub.

```bash
# Sur le R2-Master, après le git clone
cd /home/artoo/r2d2/master/config
cp local.cfg.example local.cfg
# C'est tout — toutes les valeurs sont déjà pré-remplies dans l'exemple.
# [home_wifi] sera rempli automatiquement par setup_master_network.sh (étape 2).
```

> Si tu veux personnaliser le SSID/password du hotspot ou le pin du bouton dôme,
> éditer `local.cfg` avec `nano local.cfg` avant de passer à l'étape 2.

---

## ÉTAPE 1 — Préparation des deux Pi

### 1.1 — Sur le R2-Master (Pi 4B 4G — Dôme)

> **Prérequis Imager** : lors de la gravure de la carte SD, configurer via
> Raspberry Pi Imager → ⚙️ Options :
> - Username : `artoo` / Password : (ton choix)
> - Hostname : `r2-master`
> - WiFi : ton réseau maison (SSID + mot de passe)
> - SSH activé
>
> Le Pi bootera directement connecté à ton WiFi maison sur `wlan0`.

```bash
# Connexion SSH (réseau domestique, première fois)
ssh artoo@r2-master.local
# ou avec l'IP si .local ne fonctionne pas encore :
ssh artoo@<IP_R2MASTER_RESEAU_MAISON>

# Définir le hostname
sudo hostnamectl set-hostname r2-master

# Mise à jour système
sudo apt-get update && sudo apt-get upgrade -y

# Paquets système
sudo apt-get install -y python3-pip python3-serial git rsync

# Dépendances Python
pip3 install --break-system-packages -r /home/artoo/r2d2/master/requirements.txt

# Activer UART hardware (désactiver console série)
sudo raspi-config nonint do_serial_hw 0   # active UART hardware
sudo raspi-config nonint do_serial_cons 1  # désactive console sur UART

# Activer I2C
sudo raspi-config nonint do_i2c 0

# Cloner le repo depuis GitHub (adapter l'URL)
git clone https://github.com/<TON_USER>/r2d2.git /home/artoo/r2d2

# Générer le fichier VERSION
cd /home/artoo/r2d2
git rev-parse --short HEAD > /home/artoo/r2d2/VERSION

sudo reboot
```

### 1.2 — Sur le R2-Slave (Pi 4B 2G — Corps)

> **Prérequis Imager** : même chose que le Master :
> - Username : `artoo` / Hostname : `r2-slave`
> - WiFi : ton réseau maison (le Slave passera ensuite sur le hotspot Master)
> - SSH activé

```bash
# Connexion SSH (réseau domestique, première fois)
ssh artoo@r2-slave.local

# Définir le hostname
sudo hostnamectl set-hostname r2-slave

# Mise à jour système
sudo apt-get update && sudo apt-get upgrade -y

# Paquets système
sudo apt-get install -y python3-pip python3-serial git

# Dépendances Python (copiées par rsync à l'étape 4)
# pip3 install --break-system-packages -r /home/artoo/r2d2/slave/requirements.txt  ← après le premier rsync

# Activer UART hardware
sudo raspi-config nonint do_serial_hw 0
sudo raspi-config nonint do_serial_cons 1

# Activer I2C
sudo raspi-config nonint do_i2c 0

# Créer le dossier du repo (sera rempli par rsync depuis le Master)
mkdir -p /home/artoo/r2d2

sudo reboot
```

---

## ÉTAPE 2 — Hotspot Wi-Fi sur R2-Master

### Principe

Raspberry Pi OS Trixie utilise **NetworkManager** par défaut.
Le script détecte automatiquement les credentials WiFi de ton réseau maison
(déjà configuré sur wlan0 par l'Imager), les sauvegarde dans `local.cfg`,
puis bascule l'interface :

```
État initial (sorti de l'Imager) :
  wlan0  → connecté à ton WiFi maison

État final après le script :
  wlan0  → Hotspot "R2D2_Control"  192.168.4.1   (Slave + télécommande)
  wlan1  → ton WiFi maison          DHCP          (git pull / GitHub)
```

### 2.1 — Brancher la clé USB WiFi (wlan1)

Brancher la clé USB WiFi sur un port USB **avant** de lancer le script.

Vérifier qu'elle apparaît :
```bash
ip link show
# doit afficher wlan0  ET  wlan1
```

> Si la clé n'est pas encore disponible, le script la configure quand même.
> Elle se connectera automatiquement au premier branchement.

### 2.2 — Lancer le script de configuration réseau

```bash
sudo bash /home/artoo/r2d2/scripts/setup_master_network.sh
```

Le script :
1. **Lit** le SSID et mot de passe du WiFi maison depuis NetworkManager
2. **Confirme** avec toi (ou te permet de saisir manuellement si non détecté)
3. **Sauvegarde** dans `master/config/local.cfg` → section `[home_wifi]`
4. **Configure wlan1** avec ces credentials (connexion automatique)
5. **Convertit wlan0** en hotspot `R2D2_Control` (IP fixe 192.168.4.1)
6. Active **avahi-daemon** pour la résolution `.local`

```bash
sudo reboot
```

### 2.3 — Vérification après reboot

```bash
# Depuis ton PC connecté au hotspot "R2D2_Control" :
ping 192.168.4.1          # R2-Master répond ✓

# Vérifier que wlan1 est connecté à internet :
ssh artoo@192.168.4.1
ping -I wlan1 8.8.8.8     # internet via wlan1 ✓

# Vérifier la config réseau :
nmcli device status
# wlan0  wifi  connecté  r2d2-hotspot
# wlan1  wifi  connecté  r2d2-internet
```

### 2.4 — Vérifier local.cfg

```bash
cat /home/artoo/r2d2/master/config/local.cfg
# Doit contenir :
# [home_wifi]
# ssid = TON_WIFI_MAISON
# password = ***
```

> `local.cfg` est **gitignored** — il ne sera jamais écrasé par un `git pull`.
> Si tu changes de WiFi maison, éditer manuellement cette section et relancer
> `nmcli connection modify r2d2-internet wifi-sec.psk "NOUVEAU_MOT_DE_PASSE"`

---

## ÉTAPE 1b — Préparation du R2-Slave (paquets de base)

> Le Slave est encore sur ton WiFi maison à ce stade — c'est normal.
> Son réseau sera basculé vers le hotspot Master à l'étape 2b.

```bash
# Connexion SSH (WiFi maison, pendant que le Slave est encore dessus)
ssh artoo@r2-slave.local

# Mise à jour système
sudo apt-get update && sudo apt-get upgrade -y

# Paquets système
sudo apt-get install -y python3-pip python3-serial git alsa-utils

# Activer UART hardware (désactiver console série)
sudo raspi-config nonint do_serial_hw 0
sudo raspi-config nonint do_serial_cons 1

# Activer I2C
sudo raspi-config nonint do_i2c 0

# Créer le dossier du repo (sera rempli par rsync depuis le Master)
mkdir -p /home/artoo/r2d2

# Pas de reboot ici — attendre l'étape 2b
```

---

## ÉTAPE 2b — Réseau Slave : connexion au hotspot Master

> ⚠️ Le Master doit être **rebooté et son hotspot actif** avant de continuer.
> Connecter ton PC au hotspot `R2D2_Control` pour vérifier qu'il répond :
> ```bash
> ping 192.168.4.1   # doit répondre
> ```

### 2b.1 — Copier le script sur le Slave

Le repo n'est pas encore sur le Slave — copier le script depuis le Master :

```bash
# Depuis le Master (sur ton WiFi maison ou via hotspot)
scp /home/artoo/r2d2/scripts/setup_slave_network.sh \
    artoo@r2-slave.local:/home/artoo/setup_slave_network.sh
```

> Si tu n'as pas encore accès SSH au Slave depuis le Master, copier
> le script directement depuis ton PC (qui est encore sur le WiFi maison).

### 2b.2 — Lancer le script sur le Slave

```bash
# Sur le R2-Slave (SSH via WiFi maison — dernière fois)
ssh artoo@r2-slave.local

sudo bash /home/artoo/setup_slave_network.sh
```

Le script demande :
- **SSID du hotspot Master** (défaut: `R2D2_Control` — modifier si tu l'as personnalisé)
- **Mot de passe** du hotspot (celui que tu as défini lors du setup Master)

```bash
sudo reboot
```

### 2b.3 — Vérification après reboot du Slave

```bash
# Depuis ton PC connecté au hotspot R2D2_Control (ou depuis le Master)
ping r2-slave.local         # doit répondre depuis le hotspot ✓
ssh artoo@r2-slave.local    # connexion sans problème ✓

# Sur le Slave — vérifier l'IP reçue
ip addr show wlan0
# doit afficher 192.168.4.x
```

---

## ÉTAPE 3 — SSH sans mot de passe R2-Master → R2-Slave

> Les deux Pi sont maintenant sur le même réseau (hotspot `R2D2_Control`).
> Le Slave répond à `r2-slave.local` depuis le Master.

### 3.1 — Générer et copier les clés SSH

```bash
# Depuis le R2-Master
bash /home/artoo/r2d2/scripts/setup_ssh_keys.sh
# Entrer le mot de passe du R2-Slave quand demandé (une dernière fois)
```

Vérification :
```bash
ssh artoo@r2-slave.local echo "SSH OK"
# Doit afficher "SSH OK" sans mot de passe
```

---

## ÉTAPE 4 — Déploiement initial du code

### 4.1 — Copier le code Slave sur le R2-Slave

```bash
# Depuis le R2-Master
rsync -avz --delete \
  -e "ssh -o StrictHostKeyChecking=no" \
  /home/artoo/r2d2/slave/ \
  artoo@r2-slave.local:/home/artoo/r2d2/

# Copier aussi le dossier shared
rsync -avz \
  -e "ssh -o StrictHostKeyChecking=no" \
  /home/artoo/r2d2/shared/ \
  artoo@r2-slave.local:/home/artoo/r2d2/shared/

# Copier le fichier VERSION
rsync \
  -e "ssh -o StrictHostKeyChecking=no" \
  /home/artoo/r2d2/VERSION \
  artoo@r2-slave.local:/home/artoo/r2d2/VERSION
```

### 4.2 — Vérifier le code sur le R2-Slave

```bash
ssh artoo@r2-slave.local
ls /home/artoo/r2d2/
# Doit afficher: main.py  uart_listener.py  watchdog.py  version_check.py  drivers/  services/
cat /home/artoo/r2d2/VERSION
# Doit afficher le même hash que sur le R2-Master
```

---

## ÉTAPE 5 — Services systemd

### 5.1 — Sur le R2-Master

```bash
# Copier les fichiers service
sudo cp /home/artoo/r2d2/master/services/r2d2-master.service /etc/systemd/system/
sudo cp /home/artoo/r2d2/master/services/r2d2-monitor.service /etc/systemd/system/

# Recharger systemd
sudo systemctl daemon-reload

# Activer et démarrer
sudo systemctl enable r2d2-master r2d2-monitor
sudo systemctl start r2d2-master

# Vérifier l'état
sudo systemctl status r2d2-master
journalctl -u r2d2-master -f   # logs en temps réel
```

### 5.2 — Sur le R2-Slave

```bash
# Copier les fichiers service
sudo cp /home/artoo/r2d2/services/r2d2-slave.service /etc/systemd/system/
sudo cp /home/artoo/r2d2/services/r2d2-version.service /etc/systemd/system/

# Recharger systemd
sudo systemctl daemon-reload

# Activer et démarrer
sudo systemctl enable r2d2-version r2d2-slave
sudo systemctl start r2d2-slave

# Vérifier l'état
sudo systemctl status r2d2-slave
journalctl -u r2d2-slave -f   # logs en temps réel
```

---

## ÉTAPE 6 — Firmware RP2040

### 6.1 — Prérequis

- Installer **Thonny** sur ton PC ou utiliser `mpremote`
- Le RP2040 doit avoir MicroPython installé

### 6.2 — Installer MicroPython sur le RP2040

1. Télécharger le firmware MicroPython pour RP2040 :
   https://micropython.org/download/RPI_PICO/

2. Brancher le RP2040 en mode BOOTSEL (maintenir BOOT enfoncé, brancher USB)

3. Copier le fichier `.uf2` sur le lecteur `RPI-RP2` qui apparaît

### 6.3 — Installer le driver GC9A01

Via `mpremote` depuis ton PC :
```bash
pip install mpremote
mpremote connect auto mip install gc9a01
```

### 6.4 — Copier le firmware R2-D2

```bash
# Depuis le dossier rp2040/firmware/
cd J:/R2-D2_Build/software/rp2040/firmware

mpremote connect auto cp main.py :main.py
mpremote connect auto cp display.py :display.py
mpremote connect auto cp touch.py :touch.py
```

### 6.5 — Tester l'affichage

```bash
mpremote connect auto repl
# Dans le REPL MicroPython :
import display, gc9a01
# ... ou simplement laisser main.py démarrer
```

Le RP2040 doit afficher l'écran de boot R2-D2 au démarrage.

---

## ÉTAPE 7 — Tests de validation Phase 1

### 7.1 — Test UART + CRC

Depuis le R2-Master, tester manuellement :
```bash
python3 -c "
import sys; sys.path.insert(0, '/home/artoo/r2d2')
from shared.uart_protocol import build_msg, parse_msg
print(build_msg('H', '1'))       # H:1:59\n attendu
print(build_msg('M', '50'))      # M:50:7F\n attendu
print(parse_msg('H:1:59'))       # ('H', '1') attendu
print(parse_msg('H:1:00'))       # None attendu (CRC invalide)
"
```

### 7.2 — Test Watchdog

```bash
# Sur le R2-Slave
journalctl -u r2d2-slave -f

# Sur le R2-Master — arrêter temporairement le service Master
sudo systemctl stop r2d2-master

# Observer dans les logs Slave :
# → après 500ms : "WATCHDOG DÉCLENCHÉ"
# → redémarrer Master : "Watchdog: heartbeat repris"
sudo systemctl start r2d2-master
```

### 7.3 — Test Version Sync

```bash
# Simuler une divergence de version sur le R2-Slave
ssh artoo@r2-slave.local "echo 'aabbcc' > /home/artoo/r2d2/VERSION"

# Redémarrer le Slave
ssh artoo@r2-slave.local "sudo systemctl restart r2d2-slave"

# Observer les logs — doit tenter une synchro
ssh artoo@r2-slave.local "journalctl -u r2d2-slave -f"
```

### 7.4 — Test Teeces32

```bash
# Sur le R2-Master
python3 -c "
import configparser, sys
sys.path.insert(0, '/home/artoo/r2d2')
from master.teeces_controller import TeecesController
cfg = configparser.ConfigParser()
cfg.read('/home/artoo/r2d2/master/config/main.cfg')
t = TeecesController(cfg)
if t.setup():
    t.random_mode()
    import time; time.sleep(2)
    t.leia_mode()
    time.sleep(2)
    t.fld_text('R2D2 OK')
    t.shutdown()
"
```

### 7.5 — Test Bouton Dôme

```bash
# Vérifier que le pin BCM17 est bien câblé (bouton vers GND)
python3 -c "
import RPi.GPIO as GPIO, time
GPIO.setmode(GPIO.BCM)
GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
print('Appuie sur le bouton...')
while True:
    print('État:', GPIO.input(17))
    time.sleep(0.1)
"
```

### 7.6 — Test écran RP2040

Brancher le RP2040 sur le R2-Slave (USB), puis :
```bash
# Sur R2-Slave — envoyer une commande DISP: manuellement
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyACM2', 115200)
s.write(b'DISP:BOOT\n'); time.sleep(1)
s.write(b'DISP:SYNCING:abc123\n'); time.sleep(2)
s.write(b'DISP:OK:abc123\n'); time.sleep(2)
s.write(b'DISP:TELEM:25.4V:38C\n')
s.close()
"
```

### 7.7 — Test Audio (jack 3.5mm natif)

```bash
# Sur R2-Slave — tester la sortie audio jack 3.5mm
aplay /home/artoo/r2d2/slave/sounds/001.wav

# Ou via Python subprocess
python3 -c "
import subprocess
subprocess.run(['aplay', '/home/artoo/r2d2/slave/sounds/001.wav'])
"
```

---

## Câblage UART à vérifier

```
R2-Master  BCM14 (TX, pin 8)  ──→  BCM15 (RX, pin 10)  R2-Slave
R2-Master  BCM15 (RX, pin 10) ←──  BCM14 (TX, pin 8)   R2-Slave
R2-Master  GND   (pin 6)      ───  GND   (pin 6)        R2-Slave
```

> **Les fils UART traversent le slipring.** Vérifier la continuité au multimètre avant de démarrer les services.
> R2-Master et R2-Slave utilisent `/dev/ttyAMA0` — même port, chacun sur son propre hardware.

---

## ÉTAPE 8 — Câblage VESC (Phase 2)

### 8.1 — Connexion USB

Les deux VESC se branchent directement sur le R2-Slave (Pi 4B) via USB :

```
R2-Slave  USB  ──→  VESC Gauche  (/dev/ttyACM0)
R2-Slave  USB  ──→  VESC Droit   (/dev/ttyACM1)
```

Vérifier les ports après branchement :
```bash
ls /dev/ttyACM*
# Doit afficher: /dev/ttyACM0  /dev/ttyACM1
```

### 8.2 — Configuration VESC (via VESC Tool)

Sur chaque VESC, configurer via VESC Tool (depuis un PC) :
- **Motor Type** : FOC ou BLDC selon ton moteur
- **Current Limits** : adapter à ton moteur (ex: 30A max)
- **Direction** : inverser le VESC droit si les roues tournent en sens opposé
- **UART Baud** : 115200

### 8.3 — Permissions USB sur le Slave

```bash
sudo usermod -a -G dialout artoo
# Déconnexion/reconnexion SSH requise pour prendre effet
```

---

## ÉTAPE 9 — Câblage moteur dôme (Phase 2)

### 9.1 — Connexion Syren10 / Sabertooth

Le contrôleur de dôme reçoit les commandes du R2-Slave via UART :

```
R2-Slave  /dev/ttyUSB1  ──→  Syren10 S1
R2-Slave  GND           ───  Syren10 0V
```

> Si `/dev/ttyUSB1` n'est pas disponible (conflits avec Teeces), adapter dans `slave/main.py`.

### 9.2 — Configuration Syren10

Interrupteurs DIP Syren10 pour mode UART simplex :
- SW1=OFF, SW2=OFF, SW3=ON, SW4=OFF, SW5=ON, SW6=ON (adresse 129)

Vérification :
```bash
# Envoyer une commande manuelle (vitesse 0 = arrêt)
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyUSB1', 9600)
s.write(bytes([0x80]))  # adresse 129 → neutre
time.sleep(0.5)
s.close()
"
```

---

## ÉTAPE 10 — Câblage servos body (Phase 2)

### 10.1 — Connexion PCA9685 I2C

```
R2-Slave  GPIO2 (SDA, pin 3)  ──→  PCA9685 SDA
R2-Slave  GPIO3 (SCL, pin 5)  ──→  PCA9685 SCL
R2-Slave  3.3V  (pin 1)       ──→  PCA9685 VCC
R2-Slave  GND   (pin 6)       ──→  PCA9685 GND
Alimentation externe 5-6V     ──→  PCA9685 V+ (pour les servos)
```

Vérifier la détection I2C :
```bash
sudo i2cdetect -y 1
# Doit afficher "40" à l'adresse 0x40
```

### 10.2 — Mapping des canaux servo

Éditer `slave/drivers/body_servo_driver.py` → dict `SERVO_MAP` :
```python
SERVO_MAP = {
    'utility_arm_left':   (0, 1000, 2000),  # canal 0
    'utility_arm_right':  (1, 1000, 2000),  # canal 1
    'panel_front_top':    (2, 1000, 2000),  # canal 2
    # ...
}
```

Ajuster `pulse_min_us` / `pulse_max_us` selon chaque servo (tester à la main d'abord).

---

## ÉTAPE 11 — Activation des drivers Phase 2

### 11.1 — Sur le R2-Slave

Éditer `slave/main.py` et décommenter le bloc Phase 2 :
```python
# ---- Phase 2 — Décommenter pour activer ----
from slave.drivers.vesc_driver       import VescDriver
from slave.drivers.body_servo_driver import BodyServoDriver
```

Et plus bas dans `main()` :
```python
vesc  = VescDriver()
servo = BodyServoDriver()
if vesc.setup():
    uart.register_callback('M', vesc.handle_uart)
    watchdog.register_stop_callback(vesc.stop)
if servo.setup():
    uart.register_callback('SRV', servo.handle_uart)
```

### 11.2 — Sur le R2-Master

Éditer `master/main.py` et décommenter le bloc Phase 2 :
```python
from master.drivers.vesc_driver       import VescDriver
from master.drivers.dome_motor_driver import DomeMotorDriver
from master.drivers.body_servo_driver import BodyServoDriver
```

Et dans `main()` :
```python
vesc  = VescDriver(uart)
dome  = DomeMotorDriver(uart)
servo = BodyServoDriver(uart)
if vesc.setup():  reg.vesc  = vesc
if dome.setup():  reg.dome  = dome
if servo.setup(): reg.servo = servo
```

### 11.3 — Déployer et tester

```bash
# Depuis le R2-Master
bash /home/artoo/r2d2/scripts/deploy.sh

# Test propulsion manuel via Python
python3 -c "
import sys; sys.path.insert(0, '/home/artoo/r2d2')
import configparser
from master.config.config_loader import load
from master.uart_controller import UARTController
from master.drivers.vesc_driver import VescDriver
cfg = load()
uart = UARTController(cfg)
uart.setup(); uart.start()
vesc = VescDriver(uart)
vesc.setup()
import time
vesc.drive(0.3, 0.3)   # avancer doucement
time.sleep(1)
vesc.stop()
uart.stop()
"
```

---

## ÉTAPE 12 — Scripts de séquence (Phase 3)

Les scripts `.scr` sont des fichiers CSV dans `master/scripts/`.
Chaque ligne = une commande. Les commentaires commencent par `#`.

### 12.1 — Format des commandes

```csv
# Exemples de commandes
sound,Happy001               # joue un son spécifique
sound,RANDOM,happy           # son aléatoire de la catégorie
dome,turn,0.5                # rotation dôme (vitesse -1.0 à 1.0)
dome,stop                    # arrêt dôme
dome,random,on               # active rotation aléatoire
servo,utility_arm_left,1.0,500   # servo: nom, position (0-1), durée ms
servo,all,open               # ouvre tous les servos
servo,all,close              # ferme tous les servos
motion,0.4,0.4,2000          # propulsion: gauche, droite, durée ms
motion,stop                  # arrêt propulsion
teeces,random                # LEDs Teeces en mode aléatoire
teeces,leia                  # LEDs Teeces en mode Leia
teeces,text,HELLO            # texte sur le FLD
sleep,1.5                    # pause 1.5 secondes
sleep,random,2,5             # pause aléatoire 2 à 5 secondes
```

### 12.2 — Scripts inclus

| Script | Description |
|--------|-------------|
| `patrol.scr` | Patrouille : sons + rotation dôme + bras utilitaire |
| `celebrate.scr` | Célébration : bras + dôme + son Celebration |
| `cantina.scr` | Danse de la cantina avec musique |
| `leia.scr` | Mode Leia holographique (Teeces + son) |

### 12.3 — Créer un nouveau script

```bash
nano /home/artoo/r2d2/master/scripts/mon_script.scr
```

```csv
# Mon script personnalisé
sound,RANDOM,happy
sleep,1.0
dome,turn,0.3
sleep,2.0
dome,stop
teeces,random
```

---

## ÉTAPE 13 — Activation du ScriptEngine (Phase 3)

Éditer `master/main.py` et décommenter le bloc Phase 3 :
```python
from master.script_engine import ScriptEngine
```

Dans `main()` :
```python
engine = ScriptEngine(
    uart=uart, teeces=teeces,
    vesc=reg.vesc, dome=reg.dome, servo=reg.servo
)
reg.engine = engine
```

Test en ligne de commande :
```bash
python3 -c "
import sys; sys.path.insert(0, '/home/artoo/r2d2')
from master.script_engine import ScriptEngine
engine = ScriptEngine()   # sans drivers = mode dry-run
sid = engine.run('patrol')
import time; time.sleep(10)
engine.stop(sid)
"
```

---

## ÉTAPE 14 — API REST Flask (Phase 4)

### 14.1 — Activation

Éditer `master/main.py` et décommenter le bloc Phase 4 :
```python
from master.flask_app import create_app
```

Dans `main()` :
```python
app = create_app()
flask_port = cfg.getint('master', 'flask_port', fallback=5000)
flask_thread = threading.Thread(
    target=lambda: app.run(host='0.0.0.0', port=flask_port,
                           use_reloader=False, threaded=True),
    name='flask', daemon=True
)
flask_thread.start()
```

Ajouter dans `master/config/main.cfg` :
```ini
[master]
flask_port = 5000
```

### 14.2 — Endpoints disponibles

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/status` | État complet JSON |
| POST | `/audio/play` | Jouer un son `{"sound": "Happy001"}` |
| POST | `/audio/random` | Son aléatoire `{"category": "happy"}` |
| POST | `/audio/stop` | Arrêter le son |
| GET | `/audio/categories` | Liste des catégories |
| POST | `/motion/drive` | Propulsion `{"left": 0.5, "right": 0.5}` |
| POST | `/motion/arcade` | Arcade drive `{"throttle": 0.5, "steering": 0.0}` |
| POST | `/motion/stop` | Arrêt propulsion |
| POST | `/motion/dome/turn` | Rotation dôme `{"speed": 0.3}` |
| POST | `/motion/dome/random` | Mode aléatoire dôme `{"enabled": true}` |
| POST | `/servo/move` | Déplacer servo `{"name": "...", "position": 0.5}` |
| POST | `/servo/open_all` | Ouvrir tous les servos |
| POST | `/servo/close_all` | Fermer tous les servos |
| POST | `/scripts/run` | Lancer un script `{"name": "patrol", "loop": false}` |
| POST | `/scripts/stop_all` | Arrêter tous les scripts |
| POST | `/teeces/random` | Mode LEDs aléatoire |
| POST | `/teeces/leia` | Mode Leia |
| POST | `/teeces/text` | Texte FLD `{"text": "HELLO"}` |
| POST | `/system/reboot` | Reboot Master |
| POST | `/system/reboot_slave` | Reboot Slave via UART |

### 14.3 — Tester l'API

```bash
# Depuis n'importe quel appareil connecté au hotspot R2D2_Control
curl http://192.168.4.1:5000/status
curl -X POST http://192.168.4.1:5000/audio/random \
     -H "Content-Type: application/json" \
     -d '{"category": "happy"}'
curl -X POST http://192.168.4.1:5000/motion/drive \
     -H "Content-Type: application/json" \
     -d '{"left": 0.3, "right": 0.3}'
```

---

## ÉTAPE 15 — Dashboard Web (Phase 4)

### 15.1 — Accès

Une fois Flask démarré, ouvrir dans un navigateur (depuis le hotspot R2D2_Control) :
```
http://192.168.4.1:5000
# ou
http://r2-master.local:5000
```

### 15.2 — Fonctionnalités du dashboard

| Panneau | Contrôles |
|---------|-----------|
| **Status** | Heartbeat, UART, Teeces, VESC, uptime, version |
| **Audio** | Boutons par catégorie (13 catégories, 306 sons), Stop |
| **Propulsion** | D-pad (clic/touch), WASD/flèches clavier, limite vitesse |
| **Dôme** | Gauche/Droite, Centre, Mode aléatoire toggle |
| **Teeces** | Aléatoire / Leia / OFF / texte FLD |
| **Servos** | Ouvrir/Fermer individuel + Tout ouvrir/fermer |
| **Scripts** | Lancer (Run/Loop) + Stop all + liste en cours |
| **Système** | Reboot Master, Reboot Slave, Shutdown |

### 15.3 — Contrôle clavier (navigateur PC)

| Touche | Action |
|--------|--------|
| `W` / `↑` | Avancer |
| `S` / `↓` | Reculer |
| `A` / `←` | Pivoter gauche |
| `D` / `→` | Pivoter droite |
| Relâcher | Arrêt automatique |

---

## ÉTAPE 16 — Tests de validation Phase 4

### 16.1 — Test API status

```bash
curl http://r2-master.local:5000/status
# Doit retourner un JSON avec heartbeat_ok, version, uptime, etc.
```

### 16.2 — Test audio via API

```bash
curl -X POST http://r2-master.local:5000/audio/random \
     -H "Content-Type: application/json" \
     -d '{"category": "happy"}'
# Doit jouer un son sur le Slave et retourner {"status": "ok"}
```

### 16.3 — Test script via API

```bash
# Lancer le script celebrate
curl -X POST http://r2-master.local:5000/scripts/run \
     -H "Content-Type: application/json" \
     -d '{"name": "celebrate"}'

# Vérifier qu'il tourne
curl http://r2-master.local:5000/scripts/running

# L'arrêter
curl -X POST http://r2-master.local:5000/scripts/stop_all
```

### 16.4 — Test dashboard mobile

Depuis un smartphone connecté au hotspot `R2D2_Control` :
1. Ouvrir `http://192.168.4.1:5000`
2. Vérifier que les indicateurs de status sont verts
3. Tester les boutons audio
4. Tester le D-pad (touch)

---

## Après chaque modification de code

```bash
# Depuis le R2-Master
cd /home/artoo/r2d2
git pull                    # récupérer les modifs
bash scripts/deploy.sh      # raccourci : rsync + reboot Slave
```

Ou utiliser le **bouton physique dôme** :
- Appui court (< 2s) : git pull + rsync + reboot Slave
- Appui long (> 2s) : rollback vers la version précédente
- Double appui : afficher la version courante sur Teeces32

---

## Logs utiles

```bash
# R2-Master
journalctl -u r2d2-master -f

# R2-Slave (via SSH)
ssh artoo@r2-slave.local "journalctl -u r2d2-slave -f"

# Tous les logs R2-D2 en même temps (depuis le R2-Master)
journalctl -u r2d2-master -f &
ssh artoo@r2-slave.local "journalctl -u r2d2-slave -f"
```
