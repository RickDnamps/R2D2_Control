#!/bin/bash
# Test UART — Lance Master + Slave et affiche les logs en temps réel
# Usage: bash scripts/test_uart.sh
# Ctrl+C pour tout arrêter
#
# Si le port /dev/ttyAMA0 est occupé (service systemd), arrêter d'abord :
#   sudo systemctl stop r2d2-master.service r2d2-monitor.service
#   ssh artoo@r2-slave.local "sudo systemctl stop r2d2-slave.service"

REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local

echo "=== Nettoyage ==="
ssh $SLAVE "pkill -9 -f 'slave.main' 2>/dev/null; true"
pkill -9 -f 'master.main' 2>/dev/null
sleep 1
> /tmp/master.log
ssh $SLAVE "> /tmp/slave.log"
echo "OK"

echo "=== Démarrage Slave ==="
ssh $SLAVE "cd $REPO && python3 -m slave.main >> /tmp/slave.log 2>&1" &
SSH_PID=$!
sleep 2

echo "=== Démarrage Master ==="
cd $REPO
python3 -m master.main >> /tmp/master.log 2>&1 &
MASTER_PID=$!
sleep 1

echo ""
echo "=== Logs en direct — Ctrl+C pour tout arrêter ==="
echo ""

trap "echo ''; echo '=== Arrêt ==='; kill $MASTER_PID 2>/dev/null; kill $SSH_PID 2>/dev/null; kill $TAIL_M $TAIL_S 2>/dev/null; ssh $SLAVE 'pkill -9 -f slave.main' 2>/dev/null; exit 0" INT TERM

tail -f /tmp/master.log | sed 's/^/[MASTER] /' &
TAIL_M=$!
ssh $SLAVE "tail -f /tmp/slave.log" | sed 's/^/[SLAVE]  /' &
TAIL_S=$!

wait $TAIL_M $TAIL_S
