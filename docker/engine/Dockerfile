# Engine container — the analytical brain + Streamlit dashboard (README §10 step 10).
#
# Plain Linux Python, NO Wine, NO MetaTrader5. This is macOS-installable code, so
# the image is small. It talks to the mt5 container over RPC (never imports MT5).
FROM python:3.12-slim

WORKDIR /app

# Core deps only (requirements.txt has NO MetaTrader5).
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code.
COPY config/ /app/config/
COPY src/ /app/src/
COPY dashboard/ /app/dashboard/
COPY conftest.py /app/conftest.py

EXPOSE 8501

# Default: serve the Streamlit dashboard (backtest works with no mt5 container).
CMD ["python", "-m", "streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
