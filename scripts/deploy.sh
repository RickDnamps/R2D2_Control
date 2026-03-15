#!/bin/bash
# deploy.sh — Déploie le code Slave sur le R2-Slave (Pi 4B 2G) et redémarre le service
# Usage: bash scripts/deploy.sh [--no-reboot] [--git-pull]
#
# Options:
#   --no-reboot   rsync uniquement, sans redémarrer le Slave
#   --git-pull    git pull avant le rsync (nécessite wlan1 connecté)

set -e

REPO_PATH="/home/artoo/r2d2"
SLAVE_USER="artoo"
SLAVE_HOST="r2-slave.local"
SLAVE_REPO="/home/artoo/r2d2"
VERSION_FILE="/home/artoo/r2d2/VERSION"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"
VENDOR_DIR="$REPO_PATH/slave/vendor"

DO_REBOOT=true
DO_GIT_PULL=false
FIRST_INSTALL=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --no-reboot)     DO_REBOOT=false ;;
        --git-pull)      DO_GIT_PULL=true ;;
        --first-install) FIRST_INSTALL=true ;;
    esac
done

echo "=== R2-D2 Deploy ==="

# ------------------------------------------------------------------
# git pull optionnel
# ------------------------------------------------------------------
if [ "$DO_GIT_PULL" = true ]; then
    echo "[1/4] git pull..."
    if ip addr show wlan1 | grep -q "inet "; then
        cd "$REPO_PATH"
        git pull && git rev-parse --short HEAD > "$VERSION_FILE"
        echo "      git pull OK — version: $(cat $VERSION_FILE)"
    else
        echo "      wlan1 non disponible — git pull ignoré"
    fi
else
    echo "[1/4] git pull ignoré (utiliser --git-pull pour l'activer)"
fi

# ------------------------------------------------------------------
# Vérifier que le Slave est joignable
# ------------------------------------------------------------------
echo "[2/4] Vérification connexion Slave (${SLAVE_HOST})..."
if ! ssh $SSH_OPTS "${SLAVE_USER}@${SLAVE_HOST}" echo "ping" > /dev/null 2>&1; then
    echo "ERREUR: Impossible de joindre le Slave ${SLAVE_HOST}"
    echo "       Vérifier que le R2-Slave est connecté au hotspot R2D2_Control"
    exit 1
fi
echo "      Slave joignable OK"

# ------------------------------------------------------------------
# rsync slave/ + shared/ + VERSION
# ------------------------------------------------------------------
echo "[3/4] rsync vers ${SLAVE_HOST}..."

rsync -avz --delete \
    -e "ssh $SSH_OPTS" \
    "$REPO_PATH/slave/" \
    "${SLAVE_USER}@${SLAVE_HOST}:${SLAVE_REPO}/slave/"

rsync -avz \
    -e "ssh $SSH_OPTS" \
    "$REPO_PATH/shared/" \
    "${SLAVE_USER}@${SLAVE_HOST}:${SLAVE_REPO}/shared/"

rsync -az \
    -e "ssh $SSH_OPTS" \
    "$VERSION_FILE" \
    "${SLAVE_USER}@${SLAVE_HOST}:${VERSION_FILE}"

LOCAL_VERSION=$(cat "$VERSION_FILE" 2>/dev/null || echo "unknown")
echo "      rsync OK — version déployée: ${LOCAL_VERSION}"

# ------------------------------------------------------------------
# Dépendances pip — installation depuis le cache local (vendor/)
# Le vendor/ est pré-téléchargé sur le Master (internet requis une fois)
# puis transféré au Slave via rsync → aucun internet requis sur le Slave
# ------------------------------------------------------------------
echo "      Dépendances pip..."
REQS="$REPO_PATH/slave/requirements.txt"

if [ -d "$VENDOR_DIR" ] && [ "$(ls -A $VENDOR_DIR)" ]; then
    # Installer depuis le cache local — fonctionne sans internet
    echo "      → installation offline depuis vendor/"
    ssh $SSH_OPTS "${SLAVE_USER}@${SLAVE_HOST}" \
        "pip3 install --break-system-packages -q --no-index --find-links=${SLAVE_REPO}/vendor -r ${SLAVE_REPO}/requirements.txt"
else
    # Pas de vendor/ : télécharger depuis PyPI (nécessite NAT wlan1 actif)
    echo "      → vendor/ absent, téléchargement PyPI (nécessite internet via Master NAT)"
    if ip addr show wlan1 2>/dev/null | grep -q "inet "; then
        # Pré-télécharger sur le Master ET installer sur le Slave
        mkdir -p "$VENDOR_DIR"
        pip3 download -q -r "$REQS" -d "$VENDOR_DIR"
        # Re-rsync le vendor/ fraîchement créé
        rsync -az -e "ssh $SSH_OPTS" "$VENDOR_DIR/" "${SLAVE_USER}@${SLAVE_HOST}:${SLAVE_REPO}/vendor/"
        ssh $SSH_OPTS "${SLAVE_USER}@${SLAVE_HOST}" \
            "pip3 install --break-system-packages -q --no-index --find-links=${SLAVE_REPO}/vendor -r ${SLAVE_REPO}/requirements.txt"
        echo "      → vendor/ créé pour les prochains déploiements offline"
    else
        echo "      ATTENTION: vendor/ absent et wlan1 indisponible — pip ignoré"
        echo "                 Lancer 'bash scripts/vendor_deps.sh' avec internet pour créer le cache"
    fi
fi

# ------------------------------------------------------------------
# Premier install : services systemd sur le Slave
# ------------------------------------------------------------------
if [ "$FIRST_INSTALL" = true ]; then
    echo "[4/5] Installation services systemd sur le Slave..."
    ssh $SSH_OPTS "${SLAVE_USER}@${SLAVE_HOST}" bash << 'REMOTE'
        sudo cp /home/artoo/r2d2/services/r2d2-slave.service   /etc/systemd/system/
        sudo cp /home/artoo/r2d2/services/r2d2-version.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable r2d2-version r2d2-slave
        echo "Services installés et activés"
REMOTE
    echo "      Services systemd OK"
else
    echo "[4/5] Services systemd ignorés (--first-install non spécifié)"
fi

# ------------------------------------------------------------------
# Reboot Slave
# ------------------------------------------------------------------
if [ "$DO_REBOOT" = true ]; then
    echo "[5/5] Redémarrage service r2d2-slave sur le Slave..."
    ssh $SSH_OPTS "${SLAVE_USER}@${SLAVE_HOST}" \
        "sudo systemctl restart r2d2-slave" 2>/dev/null || \
    ssh $SSH_OPTS "${SLAVE_USER}@${SLAVE_HOST}" \
        "sudo reboot" 2>/dev/null || true
    echo "      Slave redémarré"
else
    echo "[5/5] Reboot ignoré (--no-reboot)"
fi

echo ""
echo "=== Deploy terminé — version: ${LOCAL_VERSION} ==="
