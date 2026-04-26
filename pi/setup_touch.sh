#!/bin/bash
# One-time touch setup for Adafruit PiTFT 2.8" (FT6236 / stmpe / ads7846).
# Installs tslib, creates a stable device symlink, and runs ts_calibrate.
# The calibration handles axis swap and scaling — no app-level math needed.
#
# Run as root on the Pi:  sudo bash pi/setup_touch.sh
set -e

echo "=== PiTFT touch setup ==="

apt-get install -y tslib

# Find the touch input device by scanning sysfs names
TOUCH_DEV=$(python3 - <<'PYEOF'
import os, sys
keywords = ("touch", "ads", "stmpe", "ft5", "ft6", "goodix", "edt-ft", "ili")
for d in sorted(os.listdir("/sys/class/input")):
    nf = f"/sys/class/input/{d}/device/name"
    if os.path.exists(nf):
        n = open(nf).read().strip().lower()
        if any(k in n for k in keywords):
            for sub in sorted(os.listdir(f"/sys/class/input/{d}")):
                if sub.startswith("event"):
                    print(f"/dev/input/{sub}")
                    sys.exit(0)
PYEOF
)

if [ -z "$TOUCH_DEV" ]; then
    echo "ERROR: touch device not found"
    echo "Check: cat /proc/bus/input/devices"
    exit 1
fi
echo "Found: $TOUCH_DEV"

# Stable symlink so the eventX number never changes between boots
cat > /etc/udev/rules.d/51-pitft-touch.rules << 'EOF'
SUBSYSTEM=="input", ATTRS{name}=="ft6x06_ts", SYMLINK+="input/touchscreen", MODE="0660", GROUP="input"
SUBSYSTEM=="input", ATTRS{name}=="stmpe-ts",  SYMLINK+="input/touchscreen", MODE="0660", GROUP="input"
SUBSYSTEM=="input", ATTRS{name}=="ads7846",   SYMLINK+="input/touchscreen", MODE="0660", GROUP="input"
EOF
udevadm control --reload-rules && udevadm trigger

# tslib filter chain: raw input → dejitter → linear calibration
cat > /etc/ts.conf << 'EOF'
module_raw input
module dejitter delta=30
module linear
EOF

# Persist env vars for tslib (picked up by the display service)
set_env() {
    local KEY="${1%%=*}"
    grep -v "^${KEY}=" /etc/environment > /tmp/_env 2>/dev/null || true
    mv /tmp/_env /etc/environment
    echo "$1" >> /etc/environment
}
set_env "TSLIB_TSDEVICE=/dev/input/touchscreen"
set_env "TSLIB_CALIBFILE=/etc/pointercal"
set_env "TSLIB_CONFFILE=/etc/ts.conf"
set_env "TSLIB_FBDEVICE=/dev/fb0"

echo ""
echo "=== Running ts_calibrate ==="
echo "Tap each crosshair precisely when it appears."
echo "ts_calibrate solves the full affine transform including axis swap."
echo ""

unset DISPLAY
export TSLIB_TSDEVICE="$TOUCH_DEV"
export TSLIB_CALIBFILE=/etc/pointercal
export TSLIB_CONFFILE=/etc/ts.conf
export TSLIB_FBDEVICE=/dev/fb0

ts_calibrate

echo ""
echo "Done. Calibration written to /etc/pointercal"
echo "Restart:  sudo systemctl restart train-display"
