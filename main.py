#!/usr/bin/env python3
"""
internet_toggle.py — Full-featured router control panel for OxyGEN router.

Features:
  - Toggle internet ON/OFF for all devices
  - Device list
  - Windows toast notifications + offline reminder
  - Password prompt on every launch (never saved)
  - System tray (green/red icon, quick ON/OFF menu)
  - Connection history log (saved to internet_log.json)
  - Light / Dark / Midnight themes
  - Speed test (download, upload, ping)

Requirements:
  pip install PyQt6 requests winotify speedtest-cli

Run:
  python internet_toggle.py
"""

import sys, re, json, os
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSystemTrayIcon, QMenu,
    QDialog, QLineEdit, QSizePolicy, QTabWidget, QComboBox
)
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QPropertyAnimation,
                           QEasingCurve, pyqtProperty, QTimer)
from PyQt6.QtGui import QPainter, QColor, QBrush, QIcon, QPixmap, QLinearGradient, QPen, QFont

# ─── SETTINGS ─────────────────────────────────────────────────────────────────
# Router IP — usually 192.168.1.1 or 192.168.1.254. Check yours at:
#   Windows: run `ipconfig` and look for "Default Gateway"
#   Mac/Linux: run `ip route | grep default`
ROUTER_IP  = "192.168.1.1"

# Router login username — common values: "user", "admin", "root"
# Check the sticker on the back of your router
USERNAME   = "user"

# WAN connection flags — these are the active internet connections on your router.
# To find yours: log into your router admin panel and check the WAN/Internet page.
# Look for connections with a green/connected status.
# Examples: "VDSL_PPPoE", "ADSL_PPPoE", "Eth_PPPoE", "ETH_FWA_Internet"
WAN_FLAGS  = ["VDSL_PPPoE"]

# The string the router uses to show the WAN status in its HTML.
# Format: "<FLAG>_stat" — e.g. "VDSL_PPPoE_stat", "ADSL_PPPoE_stat"
WAN_STATUS_KEY = "VDSL_PPPoE_stat"

BASE_URL   = f"http://{ROUTER_IP}/cgi-bin/page.pl"
REDIRECT   = "../cgi-bin/page.pl%3Ftype%3Dwan%26page%3Dlist"
LOG_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "internet_log.json")
# ──────────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
#  THEMES
# ═══════════════════════════════════════════════════════════════════════════════
THEMES = {
    "Dark": {
        "bg": "#0f172a", "bg2": "#1e293b", "bg3": "#334155",
        "text": "#f1f5f9", "text2": "#94a3b8", "text3": "#475569",
        "border": "#334155", "accent": "#3b82f6",
        "green": "#4ade80", "green_bg": "#14532d",
        "red": "#ef4444",   "red_bg":   "#7f1d1d",
        "amber": "#f59e0b", "amber_bg": "#451a03",
        "log_on": "#166534", "log_off": "#7f1d1d",
    },
    "Light": {
        "bg": "#f8fafc", "bg2": "#e2e8f0", "bg3": "#cbd5e1",
        "text": "#0f172a", "text2": "#475569", "text3": "#94a3b8",
        "border": "#cbd5e1", "accent": "#2563eb",
        "green": "#16a34a", "green_bg": "#dcfce7",
        "red": "#dc2626",   "red_bg":   "#fee2e2",
        "amber": "#d97706", "amber_bg": "#fef3c7",
        "log_on": "#bbf7d0", "log_off": "#fecaca",
    },
    "Midnight": {
        "bg": "#000000", "bg2": "#0d0d0d", "bg3": "#1a1a1a",
        "text": "#e2e8f0", "text2": "#64748b", "text3": "#334155",
        "border": "#1a1a1a", "accent": "#7c3aed",
        "green": "#34d399", "green_bg": "#064e3b",
        "red": "#f87171",   "red_bg":   "#450a0a",
        "amber": "#fbbf24", "amber_bg": "#431407",
        "log_on": "#065f46", "log_off": "#450a0a",
    },
}
_current_theme = "Dark"
def T(k): return THEMES[_current_theme][k]


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG
# ═══════════════════════════════════════════════════════════════════════════════
def log_event(action: str, note: str = ""):
    try:
        entries = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                entries = json.load(f)
    except Exception:
        entries = []
    entries.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": action, "note": note})
    entries = entries[-200:]
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
    except Exception:
        pass

def load_log() -> list:
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


# ═══════════════════════════════════════════════════════════════════════════════
#  TOAST
# ═══════════════════════════════════════════════════════════════════════════════
def toast(title: str, msg: str):
    try:
        from winotify import Notification, audio
        n = Notification(app_id="Internet Control", title=title, msg=msg, duration="short")
        n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  ROUTER API
# ═══════════════════════════════════════════════════════════════════════════════
def make_session(pw):
    s = requests.Session(); s.auth = HTTPBasicAuth(USERNAME, pw); return s

def get_wan_status(pw) -> str:
    try:
        s = make_session(pw)
        r = s.get(BASE_URL, params={"type": "wan", "page": "list"}, timeout=5)
        if r.status_code == 200:
            idx = r.text.find(WAN_STATUS_KEY)
            if idx != -1:
                snippet = r.text[idx:idx+200]
                if "b_green" in snippet: return "ON"
                if "b_red"   in snippet: return "OFF"
    except Exception:
        pass
    return "UNKNOWN"

