#!/usr/bin/env bash
# Start a virtual framebuffer (xvfb), then run the MT5 execution service under it.
# README §13: MT5 is a GUI app, so "headless" = a virtual display, not a true
# no-GUI mode. xvfb gives a display with no real monitor and minimal memory.
set -euo pipefail

DISPLAY_NUM="${DISPLAY#:}"
XVFB_RES="${XVFB_RES:-1024x768x16}"

# Clear any stale X lock left by a previous (crashed) run so Xvfb can start.
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true

echo "[entrypoint] starting Xvfb on ${DISPLAY} (${XVFB_RES})"
Xvfb "${DISPLAY}" -screen 0 "${XVFB_RES}" -nolisten tcp &
XVFB_PID=$!

# Give Xvfb a moment to come up.
sleep 3

cleanup() {
    echo "[entrypoint] shutting down"
    kill "${XVFB_PID}" 2>/dev/null || true
    rm -f "/tmp/.X${DISPLAY_NUM}-lock" 2>/dev/null || true
}
trap cleanup EXIT

# Run the execution service via Wine's Windows Python. Use the module form so the
# `src` / `config` packages resolve via PYTHONPATH (set in the Dockerfile).
echo "[entrypoint] launching MT5 execution service under Wine"
cd /app
exec wine python -m src.execution.mt5_service "$@"
