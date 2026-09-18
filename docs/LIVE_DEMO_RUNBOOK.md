# Live Demo Session — Runbook

How to run the system against a real MT5 **demo** account so report objective 4
("evaluate on a live demo account") is satisfied by this project's own trades,
and the < 500 ms latency target finally has a measurement.

Setup of the Windows host is in `docs/COMMANDS.md` §5 and is not repeated here.
This document is the **session protocol**: what to run, what to record, and how to
write it up without overclaiming.

---

## 1. What this does and does not prove

Read this first, because it determines what you may write in Chapter 4.

**It proves:**
- The system can generate a signal from live market data and route the resulting
  order to a real broker, end to end, with no human choosing the trade.
- The execution path works against a real broker: fill mode, lot conversion, magic
  number, stop/target placement.
- **Signal-to-fill latency**, measured per order against the 500 ms target.

**It does not prove:**
- Anything about win rate, profit factor, drawdown or Sharpe. On the test set the
  volume gate passes about 13% of hourly bars and both gates about 5–10%, but only one
  position is held at a time, so the system trades on roughly 1.2–1.5% of bars:
  expect **1–2 trades per pair per week**. Ten trades is
  not a performance result and must never be presented as one.

Say this explicitly in the report. A small, honest live-execution validation next to
a large held-out backtest is a strong chapter. A handful of live trades dressed up as
performance evidence is the one thing that can sink a viva.

---

## 2. Before you start

- [ ] MT5 **demo** account, logged in once by hand, **Algo Trading enabled** in the
      toolbar (otherwise every order returns `10027`).
- [ ] RPC service running on the Windows host: `python -m src.execution.mt5_service`
- [ ] `.env` on the engine machine: `EXECUTION_HANDLER=remote_mt5`, `MT5_RPC_HOST`,
      `MT5_RPC_PORT=9099`, and the same `MT5_RPC_TOKEN` as the Windows host.
- [ ] Models trained for the pairs you'll run:
      `.venv/bin/python scripts/run_backtest.py EURUSD 1h` (and `GBPUSD`).
- [ ] Note the demo account's actual balance — you'll pass it as `--equity` so the
      position sizing is realistic rather than the $10,000 default.

Never point this at a funded account. Never commit or print credentials.

---

## 3. The session

### Step 1 — dry run (no orders, no broker needed)

```bash
.venv/bin/python scripts/live_session.py EURUSD 1h
```

Prints the current bar, P(bullish), the volume Z-Score, whether each gate passed, and
the sized order it *would* place. Run this until you've seen it produce a non-HOLD
decision at least once. Nothing is sent.

### Step 2 — paper order through the full chain

With `EXECUTION_HANDLER=mock` still set:

```bash
.venv/bin/python scripts/live_session.py EURUSD 1h --send
```

Same chain, filled in the in-process simulated broker. This confirms the plumbing
before a real broker is involved. **Screenshot this** — it's a Chapter 4 figure.

**If it says HOLD, that is normal**: the volume gate passes only about 13% of bars,
and the system trades on roughly 1.2–1.5% of them, so most hours produce no trade. Don't wait days to find out whether the order path itself
works. Force one through by temporarily lowering the gate, writing to a **scratch log**
so your evidence log stays clean:

```bash
VOLUME_ZSCORE_THRESHOLD=-5 .venv/bin/python scripts/live_session.py EURUSD 1h \
    --send --log logs/smoke_test.jsonl
```

That exercises sizing, `place_order`, the latency timer and the broker-result logging.
It is a **plumbing test only** — the lowered threshold means the trade is not a real
signal, so never quote it as a result or include it in the Chapter 4 trade table.
Run the same command against `EXECUTION_HANDLER=mt5` once on the Windows box to prove
the broker link before the real session starts.

### Step 3 — live demo session

**Pick the topology first. If you have a Windows machine, option A is far less work.**

**Option A — everything on the Windows PC (simplest; no RPC, no second machine).**
MetaTrader 5 and its Python API are Windows-only, so if you run the *whole engine*
there, the network boundary disappears:

```cmd
git clone <this repo>  &&  cd scikit-automated-trading-system
pip install -r requirements.txt
pip install -r requirements-mt5.txt
python scripts\run_backtest.py EURUSD 1h          :: trains + saves the model there
set EXECUTION_HANDLER=mt5
python scripts\live_session.py EURUSD 1h --send --loop --equity 5000
```

`EXECUTION_HANDLER=mt5` talks to the local terminal directly. No `MT5_RPC_HOST`, no
token, no firewall. This is the recommended path when time is short.

#### ⚠️ If that machine also runs a live system (e.g. the gadel VPS)

Reusing a VPS that already trades real money is the highest-risk option in this
document. It is workable, but only with these five precautions — the first two are
not optional.

1. **Install a SECOND, separate MT5 terminal** for this project and point
   `MT5_TERMINAL_PATH` at its `terminal64.exe`. Without it, `initialize()` attaches
   to the terminal that is already running — the live one — and `login()` then
   switches that terminal to a different account, which would knock the live EA off
   its account mid-session. A portable install in its own folder is cleanest.
2. **Use a dedicated DEMO account**, never the funded one. Keep
   `MT5_REQUIRE_DEMO=true`; the handler reads `account_info().trade_mode` after
   logging in and refuses to continue on a real account, before any order is sent.
