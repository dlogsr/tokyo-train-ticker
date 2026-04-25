#!/usr/bin/env bash
# Quick launch script for development/testing on Pi
# Runs backend + display in the same terminal (Ctrl+C to stop both)
set -euo pipefail

INSTALL_DIR="$(dirname "$0")/.."
cd "$INSTALL_DIR"

[ -f .env ] && export $(grep -v '^#' .env | xargs)

# Start backend
source venv/bin/activate
echo "Starting backend on :8000..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 2

# Start display
echo "Starting pygame display..."
if [ -e /dev/fb1 ]; then
  SDL_FBDEV=/dev/fb1 SDL_VIDEODRIVER=fbcon SDL_NOMOUSE=1 \
    python3 pi/pygame_display.py &
else
  echo "No /dev/fb1 — running in windowed mode"
  python3 pi/pygame_display.py &
fi
DISPLAY_PID=$!

trap "kill $BACKEND_PID $DISPLAY_PID 2>/dev/null; exit" INT TERM
wait
