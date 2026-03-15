#!/bin/bash
# =============================================================================
# setup_master.sh — Installation complète du R2-Master (une seule commande)
# =============================================================================
#
# Ce script automatise toutes les étapes d'installation du Master :
#   1. Mise à jour système + paquets
#   2. Clone du repo git
#   3. Fix UART (disable-bt pour libérer ttyAMA0)
#   4. Activation UART + I2C via raspi-config
#   5. Installation dépendances Python
#   6. Copie local.cfg
#   7. Configuration réseau (hotspot wlan0 + wlan1 internet)
#   8. Installation services systemd
#   → reboot final
#
# Usage (sur le R2-Master, connecté au WiFi maison) :
#   curl -fsSL https://raw.githubusercontent.com/RickDnamps/R2D2_Control/main/scripts/setup_master.sh | sudo bash
#
# Ou si le repo est déjà cloné :
#   sudo bash /home/artoo/r2d2/scripts/setup_master.sh
#
# =============================================================================

set -e

REPO_URL="https://github.com/RickDnamps/R2D2_Control.git"
REPO_PATH="/home/artoo/r2d2"
USER="artoo"

# Couleurs
RED='\033[0;31m'
GRN='\033[0;32m'
YEL='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YEL}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERR ]${NC}  $*"; exit 1; }

# Vérifier qu'on tourne en root
[ "$EUID" -eq 0 ] || err "Lancer avec sudo : sudo bash $0"

# Vérifier qu'on est sur le bon user
id "$USER" &>/dev/null || err "L'utilisateur '$USER' n'existe pas — reconfigurer via Raspberry Pi Imager"

echo ""
echo "============================================================"
echo "  R2-D2 Master — Installation automatique"
echo "============================================================"
echo ""

# =============================================================================
# ÉTAPE 1 — Mise à jour système + paquets
# =============================================================================
info "Étape 1/8 — Mise à jour système..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq python3-pip python3-serial git rsync avahi-daemon
ok "Paquets installés"

# =============================================================================
# ÉTAPE 2 — Clone du repo
# =============================================================================
info "Étape 2/8 — Clone du repo git..."
if [ -d "$REPO_PATH/.git" ]; then
    warn "Repo déjà présent — git pull..."
    sudo -u "$USER" git -C "$REPO_PATH" pull --ff-only || warn "git pull échoué (pas de connexion ?)"
else
    sudo -u "$USER" git clone "$REPO_URL" "$REPO_PATH" || err "git clone échoué — vérifier la connexion internet"
fi
sudo -u "$USER" git -C "$REPO_PATH" rev-parse --short HEAD > "$REPO_PATH/VERSION"
ok "Repo cloné — version : $(cat $REPO_PATH/VERSION)"

# =============================================================================
# ÉTAPE 3 — Fix UART : libérer ttyAMA0 du Bluetooth
# =============================================================================
info "Étape 3/8 — Fix UART (disable-bt)..."
CONFIG="/boot/firmware/config.txt"
if grep -q "dtoverlay=disable-bt" "$CONFIG"; then
    ok "dtoverlay=disable-bt déjà présent"
else
    echo "dtoverlay=disable-bt" >> "$CONFIG"
    ok "dtoverlay=disable-bt ajouté dans $CONFIG"
fi

# =============================================================================
# ÉTAPE 4 — Activation UART hardware + I2C
# =============================================================================
info "Étape 4/8 — Activation UART + I2C..."
raspi-config nonint do_serial_hw 0   # active UART hardware
raspi-config nonint do_serial_cons 1 # désactive console série sur UART
raspi-config nonint do_i2c 0         # active I2C
ok "UART hardware activé, console série désactivée, I2C activé"

# =============================================================================
# ÉTAPE 5 — Dépendances Python
# =============================================================================
info "Étape 5/8 — Installation dépendances Python..."
sudo -u "$USER" pip3 install --break-system-packages -q \
    -r "$REPO_PATH/master/requirements.txt"
ok "Dépendances Python installées"

# =============================================================================
# ÉTAPE 6 — Copie local.cfg
# =============================================================================
info "Étape 6/8 — Configuration local.cfg..."
LOCAL_CFG="$REPO_PATH/master/config/local.cfg"
if [ -f "$LOCAL_CFG" ]; then
    warn "local.cfg déjà présent — conservé tel quel"
else
    sudo -u "$USER" cp "$REPO_PATH/master/config/local.cfg.example" "$LOCAL_CFG"
    ok "local.cfg créé depuis l'exemple (toutes les valeurs sont pré-remplies)"
fi

# =============================================================================
# ÉTAPE 7 — Configuration réseau (hotspot + wlan1)
# =============================================================================
info "Étape 7/8 — Configuration réseau..."
bash "$REPO_PATH/scripts/setup_master_network.sh"

# =============================================================================
# ÉTAPE 8 — Services systemd
# =============================================================================
info "Étape 8/8 — Installation services systemd..."
cp "$REPO_PATH/master/services/r2d2-master.service"  /etc/systemd/system/
cp "$REPO_PATH/master/services/r2d2-monitor.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable r2d2-master r2d2-monitor
ok "Services systemd installés et activés"

# =============================================================================
# Résumé
# =============================================================================
echo ""
echo "============================================================"
echo "  Installation Master terminée ✓"
echo "============================================================"
echo ""
echo "  Repo    : $REPO_PATH"
echo "  Version : $(cat $REPO_PATH/VERSION)"
echo ""
echo "  Après le reboot :"
echo "    → Connecte-toi au hotspot R2D2_Control"
echo "    → SSH : ssh artoo@192.168.4.1"
echo "    → Vérifie : sudo systemctl status r2d2-master"
echo ""
echo "  Prochaine étape : installer le Slave"
echo "    sudo bash $REPO_PATH/scripts/setup_slave_network.sh"
echo ""
echo "============================================================"
echo ""

read -p "Rebooter maintenant ? [O/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    reboot
fi
