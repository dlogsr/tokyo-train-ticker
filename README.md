# Tokyo Train Ticker

Real-time Tokyo train departure board for Raspberry Pi + Adafruit PiTFT 2.8" (320×240). Works in demo mode with no API key, or live with a free ODPT key.

![320×240 display](https://img.shields.io/badge/display-320×240-informational) ![Python 3](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Station mode** — next trains at a station, platform filter, 60-min lookahead
- **Line mode** — all current trains on a line with journey and delay info
- **Demo mode** — realistic simulated data with peak-hour headways, no API key needed
- **Pi display** — direct `/dev/fb0` framebuffer rendering via Pillow, no X11/SDL required
- **Touch input** — capacitive touchscreen support for navigation on Pi

## Architecture

```
browser / Pi display
        │  HTTP + WebSocket
        ▼
FastAPI backend (port 8000)
        │
        ▼
ODPT API  ──or──  demo data generator
```

- **`backend/`** — FastAPI server, ODPT client, demo data, WebSocket push
- **`frontend/`** — single-page 320×240 UI (HTML/CSS/JS)
- **`pi/`** — framebuffer renderer + systemd service files

## Quick Start

### Prerequisites

- Python 3.9+
- (Optional) Free ODPT API key from [developer.odpt.org](https://developer.odpt.org/)

### Run locally

```bash
make install       # create venv + install deps
cp .env.example .env
# edit .env — leave ODPT_API_KEY blank to use demo mode
make dev           # starts server + opens http://localhost:8000
```

### Docker

```bash
docker-compose up
```

### Deploy to Railway

This repo builds and runs as-is on [Railway](https://railway.app):

1. Push this repo to GitHub (already done if you're reading this from there).
2. On Railway: **New Project → Deploy from GitHub repo** and pick this repo.
3. Railway detects the root `Dockerfile` and builds it automatically — no config needed.
4. (Optional) Set the `ODPT_API_KEY` environment variable in the Railway service settings for live data; leave it unset to run in demo mode.
5. Railway assigns a public URL and injects `PORT`, which the container already listens on.

`railway.json` pins the build to the Dockerfile and adds a `/api/status` healthcheck.

## Configuration

Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|---|---|---|
| `ODPT_API_KEY` | _(empty)_ | ODPT API key — leave blank for demo mode |
| `DEFAULT_STATION` | `shibuya` | Station shown on boot |
| `DEFAULT_MODE` | `station` | Boot mode: `station` or `line` |

## Raspberry Pi Setup

Tested on Pi Zero 2 W with Adafruit PiTFT 2.8" (320×240, SPI, `/dev/fb0`).

### Dependencies

```bash
sudo apt install -y python3-pil python3-numpy
sudo pip3 install --break-system-packages httpx
```

### Install as system services

```bash
sudo cp pi/services/train-backend.service /etc/systemd/system/
sudo cp pi/services/train-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable train-backend train-display
sudo systemctl start train-backend train-display
```

The display service waits for the backend to start and renders at 8 FPS directly to the framebuffer. No desktop environment needed.

### Check status

```bash
sudo systemctl status train-backend train-display
```

## Makefile

| Target | Description |
|---|---|
| `make dev` | Start dev server with hot reload |
| `make install` | Create venv and install dependencies |
| `make stop` | Kill the running server |

## Android App

`android/` is a native Android wrapper around this same backend, plus a resizable
home-screen widget:

- **App** — a thin WebView shell that loads the existing `frontend/` UI from whatever
  backend URL you point it at (a Railway deployment, or your Pi's LAN address).
- **Widget** — a native home-screen widget, resizable between **2×2 and 4×2**, showing
  next departures for one station. It's configured independently of the app (pick a
  backend URL + station when you place it) and refreshes every 5 minutes, or on tap.

### CI builds

Every push to `android/**` runs [`.github/workflows/android.yml`](.github/workflows/android.yml),
which builds a debug APK and uploads it as a workflow artifact (**Actions tab → latest
run → Artifacts**). Pushing a tag like `android-v1` also attaches the APK to a GitHub
Release. The debug build is signed with Gradle's auto-generated debug key — fine for
sideloading onto your own device, not for the Play Store.

### Build locally

```bash
cd android
./gradlew assembleDebug
# APK lands at app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Requires JDK 17+ and the Android SDK (`ANDROID_HOME`/`local.properties` → `sdk.dir`).

### Using it

1. Open the app once and enter your backend URL (e.g. your Railway URL, or
   `http://192.168.1.20:8000` for a Pi on your LAN).
2. Long-press the home screen → **Widgets** → **Tokyo Train Ticker** → drag it out,
   which opens the station picker (same backend URL + a station from `/api/stations`).
3. Drag the widget's side handles to resize between 2×2 and 4×2 — the layout switches
   automatically (3 departure rows at 2×2, 4 rows with platform/delay at 4×2).
