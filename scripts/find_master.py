#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trouve l'IP de r2-master depuis Windows.
Tente mDNS d'abord, puis scan SSH sur le sous-réseau local.
Usage: python3 scripts/find_master.py
"""
import socket
import concurrent.futures
import sys

# Windows cp1252 : forcer UTF-8 sur stdout
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def _try_mdns(hostname='r2-master.local', timeout=2) -> str | None:
    try:
        socket.setdefaulttimeout(timeout)
        ip = socket.gethostbyname(hostname)
        return ip
    except Exception:
        return None


def _get_local_subnet() -> str | None:
    """Retourne le préfixe de sous-réseau local (ex: '192.168.2.')."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return '.'.join(ip.split('.')[:3]) + '.'
    except Exception:
        return None


def _scan_ssh(prefix: str, port=22, timeout=0.5) -> list[str]:
    """Scan SSH sur toutes les IPs du sous-réseau."""
    def check(ip):
        s = socket.socket()
        s.settimeout(timeout)
        r = s.connect_ex((ip, port))
        s.close()
        return ip if r == 0 else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(check, [f'{prefix}{i}' for i in range(2, 255)]))
    return [ip for ip in results if ip]


def find_master() -> str | None:
    # 1. Tentative mDNS
    print('Tentative mDNS r2-master.local...', end=' ', flush=True)
    ip = _try_mdns()
    if ip:
        print(f'trouvé → {ip}')
        return ip
    print('échec')

    # 2. Scan SSH sur le sous-réseau
    prefix = _get_local_subnet()
    if not prefix:
        print('Impossible de déterminer le sous-réseau local')
        return None
    print(f'Scan SSH sur {prefix}0/24...', end=' ', flush=True)
    hosts = _scan_ssh(prefix)
    if not hosts:
        print('aucun hôte SSH trouvé')
        return None
    print(f'{len(hosts)} hôte(s) SSH: {hosts}')

    # Si un seul hôte SSH → c'est probablement le Pi
    if len(hosts) == 1:
        print(f'→ r2-master probablement à {hosts[0]}')
        return hosts[0]

    # Plusieurs hôtes → afficher la liste, laisser l'utilisateur choisir
    print('Plusieurs hôtes SSH trouvés. Lequel est r2-master ?')
    for i, h in enumerate(hosts):
        print(f'  [{i}] {h}')
    return None


if __name__ == '__main__':
    ip = find_master()
    if ip:
        print(f'\nr2-master IP: {ip}')
        sys.exit(0)
    else:
        print('\nNon trouvé')
        sys.exit(1)