def set_internet(state, pw) -> tuple:
    page = "redial" if state == "on" else "hangup"
    s = make_session(pw); errors = []
    for flag in WAN_FLAGS:
        params = {"type": "wan", "page": page, "set_mode": "1",
                  "flag": flag, "redirect_url": REDIRECT}
        try:
            r = s.get(BASE_URL, params=params, timeout=6)
            if r.status_code != 200: errors.append(f"{flag}: HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            errors.append("Cannot reach router"); break
        except requests.exceptions.Timeout:
            errors.append("Router timed out"); break
    return (False, " | ".join(errors)) if errors else (True, "ON" if state=="on" else "OFF")

def get_devices(pw) -> list:
    try:
        s = make_session(pw)
        r = s.get(BASE_URL, params={"type": "lan", "page": "clients"}, timeout=6)
        if r.status_code != 200: return []
        pattern = r'value="([\d.]+)@([^@"]*)@([0-9a-fA-F:]{17})"[^>]*>([^<]*)<'
        devices = []
        for m in re.finditer(pattern, r.text):
            ip, name_attr, mac, label = m.groups()
            display_name = name_attr.strip() or label.strip() or ip
            devices.append({"name": display_name, "ip": ip, "mac": mac})
        return devices
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  SPEED TEST
# ═══════════════════════════════════════════════════════════════════════════════
def run_speedtest() -> dict:
    """Returns dict with download, upload (Mbps), ping (ms), server name."""
    import speedtest as st
    s = st.Speedtest(secure=True)
    s.get_best_server()
    s.download(threads=4)
    s.upload(threads=4)
    res = s.results.dict()
    return {
        "download": round(res["download"] / 1_000_000, 2),
        "upload":   round(res["upload"]   / 1_000_000, 2),
        "ping":     round(res["ping"], 1),
        "server":   res["server"]["name"] + ", " + res["server"]["country"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  WORKERS
# ═══════════════════════════════════════════════════════════════════════════════
class WanWorker(QThread):
    done = pyqtSignal(bool, str)
    def __init__(self, state, pw): super().__init__(); self.state=state; self.pw=pw
    def run(self): self.done.emit(*set_internet(self.state, self.pw))

class StatusWorker(QThread):
    done = pyqtSignal(str)
    def __init__(self, pw): super().__init__(); self.pw=pw
    def run(self): self.done.emit(get_wan_status(self.pw))

class DeviceWorker(QThread):
    done = pyqtSignal(list)
    def __init__(self, pw): super().__init__(); self.pw=pw
    def run(self): self.done.emit(get_devices(self.pw))

class ServerListWorker(QThread):
    """Fetches nearby Speedtest servers in the background."""
    done = pyqtSignal(list)
    def run(self):
        try:
            import speedtest as st, xml.etree.ElementTree as ET, urllib.request, gzip

            # Build the speedtest.net config to get the user agent / config
            s = st.Speedtest(secure=True)

            # Fetch the FULL global server list by making multiple requests
            # with different lat/lon offsets to bypass the location filter
            all_servers = {}

            def fetch_server_list(url):
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "Mozilla/5.0 speedtest-cli/2.1.3")
                req.add_header("Accept-Encoding", "gzip")
                try:
                    resp = urllib.request.urlopen(req, timeout=15)
                    raw = resp.read()
                    try: data = gzip.decompress(raw).decode("utf-8")
                    except: data = raw.decode("utf-8")
                    root = ET.fromstring(data)
                    for node in root.findall(".//Server"):
                        a = node.attrib
                        sid = a.get("id")
                        if sid and sid not in all_servers:
                            all_servers[sid] = {
                                "id":      sid,
                                "name":    a.get("name",""),
                                "country": a.get("country",""),
                                "sponsor": a.get("sponsor",""),
                                "host":    a.get("host",""),
                                "d":       0.0,
                            }
                except Exception as e:
                    pass

            # Use the speedtest.net servers-static endpoint with different
            # thread counts to get more servers, and also the dynamic endpoint
            fetch_server_list("https://www.speedtest.net/speedtest-servers-static.php?threads=4")
            fetch_server_list("http://c.speedtest.net/speedtest-servers-static.php?threads=4")
            fetch_server_list("https://www.speedtest.net/speedtest-servers.php?threads=4")

            # Also get whatever speedtest-cli fetches natively (nearby servers)
            # and merge them in
            try:
                s.get_servers([])
                for lst in s.servers.values():
                    for srv in lst:
                        sid = str(srv["id"])
                        if sid not in all_servers:
                            all_servers[sid] = {
                                "id":      sid,
                                "name":    srv.get("name",""),
                                "country": srv.get("country",""),
                                "sponsor": srv.get("sponsor",""),
                                "host":    srv.get("host",""),
                                "d":       round(srv.get("d", 0), 1),
                            }
            except Exception:
                pass

            result = list(all_servers.values())
            result.sort(key=lambda x: (x["country"].lower(), x["name"].lower()))
            self.done.emit(result if result else [])
        except Exception as e:
            self.done.emit([])

class SpeedTestWorker(QThread):
    progress = pyqtSignal(str)
    done     = pyqtSignal(dict)

    def __init__(self, server_id=None):
        super().__init__()
        self.server_id = server_id

    def run(self):
        try:
            import speedtest as st
            s = st.Speedtest(secure=True)
            if self.server_id:
                self.progress.emit("Connecting to selected server…")
                s.get_servers([self.server_id])
                s.get_best_server()
            else:
                self.progress.emit("Finding best server…")
                s.get_best_server()
            srv = s.results.server
            self.progress.emit(f"Testing via {srv['name']}, {srv['country']}…")
            self.progress.emit("Testing download…")
            s.download(threads=4)
            dl = round(s.results.download / 1_000_000, 2)
            self.progress.emit(f"Download: {dl} Mbps  —  Testing upload…")
            s.upload(threads=4)
            res = s.results.dict()
            self.done.emit({
                "download": round(res["download"] / 1_000_000, 2),
                "upload":   round(res["upload"]   / 1_000_000, 2),
                "ping":     round(res["ping"], 1),
                "server":   res["server"]["name"] + ", " + res["server"]["country"],
            })
        except Exception as e:
            self.done.emit({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
#  PASSWORD DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
class PasswordDialog(QDialog):
    def __init__(self, parent=None, error=False):
        super().__init__(parent)
        self.setWindowTitle("Router Login")
        self.setFixedSize(320, 190)
        self.setStyleSheet(f"QDialog{{background:{T('bg')};}} QWidget{{background:{T('bg')};}}")
        layout = QVBoxLayout(self)
        layout.setSpacing(12); layout.setContentsMargins(24,24,24,24)

        title = QLabel("🔐  Enter router password")
        title.setStyleSheet(f"font-size:15px; font-weight:700; color:{T('text')};")
        layout.addWidget(title)
        if error:
            e = QLabel("⚠ Wrong password — try again.")
            e.setStyleSheet(f"color:{T('red')}; font-size:11px;")
            layout.addWidget(e)

        self.pw = QLineEdit()
        self.pw.setPlaceholderText("Password")
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setStyleSheet(
            f"background:{T('bg2')}; border:1px solid {T('border')}; border-radius:6px;"
            f"padding:8px; color:{T('text')}; font-size:13px;")
        layout.addWidget(self.pw)

        btn = QPushButton("Sign in")
        btn.setFixedHeight(38)
        btn.setStyleSheet(
            f"background:{T('accent')}; color:white; border:none;"
            f"border-radius:6px; font-size:13px; font-weight:700;")
        btn.clicked.connect(self.accept)
        self.pw.returnPressed.connect(self.accept)
        layout.addWidget(btn)

    def password(self): return self.pw.text()


# ═══════════════════════════════════════════════════════════════════════════════
#  TOGGLE SWITCH
# ═══════════════════════════════════════════════════════════════════════════════
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 50)
        self._checked = True; self._enabled = True; self._knob_x = 54.0
        self._anim = QPropertyAnimation(self, b"knob_pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @pyqtProperty(float)
    def knob_pos(self): return self._knob_x
    @knob_pos.setter
    def knob_pos(self, v): self._knob_x = v; self.update()

    def setChecked(self, val):
        self._checked = val
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(54.0 if val else 4.0)
        self._anim.start()

    def setEnabled(self, val):
        self._enabled = val
        self.setCursor(Qt.CursorShape.PointingHandCursor if val else Qt.CursorShape.ForbiddenCursor)
        self.update()

    def isChecked(self): return self._checked

    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked); self.toggled.emit(self._checked)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = 180 if not self._enabled else 255
        color = QColor(T("green") if self._checked else T("red")); color.setAlpha(alpha)
        p.setBrush(QBrush(color)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 4, 100, 42, 21, 21)
        p.setBrush(QBrush(QColor(0,0,0,35)))
        p.drawEllipse(int(self._knob_x)+2, 9, 38, 38)
        p.setBrush(QBrush(QColor(255,255,255) if self._enabled else QColor(200,200,200)))
        p.drawEllipse(int(self._knob_x), 7, 38, 38)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  TRAY ICON
# ═══════════════════════════════════════════════════════════════════════════════
def make_tray_icon(state: str) -> QIcon:
    pix = QPixmap(32, 32); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = {"ON": QColor("#4ade80"), "OFF": QColor("#ef4444")}.get(state, QColor("#f59e0b"))
    p.setBrush(QBrush(color)); p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(4, 4, 24, 24); p.end()
    return QIcon(pix)


# ═══════════════════════════════════════════════════════════════════════════════
#  DEVICE ROW
# ═══════════════════════════════════════════════════════════════════════════════
class DeviceRow(QFrame):
    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame{{background:{T('bg2')};border-radius:8px;margin:2px 0;}}")
        self.setFixedHeight(56)
        layout = QHBoxLayout(self); layout.setContentsMargins(12,0,12,0); layout.setSpacing(10)
        dot = QLabel("●"); dot.setStyleSheet(f"color:{T('green')};font-size:10px;"); dot.setFixedWidth(14)
        layout.addWidget(dot)
        info = QVBoxLayout(); info.setSpacing(1)
        n = device["name"][:28] + ("…" if len(device["name"])>28 else "")
        name_lbl = QLabel(n); name_lbl.setStyleSheet(f"color:{T('text')};font-size:13px;font-weight:600;")
        ip_lbl   = QLabel(f"{device['ip']}  ·  {device['mac']}")
        ip_lbl.setStyleSheet(f"color:{T('text3')};font-size:10px;")
        info.addWidget(name_lbl); info.addWidget(ip_lbl)
        layout.addLayout(info); layout.addStretch()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(12,12,12,12); layout.setSpacing(8)
        hdr = QHBoxLayout()
        title = QLabel("Connection History")
        title.setStyleSheet(f"font-size:13px;font-weight:700;color:{T('text2')};letter-spacing:1px;")
        self.clear_btn = QPushButton("🗑 Clear"); self.clear_btn.setFixedSize(70,26)
        self.clear_btn.setStyleSheet(
            f"QPushButton{{background:{T('bg2')};color:{T('text3')};border:1px solid {T('border')};"
            f"border-radius:5px;font-size:11px;}}QPushButton:hover{{color:{T('text2')};}}")
        self.clear_btn.clicked.connect(self._clear)
        hdr.addWidget(title); hdr.addStretch(); hdr.addWidget(self.clear_btn)
        layout.addLayout(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:transparent;}}"
                             f"QScrollBar:vertical{{background:{T('bg')};width:6px;}}"
                             f"QScrollBar::handle:vertical{{background:{T('bg3')};border-radius:3px;}}")
        self.container = QWidget(); self.container.setStyleSheet("background:transparent;")
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0,0,0,0); self.vbox.setSpacing(4)
        self.vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.container); layout.addWidget(scroll)
        self.refresh()

    def refresh(self):
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        entries = load_log()
        if not entries:
            lbl = QLabel("No history yet.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color:{T('text3')};font-size:12px;padding:20px;")
            self.vbox.addWidget(lbl); return
        for i, entry in enumerate(reversed(entries)):
            action = entry.get("action","?"); time_s = entry.get("time",""); is_on = action=="ON"
            real_idx = len(entries)-1-i; dur = ""
            if real_idx+1 < len(entries):
                try:
                    t1 = datetime.strptime(time_s, "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.strptime(entries[real_idx+1]["time"], "%Y-%m-%d %H:%M:%S")
                    s  = abs(int((t2-t1).total_seconds()))
                    dur = f"{s//3600}h {(s%3600)//60}m" if s>=3600 else f"{s//60}m {s%60}s" if s>=60 else f"{s}s"
                except: pass
            row = QFrame()
            row.setStyleSheet(
                f"QFrame{{background:{T('bg2')};border-radius:6px;"
                f"border-left:3px solid {'#4ade80' if is_on else '#ef4444'};}}")
            row.setFixedHeight(48)
            rl = QHBoxLayout(row); rl.setContentsMargins(10,0,10,0); rl.setSpacing(8)
            em = QLabel("✅" if is_on else "🚫"); em.setFixedWidth(22); em.setStyleSheet("font-size:14px;")
            rl.addWidget(em)
            tc = QVBoxLayout(); tc.setSpacing(1)
            al = QLabel(f"Internet turned {'ON' if is_on else 'OFF'}")
            al.setStyleSheet(f"color:{T('text')};font-size:12px;font-weight:600;")
            tl = QLabel(time_s + (f"  ·  lasted {dur}" if dur else ""))
            tl.setStyleSheet(f"color:{T('text3')};font-size:10px;")
            tc.addWidget(al); tc.addWidget(tl)
            rl.addLayout(tc); rl.addStretch()
            self.vbox.addWidget(row)

    def _clear(self):
        try:
            if os.path.exists(LOG_FILE): os.remove(LOG_FILE)
        except: pass
        self.refresh()


# ═══════════════════════════════════════════════════════════════════════════════
#  SPEED TEST PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class SpeedGauge(QWidget):
    """Circular arc gauge for a single speed value."""
    def __init__(self, label, color, parent=None):
        super().__init__(parent)
        self.label  = label
        self.color  = QColor(color)
        self._value = 0.0
        self._max   = 100.0
        self.setFixedSize(140, 140)

    def setValue(self, v, max_v=None):
        self._value = v
        if max_v: self._max = max_v
        self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy, r = w//2, h//2, 52

        # Background arc
        bg = QColor(T("bg3")); bg.setAlpha(100)
        pen = QPen(bg, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(cx-r, cy-r, r*2, r*2, 225*16, -270*16)

        # Value arc
        if self._value > 0:
            fraction = min(self._value / self._max, 1.0)
            span = int(-270 * 16 * fraction)
            pen2 = QPen(self.color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen2)
            p.drawArc(cx-r, cy-r, r*2, r*2, 225*16, span)

        # Value text
        p.setPen(QPen(QColor(T("text"))))
        p.setFont(self._font(18, bold=True))
        p.drawText(0, cy-14, w, 24, Qt.AlignmentFlag.AlignCenter, f"{self._value:.1f}")

        # Unit
        p.setPen(QPen(QColor(T("text2"))))
        p.setFont(self._font(10))
        p.drawText(0, cy+10, w, 16, Qt.AlignmentFlag.AlignCenter, "Mbps")

        # Label
        p.setPen(QPen(self.color))
        p.setFont(self._font(11, bold=True))
        p.drawText(0, cy+28, w, 16, Qt.AlignmentFlag.AlignCenter, self.label)
        p.end()

    def _font(self, size, bold=False):
        f = QFont("Segoe UI", size)
        f.setBold(bold)
        return f


class SpeedTestPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._servers  = []   # full list from speedtest
        self._filtered = []   # currently shown in dropdown
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # Title
        title = QLabel("Speed Test")
        title.setStyleSheet(f"font-size:16px;font-weight:700;color:{T('text')};")
        layout.addWidget(title)

        # Server picker row
        srv_row = QHBoxLayout(); srv_row.setSpacing(8)
        srv_label = QLabel("Server:")
        srv_label.setStyleSheet(f"color:{T('text2')};font-size:12px;font-weight:600;")
        srv_label.setFixedWidth(52)
        self.srv_combo = QComboBox()
        self.srv_combo.addItem("Loading servers…")
        self.srv_combo.setEnabled(False)
        self.srv_combo.setStyleSheet(f"""
            QComboBox {{
                background:{T('bg2')}; color:{T('text')}; border:1px solid {T('border')};
                border-radius:6px; padding:5px 10px; font-size:11px;
            }}
            QComboBox::drop-down {{ border:none; width:20px; }}
            QComboBox QAbstractItemView {{
                background:{T('bg2')}; color:{T('text')};
                selection-background-color:{T('accent')};
                border:1px solid {T('border')};
            }}
        """)
        self.reload_btn = QPushButton("↻")
        self.reload_btn.setFixedSize(30, 30)
        self.reload_btn.setToolTip("Reload server list")
        self.reload_btn.setStyleSheet(
            f"QPushButton{{background:{T('bg2')};color:{T('text2')};border:1px solid {T('border')};"
            f"border-radius:6px;font-size:14px;}}QPushButton:hover{{color:{T('text')};border-color:{T('accent')};}}")
        self.reload_btn.clicked.connect(self._load_servers)
        srv_row.addWidget(srv_label)
        srv_row.addWidget(self.srv_combo, 1)
        srv_row.addWidget(self.reload_btn)
        layout.addLayout(srv_row)

        # Search filter
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍  Filter by country or city…  e.g. Greece, Athens")
        self.search_box.setStyleSheet(
            f"QLineEdit{{background:{T('bg2')};border:1px solid {T('border')};border-radius:6px;"
            f"padding:6px 10px;color:{T('text')};font-size:11px;}}"
            f"QLineEdit:focus{{border-color:{T('accent')};}}")
        self.search_box.textChanged.connect(self._filter_servers)
        layout.addWidget(self.search_box)

        # Gauges row
        gauges_row = QHBoxLayout()
        gauges_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gauges_row.setSpacing(20)
        self.dl_gauge = SpeedGauge("Download", T("green"))
        self.ul_gauge = SpeedGauge("Upload",   T("accent"))
        gauges_row.addWidget(self.dl_gauge)
        gauges_row.addWidget(self.ul_gauge)
        layout.addLayout(gauges_row)

        # Ping + server info card
        info_card = QFrame()
        info_card.setStyleSheet(
            f"QFrame{{background:{T('bg2')};border-radius:12px;border:1px solid {T('border')};}}")
        info_card.setFixedHeight(72)
        il = QHBoxLayout(info_card); il.setContentsMargins(20,0,20,0); il.setSpacing(0)

        ping_col = QVBoxLayout(); ping_col.setSpacing(2)
        ping_lbl = QLabel("PING")
        ping_lbl.setStyleSheet(f"color:{T('text2')};font-size:10px;font-weight:600;letter-spacing:1px;")
        self.ping_val = QLabel("— ms")
        self.ping_val.setStyleSheet(f"color:{T('text')};font-size:20px;font-weight:700;")
        ping_col.addWidget(ping_lbl); ping_col.addWidget(self.ping_val)
        il.addLayout(ping_col)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{T('border')};"); sep.setFixedWidth(1)
        il.addSpacing(24); il.addWidget(sep); il.addSpacing(24)

        srv_col = QVBoxLayout(); srv_col.setSpacing(2)
        srv_lbl2 = QLabel("USED SERVER")
        srv_lbl2.setStyleSheet(f"color:{T('text2')};font-size:10px;font-weight:600;letter-spacing:1px;")
        self.srv_val = QLabel("—")
        self.srv_val.setStyleSheet(f"color:{T('text')};font-size:12px;font-weight:600;")
        srv_col.addWidget(srv_lbl2); srv_col.addWidget(self.srv_val)
        il.addLayout(srv_col); il.addStretch()
        layout.addWidget(info_card)

        # Status label
        self.status_lbl = QLabel("Select a server and press Run")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(f"color:{T('text2')};font-size:12px;")
        layout.addWidget(self.status_lbl)

        # Run button
        self.run_btn = QPushButton("▶  Run Speed Test")
        self.run_btn.setFixedHeight(44)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background:{T('accent')}; color:white; border:none;
                border-radius:10px; font-size:14px; font-weight:700;
            }}
            QPushButton:disabled {{ background:{T('bg3')}; color:{T('text3')}; }}
        """)
        self.run_btn.clicked.connect(self._run)
        layout.addWidget(self.run_btn)

        self.last_lbl = QLabel("")
        self.last_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.last_lbl.setStyleSheet(f"color:{T('text3')};font-size:10px;")
        layout.addWidget(self.last_lbl)
        layout.addStretch()

        # Auto-load servers on creation
        self._load_servers()

    def _load_servers(self):
        self.srv_combo.clear()
        self.srv_combo.addItem("Loading servers…")
        self.srv_combo.setEnabled(False)
        self.reload_btn.setEnabled(False)
        self.status_lbl.setText("Fetching server list…")
        self.status_lbl.setStyleSheet(f"color:{T('amber')};font-size:12px;")
        w = ServerListWorker()
        w.done.connect(self._on_servers_loaded)
        w.start()
        self._srv_worker = w   # keep reference

    def _on_servers_loaded(self, servers):
        self.reload_btn.setEnabled(True)
        if not servers:
            self.srv_combo.clear()
            self.srv_combo.addItem("Failed to load servers")
            self.status_lbl.setText("⚠ Could not fetch server list. Check your connection.")
            self.status_lbl.setStyleSheet(f"color:{T('red')};font-size:12px;")
            return
        self._servers = servers
        self._filter_servers(self.search_box.text())
        self.status_lbl.setText(f"{len(servers)} servers worldwide loaded. Type a country to filter.")
        self.status_lbl.setStyleSheet(f"color:{T('text2')};font-size:12px;")

    def _filter_servers(self, text=""):
        """Re-populate combo with servers matching the search text."""
        q = text.strip().lower()
        self._filtered = [s for s in self._servers
                          if not q or q in s["country"].lower() or q in s["name"].lower()
                          or q in s["sponsor"].lower()]
        self.srv_combo.clear()
        if not self._filtered:
            self.srv_combo.addItem("No matches — try a different search")
            self.srv_combo.setEnabled(False)
            return
        for srv in self._filtered:
            label = f"{srv['country']}  •  {srv['name']}  —  {srv['sponsor']}  ({srv['d']} km)"
            self.srv_combo.addItem(label)
        self.srv_combo.setEnabled(True)

    def _run(self):
        # Get selected server ID (None = auto)
        server_id = None
        idx = self.srv_combo.currentIndex()
        filtered = getattr(self, "_filtered", self._servers)
        if filtered and 0 <= idx < len(filtered):
            server_id = filtered[idx]["id"]

        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self.status_lbl.setStyleSheet(f"color:{T('amber')};font-size:12px;")
        self.dl_gauge.setValue(0); self.ul_gauge.setValue(0)
        self.ping_val.setText("— ms"); self.srv_val.setText("—")

        self._worker = SpeedTestWorker(server_id)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, msg):
        self.status_lbl.setText(msg)

    def _on_done(self, result):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("▶  Run Speed Test")
        if "error" in result:
            self.status_lbl.setText(f"⚠ Error: {result['error']}")
            self.status_lbl.setStyleSheet(f"color:{T('red')};font-size:12px;")
            return
        dl = result["download"]; ul = result["upload"]
        ping = result["ping"];   srv = result["server"]
        top  = max(dl, ul, 10)
        max_v = 25 if top<=25 else 50 if top<=50 else 100 if top<=100 else 200 if top<=200 else 500
        self.dl_gauge.setValue(dl, max_v)
        self.ul_gauge.setValue(ul, max_v)
        self.ping_val.setText(f"{ping} ms")
        self.srv_val.setText(srv[:34] + ("…" if len(srv)>34 else ""))
        self.status_lbl.setText(f"✅ Done! ↓ {dl} Mbps  ↑ {ul} Mbps  ping {ping} ms")
        self.status_lbl.setStyleSheet(f"color:{T('green')};font-size:12px;")
        self.last_lbl.setText(f"Last test: {datetime.now().strftime('%H:%M:%S')}")
        toast("Speed Test Complete", f"↓ {dl} Mbps  ↑ {ul} Mbps  Ping {ping} ms")

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QWidget):
    def __init__(self, password):
        super().__init__()
        self.password = password
        self._workers = []
        self._internet_is_off = False
        self._last_off_time = None

        self.setWindowTitle("Internet Control")
        self.setFixedSize(440, 700)
        self._apply_theme()
        self._build_ui()
        self._build_tray()
        self._check_status()
        self._refresh_devices()

        self._offline_timer = QTimer(self)
        self._offline_timer.setInterval(5*60*1000)
        self._offline_timer.timeout.connect(self._offline_reminder)

    # ── Theme ──────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        self.setStyleSheet(f"""
            QWidget     {{ background:{T('bg')}; color:{T('text')}; font-family:'Segoe UI',Arial,sans-serif; }}
            QTabWidget::pane {{ border:1px solid {T('border')}; background:{T('bg')}; }}
            QTabBar::tab {{ background:{T('bg2')}; color:{T('text2')}; padding:8px 16px;
                            font-size:12px; }}
            QTabBar::tab:selected {{ background:{T('bg')}; color:{T('text')}; font-weight:700;
                                     border-bottom:2px solid {T('accent')}; }}
            QScrollArea {{ border:none; background:transparent; }}
            QScrollBar:vertical {{ background:{T('bg')}; width:6px; }}
            QScrollBar::handle:vertical {{ background:{T('bg3')}; border-radius:3px; }}
        """)

    def _change_theme(self, name):
        global _current_theme
        _current_theme = name
        self._apply_theme()
        self._refresh_devices()
        if hasattr(self, "log_panel"): self.log_panel.refresh()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Top bar
        top_bar = QHBoxLayout(); top_bar.setContentsMargins(16,10,16,0)
        app_lbl = QLabel("🌐 Internet Control")
        app_lbl.setStyleSheet(f"font-size:14px;font-weight:700;color:{T('text')};")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(_current_theme)
        self.theme_combo.setFixedSize(100, 28)
        self.theme_combo.setStyleSheet(
            f"QComboBox{{background:{T('bg2')};color:{T('text')};border:1px solid {T('border')};"
            f"border-radius:5px;padding:2px 8px;font-size:11px;}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{T('bg2')};color:{T('text')};"
            f"selection-background-color:{T('accent')};}}")
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        top_bar.addWidget(app_lbl); top_bar.addStretch(); top_bar.addWidget(self.theme_combo)
        root.addLayout(top_bar)

        # Tabs
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs)

        control_tab  = QWidget(); self.tabs.addTab(control_tab,  "Control")
        devices_tab  = QWidget(); self.tabs.addTab(devices_tab,  "Devices")
        history_tab  = QWidget(); self.tabs.addTab(history_tab,  "History")
        speed_tab    = QWidget(); self.tabs.addTab(speed_tab,    "Speed Test")

        self._build_control(control_tab)
        self._build_devices(devices_tab)
        self._build_history(history_tab)
        self._build_speed(speed_tab)

    def _build_control(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(24,20,24,20); layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.sub_lbl = QLabel(f"Router: {ROUTER_IP}  ·  Checking…")
        self.sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_lbl.setStyleSheet(f"font-size:11px;color:{T('text3')};margin-bottom:20px;")
        layout.addWidget(self.sub_lbl)

        self.circle = QLabel("…")
        self.circle.setFixedSize(120,120)
        self.circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_circle("LOADING")
        layout.addWidget(self.circle, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_lbl = QLabel("Checking…")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(f"font-size:20px;font-weight:700;color:{T('amber')};margin-top:16px;")
        layout.addWidget(self.status_lbl)

        self.msg_lbl = QLabel("Reading router status…")
        self.msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet(f"font-size:11px;color:{T('text2')};margin-top:4px;margin-bottom:28px;")
        layout.addWidget(self.msg_lbl)

        tog_row = QHBoxLayout(); tog_row.setAlignment(Qt.AlignmentFlag.AlignCenter); tog_row.setSpacing(14)
        off_lbl = QLabel("OFF"); off_lbl.setStyleSheet(f"color:{T('text3')};font-size:12px;font-weight:600;")
        self.toggle = ToggleSwitch(); self.toggle.setEnabled(False)
        self.toggle.toggled.connect(self._on_toggle)
        on_lbl = QLabel("ON"); on_lbl.setStyleSheet(f"color:{T('text3')};font-size:12px;font-weight:600;")
        tog_row.addWidget(off_lbl); tog_row.addWidget(self.toggle); tog_row.addWidget(on_lbl)
        layout.addLayout(tog_row)

        footer = QLabel(f"Connection: {WAN_FLAGS[0]}  ·  {USERNAME}@{ROUTER_IP}")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"font-size:10px;color:{T('bg3')};margin-top:30px;")
        layout.addWidget(footer)

    def _build_devices(self, parent):
        layout = QVBoxLayout(parent); layout.setContentsMargins(16,12,16,12); layout.setSpacing(8)
        hdr = QHBoxLayout()
        dev_title = QLabel("Connected Devices")
        dev_title.setStyleSheet(f"font-size:13px;font-weight:700;color:{T('text2')};letter-spacing:1px;")
        self.refresh_btn = QPushButton("↻ Refresh"); self.refresh_btn.setFixedSize(80,26)
        self.refresh_btn.setStyleSheet(
            f"QPushButton{{background:{T('bg2')};color:{T('text3')};border:1px solid {T('border')};"
            f"border-radius:5px;font-size:11px;}}QPushButton:hover{{color:{T('text2')};}}")
        self.refresh_btn.clicked.connect(self._refresh_devices)
        hdr.addWidget(dev_title); hdr.addStretch(); hdr.addWidget(self.refresh_btn)
        layout.addLayout(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.dev_container = QWidget(); self.dev_container.setStyleSheet("background:transparent;")
        self.dev_layout = QVBoxLayout(self.dev_container)
        self.dev_layout.setContentsMargins(0,0,0,0); self.dev_layout.setSpacing(4)
        self.dev_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.dev_container); layout.addWidget(scroll)

    def _build_history(self, parent):
        layout = QVBoxLayout(parent); layout.setContentsMargins(0,0,0,0)
        self.log_panel = LogPanel(); layout.addWidget(self.log_panel)

    def _build_speed(self, parent):
        layout = QVBoxLayout(parent); layout.setContentsMargins(0,0,0,0)
        self.speed_panel = SpeedTestPanel(); layout.addWidget(self.speed_panel)

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_tray_icon("LOADING"), self)
        self.tray.setToolTip("Internet Control")
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu{{background:{T('bg2')};color:{T('text')};border:1px solid {T('border')};font-size:12px;}}"
            f"QMenu::item:selected{{background:{T('accent')};}}"
            f"QMenu::separator{{background:{T('border')};height:1px;margin:4px 0;}}")
        self.tray_status = menu.addAction("Status: checking…"); self.tray_status.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Turn ON").triggered.connect(lambda: self._force_state("on"))
        menu.addAction("Turn OFF").triggered.connect(lambda: self._force_state("off"))
        menu.addSeparator()
        menu.addAction("Open").triggered.connect(self._restore)
        menu.addAction("Quit").triggered.connect(QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self._restore()
                                    if r==QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    # ── Circle ────────────────────────────────────────────────────────────────
    def _update_circle(self, state):
        cfg = {"ON":(T("green_bg"),T("green"),T("green"),"✓"),
               "OFF":(T("red_bg"),T("red"),T("red"),"✕"),
               "LOADING":(T("amber_bg"),T("amber"),T("amber"),"…")}.get(state,(T("amber_bg"),T("amber"),T("amber"),"…"))
        bg,border,fg,icon = cfg
        self.circle.setStyleSheet(
            f"QLabel{{background:{bg};border:4px solid {border};border-radius:60px;"
            f"font-size:46px;color:{fg};font-weight:900;}}")
        self.circle.setText(icon)

    def _apply_state(self, is_on, msg=""):
        state = "ON" if is_on else "OFF"
        self._update_circle(state); self.toggle.setChecked(is_on)
        color = T("green") if is_on else T("red")
        self.status_lbl.setText(f"Internet is {state}")
        self.status_lbl.setStyleSheet(f"font-size:20px;font-weight:700;color:{color};margin-top:16px;")
        self.msg_lbl.setText(msg or ("All devices have internet access" if is_on else "Internet blocked for all devices"))
        self.sub_lbl.setText(f"Router: {ROUTER_IP}  ·  {WAN_FLAGS[0]} {'active' if is_on else 'down'}")
        self.tray.setIcon(make_tray_icon(state))
        self.tray.setToolTip(f"Internet is {state}")
        self.tray_status.setText(f"Status: {state}")
        self._internet_is_off = not is_on
        if not is_on:
            self._last_off_time = datetime.now(); self._offline_timer.start()
        else:
            self._offline_timer.stop()

    # ── Workers ───────────────────────────────────────────────────────────────
    def _check_status(self):
        w = StatusWorker(self.password); w.done.connect(self._on_status_known)
        w.start(); self._workers.append(w)

    def _on_status_known(self, state):
        self.toggle.setEnabled(True)
        self._apply_state(state != "OFF")

    def _on_toggle(self, checked):
        self.toggle.setEnabled(False)
        self._update_circle("LOADING")
        self.status_lbl.setText("Connecting…")
        self.status_lbl.setStyleSheet(f"font-size:20px;font-weight:700;color:{T('amber')};margin-top:16px;")
        self.msg_lbl.setText("Sending command to router…")
        w = WanWorker("on" if checked else "off", self.password)
        w.done.connect(self._on_wan_done); w.start(); self._workers.append(w)

    def _force_state(self, state):
        want_on = state=="on"
        if self.toggle.isChecked()==want_on: return
        self.toggle.setChecked(want_on); self._on_toggle(want_on)

    def _on_wan_done(self, ok, msg):
        self.toggle.setEnabled(True)
        if ok:
            is_on = self.toggle.isChecked(); self._apply_state(is_on)
            log_event("ON" if is_on else "OFF")
            if hasattr(self,"log_panel"): self.log_panel.refresh()
            toast("Internet ON ✅" if is_on else "Internet OFF 🚫",
                  "All devices connected." if is_on else "Internet blocked for all devices.")
        else:
            self.toggle.setChecked(not self.toggle.isChecked())
            self._update_circle("ON" if self.toggle.isChecked() else "OFF")
            self.status_lbl.setText("⚠ Error")
            self.status_lbl.setStyleSheet(f"font-size:18px;font-weight:700;color:{T('amber')};margin-top:16px;")
            self.msg_lbl.setText(msg)

    def _refresh_devices(self):
        self.refresh_btn.setEnabled(False); self.refresh_btn.setText("…")
        w = DeviceWorker(self.password); w.done.connect(self._on_devices)
        w.start(); self._workers.append(w)

    def _on_devices(self, devices):
        self.refresh_btn.setEnabled(True); self.refresh_btn.setText("↻ Refresh")
        while self.dev_layout.count():
            item = self.dev_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if not devices:
            lbl = QLabel("No devices found.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color:{T('text3')};font-size:12px;padding:20px;")
            self.dev_layout.addWidget(lbl); return
        for dev in devices:
            self.dev_layout.addWidget(DeviceRow(dev))

    def _offline_reminder(self):
        if self._internet_is_off:
            mins = ""
            if self._last_off_time:
                elapsed = int((datetime.now()-self._last_off_time).total_seconds()/60)
                mins = f" ({elapsed} min ago)"
            toast("⚠ Internet still OFF", f"Internet has been off{mins}.")

    def _restore(self):
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, e):
        e.ignore(); self.hide()
        self.tray.showMessage("Internet Control","Running in tray. Double-click to reopen.",
                              QSystemTrayIcon.MessageIcon.Information, 2000)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    dlg = PasswordDialog()
    if dlg.exec() != QDialog.DialogCode.Accepted: sys.exit(0)
    password = dlg.password()
    try:
        r = requests.get(BASE_URL, auth=HTTPBasicAuth(USERNAME, password), timeout=5)
        if r.status_code == 401:
            dlg2 = PasswordDialog(error=True)
            if dlg2.exec() != QDialog.DialogCode.Accepted: sys.exit(0)
            password = dlg2.password()
    except Exception: pass

    win = MainWindow(password)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
