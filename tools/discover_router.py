#!/usr/bin/env python3
"""
discover_router.py — Probes your OxyGEN router to find WAN connection names
and CGI commands. Run this first to find the correct values for main.py.

Usage:
    python tools/discover_router.py

Then paste the output in the README or use the values to configure main.py.
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


def fetch(params=None):
    try:
        r = requests.get(BASE_URL, params=params, auth=auth, timeout=6)
        return r.status_code, r.text
    except Exception as e:
        return None, str(e)


print("=" * 60)
print("  OxyGEN Router Discovery Tool")
print(f"  Target: {BASE_URL}")
print("=" * 60)

# 1. Test connection
print("\n[1] Testing connection…")
code, body = fetch()
print(f"    Status: {code}")
if code == 401:
    print("    ❌ Login failed — check USERNAME and PASSWORD.")
    exit(1)
elif code is None:
    print(f"    ❌ Cannot reach router: {body}")
    exit(1)
print("    ✅ Connected successfully")

# 2. Find WAN connections
print("\n[2] Scanning WAN connections page…")
code, body = fetch({"type": "wan", "page": "list"})
print(f"    Status: {code}, Size: {len(body)} bytes")

print("\n    Active connections (green = Connected):")
for line in body.splitlines():
    if "b_green" in line or "b_red" in line:
        flag = re.search(r'id=(\w+)_stat', line)
        status = "🟢 Connected" if "b_green" in line else "🔴 Disconnected"
        if flag:
            print(f"    {status}  →  {flag.group(1)}")

print("\n    All WAN flags found (use green ones in WAN_FLAGS):")
flags = re.findall(r'flag=([\w_]+)', body)
for f in sorted(set(flags)):
    print(f"    → {f}")

# 3. Test hangup/redial commands
print("\n[3] Verifying hangup/redial commands work…")
for cmd in ["hangup", "redial"]:
    c, b = fetch({"type": "wan", "page": cmd, "set_mode": "1",
                  "flag": "VDSL_PPPoE", "redirect_url": "/"})
    print(f"    type=wan&page={cmd}: HTTP {c}")

# 4. CGI exec commands
print("\n[4] CGI exec= commands found:")
execs = re.findall(r'exec[=\s\'"]+([a-zA-Z0-9_\-.]+)', body)
for e in sorted(set(execs)):
    print(f"    → {e}")

print("\n" + "=" * 60)
print("  Copy the green connection names into WAN_FLAGS in main.py")
print("  e.g.  WAN_FLAGS = [\"VDSL_PPPoE\"]")
print("        WAN_STATUS_KEY = \"VDSL_PPPoE_stat\"")
print("=" * 60)