3. **Magic numbers must not collide.** This project stamps `20260917`; gadel's EA
   uses `20260519` plus per-chart offsets, so they are already far apart. Keep
   `MT5_ONLY_OWN_POSITIONS=true` — it is what stops this system from ever seeing or
   closing a position it did not open.
4. **Never attach this project's EA-less terminal to gadel's charts**, and don't
   run the two terminals from the same data folder — MQL5 global variables are
   terminal-wide.
5. **Consider the blast radius.** A crash, a runaway loop or a filled disk on that
   VPS affects live trading. Keep `--max-trades` low, run one pair at a time, and
   prefer a cheap second VPS if one is available.

```cmd
set MT5_TERMINAL_PATH=C:\MT5-Demo\terminal64.exe
set MT5_REQUIRE_DEMO=true
set EXECUTION_HANDLER=mt5
python scripts\live_session.py EURUSD 1h --send --loop --equity 5000
```

**Option B — engine on macOS/Linux, MT5 on a Windows host (the RPC split).** Use this
only when the engine must stay on your Mac. Set `EXECUTION_HANDLER=remote_mt5`,
confirm the dashboard's Live tab shows green, then:

```bash
.venv/bin/python scripts/live_session.py EURUSD 1h --send --loop --equity 5000
.venv/bin/python scripts/live_session.py GBPUSD 1h --send --loop --equity 5000
```

Run both pairs (two terminals) to roughly double the trade rate. Leave them for
**one to two weeks**. The script re-checks at each bar close, refuses to trade the
same bar twice even across restarts, stops after `--max-trades` (default 5), and
respects the drawdown and daily-loss limits.

Everything lands in `logs/live_session_<PAIR>_<TF>.jsonl`, one JSON record per check.

### Step 4 — collect

```bash
# every order actually sent
grep '"order_sent": true' logs/live_session_*.jsonl | python -m json.tool

# latency figures
python - <<'PY'
import json, glob
lat = [json.loads(l)["latency_ms"]
       for f in glob.glob("logs/live_session_*.jsonl")
       for l in open(f) if '"order_sent": true' in l]
print(f"n={len(lat)}  min={min(lat):.0f}  median={sorted(lat)[len(lat)//2]:.0f}  max={max(lat):.0f} ms")
PY
```

Screenshot MetaTrader's **Trade** and **History** tabs showing the positions, and the
terminal output of a live signal. Redact the account number, balance and server name
in every screenshot.

---

## 4. What to record for each trade

The JSONL already captures all of it; this is what matters when you tabulate:

| Field | Why it matters |
|---|---|
| `bar_time`, `probability`, `volume_zscore` | proves the trade came from the model + gate, not a human |
| `rule_pass` / `ml_pass` | shows the AND-logic actually operating |
| `side`, `lots`, `stop_loss`, `take_profit` | the RiskManager's sizing in the real world |
| `latency_ms`, `meets_latency_target` | **the objective-4 measurement** |
| `broker_status`, `broker_ticket`, `broker_retcode` | broker-side confirmation |

---

## 5. Writing it up in Chapter 4

Give it its own short section — *Live Execution Validation* — and keep the framing
tight. Something close to:

> The execution path was validated against a live MetaTrader 5 demo account
> (broker, account type, dates). Over N trading days the system generated M signals
> and routed each resulting order automatically; every order was accepted by the
> broker, with a median signal-to-fill latency of X ms (range Y–Z ms) against the
> 500 ms target specified in Table 3.3. Position sizing, stop-loss and take-profit
> placement were performed by the RiskManager without manual intervention.
>
> This exercise validates the execution architecture and the latency target only.
> With M trades it carries no statistical weight regarding profitability; the
> performance results in §4.x remain those obtained by backtesting on the held-out
> set with modelled transaction costs.

Then a small table of the individual trades — with N that small, show every one
rather than summary statistics. Honesty about N is what makes the section credible.

This also lets you correct two items in `docs/REPORT_CORRECTIONS.md`: **A-6** (the
live-evaluation claim) becomes true as scoped, and the **execution-latency gap** in
`DEVIATIONS_FROM_SPEC.md` closes.

---

## 6. Two caveats to state, not hide

1. **Data latency.** Signals are computed from Yahoo Finance bars, which can lag the
   broker's own feed. The decision price and the fill price therefore differ slightly.
   This is a property of the data source, not a defect — but Chapter 4 should say so,
   and it is good future work to read prices from MT5 directly.
2. **Sizing assumes the equity you pass.** `--equity` is what the RiskManager sizes
   against; it does not query the broker's live balance. Set it to the demo balance
   and say which figure you used.

---

## 7. If something goes wrong

`docs/COMMANDS.md` §7 has the troubleshooting table. The three you're most likely to
hit:

| Symptom | Cause |
|---|---|
| `10027` on every order | Algo Trading is off in the MetaTrader toolbar |
| `unauthorized` | `MT5_RPC_TOKEN` differs between the two machines |
| `below_min_volume` | the sized position is under the broker's minimum lot — by design we reject rather than round up. Raise `--equity` or `RISK_FRACTION_PER_TRADE` |
| `Refusing to trade: … is NOT a demo account` | the guard did its job — that login is a live account. Switch to the demo login |
| `account_info() returned nothing` | the terminal isn't logged in, or MT5 attached to a terminal you didn't intend — set `MT5_TERMINAL_PATH` |
| Orders appear in the **wrong terminal** | `initialize()` attached to the already-running terminal. Set `MT5_TERMINAL_PATH` to your dedicated installation |
