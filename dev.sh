#!/usr/bin/env bash
# Start the Tokyo Train Ticker dev server
# Usage: ./dev.sh
set -euo pipefail

cd "$(dirname "$0")"

[ -f .env ] && export $(grep -v '^#' .env | xargs 2>/dev/null) || true

source venv/bin/activate
echo "Starting at http://localhost:8000"
open "http://localhost:8000" 2>/dev/null || true
cd backend && uvicorn main:app --host 127.0.0.1 --port 8000 --reload
