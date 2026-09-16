# Live MT5 Execution: Why Wine Is a Dead End, and the Real Deployment Path

A definitive finding for the project. The live `MT5ExecutionHandler` cannot run
under Wine; it must run on a **native Windows host**. This is not a limitation of
this project's code — the same wall was hit and exhaustively proven on a separate,
larger project, and the conclusion is reused here rather than re-derived.

---

## The one-line verdict

**Headless MetaTrader 5 under Wine does not work. Native Windows works on the
first try.** Our code is correct and unchanged either way — only the *host* differs.

## What we confirmed in this project (2026-06-18)

Building and running the Wine container on the dev machine (Apple Silicon Mac),
everything worked **up to the broker connection**:

- Image builds (needs `--platform=linux/amd64`; tobix/pywine is x86-only).
- Container runs; xvfb + Wine boot; our RPC service listens; `ping → pong` works.
- `MetaTrader5`, pandas, and our `src` package **import** under Wine — after
  pinning `numpy==1.26.4` (numpy 2.x calls `ucrtbase.dll.crealf`, which this Wine
  build does not implement, so numpy 2 aborts).
- **Blocked at `mt5.initialize()`** — the MT5 *terminal program* could not be
  installed (the MetaQuotes installer fails silently under Wine on this stack),
  so the Python library has no terminal to attach to.

## Why we are not pushing further (the decisive evidence)

A sibling project (`gadel-engine`) ran this exact investigation to the ground over
~2 days and ~15 attempts across **three** environments. Its retrospective
(`gadel-engine/docs/debug/MODE_B_WINE_RETROSPECTIVE.md`) establishes, with proof:

- Under Wine, even when the terminal **installs and launches**,
  `mt5.initialize()` fails with **`-10005` (IPC timeout)** — the terminal starts
  but **never brings up its networking/IPC subsystem**, so the pipe the Python
  library waits on never opens.
- This reproduces on a **KasmVNC desktop image** (a real window manager, not bare
  xvfb), on **GitHub Actions native amd64** (no emulation at all), and on a **real
  x86 Linux VPS**. So it is **not** an Apple-Silicon/emulation problem and **not**
  a missing-display problem.
- A public reference repo that demonstrably works in its author's video was cloned
  **byte-for-byte** (same base image, Wine, scripts, call site) and **still
  failed** — so whatever makes it work is not in the committed code.
- A **native Windows VPS** ran the identical Python library and **succeeded on the
  first attempt**: `initialize()` returned `True`, and a **real demo trade was
  placed** (`ticket 1206892489`, EURUSD, on the same HFMarkets demo account this
  project uses).

The cause, in plain terms: MT5's Python integration needs the terminal and the
library to talk over a local Windows IPC channel. On native Windows that's a
first-class OS feature. Under Wine the terminal's IPC subsystem never starts.
MetaQuotes does not test on Wine; this is a real, hard edge, not a config gap.

## The real deployment path (what production uses)

**Run the live execution layer on a native Windows host.** Everything else in this
project is unchanged:

- The abstract `ExecutionHandler` interface, `MT5ExecutionHandler`, the RPC
  server/client, and the dashboard's live mode are all normal code that runs
  identically on Windows. They are already built and unit-tested here.
- A ~$10/month Windows VPS (or any Windows PC) hosts the terminal + RPC server
  (`python -m src.execution.mt5_service`); the engine/dashboard connects to it over
  the same socket boundary already designed, with `EXECUTION_HANDLER=remote_mt5` and
  `MT5_RPC_HOST=<windows host>`.
- **Security:** set the same `MT5_RPC_TOKEN` on both machines — the server then rejects
  any request without it. The link is plain TCP (no TLS), so also keep the port off the
  public internet (LAN, VPN, or an SSH tunnel).
- Order volume crosses the link in units; `MT5ExecutionHandler` converts to lots with
  the broker's `symbol_info` (rounding down, rejecting below the minimum lot).

For a future headless, no-click login on Windows, the proven recipe (from
`gadel-engine/docs/cloud-mt5/MODE_B_PHASE2_ARCHITECTURE.md`, refinement #2, live-verified
2026-06-23) is: take a **golden-master** MT5 install that has registered the broker
once (File → Open an Account → find broker), `copytree` it per account, drop a
blank `portable.txt`, seed the **real ~780 KB `servers.dat`** from the install's
AppData folder into `<dir>\config\`, then
`initialize(path, login, password, server, portable=True)`.

## Impact on this project: none

The entire analytical engine, the hybrid strategy, the risk manager, the
backtester, and **all README §8 evaluation results** run on the
`MockExecutionHandler` — exactly as the architecture intended (the README itself
isolates the live broker as the "last mile" that must never block the engine). The
live Windows path is a deployment detail and a demonstration extra, not a
dependency of any result in the project.

## What stays in the repo

The Wine artifacts (`docker/mt5/Dockerfile`, `entrypoint.sh`, `docker-compose*.yml`,
the `numpy<2` pin) remain as a **documented dead-end** with the fixes that got us
as far as the IPC wall, so the path is reproducible and the finding is preserved.
