#!/bin/bash
# =============================================================================
# setup_slave.sh — Installation complète du R2-Slave (une seule commande)
# =============================================================================
#
# Ce script automatise toutes les étapes d'installation du Slave :
#   1. Mise à jour système + paquets
#   2. Fix UART (disable-bt pour libérer ttyAMA0)
#   3. Activation UART + I2C via raspi-config
#   4. Création du dossier /home/artoo/r2d2
#   5. Configuration réseau (wlan0 → hotspot Master)
#   → reboot
#
# Après reboot, le Master fait le rsync + installe les services automatiquement :
#   bash /home/artoo/r2d2/scripts/deploy.sh --first-install
#
# Usage (sur le R2-Slave, connecté au WiFi maison) :
#   curl -fsSL https://raw.githubusercontent.com/RickDnamps/R2D2_Control/main/scripts/setup_slave.sh | sudo bash
#
# Ou si le script est copié depuis le Master :
#   sudo bash /home/artoo/setup_slave.sh
#
# =============================================================================

set -e

REPO_PATH="/home/artoo/r2d2"
USER="artoo"
GITHUB_RAW="https://raw.githubusercontent.com/RickDnamps/R2D2_Control/main"

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

# Vérifier que l'utilisateur artoo existe
id "$USER" &>/dev/null || err "L'utilisateur '$USER' n'existe pas — reconfigurer via Raspberry Pi Imager"

echo ""
echo "============================================================"
echo "  R2-D2 Slave — Installation automatique"
echo "============================================================"
echo ""

# =============================================================================
# ÉTAPE 1 — Mise à jour système + paquets
# =============================================================================
info "Étape 1/5 — Mise à jour système..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq python3-pip python3-serial git alsa-utils avahi-daemon
ok "Paquets installés"

# =============================================================================
# ÉTAPE 2 — Fix UART : libérer ttyAMA0 du Bluetooth
# =============================================================================
info "Étape 2/5 — Fix UART (disable-bt)..."
CONFIG="/boot/firmware/config.txt"
if grep -q "dtoverlay=disable-bt" "$CONFIG"; then
    ok "dtoverlay=disable-bt déjà présent"
else
    echo "dtoverlay=disable-bt" >> "$CONFIG"
    ok "dtoverlay=disable-bt ajouté dans $CONFIG"
fi

# =============================================================================
# ÉTAPE 3 — Activation UART hardware + I2C
# =============================================================================
info "Étape 3/5 — Activation UART + I2C..."
raspi-config nonint do_serial_hw 0   # active UART hardware
raspi-config nonint do_serial_cons 1 # désactive console série sur UART
raspi-config nonint do_i2c 0         # active I2C
ok "UART hardware activé, console série désactivée, I2C activé"

# =============================================================================
# ÉTAPE 4 — Créer le dossier du repo (sera rempli par rsync depuis le Master)
# =============================================================================
info "Étape 4/5 — Préparation dossier repo..."
mkdir -p "$REPO_PATH"
chown "$USER:$USER" "$REPO_PATH"
ok "Dossier $REPO_PATH prêt"

# =============================================================================
# ÉTAPE 5 — Configuration réseau (wlan0 → hotspot Master)
# =============================================================================
info "Étape 5/5 — Configuration réseau..."

# Trouver le script setup_slave_network.sh
NETWORK_SCRIPT=""

# Chercher localement (si lancé depuis le repo ou copié)
for candidate in \
    "$(dirname "$0")/setup_slave_network.sh" \
    "/home/artoo/r2d2/scripts/setup_slave_network.sh" \
    "/home/artoo/setup_slave_network.sh"
do
    if [ -f "$candidate" ]; then
        NETWORK_SCRIPT="$candidate"
        break
    fi
done

# Sinon télécharger depuis GitHub
if [ -z "$NETWORK_SCRIPT" ]; then
    warn "setup_slave_network.sh non trouvé localement — téléchargement depuis GitHub..."
    TMP_SCRIPT=$(mktemp /tmp/setup_slave_network_XXXXXX.sh)
    if curl -fsSL "$GITHUB_RAW/scripts/setup_slave_network.sh" -o "$TMP_SCRIPT" 2>/dev/null; then
        NETWORK_SCRIPT="$TMP_SCRIPT"
        ok "Script téléchargé"
    else
        err "Impossible de télécharger setup_slave_network.sh — vérifier la connexion internet"
    fi
fi

bash "$NETWORK_SCRIPT"

# =============================================================================
# Résumé
# =============================================================================
echo ""
echo "============================================================"
echo "  Installation Slave terminée ✓"
echo "============================================================"
echo ""
echo "  Après le reboot :"
echo "    Le Slave se connecte au hotspot R2D2_Control du Master."
echo ""
echo "  Sur le Master, lancer le premier déploiement :"
echo "    bash /home/artoo/r2d2/scripts/deploy.sh --first-install"
echo ""
echo "  Cela va :"
echo "    → rsync le code sur le Slave"
echo "    → installer les dépendances Python"
echo "    → installer les services systemd"
echo "    → démarrer r2d2-slave"
echo "============================================================"
echo ""

read -p "Rebooter maintenant ? [O/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    reboot
fi
