#!/bin/bash
# update.sh — Mise à jour complète R2-D2 : git pull + rsync Slave + restart tout
# Usage: bash scripts/update.sh
# À exécuter sur le Master (r2-master.local)

REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10"
VERSION_FILE=$REPO/VERSION
ERRORS=0

# ──────────────────────────────────────────────
# Helpers affichage
# ──────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; ERRORS=$((ERRORS+1)); }
step() { echo -e "\n${CYAN}[$1]${NC} $2"; }

echo -e "${CYAN}"
echo "  ██████╗ ██████╗    ██████╗ ██████╗ "
echo "  ██╔══██╗╚════██╗   ██╔══██╗╚════██╗"
echo "  ██████╔╝ █████╔╝   ██║  ██║ █████╔╝"
echo "  ██╔══██╗██╔═══╝    ██║  ██║██╔═══╝ "
echo "  ██║  ██║███████╗   ██████╔╝███████╗"
echo "  ╚═╝  ╚═╝╚══════╝   ╚═════╝ ╚══════╝"
echo -e "         UPDATE SYSTEM${NC}"
echo "  ────────────────────────────────────"

# ──────────────────────────────────────────────
# 1. Git pull
# ──────────────────────────────────────────────
step "1/5" "Git pull"
if ip addr show wlan1 2>/dev/null | grep -q "inet "; then
    cd "$REPO"
    if git pull --ff-only 2>&1 | grep -q "Already up to date"; then
        ok "Déjà à jour — $(cat $VERSION_FILE 2>/dev/null || git rev-parse --short HEAD)"
    else
        git rev-parse --short HEAD > "$VERSION_FILE"
        ok "Mis à jour → version: $(cat $VERSION_FILE)"
    fi
else
    warn "wlan1 non disponible — git pull ignoré, version locale utilisée"
fi

# ──────────────────────────────────────────────
# 2. Vérifier le Slave
# ──────────────────────────────────────────────
step "2/5" "Connexion Slave"
if ! $SSH $SLAVE "echo ok" > /dev/null 2>&1; then
    fail "Slave inaccessible — vérifier le Wi-Fi hotspot"
    echo -e "\n${RED}Arrêt — Slave requis pour continuer.${NC}"
    exit 1
fi
ok "Slave joignable ($SLAVE)"

# ──────────────────────────────────────────────
# 3. Rsync vers le Slave
# ──────────────────────────────────────────────
step "3/5" "Sync code vers Slave"

rsync -az --delete \
    -e "$SSH" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='sounds/*.mp3' \
    --exclude='vendor/' \
    "$REPO/slave/" "$SLAVE:$REPO/slave/" 2>&1 && ok "slave/ synchronisé" || fail "rsync slave/ échoué"

rsync -az \
    -e "$SSH" \
    --exclude='__pycache__' \
    "$REPO/shared/" "$SLAVE:$REPO/shared/" 2>&1 && ok "shared/ synchronisé" || fail "rsync shared/ échoué"

rsync -az -e "$SSH" "$VERSION_FILE" "$SLAVE:$VERSION_FILE" 2>/dev/null
ok "VERSION synchronisé → $(cat $VERSION_FILE 2>/dev/null || echo 'unknown')"

# ──────────────────────────────────────────────
# 4. Redémarrer le Slave
# ──────────────────────────────────────────────
step "4/5" "Redémarrage Slave"
if $SSH $SLAVE "sudo systemctl restart r2d2-slave.service" 2>/dev/null; then
    ok "Service r2d2-slave redémarré"
else
    warn "systemctl échoué — reboot Slave..."
    $SSH $SLAVE "sudo reboot" 2>/dev/null && ok "Slave en reboot" || fail "Reboot Slave échoué"
fi

# ──────────────────────────────────────────────
# 5. Redémarrer le Master
# ──────────────────────────────────────────────
step "5/5" "Redémarrage Master"
echo -e "  ${YELLOW}→ Le Master va redémarrer dans 3 secondes...${NC}"
sleep 1

VERSION=$(cat "$VERSION_FILE" 2>/dev/null || echo "unknown")

echo ""
echo "  ────────────────────────────────────"
if [ $ERRORS -eq 0 ]; then
    echo -e "  ${GREEN}✓ Update terminé — version: ${VERSION}${NC}"
else
    echo -e "  ${YELLOW}⚠ Update terminé avec $ERRORS erreur(s) — version: ${VERSION}${NC}"
fi
echo "  ────────────────────────────────────"
echo ""

sleep 2
sudo systemctl restart r2d2-master.service r2d2-monitor.service 2>/dev/null || \
    sudo systemctl restart r2d2-master.service 2>/dev/null || \
    { echo "systemctl non disponible — relance manuelle requise"; }
