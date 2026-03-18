#!/bin/bash
# Test UART — Nettoie, lance Master+Slave, affiche logs en parallèle
# Usage: bash scripts/test_uart.sh
# Ctrl+C pour tout arrêter

REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local

echo "=== Nettoyage ==="
pkill -f 'master.main' 2>/dev/null
pkill -f 'python3 -m master' 2>/dev/null
ssh $SLAVE "pkill -f 'slave.main'; pkill -f 'python3 -m slave'" 2>/dev/null
sleep 1
echo "OK"

echo "=== Démarrage Slave ==="
ssh $SLAVE "cd $REPO && python3 -m slave.main > /tmp/slave.log 2>&1" &
SSH_PID=$!
sleep 2

echo "=== Démarrage Master ==="
cd $REPO && python3 -m master.main > /tmp/master.log 2>&1 &
MASTER_PID=$!
sleep 1

echo "=== Logs en direct (Ctrl+C pour tout arrêter) ==="

trap "
  echo '';
  echo '=== Arrêt ===';
  kill $MASTER_PID 2>/dev/null;
  ssh $SLAVE 'pkill -f slave.main' 2>/dev/null;
  kill $TAIL_M $TAIL_S 2>/dev/null;
  exit 0
" INT

tail -f /tmp/master.log | sed 's/^/[MASTER] /' &
TAIL_M=$!
ssh $SLAVE "tail -f /tmp/slave.log" | sed 's/^/[SLAVE]  /' &
TAIL_S=$!

wait $SSH_PID
