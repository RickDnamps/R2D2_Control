#!/bin/bash
# Test UART — Lance Master + Slave et affiche les logs en temps réel
# Usage: bash scripts/test_uart.sh
# Ctrl+C pour tout arrêter

REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local

echo "=== Test UART R2-D2 ==="
echo "Démarrage Slave..."

# Lance slave.main sur le Slave en background via SSH, logs dans /tmp/slave.log
ssh $SLAVE "cd $REPO && python3 -m slave.main > /tmp/slave.log 2>&1" &
SSH_PID=$!

sleep 1
echo "Démarrage Master..."

# Lance master.main en background, logs dans /tmp/master.log
python3 -m master.main > /tmp/master.log 2>&1 &
MASTER_PID=$!

sleep 1
echo "=== Logs en direct (Ctrl+C pour arrêter) ==="
echo ""

# Cleanup à Ctrl+C
trap "echo ''; echo 'Arrêt...'; kill $MASTER_PID 2>/dev/null; ssh $SLAVE 'pkill -f slave.main' 2>/dev/null; exit 0" INT

# Affiche les deux logs en parallèle avec préfixe
tail -f /tmp/master.log | sed 's/^/[MASTER] /' &
TAIL_M=$!
ssh $SLAVE "tail -f /tmp/slave.log" | sed 's/^/[SLAVE]  /' &
TAIL_S=$!

wait $SSH_PID
