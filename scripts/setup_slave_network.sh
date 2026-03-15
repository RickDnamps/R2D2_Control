#!/bin/bash
# =============================================================================
# setup_slave_network.sh — Configuration réseau R2-D2 Slave
# =============================================================================
#
# ⚠️  INSTALLER LE MASTER EN PREMIER (setup_master_network.sh).
#     Ce script a besoin du SSID et mot de passe du hotspot Master.
#
# Ce script doit être exécuté UNE SEULE FOIS sur le R2-Slave.
#
# Ce qu'il fait :
#   1. Demande le SSID et mot de passe du hotspot R2-Master
#   2. Remplace la connexion WiFi maison (wlan0) par le hotspot Master
#   3. Configure le hostname r2-slave
#   4. Active avahi-daemon pour résolution r2-slave.local
#
# Résultat final :
#   wlan0  → Hotspot R2-Master  192.168.4.x  (DHCP attribué par Master)
#   (pas de wlan1 — le Slave n'a pas besoin d'internet directement)
#
# Prérequis :
#   - Raspberry Pi OS Bookworm 64-bit Lite (NetworkManager actif)
#   - Slave connecté au WiFi maison via wlan0 (état initial)
#   - R2-Master configuré et hotspot démarré (reboot Master effectué)
#   - SSID + mot de passe du hotspot Master à portée de main
#
# Usage :
#   sudo bash /home/artoo/r2d2/scripts/setup_slave_network.sh
#
# =============================================================================

set -e

HOTSPOT_CON="r2d2-master-hotspot"

# Couleurs
RED='\033[0;31m'
GRN='\033[0;32m'
YEL='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YEL}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERR ]${NC}  $*" >&2; exit 1; }

# =============================================================================
echo ""
echo -e "${BLU}========================================${NC}"
echo -e "${BLU}  R2-D2 Slave — Configuration réseau   ${NC}"
echo -e "${BLU}========================================${NC}"
echo ""
echo -e "  ${YEL}⚠  Le R2-Master doit être configuré et redémarré avant de continuer.${NC}"
echo    "     (setup_master_network.sh doit avoir été exécuté sur le Master)"
echo ""
read -r -p "  Le Master est prêt et son hotspot est actif ? [o/N] " READY
[[ "$READY" =~ ^[Oo] ]] || die "Configurer le Master en premier, puis relancer ce script."

# --- Vérification root ---
[[ $EUID -eq 0 ]] || die "Ce script doit être exécuté avec sudo"

# --- Vérification NetworkManager ---
if ! systemctl is-active --quiet NetworkManager; then
    die "NetworkManager n'est pas actif. Bookworm requis."
fi
ok "NetworkManager actif"

# =============================================================================
# ÉTAPE 1 — Saisir les credentials du hotspot Master
# =============================================================================
echo ""
echo -e "${BLU}--- Credentials du hotspot R2-Master ---${NC}"
echo ""
echo    "  Ces informations se trouvent à la fin de setup_master_network.sh"
echo    "  ou dans /home/artoo/r2d2/master/config/local.cfg [hotspot] sur le Master."
echo ""

HOTSPOT_SSID=""
HOTSPOT_PASS=""

read -r -p "  SSID du hotspot Master [R2D2_Control] : " INPUT
HOTSPOT_SSID="${INPUT:-R2D2_Control}"

while true; do
    read -r -s -p "  Mot de passe du hotspot               : " HOTSPOT_PASS
    echo ""
    if [[ -z "$HOTSPOT_PASS" ]]; then
        warn "Mot de passe vide — réessayer (défaut: r2d2droid si tu n'as pas changé)"
        read -r -s -p "  Mot de passe du hotspot               : " HOTSPOT_PASS
        echo ""
        [[ -n "$HOTSPOT_PASS" ]] || HOTSPOT_PASS="r2d2droid"
    fi
    break
done

echo ""
ok "Hotspot cible : SSID='${HOTSPOT_SSID}'"

