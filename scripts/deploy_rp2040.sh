#!/usr/bin/env bash
# deploy_rp2040.sh — Pousse le firmware MicroPython vers le RP2040 via USB/ampy
# Usage: bash scripts/deploy_rp2040.sh [/dev/ttyACMx]
#
# Doit être exécuté sur le Slave Pi (où le RP2040 est branché via USB).
# Arrête temporairement r2d2-slave.service pour libérer le port USB.

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FIRMWARE_DIR="$REPO_DIR/rp2040/firmware"

# Couleurs
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[deploy_rp2040]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy_rp2040]${NC} $*"; }
err()  { echo -e "${RED}[deploy_rp2040]${NC} $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Trouver le port RP2040
# ---------------------------------------------------------------------------
find_port() {
    # Chercher par identifiant USB stable (Raspberry Pi / MicroPython)
    local by_id
    by_id=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i "Raspberry_Pi" | head -1)
    if [ -n "$by_id" ]; then
        echo "/dev/serial/by-id/$by_id"
        return
    fi
    # Fallback : tester les ports ACM du plus grand au plus petit
    # (avec VESCs branchés = ttyACM2, sans VESCs = ttyACM0)
    for p in /dev/ttyACM2 /dev/ttyACM1 /dev/ttyACM0; do
        [ -e "$p" ] && echo "$p" && return
    done
}

PORT="${1:-}"
if [ -z "$PORT" ]; then
    PORT="$(find_port)"
fi
[ -z "$PORT" ] && err "Port RP2040 introuvable. Brancher le RP2040 via USB et réessayer."
log "Port RP2040 : $PORT"

# ---------------------------------------------------------------------------
# Installer ampy si absent — s'assurer que ~/.local/bin est dans PATH
# ---------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"

if ! command -v ampy &>/dev/null; then
    warn "ampy non trouvé — installation (adafruit-ampy)..."
    pip3 install --quiet --break-system-packages adafruit-ampy
    export PATH="$HOME/.local/bin:$PATH"
fi

# ---------------------------------------------------------------------------
# Arrêter r2d2-slave.service pour libérer le port
# ---------------------------------------------------------------------------
SLAVE_WAS_RUNNING=false
if systemctl is-active --quiet r2d2-slave.service 2>/dev/null; then
    log "Arrêt r2d2-slave.service (libère le port USB)..."
    sudo systemctl stop r2d2-slave.service
    SLAVE_WAS_RUNNING=true
fi

cleanup() {
    if [ "$SLAVE_WAS_RUNNING" = true ]; then
        log "Redémarrage r2d2-slave.service..."
        sudo systemctl start r2d2-slave.service
    fi
}
trap cleanup EXIT

# Courte pause pour que le port soit bien libéré
sleep 1

# ---------------------------------------------------------------------------
# Pousser les fichiers firmware
# ---------------------------------------------------------------------------
log "Upload display.py..."
ampy --port "$PORT" put "$FIRMWARE_DIR/display.py" display.py

if [ -f "$FIRMWARE_DIR/touch.py" ]; then
    log "Upload touch.py..."
    ampy --port "$PORT" put "$FIRMWARE_DIR/touch.py" touch.py
fi

log "Upload main.py (en dernier — déclenche l'exécution au reset)..."
ampy --port "$PORT" put "$FIRMWARE_DIR/main.py" main.py

# ---------------------------------------------------------------------------
# Reset soft du RP2040
# ---------------------------------------------------------------------------
log "Reset RP2040 (soft reset via ampy)..."
ampy --port "$PORT" reset

log ""
log "✓ Firmware RP2040 déployé sur $PORT"
log "  Le RP2040 redémarre et affiche le spinner BOOTING (orange)."
log "  Si le service r2d2-slave était actif, il redémarre automatiquement."
