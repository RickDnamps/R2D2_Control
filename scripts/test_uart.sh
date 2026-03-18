#!/bin/bash
# Test UART — Nettoie proprement et lance Master+Slave une seule fois
# Usage: bash scripts/test_uart.sh
# Ctrl+C pour tout arrêter

REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local

echo "=== Nettoyage ==="
# Tuer les anciennes instances sur le Slave
ssh $SLAVE "pkill -9 python3 2>/dev/null; pkill -9 -f 'tail -f' 2>/dev/null; true"
# Tuer les anciennes instances locales (Master)
pkill -9 python3 2>/dev/null
# Tuer les anciennes queues de log
pkill -9 -f 'tail -f /tmp/master.log' 2>/dev/null
pkill -9 -f 'tail -f /tmp/slave.log' 2>/dev/null
sleep 3

# Vider les logs
> /tmp/master.log
ssh $SLAVE "> /tmp/slave.log"
echo "OK"

echo "=== Démarrage Slave ==="
ssh -n $SLAVE "cd $REPO && python3 -m slave.main >> /tmp/slave.log 2>&1 &"
sleep 2

echo "=== Démarrage Master ==="
cd $REPO
python3 -m master.main >> /tmp/master.log 2>&1 &
MASTER_PID=$!
sleep 1

echo ""
echo "=== Logs en direct — Ctrl+C pour tout arrêter ==="
echo ""

cleanup() {
    echo ""
    echo "=== Arrêt ==="
    kill $TAIL_M $TAIL_S 2>/dev/null
    kill $MASTER_PID 2>/dev/null
    ssh $SLAVE "pkill -9 python3" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

tail -f /tmp/master.log | sed 's/^/[MASTER] /' &
TAIL_M=$!

ssh $SLAVE "tail -f /tmp/slave.log" | sed 's/^/[SLAVE]  /' &
TAIL_S=$!

wait $TAIL_M $TAIL_S
