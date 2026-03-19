#!/bin/bash
# Test servos Master + Slave — vérifie I2C, installe libs si besoin, teste les servos
# Usage: bash scripts/test_servos.sh
# Ctrl+C pour arrêter les tests

REPO=/home/artoo/r2d2
SLAVE=artoo@r2-slave.local

# ──────────────────────────────────────────────
# MASTER — vérification I2C + install + test
# ──────────────────────────────────────────────
echo "=== MASTER — I2C ==="
if ! command -v i2cdetect &>/dev/null; then
    echo "Installation i2c-tools..."
    sudo apt-get install -y i2c-tools -q
fi

I2C_MASTER=$(sudo /usr/sbin/i2cdetect -y 1 2>&1)
echo "$I2C_MASTER" | grep -q "40" && echo "✓ PCA9685 @ 0x40 détecté" || echo "✗ 0x40 NON détecté — vérifier branchement I2C Master"

echo ""
echo "=== MASTER — Dépendances Python ==="
python3 -c "import adafruit_pca9685" 2>/dev/null && echo "✓ adafruit-pca9685 déjà installé" || {
    echo "Installation adafruit-circuitpython-pca9685..."
    pip install adafruit-circuitpython-pca9685 -q && echo "✓ Installé"
}

# ──────────────────────────────────────────────
# SLAVE — vérification I2C + install + test
# ──────────────────────────────────────────────
echo ""
echo "=== SLAVE — Sync scripts ==="
rsync -a $REPO/scripts/ $SLAVE:$REPO/scripts/ && echo "✓ Scripts synchronisés" || echo "⚠ rsync échoué"

echo ""
echo "=== SLAVE — I2C ==="
I2C_SLAVE=$(ssh $SLAVE "sudo /usr/sbin/i2cdetect -y 1 2>&1" 2>&1)
echo "$I2C_SLAVE" | grep -q "41" && echo "✓ PCA9685 @ 0x41 détecté" || echo "✗ 0x41 NON détecté — vérifier branchement I2C Slave"

echo ""
echo "=== SLAVE — Dépendances Python ==="
ssh $SLAVE "python3 -c 'import adafruit_pca9685' 2>/dev/null && echo '✓ adafruit-pca9685 déjà installé' || { pip install adafruit-circuitpython-pca9685 -q && echo '✓ Installé'; }"

# ──────────────────────────────────────────────
# Abort si I2C manquant
# ──────────────────────────────────────────────
if ! echo "$I2C_MASTER" | grep -q "40"; then
    echo ""
    echo "✗ Test annulé — PCA9685 Master non détecté"
    exit 1
fi
if ! echo "$I2C_SLAVE" | grep -q "41"; then
    echo ""
    echo "✗ Test annulé — PCA9685 Slave non détecté"
    exit 1
fi

# ──────────────────────────────────────────────
# LANCEMENT DES TESTS EN PARALLÈLE
# ──────────────────────────────────────────────
echo ""
echo "=== Test servo en cours — Ctrl+C pour arrêter ==="
echo "  Master : PCA9685 @ 0x40, canal 0  (servo dôme)"
echo "  Slave  : PCA9685 @ 0x41, canal 0  (servo body)"
echo ""

cleanup() {
    echo ""
    echo "=== Arrêt ==="
    # SIGINT pour déclencher except KeyboardInterrupt → pca.deinit() → servo s'arrête
    pkill -INT -f test_servo_master.py 2>/dev/null
    ssh $SLAVE "pkill -INT -f test_servo_slave.py" 2>/dev/null
    sleep 1
    kill $MASTER_PID $SLAVE_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

python3 $REPO/scripts/test_servo_master.py 2>&1 | sed 's/^/[MASTER] /' &
MASTER_PID=$!

ssh $SLAVE "python3 $REPO/scripts/test_servo_slave.py 2>&1" | sed 's/^/[SLAVE]  /' &
SLAVE_PID=$!

wait $MASTER_PID $SLAVE_PID
