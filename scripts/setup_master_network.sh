#!/bin/bash
# =============================================================================
# setup_master_network.sh — Configuration réseau R2-D2 Master
# =============================================================================
#
# Ce script doit être exécuté UNE SEULE FOIS sur le R2-Master.
#
# Ce qu'il fait :
#   1. Lit les credentials WiFi maison déjà configurés sur wlan0
#   2. Les sauvegarde dans local.cfg (survit aux git pull)
#   3. Configure wlan1 (clé USB) pour se connecter au WiFi maison
#   4. Convertit wlan0 en point d'accès R2D2_Control (192.168.4.1)
#
# Résultat final :
#   wlan0  → Hotspot "R2D2_Control"  192.168.4.1  (Slave + télécommande)
#   wlan1  → WiFi maison              DHCP         (git pull / GitHub)
#
# Prérequis :
#   - Raspberry Pi OS Bookworm 64-bit Lite (NetworkManager actif)
#   - Pi connecté au WiFi maison via wlan0 (état initial)
#   - Clé USB WiFi branchée (sera wlan1) OU brancher plus tard
#
# Usage :
#   sudo bash /home/artoo/r2d2/scripts/setup_master_network.sh
#
# =============================================================================

set -e

REPO_PATH="/home/artoo/r2d2"
LOCAL_CFG="${REPO_PATH}/master/config/local.cfg"
LOCAL_CFG_EXAMPLE="${REPO_PATH}/master/config/local.cfg.example"

HOTSPOT_SSID="R2D2_Control"
HOTSPOT_PASS="r2d2droid"
HOTSPOT_IP="192.168.4.1/24"
HOTSPOT_CON="r2d2-hotspot"
INTERNET_CON="r2d2-internet"

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
echo -e "${BLU}  R2-D2 Master — Configuration réseau  ${NC}"
echo -e "${BLU}========================================${NC}"
echo ""

# --- Vérification root ---
[[ $EUID -eq 0 ]] || die "Ce script doit être exécuté avec sudo"

# --- Vérification NetworkManager ---
if ! systemctl is-active --quiet NetworkManager; then
    die "NetworkManager n'est pas actif. Bookworm requis.\n    sudo systemctl enable --now NetworkManager"
fi
ok "NetworkManager actif"

# --- Vérification repo ---
[[ -d "$REPO_PATH" ]] || die "Repo introuvable: $REPO_PATH\n    Cloner d'abord: git clone ... $REPO_PATH"

# =============================================================================
# ÉTAPE 1 — Récupérer les credentials WiFi maison depuis wlan0
# =============================================================================
echo ""
info "Étape 1 — Lecture des credentials WiFi maison (wlan0 actuel)..."

HOME_SSID=""
HOME_PASS=""

# Trouver le nom de connexion active sur wlan0
WLAN0_CON=$(nmcli -g GENERAL.CONNECTION device show wlan0 2>/dev/null | tr -d ' ')

if [[ -n "$WLAN0_CON" && "$WLAN0_CON" != "--" ]]; then
    info "Connexion active sur wlan0 : '$WLAN0_CON'"

    # Extraire SSID
    HOME_SSID=$(nmcli -g 802-11-wireless.ssid connection show "$WLAN0_CON" 2>/dev/null | tr -d ' ')

    # Extraire mot de passe (requiert sudo, déjà root ici)
    HOME_PASS=$(nmcli -s -g 802-11-wireless-security.psk connection show "$WLAN0_CON" 2>/dev/null | tr -d ' ')

    if [[ -n "$HOME_SSID" ]]; then
        ok "SSID détecté : '$HOME_SSID'"
    fi
    if [[ -n "$HOME_PASS" ]]; then
        ok "Mot de passe récupéré (masqué)"
    else
        warn "Mot de passe non trouvé automatiquement (réseau ouvert ou format inconnu)"
    fi
