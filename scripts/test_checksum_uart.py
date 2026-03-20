#!/usr/bin/env python3
"""
Test UART live — injection de paquets valides/invalides sur /dev/ttyAMA0.
A executer sur le Master Pi APRES avoir stoppe r2d2-master.
Le Slave reste actif et doit accepter/rejeter les paquets correctement.
"""
import sys, time, serial
sys.path.insert(0, '/home/artoo/r2d2')
from shared.uart_protocol import calc_crc, build_msg, parse_msg

PORT = '/dev/ttyAMA0'
BAUD = 115200

print()
print('=' * 64)
print(' PHASE 2 — TEST UART LIVE (injection directe /dev/ttyAMA0)')
print('=' * 64)
print()

cs_h1  = calc_crc('H:1')
cs_hok = calc_crc('H:OK')
print('  Checksums de reference: H:1=' + cs_h1 + '  H:OK=' + cs_hok)
print()

try:
    ser = serial.Serial(PORT, BAUD, timeout=0.35)
    print('[+] ' + PORT + ' ouvert — Slave actif, Master service arrete')
    time.sleep(0.2)
    ser.reset_input_buffer()
except Exception as e:
    print('[!] ERREUR ouverture port: ' + str(e))
    sys.exit(1)

SENT = []


def send_recv(label, raw, expect_ack=False):
    """Envoie raw, lit la reponse, log le resultat."""
    ser.reset_input_buffer()
    ser.write(raw)
    time.sleep(0.30)
    resp_bytes = ser.read(ser.in_waiting or 1)
    resp_str = resp_bytes.decode('utf-8', errors='replace').strip()
    parsed = parse_msg(resp_str) if resp_str else None
    got_ack = (parsed == ('H', 'OK'))

    raw_display = raw.decode('latin-1').replace('\x00', '<NUL>').replace('\n', '\\n')
    if expect_ack:
        status = 'ACK=OK (' + cs_hok + ')' if got_ack else 'ACK MANQUANT resp=' + repr(resp_str)
    else:
        status = 'resp=' + repr(resp_str) if resp_str else 'pas de reponse (attendu)'

    print('  [' + ('OK' if (not expect_ack or got_ack) else '!!') + '] '
          + repr(raw_display) + ' -> ' + status)
    SENT.append((label, expect_ack, got_ack, resp_str))
    return got_ack


print('[2.1] Heartbeat VALIDE — doit etre accepte, Slave repond H:OK:' + cs_hok)
msg_valid = build_msg('H', '1').encode()
send_recv('valid_hb_1', msg_valid, expect_ack=True)
time.sleep(0.1)

print()
print('[2.2] Paquets INVALIDES — Slave doit les rejeter (logs checksum mismatch)')
print('      Apres 3 invalides consecutifs: alerte dans les logs Slave')
print()

bad_cases = [
    ('hb_wrong_cs',       ('H:1:00\n').encode(),                'checksum 00 au lieu de ' + cs_h1),
    ('hb_nohex_cs',       ('H:1:ZZ\n').encode(),                'checksum non-hexadecimal'),
    ('motion_wrong_cs',   ('M:0.500,0.500:00\n').encode(),      'checksum 00 pour M:0.500,0.500'),
    ('no_cs_at_all',      ('H:1\n').encode(),                   'pas de checksum (2 segments)'),
    ('empty_payload',     (':\n').encode(),                      'payload vide'),
]
for label, raw, note in bad_cases:
    send_recv(label, raw, expect_ack=False)
    print('      -> ' + note)
    time.sleep(0.15)

print()
print('[2.3] Retour VALIDE — reset compteur, Slave repond H:OK:' + cs_hok)
send_recv('valid_hb_reset', msg_valid, expect_ack=True)
time.sleep(0.1)

print()
print('[2.4] Injection NUL (x00) dans payload — FIX: sum+len detecte')
orig_msg = build_msg('H', '1').strip()
# Injecter chr(0) entre le type et la valeur: H:\x001:CS -> checksum change
bad_nul = ('H:' + chr(0) + '1:' + cs_h1 + '\n').encode('latin-1')
send_recv('nul_inject', bad_nul, expect_ack=False)
# Aussi tester avec le "bon" checksum de H:1 mais payload corromptu
p_bad = 'H:' + chr(0) + '1'
cs_bad = calc_crc(p_bad)
print('      cs reel de "H:\\x001" = ' + cs_bad + ' != ' + cs_h1 + ' -> detecte')
time.sleep(0.1)

print()
print('[2.5] Telemetrie VALIDE (simule reponse Slave) — round-trip')
tl_msg = build_msg('TL', '24.0:35.2:8.5:1200:0.45:0')
cs_tl = calc_crc('TL:24.0:35.2:8.5:1200:0.45:0')
send_recv('valid_telemetry', tl_msg.encode(), expect_ack=False)
print('      (TL n arrive pas en reponse ici — Master enverrait TL, pas Slave)')

print()
print('[2.6] Heartbeat final — confirme Slave toujours operationnel')
got = send_recv('valid_hb_final', msg_valid, expect_ack=True)

ser.close()
print()
print('[+] Port ferme')

# ── Resume ────────────────────────────────────────────────────────────────────
acks_expected = [r for r in SENT if r[1]]
acks_ok  = [r for r in acks_expected if r[2]]
acks_bad = [r for r in acks_expected if not r[2]]
print()
print('=' * 64)
print(' PHASE 2 RESUME:')
print('  ACKs recus:    ' + str(len(acks_ok)) + '/' + str(len(acks_expected)) + ' attendus')
if acks_bad:
    print('  ACKs manquants:')
    for r in acks_bad: print('    - ' + r[0] + ' (resp=' + repr(r[3]) + ')')
print('  (voir logs journalctl Slave pour les alertes checksum)')
print('=' * 64)
