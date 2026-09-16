# MT5 Container — Flow, Logic & How to Test

How the live MT5 piece works and how to bring it up and verify it on your own
machine. Plain and practical. (For the *why* behind the design, see
`docs/MT5_INTEGRATION_PLAN.md`.)

> **Status (2026-09-15): the Wine container is a documented DEAD END** — see the
> "Build/run status" section below and `docs/WINE_VERDICT.md`. The RPC design in this
> doc is still the live path; only the host changes: run `mt5_service.py` on a
> **native Windows** machine and point the engine at it with
> `EXECUTION_HANDLER=remote_mt5`, `MT5_RPC_HOST=<windows host>` and the same
> `MT5_RPC_TOKEN` on both sides.

---

## The flow (what talks to what)

```
You (browser)
   │  pick "Live (MT5 demo)" + click "Send order"
   ▼
engine container  ─ RemoteMT5ExecutionHandler ─►  RPC over TCP (port 9099)
   │                                                   │
   │                                                   ▼
   │                                        mt5 container (Wine + xvfb)
   │                                          mt5_service.py  (RPC server)
   │                                                   │ calls MetaTrader5 API
   │                                                   ▼
   │                                            MT5 terminal (headless)
   │                                                   │
   ▼                                                   ▼
result shown in dashboard  ◄──── RPC reply ────  broker (demo account)
```

**Two containers, one network:**
- **engine** — your Python code + dashboard. No Wine, no MetaTrader5.
- **mt5** — Wine + a headless MT5 terminal + the RPC server. The only place
  `MetaTrader5` exists.

They never share code imports — they talk over a **socket**. The engine sends
"place this order" as a JSON line; the mt5 container does it and replies.

---

## The logic (each piece's job)

| File | Runs in | Job |
|------|---------|-----|
| `src/execution/remote_mt5.py` | engine | RPC **client**: forwards each interface call over TCP. Fails gracefully if mt5 is down. |
| `src/execution/rpc_protocol.py` | both | The shared message format (JSON + newline). |
| `src/execution/mt5_service.py` | mt5 container | RPC **server**: receives calls, runs them on the real handler. |
| `src/execution/mt5.py` | mt5 container | The real `MetaTrader5` API calls (BUY@ask, SELL@bid, close, positions). |
| `docker/mt5/Dockerfile` | — | Builds Wine + Windows-Python + xvfb + the code. |
| `docker/mt5/entrypoint.sh` | mt5 container | Starts the virtual screen (xvfb), then the RPC server under Wine. |

**Key safety properties (already unit-tested):**
- The engine never imports `MetaTrader5` — proven by a test that asserts it's
  absent from `sys.modules` after importing everything.
- If the MT5 service is down, the dashboard shows a friendly message instead of
  crashing.
- With `MT5_RPC_TOKEN` set, the server rejects any request without the matching token
  (tested). The link is plain TCP, so also keep the port private.
- Order volume crosses the boundary in **units**; `MT5ExecutionHandler` converts to
  broker lots with the symbol's real contract size, rounding down (tested).
- Backtesting uses the **mock** and never touches any of this.

---

## How to test it (step by step)

### Prerequisites
1. **Docker** running on your machine (you have 24 GB RAM — plenty).
2. A **free MT5 DEMO account** from any MT5 broker (e.g. MetaQuotes demo). You
   need its **Login**, **Password**, and **Server**. Demo only — never live (§9).
3. Put them in `.env` (gitignored):
   ```
   MT5_LOGIN=<your demo login>
   MT5_PASSWORD=<your demo password>
   MT5_SERVER=<your demo server>
   ```

### Step 1 — Build the images
```bash
# Engine is quick; the mt5 (Wine) image is a large one-time download.
docker compose --profile live build
```

### Step 2 — Start everything (dev profile = headless, realistic limits)
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile live up
```
Watch the logs. Success looks like:
```
ats-mt5    | [entrypoint] starting Xvfb on :99
ats-mt5    | MT5 RPC service listening on 0.0.0.0:9099
ats-mt5    | MT5 handler connected and ready for RPC.   (appears on first call)
```

### Step 3 — Verify from the dashboard
1. Set `EXECUTION_HANDLER=remote_mt5` in `.env` (the default `mock` routes Live-mode
   orders to the paper broker instead).
2. Open `http://localhost:8501` and choose **Live (paper or MT5 demo)**.
3. The status box should say **Connected to MT5 RPC service…** (green).
4. Fill side/volume (lots)/SL/TP, click **Send order**, and read the result
   (it includes `latency_ms`, the signal → fill-confirmation time).