else
    warn "Aucune connexion active sur wlan0"
fi

# --- Demander confirmation ou saisie manuelle ---
echo ""
if [[ -n "$HOME_SSID" ]]; then
    read -r -p "Utiliser le WiFi '${HOME_SSID}' pour wlan1 (internet) ? [O/n] " CONFIRM
    if [[ "$CONFIRM" =~ ^[Nn] ]]; then
        HOME_SSID=""
        HOME_PASS=""
    fi
fi

if [[ -z "$HOME_SSID" ]]; then
    echo ""
    info "Saisie manuelle des credentials WiFi maison :"
    read -r -p "  SSID (nom du réseau WiFi) : " HOME_SSID
    [[ -n "$HOME_SSID" ]] || die "SSID vide — abandon"
    read -r -s -p "  Mot de passe WiFi        : " HOME_PASS
    echo ""
fi

# =============================================================================
# ÉTAPE 2 — Sauvegarder dans local.cfg
# =============================================================================
echo ""
info "Étape 2 — Sauvegarde dans local.cfg..."

# Créer local.cfg depuis l'exemple s'il n'existe pas encore
if [[ ! -f "$LOCAL_CFG" ]]; then
    if [[ -f "$LOCAL_CFG_EXAMPLE" ]]; then
        cp "$LOCAL_CFG_EXAMPLE" "$LOCAL_CFG"
        chown artoo:artoo "$LOCAL_CFG"
        info "local.cfg créé depuis l'exemple"
    else
        die "local.cfg.example introuvable : $LOCAL_CFG_EXAMPLE"
    fi
fi

# Fonction pour écrire/mettre à jour une clé dans une section .cfg
cfg_set() {
    local file="$1" section="$2" key="$3" value="$4"
    # Vérifier si la section existe
    if grep -q "^\[${section}\]" "$file"; then
        # Mettre à jour ou ajouter la clé dans la section
        if grep -q "^${key}\s*=" "$file"; then
            sed -i "s|^${key}\s*=.*|${key} = ${value}|" "$file"
        else
            sed -i "/^\[${section}\]/a ${key} = ${value}" "$file"
        fi
    else
        # Ajouter la section entière
        echo "" >> "$file"
        echo "[${section}]" >> "$file"
        echo "${key} = ${value}" >> "$file"
    fi
}

cfg_set "$LOCAL_CFG" "home_wifi" "ssid"     "$HOME_SSID"
cfg_set "$LOCAL_CFG" "home_wifi" "password" "$HOME_PASS"
chown artoo:artoo "$LOCAL_CFG"

ok "Credentials WiFi sauvegardés dans local.cfg [home_wifi]"

# =============================================================================
# ÉTAPE 3 — Configurer wlan1 (clé USB) pour le WiFi maison
# =============================================================================
echo ""
info "Étape 3 — Configuration wlan1 → WiFi maison '$HOME_SSID'..."

# Supprimer l'ancienne connexion r2d2-internet si elle existe
if nmcli connection show "$INTERNET_CON" &>/dev/null; then
    nmcli connection delete "$INTERNET_CON"
    info "Ancienne connexion '$INTERNET_CON' supprimée"
fi

# Créer la connexion wlan1
if [[ -n "$HOME_PASS" ]]; then
    nmcli connection add \
        type wifi \
        ifname wlan1 \
        con-name "$INTERNET_CON" \
        ssid "$HOME_SSID" \
        wifi-sec.key-mgmt wpa-psk \
        wifi-sec.psk "$HOME_PASS" \
        connection.autoconnect yes \
        connection.autoconnect-priority 10
else
    # Réseau ouvert
    nmcli connection add \
        type wifi \
        ifname wlan1 \
        con-name "$INTERNET_CON" \
        ssid "$HOME_SSID" \
        connection.autoconnect yes \
        connection.autoconnect-priority 10
fi

ok "Connexion '$INTERNET_CON' créée pour wlan1"

