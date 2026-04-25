#!/usr/bin/env bash
# ============================================================
# Tokyo Train Ticker — Raspberry Pi Zero W setup script
# Target: Raspberry Pi OS Lite (Bookworm/Bullseye)
# Screen: Adafruit PiTFT 2.8" 320x240 (SPI, ILI9341)
# ============================================================
set -euo pipefail

echo "===== Tokyo Train Ticker Pi Setup ====="

# ── 1. System packages ─────────────────────────────────────
sudo apt-get update -q
sudo apt-get install -y --no-install-recommends \
  python3 python3-pip python3-venv \
  python3-pygame \
  git curl wget \
  libopenblas-dev libopenjp2-7 libtiff6 \
  fonts-noto-cjk \
  fbset

# ── 2. Python venv ─────────────────────────────────────────
INSTALL_DIR="/opt/tokyo-train-ticker"
sudo mkdir -p "$INSTALL_DIR"
sudo chown pi:pi "$INSTALL_DIR"

cp -r "$(dirname "$0")/../" "$INSTALL_DIR/"
cd "$INSTALL_DIR"

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install pygame httpx websockets

# ── 3. Adafruit PiTFT driver setup ─────────────────────────
# Install the fbcp-ili9341 framebuffer copy driver OR
# use the Adafruit kernel overlay (recommended).
# The Adafruit installer handles the kernel module + overlay:

echo ""
echo ">>> Installing Adafruit PiTFT display drivers..."
echo "    This requires internet access and will reboot at the end."
echo "    Press Ctrl+C to skip (driver already installed or manual setup)"
echo ""
read -t 10 -p "Install Adafruit PiTFT drivers? [Y/n] " INSTALL_DRIVER || true
INSTALL_DRIVER="${INSTALL_DRIVER:-Y}"

if [[ "$INSTALL_DRIVER" =~ ^[Yy]$ ]]; then
  cd /tmp
  wget -O adafruit-pitft-helper.py https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/adafruit-pitft.py
  sudo python3 adafruit-pitft-helper.py --display=28r --rotation=90 --install-type=fbcp
  # 28r = PiTFT 2.8" resistive, fbcp mirrors HDMI to TFT
  cd "$INSTALL_DIR"
fi

# ── 4. Configure /boot/config.txt for 320x240 HDMI ────────
# (fbcp mode: HDMI → /dev/fb0 → fbcp → /dev/fb1 TFT)
CONFIG=/boot/firmware/config.txt
if [ ! -f "$CONFIG" ]; then CONFIG=/boot/config.txt; fi

if ! grep -q "tokyo-train-ticker" "$CONFIG" 2>/dev/null; then
  sudo tee -a "$CONFIG" > /dev/null << 'EOF'

# Tokyo Train Ticker — 320x240 display
hdmi_group=2
hdmi_mode=87
hdmi_cvt=320 240 60 1 0 0 0
hdmi_drive=1
hdmi_force_hotplug=1
EOF
  echo "Added HDMI config to $CONFIG"
fi

# ── 5. Environment file ─────────────────────────────────────
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  echo "Created .env — edit $INSTALL_DIR/.env to add your ODPT_API_KEY"
fi

# ── 6. Systemd service ──────────────────────────────────────
sudo tee /etc/systemd/system/tokyo-train-backend.service > /dev/null << EOF
[Unit]
Description=Tokyo Train Ticker Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=${INSTALL_DIR}/backend
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/tokyo-train-display.service > /dev/null << EOF
[Unit]
Description=Tokyo Train Ticker Pygame Display
After=tokyo-train-backend.service
Requires=tokyo-train-backend.service

[Service]
Type=simple
User=pi
WorkingDirectory=${INSTALL_DIR}/pi
Environment=SDL_FBDEV=/dev/fb1
Environment=SDL_VIDEODRIVER=fbcon
Environment=SDL_NOMOUSE=1
Environment=API_BASE=http://localhost:8000
ExecStartPre=/bin/sleep 3
ExecStart=${INSTALL_DIR}/venv/bin/python3 pygame_display.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tokyo-train-backend
sudo systemctl enable tokyo-train-display

echo ""
echo "===== Setup complete! ====="
echo ""
echo "Next steps:"
echo "  1. Edit /opt/tokyo-train-ticker/.env — add ODPT_API_KEY (optional, free from developer.odpt.org)"
echo "  2. Run: sudo systemctl start tokyo-train-backend"
echo "  3. Run: sudo systemctl start tokyo-train-display"
echo "  4. Or: sudo reboot (services start automatically)"
echo ""
echo "Web UI (local network): http://$(hostname -I | awk '{print $1}'):8000"
