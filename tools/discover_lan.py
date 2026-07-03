#!/usr/bin/env python3
"""
discover_lan.py — Probes your OxyGEN router's LAN pages to verify
that the device list endpoint is accessible with your credentials.

Usage:
    python tools/discover_lan.py
"""

import requests
from requests.auth import HTTPBasicAuth
import re

# ─── SET THESE BEFORE RUNNING ─────────────────────────────────────────────────
ROUTER_IP = "192.168.1.1"
USERNAME  = "user"
PASSWORD  = "your_password_here"
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = f"http://{ROUTER_IP}/cgi-bin/page.pl"
auth     = HTTPBasicAuth(USERNAME, PASSWORD)


def fetch(params):
    try:
        r = requests.get(BASE_URL, params=params, auth=auth, timeout=6)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)


print("=" * 60)
print("  OxyGEN LAN Device Discovery Tool")
print("=" * 60)

print("\n[1] Fetching device list (type=lan&page=clients)...")
code, body = fetch({"type": "lan", "page": "clients"})
print(f"    Status: {code}, Size: {len(body)} bytes")

if code == 401:
    print("    Login denied — try a different username (e.g. 'admin')")
    exit(1)
elif code != 200:
    print(f"    Unexpected status: {code}")
    exit(1)

print("\n    Devices found:")
pattern = r'value="([\d.]+)@([^@"]*)@([0-9a-fA-F:]{17})"[^>]*>([^<]*)<'
devices = []
for m in re.finditer(pattern, body):
    ip, name_attr, mac, label = m.groups()
    name = name_attr.strip() or label.strip() or ip
    devices.append((ip, name, mac))
    print(f"    {ip:16s}  {name:30s}  {mac}")

if not devices:
    print("    (none found — device list may require admin credentials)")

print(f"\n    Total: {len(devices)} devices")
print("\n" + "=" * 60)
print("  If devices shown above, the Devices tab in main.py will work.")
print("=" * 60)
