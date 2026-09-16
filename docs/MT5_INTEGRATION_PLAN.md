# MT5 Live Integration — Design & Plan

How the engine and the real MT5 terminal connect, and how the dashboard offers
**backtest (no MT5)** vs **live (MT5 demo)** cleanly.

---

## Architecture (two containers, network boundary)

```
┌──────────────────────┐         RPC (JSON over TCP)        ┌───────────────────────┐
│   engine container    │  ───── place_order / close ─────► │   mt5 container (Wine) │
│  (dashboard + engine) │  ◄──── result / positions ─────   │  xvfb + MT5 terminal   │ ──► broker (demo)
└──────────────────────┘                                    └───────────────────────┘
        Linux, no Wine                                        Windows-Python under Wine
```

The engine **never imports MetaTrader5**. It calls a small RPC client; the mt5
container runs an RPC server that calls the real `MetaTrader5` API. This is the
"thin RPC/socket boundary" README §13 leaves open.

Both implement the SAME `ExecutionHandler` contract, so the engine code is
identical whether it talks to the mock or the remote MT5 — only which handler it
holds changes.

Three execution handlers now:
- `MockExecutionHandler` — in-process simulation (backtesting).
- `MT5ExecutionHandler` — direct MetaTrader5 (runs INSIDE the mt5 container).
- `RemoteMT5ExecutionHandler` — RPC client (runs in the ENGINE, talks to the mt5 container).

---

## Dashboard: two modes (the key decision)

A **mode selector** at the top. The two modes are genuinely different jobs:

| | Backtest mode (default) | Live mode (opt-in) |
|---|---|---|
| Data | historical (held-out) | manual order inputs |
| Handler | Mock (always) | whatever `EXECUTION_HANDLER` selects: `mock` (paper, default), `remote_mt5` (RPC), `mt5` (direct, Windows only) |
| Needs MT5 running? | **No** | only for `remote_mt5` / `mt5` |
| Purpose | evaluation / §8 metrics | paper or actual demo trading |
| Action | "Run Backtest" | connection status + "Send order" |

**Rules that keep it safe and decoupled:**
1. Backtest is the default and **never** touches MT5 or the RPC client.
2. Live mode degrades gracefully: if the MT5 service isn't reachable, show a friendly
   "unreachable" message, never crash.
3. Live mode is **manual** (single-shot orders), not an always-on auto-trader —
   safer for a demo/viva, no runaway loop. (Auto-trade can be future work.)
4. The RPC server accepts an optional shared secret (`MT5_RPC_TOKEN`); the link is
   plain TCP, so the port must stay private (LAN / VPN / SSH tunnel).
5. Volume crosses the boundary in units; the MT5 side converts to lots.

> **Update (2026-06-18 / 2026-09-15):** the mt5 container below turned out to be a
> dead end — MT5's Python API can't initialise under Wine (`docs/WINE_VERDICT.md`).
> The architecture is unchanged; the "mt5 container" box becomes a native Windows host
> running `python -m src.execution.mt5_service`.

---

## Dev vs Prod (same images, different limits)

Both **headless**. Dev simulates prod, just with enough headroom to work smoothly.

| | Dev | Prod |
|---|---|---|
| MT5 container | headless (xvfb) | headless (xvfb) |
| Memory cap (mt5) | ~1.5g (room to debug) | ~1g (tight) |
| Memory cap (engine) | ~1g | ~768m |
| Restart policy | no | `unless-stopped` |
| MT5 runs by default? | **No** — `--profile live` | yes |

The mt5 service sits behind a Docker **profile** (`live`) so normal backtesting
never starts the heavy Wine container. Start it only for live trading:
`docker compose --profile live up`.

---

## Build steps

1. **RPC server** in the mt5 container (`mt5_service.py` gains a socket server that
   wraps `MT5ExecutionHandler`).
2. **RPC client** `RemoteMT5ExecutionHandler` (implements the interface; used by the
   engine). Add `"remote_mt5"` to the factory.
3. **Engine Dockerfile** (`docker/engine/Dockerfile`) — Python + core deps, runs the
   dashboard.
4. **docker-compose**: `engine` service + `mt5` service (profile `live`), shared
   network, dev/prod overrides.
5. **Dashboard**: add the Backtest/Live mode selector + graceful live status.
6. Tests for the RPC client/server (mocked socket) — no real MT5 needed.