# Tenter de la démarrer si wlan1 existe déjà
if ip link show wlan1 &>/dev/null; then
    info "wlan1 détecté — connexion en cours..."
    nmcli connection up "$INTERNET_CON" && ok "wlan1 connecté à '$HOME_SSID'" \
        || warn "Connexion wlan1 échouée — vérifie que la clé USB WiFi est branchée"
else
    warn "wlan1 non détecté maintenant — la connexion s'activera automatiquement au prochain branchement de la clé USB"
fi

# =============================================================================
# ÉTAPE 4 — Supprimer la connexion wlan0 maison et créer le hotspot
# =============================================================================
echo ""
info "Étape 4 — Conversion wlan0 en hotspot '$HOTSPOT_SSID'..."

# Supprimer l'ancienne connexion hotspot si elle existe
if nmcli connection show "$HOTSPOT_CON" &>/dev/null; then
    nmcli connection delete "$HOTSPOT_CON"
    info "Ancien hotspot supprimé"
fi

# Supprimer la connexion WiFi maison de wlan0 pour libérer l'interface
if [[ -n "$WLAN0_CON" && "$WLAN0_CON" != "--" ]]; then
    # Désactiver d'abord, puis configurer pour ne plus être prioritaire
    # On NE supprime PAS — NetworkManager sera redirigé via autoconnect
    nmcli connection modify "$WLAN0_CON" connection.interface-name wlan1 2>/dev/null || true
    info "Connexion '$WLAN0_CON' redirigée vers wlan1"
fi

# Créer le hotspot sur wlan0
nmcli connection add \
    type wifi \
    ifname wlan0 \
    con-name "$HOTSPOT_CON" \
    ssid "$HOTSPOT_SSID" \
    mode ap \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$HOTSPOT_PASS" \
    ipv4.method shared \
    ipv4.addresses "$HOTSPOT_IP" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 100

ok "Hotspot '$HOTSPOT_CON' créé sur wlan0"

# Activer le hotspot
nmcli connection up "$HOTSPOT_CON" && ok "Hotspot démarré sur wlan0" \
    || warn "Démarrage hotspot différé au reboot"

# =============================================================================
# ÉTAPE 5 — Avahi pour résolution .local
# =============================================================================
echo ""
info "Étape 5 — Vérification avahi-daemon (.local DNS)..."

if ! command -v avahi-daemon &>/dev/null; then
    apt-get install -y avahi-daemon -qq
fi
systemctl enable --now avahi-daemon
ok "avahi-daemon actif (r2-master.local / r2-slave.local)"

# =============================================================================
# RÉSUMÉ
# =============================================================================
echo ""
echo -e "${GRN}========================================${NC}"
echo -e "${GRN}  Configuration réseau terminée ✓      ${NC}"
echo -e "${GRN}========================================${NC}"
echo ""
echo -e "  ${BLU}wlan0${NC} → Hotspot permanent"
echo    "         SSID : ${HOTSPOT_SSID}"
echo    "         Clé  : ${HOTSPOT_PASS}"
echo    "         IP   : 192.168.4.1"
echo ""
echo -e "  ${BLU}wlan1${NC} → WiFi maison (clé USB)"
echo    "         SSID : ${HOME_SSID}"
echo    "         (connexion auto au branchement)"
echo ""
echo -e "  ${YEL}Credentials sauvegardés dans :${NC}"
echo    "    ${LOCAL_CFG}"
echo    "    → section [home_wifi]"
echo ""
echo -e "  ${YEL}Prochaines étapes :${NC}"
echo    "    1. Brancher la clé USB WiFi (si pas encore fait)"
echo    "    2. sudo reboot"
echo    "    3. Connecter le R2-Slave au hotspot '${HOTSPOT_SSID}'"
echo    "    4. Tester : ping 192.168.4.1 (depuis Slave ou téléphone)"
echo ""