5. Check the trade appears in your broker's demo terminal/web.

### Step 4 — Check resource use
```bash
docker stats        # confirm mt5 stays within the compose memory cap
```

### Backtest-only (no MT5 needed) — the everyday path
```bash
docker compose up engine          # OR just run the dashboard in .venv
```
Pick **Backtest (mock)** in the dashboard. No Wine container starts.

---

## Testing WITHOUT building the Wine image (fast / CI)

You don't need the real container to test the integration logic — the test suite
already does it with a **fake** MetaTrader5 module and a real local socket:

```bash
.venv/bin/python -m pytest tests/test_rpc_execution.py tests/test_mt5_execution.py -v
```

These prove the client↔server protocol, the API mapping, graceful failure, and
the macOS-safe import — all without Docker or a broker.

---

## Build/run status (verified 2026-06-18, Apple Silicon + Docker)

A real build-and-run was attempted on an arm64 Mac. What's confirmed working, and
the one remaining blocker:

**Working (verified):**
- Image builds. Required `--platform=linux/amd64` (tobix/pywine is x86-only; arm64
  Macs emulate it). Added to the Dockerfile and compose.
- Container runs stably; xvfb + Wine boot; RPC service listens on 9099.
- RPC round-trip works end-to-end (`ping → pong` over the socket).
- **MetaTrader5 Python library imports under Wine**, along with pandas and our `src`
  package. This required pinning **numpy==1.26.4** in `requirements-mt5.txt`: numpy 2.x
  calls `ucrtbase.dll.crealf`, which this Wine build doesn't implement, so numpy 2
  (and therefore MetaTrader5) aborts. Installing MT5 deps LAST in the Dockerfile makes
  the pin authoritative.
- Our code calls `mt5.initialize()` correctly; the RPC error path is clean.

**Blocked (the genuine "last mile"):**
- `mt5.initialize()` fails with `IPC initialize failed, MetaTrader 5 x64 not found`.
  The MetaTrader5 *Python library* is installed, but the **MT5 terminal program**
  (`terminal64.exe`) is not — `initialize()` has nothing to attach to.
- The official MetaQuotes installer (`mt5setup.exe /auto`) was downloaded into the
  container (curl works, internet confirmed) but **fails silently under this Wine build**
  — it creates `AppData/Roaming/MetaQuotes` but never installs `terminal64.exe` into
  `Program Files`. Tried: `/auto`, GUI mode, explicit `WINEPREFIX=/opt/wineprefix`,
  long waits, error tracing. The installer hits an unimplemented Windows API early and
  bails without output. This is the known hard part of headless MT5-under-Wine.

**RESOLVED (2026-06-18): Wine is a dead end — use native Windows.** We confirmed
the install blocker here, then a sibling project (`gadel-engine`) supplied the
decisive proof that Wine *cannot* run MT5's Python API at all: `mt5.initialize()`
fails with `-10005` (IPC timeout) even on native x86 with no emulation, even after
cloning a working reference byte-for-byte — while native Windows works on the first
try (real trade placed). See **`docs/WINE_VERDICT.md`** for the full finding and the
native-Windows deployment path (golden-master + `servers.dat` recipe). Do not spend
more time on the Wine route.

**Impact: none on the project.** The full engine, evaluation, and all README §8 results
run on the MockExecutionHandler. The live terminal is a demonstration extra; everything
up to the terminal binary is built and verified.

## Common issues

| Symptom | Likely cause / fix |
|---------|--------------------|
| Dashboard Live = "unreachable" | RPC server not running on the MT5 host, wrong `MT5_RPC_HOST`/`PORT`, or a firewall. |
| Every call returns `unauthorized` | `MT5_RPC_TOKEN` differs between the engine and the MT5 host. |
| Order rejected `below_min_volume` | The requested units are below the broker's minimum lot (e.g. < 1,000 units for a 0.01 lot). |
| `MT5 login failed` in logs | Wrong demo creds in `.env`, or wrong server name. |
| `MT5 initialize() failed` | xvfb/Wine didn't start the terminal — check entrypoint logs. |
| mt5 container using too much RAM | Lower the cap in `docker-compose.prod.yml` / `.dev.yml`. |
| Order `rejected` | Market closed, bad SL/TP distance, or symbol not in the demo's Market Watch. |
