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