# =============================================================================
# ÉTAPE 2 — Supprimer l'ancienne connexion hotspot si elle existe déjà
# =============================================================================
echo ""
info "Étape 2 — Nettoyage des anciennes connexions..."

if nmcli connection show "$HOTSPOT_CON" &>/dev/null; then
    nmcli connection delete "$HOTSPOT_CON"
    info "Ancienne connexion '$HOTSPOT_CON' supprimée"
fi

# =============================================================================
# ÉTAPE 3 — Configurer wlan0 pour se connecter au hotspot Master
# =============================================================================
echo ""
info "Étape 3 — Configuration wlan0 → hotspot Master '${HOTSPOT_SSID}'..."

nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name "$HOTSPOT_CON" \
    ssid "$HOTSPOT_SSID" \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$HOTSPOT_PASS" \
    connection.autoconnect yes \
    connection.autoconnect-priority 100

ok "Connexion '${HOTSPOT_CON}' créée"

# Baisser la priorité des autres connexions WiFi sur wlan0
# pour que le hotspot Master soit toujours préféré
for CON in $(nmcli -g NAME connection show | grep -v "$HOTSPOT_CON"); do
    TYPE=$(nmcli -g connection.type connection show "$CON" 2>/dev/null || true)
    if [[ "$TYPE" == "802-11-wireless" ]]; then
        nmcli connection modify "$CON" connection.autoconnect-priority 1 2>/dev/null || true
        info "Priorité abaissée pour '$CON'"
    fi
done

# =============================================================================
# ÉTAPE 4 — Tenter de se connecter maintenant
# =============================================================================
echo ""
info "Étape 4 — Connexion au hotspot Master..."

# Scanner d'abord pour vérifier que le réseau est visible
VISIBLE=$(nmcli device wifi list ifname wlan0 2>/dev/null | grep "$HOTSPOT_SSID" || true)

if [[ -n "$VISIBLE" ]]; then
    nmcli connection up "$HOTSPOT_CON" && ok "Connecté au hotspot '${HOTSPOT_SSID}' ✓" \
        || warn "Connexion échouée — vérifier mot de passe ou redémarrer"
else
    warn "Hotspot '${HOTSPOT_SSID}' non visible maintenant"
    warn "La connexion s'activera automatiquement au reboot si le Master est en marche"
fi

# =============================================================================
# ÉTAPE 5 — Hostname + avahi
# =============================================================================
echo ""
info "Étape 5 — Hostname et résolution .local..."

# Vérifier/corriger le hostname
CURRENT_HOSTNAME=$(hostname)
if [[ "$CURRENT_HOSTNAME" != "r2-slave" ]]; then
    hostnamectl set-hostname r2-slave
    # Mettre à jour /etc/hosts
    sed -i "s/127.0.1.1.*/127.0.1.1\tr2-slave/" /etc/hosts
    ok "Hostname configuré : r2-slave"
else
    ok "Hostname déjà correct : r2-slave"
fi

if ! command -v avahi-daemon &>/dev/null; then
    apt-get install -y avahi-daemon -qq
fi
systemctl enable --now avahi-daemon
ok "avahi-daemon actif (r2-slave.local)"

# =============================================================================
# RÉSUMÉ
# =============================================================================
echo ""
echo -e "${GRN}========================================${NC}"
echo -e "${GRN}  Slave réseau configuré ✓              ${NC}"
echo -e "${GRN}========================================${NC}"
echo ""
echo -e "  ${BLU}wlan0${NC} → Hotspot R2-Master (au reboot)"
echo    "         SSID     : ${HOTSPOT_SSID}"
echo    "         IP reçue : 192.168.4.x (DHCP Master)"
echo ""
echo -e "  ${BLU}Hostname${NC} : r2-slave  →  r2-slave.local"
echo ""
echo -e "  ${YEL}Prochaines étapes :${NC}"
echo    "    1. sudo reboot"
echo    "    2. Depuis le Master, vérifier :"
echo    "       ping r2-slave.local"
echo    "       ssh artoo@r2-slave.local"
echo    "    3. Continuer l'installation : HOWTO.md Étape 3"
echo ""
