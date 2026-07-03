# OxygenControl 🌐

A desktop app to control your **Gennet OxyGEN / Oxygen Broadband router** from your PC — toggle internet on/off, view connected devices, run speed tests, and track connection history. Built with Python and PyQt6.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

> ⚠️ **Disclaimer**
>
> This software is provided **as-is**, for personal use only. The author is **not responsible** for any damage, data loss, network disruption, loss of connectivity, or any other issues that may arise from using this application. **Use at your own risk.**
>
> This tool communicates directly with your router's admin interface. Incorrect usage may disrupt your network. Make sure you understand what the app does before using it. The author makes no guarantees that it will work on your specific router model or firmware version.

---

## Features

- **Toggle internet ON/OFF** for all devices on your network instantly
- **Connected devices list** — see every device currently on your router
- **Speed test** — measure download/upload speed and ping with server picker
- **Connection history** — log of every time internet was cut or restored, with duration
- **System tray** — green/red icon, quick ON/OFF without opening the full window
- **Windows toast notifications** — get notified when internet changes state
- **Offline reminder** — warns you every 5 minutes if you forgot the internet is off
- **3 themes** — Dark, Light, Midnight
- **Password prompt on every launch** — never saved to disk for security

---

## Compatibility

This app was built and tested on the **Gennet OxyGEN** router (used by Greek ISPs such as Cosmote/Oxygen Broadband). It communicates via the router's CGI web interface (`/cgi-bin/page.pl`).

It may work on other routers that use the same interface. If your router uses a different admin panel, the WAN toggle commands will need to be adapted.

---

## Requirements

- Python 3.8+
- A Gennet OxyGEN router (or compatible)
- Your router's admin username and password

Install dependencies:

```bash
pip install PyQt6 requests winotify speedtest-cli
```

> **Note:** `winotify` is Windows-only (toast notifications). On macOS/Linux it will be silently skipped — everything else works fine.

---

## Setup

### 1. Find your router IP

**Windows:**
```
ipconfig
```
Look for **Default Gateway** — usually `192.168.1.1` or `192.168.1.254`.

**macOS / Linux:**
```
ip route | grep default
```

### 2. Find your WAN connection name

1. Open your browser and go to `http://192.168.1.1`
2. Log in with your router credentials
3. Go to **Internet / WAN → Connections**
4. Find the connection with a **green status** (Connected)
5. Note its name — e.g. `VDSL_PPPoE`, `ADSL_PPPoE`, `Eth_PPPoE`

### 3. Edit `main.py`

Open `main.py` and update the settings at the top:

```python
# ─── SETTINGS ─────────────────────────────────────────────────────────────────
ROUTER_IP      = "192.168.1.1"    # Your router's IP address
USERNAME       = "user"           # Router login username (check router label)
WAN_FLAGS      = ["VDSL_PPPoE"]   # Your active WAN connection name(s)
WAN_STATUS_KEY = "VDSL_PPPoE_stat" # Same as above + "_stat"
```

If you have multiple active connections (e.g. internet + IPTV), list them all:

```python
WAN_FLAGS = ["VDSL_PPPoE", "VDSL_IPTV"]
```

### 4. Run

```bash
python main.py
```

---

## Usage

| Action | How |
|--------|-----|
| Turn internet OFF | Flip the toggle on the Control tab, or right-click tray icon |
| Turn internet ON | Flip the toggle again, or right-click tray icon |
| See connected devices | Click the **Devices** tab, then **↻ Refresh** |
| Run a speed test | Click the **Speed Test** tab, filter/pick a server, click **Run** |
| View history | Click the **History** tab |
| Minimize to tray | Close the window — it stays running in the system tray |
| Quit | Right-click the tray icon → **Quit** |

---

## How it works

The app communicates with your router's built-in web interface over your local network. It does **not** require port forwarding, cloud accounts, or any external services.

- **Turning OFF** calls: `type=wan&page=hangup&flag=<WAN_FLAG>` (the router's "Hang Up" button)
- **Turning ON** calls: `type=wan&page=redial&flag=<WAN_FLAG>` (the router's "Redial" button)
- **Device list** reads: `type=lan&page=clients`
- **Status check** reads: `type=wan&page=list` and looks for the connection's status icon

---

## Discovery Tools

If you're not sure what your router's WAN flag names are, two helper scripts are included:

```bash
python tools/discover_router.py   # Finds CGI commands and WAN page structure
python tools/discover_lan.py      # Finds LAN/device list endpoints
```

Edit the credentials at the top of each script before running.

---

## Security

- Your router password is **never saved to disk**. It is only held in memory while the app is running and cleared when you close it.
- The app only communicates with your **local router IP** — no data is sent externally.
- Connection history is saved locally to `internet_log.json` in the app folder.

---

## Troubleshooting

**"Internet is OFF" but devices still have internet**
Your WAN flag name is probably wrong. Check the router admin panel and update `WAN_FLAGS` and `WAN_STATUS_KEY` in `main.py`.

**Login fails / 401 error**
Double-check your username and password. Try logging into `http://192.168.1.1` in your browser with the same credentials.

**App can't reach router**
Make sure you're connected to the router's Wi-Fi or ethernet. The app only works on the local network.

**Speed test only shows servers from one country**
This is a known limitation of `speedtest-cli` — it pre-filters servers based on your detected IP location. Use the search box to filter by country name.

---

## Project Structure

```
OxygenControl/
├── main.py              # Main application
├── tools/
│   ├── discover_router.py   # Probes router for CGI commands
│   └── discover_lan.py      # Probes router for LAN device endpoints
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Contributing

Pull requests are welcome! Some ideas for contributors:

- Timer / countdown mode (cut internet for X minutes then restore)
- Scheduling (cut internet daily at a set time)
- PIN lock to prevent others from turning internet back on
- Support for other router models / CGI interfaces
- macOS/Linux notification support

---

## License

MIT License — see [LICENSE](LICENSE) for details.