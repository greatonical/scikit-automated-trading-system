# Headless MT5 under Wine (README §13).
#
# MetaTrader5 (the Python package + the terminal) is Windows-only, so we run it
# under Wine on Linux, headless via xvfb (a virtual display — MT5 is a GUI app and
# must initialise for its Python API to attach). This image is the ONLY place the
# `MetaTrader5` package is installed; the core engine's requirements.txt stays
# macOS-installable.
#
# Resource minimisation (README §13): single terminal instance, portable mode,
# stripped Wine prefix, no real display. Memory limits are enforced in
# docker-compose.yml.
#
# Base: a Wine image with Python available inside the Wine prefix. tobix/pywine
# ships a Windows Python under Wine, which is exactly what we need so the Windows
# `MetaTrader5` wheel can run.
# Force amd64: tobix/pywine is published for x86 only, and Wine runs Windows
# (x86) binaries anyway. On Apple Silicon (arm64) Docker emulates this via
# Rosetta/QEMU — slower, but the only way to run the Windows MT5 terminal.
FROM --platform=linux/amd64 tobix/pywine:3.12

# ---- OS-level deps: xvfb (virtual framebuffer) + minimal X utils ----
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        x11-utils \
        xauth \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Install the core engine deps INSIDE the Wine prefix first ----
# `wine pip` targets the Windows Python under Wine (not the Linux Python).
COPY requirements.txt /app/requirements.txt
RUN wine pip install --no-cache-dir -r /app/requirements.txt || true

# ---- Then the MT5 deps LAST so the numpy<2 pin wins ----
# (requirements.txt has no numpy pin and would otherwise pull numpy 2.x, which
# aborts under Wine — see requirements-mt5.txt). Installing this last makes the
# numpy==1.26.4 pin authoritative.
COPY requirements-mt5.txt /app/requirements-mt5.txt
RUN wine pip install --no-cache-dir -r /app/requirements-mt5.txt

# ---- Copy the application code ----
COPY config/ /app/config/
COPY src/ /app/src/
COPY docker/mt5/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# ---- Headless display + portable, low-footprint MT5 ----
ENV DISPLAY=:99
# Keep Wine quiet and lean.
ENV WINEDEBUG=-all
# Make the app packages importable (so `from src...` and `from config...` work).
ENV PYTHONPATH=Z:\\app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/entrypoint.sh"]
