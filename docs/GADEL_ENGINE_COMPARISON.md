# gadel-engine — what it is, how far it got, and how it differs from this project

A read of the sibling project `~/Documents/Projects/BackendProjects/gadel-engine`, done
2026-09-16, so we know what was learned there and where the two projects genuinely
differ. This project already depends on one of its findings (the Wine verdict), so it
is worth knowing what else is in there.

**How this was produced.** Six parallel readers covered: `CLAUDE.md` (175 KB) and
`TODO.md` (277 KB); `CHANGELOG.md` (576 KB, 241 dated entries) plus 605 commits; the
code; `docs/cloud-mt5/` + `docs/debug/`; the GX strategy research (`docs/gx-*`,
34 files); and `docs/DECISIONS.md` / `ENGINEERING_JOURNAL.md` / `OPEN_GAPS.md` /
`RECOMMENDATIONS.md` / `MANUAL_TESTS.md` / `docs/product/` / `docs/ops/` /
`docs/mt5-protocol/`. Their own docs repeatedly warn that they drift and carry visible
self-corrections; everything below is what those files say, with their corrections
applied. Nothing in that repo was modified.

---

## 1. What it is

A **commercial, live, revenue-seeking trading platform** — not a research project.
Users connect their Telegram account, subscribe to signal channels, set rules, and
attach broker accounts; the engine parses each signal, applies per-user rules and
sizing, and executes. It also sells a proprietary MQL5 strategy ("GX Strategy") and
rents cloud-hosted MetaTrader terminals so a customer needs no machine of their own.

- **Five repos move together:** `gadel-engine` (Python execution layer), `gadel-backend`
  (NestJS API), `gadel-web-app` (dashboard), `gadel-site` (marketing), and the
  `OrderBlockConfluenceEA` MQL5 EA in its own repo.
- **Venues:** MetaTrader 5 (user-hosted *and* Gadel-hosted), Deriv, IQ Option, and
  crypto perpetuals on Bybit and WEEX.
- **Business model:** FREE / BASIC / PREMIUM subscriptions (prices still marked
  provisional), add-on slots, a referral programme paying USDT on-chain, and a 3%
  Deriv markup. Real users since the 2026-07-26 beta; real money, including on-chain
  payouts and a live WEEX cycle that cost $0.0003.

## 2. Where it has got to (May → September 2026)

| When | Milestone |
|------|-----------|
| 2026-05-16 | First vertical slice closed: Telegram → parse → queue → IQ Option → settle |
| 2026-05-27 | First real trade, and **nine cross-system bugs no unit test could catch** |
| 2026-06-02 | MT5 "Mode A" (user-hosted EA over a WebSocket bridge) end-to-end |
| **2026-06-19** | **Wine ruled out; cloud MT5 pivots to native Windows** (the finding we cite) |
| 2026-06-26 | Headless per-account MT5 login solved (golden master + real 780 KB `servers.dat` + login "priming") |
| 2026-07-08 | Terminal density unblocked — the limit was the Windows **session-0 desktop heap**, not RAM |
| 2026-07-23 | Production rebuilt onto a private network so the host agent never faces the internet |
| 2026-08-03 | Crypto perps added; WEEX proven with real money |
| 2026-08-08 | Cost crisis: a listener issuing ~146k DB queries in 20 minutes; caching + backoff rules introduced |
| 2026-09-12 | Research phase: "alpha features" that log even when switched off |
| 2026-09-15 | Head: crypto keyword actions built and demo-verified, not yet deployed |

**Current scale:** ~1,293 passing tests; 8 connected accounts over 16–18 cloud
terminals; one Windows box full at ~17–18 terminals; nightly database backups to
object storage with a *proven* restore.

**Current trading reality — worth knowing.** Their live fleet read on 2026-08-30:
31.7% win rate, reward:risk 1.81, **expectancy −0.123 per trade** against a 35.6%
break-even. A 150-day real-tick backtest of the two live trend configs gave **PF 0.84
and 0.88** — both losing. Their own summary is that this is a thin edge where
**position sizing, not signal quality, is the binding problem**.

## 3. Side by side

| | This project (scikit-automated-trading-system) | gadel-engine |
|---|---|---|
| Purpose | B.Sc. final-year project: design, build, **evaluate** | Commercial SaaS with paying users |
| Success criterion | A defensible, honestly measured result | Revenue, uptime, customer accounts |
| Machine learning | **Random Forest classifier is the core** | **None.** Classical indicators + statistics only |
| Strategy | Volume Z-Score gate AND RF probability | EMA-cross trend and SMC order blocks, in an MQL5 EA |
| Instruments | EUR/USD, GBP/USD, 1h (and 4h) | XAUUSD almost exclusively, M1–M15 |
| Data | Yahoo Finance hourly candles + CME futures volume | Broker tick data, live fills, MT5 Strategy Tester |
| Evaluation | Held-out backtest, costs modelled, Wilson intervals, no-skill baseline | Live fills first; backtests only after the harness reproduces real trades |
| Execution | Mock broker; MT5 handler built, never run live | Live across five venues, thousands of real trades |
| Risk controls | Fixed-fractional sizing, dynamic stops, drawdown + daily-loss limits | **Daily loss cap only** — no drawdown rule, no per-trade cap, no kill switch |
| Deployment | Docker for the engine; live MT5 needs a Windows host | Windows VPS fleet, private network, autoscaler (off), object storage |
| Tests | 210 | ~1,145 test functions in 81 modules (~1,290 collected) |
| Docs | 16 markdown | 60+ markdown, plus data artefacts |
| Provenance | No git repo | 605 commits, changelog with 241 dated entries |

### How it's built

A single asyncio daemon (`main.py`) whose role is chosen by `SERVICE_MODE`
(`signals` / `executor` / `mt5` / `all`), mounting subsystems as named tasks: a
Telegram listener, a BullMQ worker at concurrency 4, and ~16 perpetual reconciliation
loops (health watchers, trade reconcilers, billing sweeps, an autoscaler). Idle loops
back off to 20 minutes specifically so the managed Postgres can scale to zero — a
lesson from a bill caused by ~146k queries in 20 minutes.

Two design choices match ours almost exactly: **an abstract broker interface**
(`BrokerAdapter` with `connect / place_trade / check_result / get_balance / disconnect`,
five implementations behind it) and **rejections returned as a result object rather
than raised** — the same shape as our `ExecutionHandler` and the mock's
`{"status": "rejected"}`. Arriving at the same abstraction independently is a point
in favour of both.

The signals themselves are **other people's Telegram messages**, parsed by three
regex grammars (binary, forex, crypto). There is no in-house signal generation in the
Python at all; the one proprietary strategy is an MQL5 EA whose source lives in a
separate repo.

**The no-ML claim is now verified by grep, not inference:** a repo-wide search for
`sklearn|scikit|tensorflow|keras|torch|xgboost|lightgbm|statsmodels|scipy|numpy|pandas|RandomForest`
returns **zero matches** outside the virtualenv. The only numeric import in the
application packages is `math` (two calls, for lot-step rounding). Their offline
analysis scripts deliberately use the Python standard library only.

## 4. The finding we already depend on

Their Phase 0 (2026-06-19) tested headless MT5 under Wine on an ARM Mac under
emulation, on native amd64 CI, **and on a real x86 Linux VPS**. In every case
`mt5.initialize()` returned **`-10005`**: the terminal starts but never opens its IPC
pipe — their proof being the terminal's own log, which prints three startup lines and
then goes silent, never reaching `Network 'server': connecting…`. They ruled out
emulation, every call shape, missing credentials, a desktop session, `vcrun2019`, a
persistent wineserver, a broker-branded build and a Wine 9.0 pin, and replicated a
public working reference **byte-for-byte** — which still failed. A native Windows VPS
then worked first try. Two rules they set, now reflected in our `WINE_VERDICT.md`:
re-open only with a reference reproducible from its committed code, and **bundling a
pre-installed MT5 folder does not fix `-10005`** — the failure is runtime IPC.

**A claim there about us needs correcting.** Their `MODE_B_PLAN.md` cites this repo's
`docker/mt5/` as "all confirmed working, headless" and used it as its starting
reference. That was never true here either — our container built and the RPC server
ran, but the installer never produced `terminal64.exe`. Noted in `docs/WINE_VERDICT.md`.

## 5. Where two independent projects agree

These are the parts worth putting in Chapter 4, because they were reached separately,
by different methods, on different instruments.

- **Exit geometry beats feature engineering, and the trade-off is a law.** Their
  150-day real-tick exit test: banking at 0.5R gave the best win rate of any variant
  (**52.3%**) and still lost money (PF 0.94), because a close target is only ~7–10×
  the spread. Their fleet arithmetic: "every account at R:R ≥ 2.0 makes money, every
  one below loses." That is our Step E frontier, measured on live fills.
- **Small samples lie, and clustering makes them smaller than they look.** They treat
  897 trades as **~20 independent observations** because 879 share a signal bar, and
  require a day-level sign test, within-day demeaning, outlier concentration and an
  out-of-sample split for any claim. Our 30–37 trades have the same problem; our
  Wilson intervals are the minimum, not the whole answer.
- **A statistically beautiful result can still be wrong.** Their "persistence" edge hit
  p = 0.00001 by permutation, ~4.5 SD from null, and survived three robustness checks —
  then died: 8 of 14 at day level, with 10 of 185 trades carrying 48% of the effect.
- **Intra-candle fidelity decides tight-stop results.** They found every backtest before
  2026-09-04 ran on **invented ticks** (~4/minute vs real gold's 50,000+/day), which
  decided stop-versus-target inside the bar. Their tooling now refuses any run not
  marked "100% real ticks". Our hourly-candle "assume the stop was hit first" rule is
  the same exposure, and our close-TP config is exactly the tight-stop case.
- **Position sizing outranks signal quality.** An account went $147 → $49 in four days;
  the strategy lost ~2R and *sizing* multiplied it seventeenfold, because an
  unaffordable lot rounded **up** to the broker minimum took 7.6–28× the intended risk.
  Their Python sizing rounds *down* (`round(raw_lot - 0.005, 2)`) but then floors at
  `max(0.01, …)` — which is exactly the up-rounding their own research indicts. Our
  handler **rejects** a below-minimum order instead, which is the corrective they have
  documented but not yet applied in code.

## 6. What we should borrow

1. **Pre-registration.** They write the rule, the grid, the split *and the kill
   criteria* before seeing results, and refuse to move the threshold afterwards:
   "lowering it after seeing that the fleet's scores sit below it, then calling that
   the original test, is the one move a sealed envelope exists to prevent." Our Step C
   threshold tuning would have been stronger this way.
2. **The alpha contract:** a new feature ships **off, but still logs what it would have
   done**. Logging is deliberately not behind the switch. Our `USE_*` flags default off
   but log nothing — a cheap upgrade if we ever test another feature.
3. **Verify against the running system, not the source.** Their standing rule, learned
   from a chop filter that was live for six releases and **never fired once** because
   it could not reach its own warm-up threshold. That is the same class of defect as
   our `EXECUTION_HANDLER` that nothing read and our test with `or True` in it — they
   name it their most common bug class: "installed, configured, switched on — and inert."
4. **Leave corrections visible, with dates.** Roughly a third of their gaps and
   manual-test files is retractions of their own earlier text. Our audit doc does this;
   keep doing it.
5. **Read the artifact back.** They verify a publish by re-downloading the binary and
   checking its hash — "the upload reported success" is not evidence. Our equivalent is
   model provenance plus `inspect_model.py`.
6. **Report per-unit metrics.** "Only profit factor and expected payoff say whether the
   trades KEPT were better than the trades SKIPPED" — net profit and drawdown improve
   merely by trading less. This is exactly why our no-skill baseline compares PF, not
   just win rate.
7. **Their order-block rules — borrowed and measured (done 2026-09-17).** Their EA trades
   SMC order blocks, and our report's §2.5 promises order-block identification, so their
   rule set (break of structure confirmed by a *close*, ATR-filtered zone size, zone dies
   on mitigation) was reimplemented here as three Random Forest features and measured on
   both pairs — Step F in `docs/RESULTS.md`. It improved only GBP/USD at the default
   exits, so it ships off (`USE_ORDER_BLOCKS=false`). Their own live numbers point the
   same way: the order-block engine runs at PF 1.05–1.12 with 37–52% drawdown, and fleet
   expectancy is negative. Borrowing the *rules* was cheap and informative; borrowing the
   *claim* that order blocks work would not have been.

## 7. What this project has that theirs doesn't

Worth saying plainly, because the scale gap is intimidating and it is not the whole story.

- **A trained model with an honest baseline.** They have no ML at all. We measure the
  model against random direction with identical exits — the question "is it the model
  or the geometry?" is one they have never had to ask.
- **A sealed test set and leakage tests.** Their equivalent is live-versus-backtest
  discipline; ours is chronological splitting, `TimeSeriesSplit`, and tests that delete
  future rows to prove features don't change.
- **One-command reproducibility of every documented number.** Every row in
  `docs/RESULTS.md` has its exact command; theirs depend on a live fleet and a broker's
  tick cache, and several of their own numbers are marked VOID by later entries.
- **Risk management as a module.** Theirs enforces one rule — a per-account daily loss
  cap in Redis — with no drawdown ceiling, no per-trade size cap and no kill switch;
  stop geometry belongs to the signal provider or the EA. Ours implements README §7 in
  full: fixed-fractional sizing, dynamic stops, a drawdown ceiling and a daily limit,
  all unit-tested. Given that their own conclusion is "sizing, not signal quality, is
  the binding problem", this is the part of our project their experience most validates.
- **Scope honesty.** A graded project that measures one strategy properly beats a
  platform that measures many things loosely — and their thin-edge result (PF ~1.0 live)
  is useful context for why our 1.34/1.62 on held-out data with costs is plausible
  rather than embarrassing.
- **Secrets hygiene.** Ours are gitignored and never committed; their tracked
  diagnostic scripts contain plaintext demo logins and passwords (disposable accounts,
  and listed in their own open-gaps file — but committed nonetheless).

## 8. Actionable for this repo

**Applied 2026-09-17** — five live-path defects their production experience exposed in
our code. None can affect a backtest number (the backtester never touches this code),
and the regression snapshot confirms every documented result is unchanged.

1. **✅ Fill mode was wrong for our own broker.** `src/execution/mt5.py` hardcoded
   `ORDER_FILLING_IOC`. They hit retcode **`10030` (invalid fill mode)** in production
   on **HFMarkets — the broker in our `.env`** — because those symbols accept **FOK**
   only. Fixed: we now read each symbol's `filling_mode` bitmask and request a mode the
   broker advertises, falling back to RETURN. Our first live order would otherwise have
   bounced. (Their user-hosted EA still hardcodes IOC; their RPC server was the pattern
   to copy.)
2. **✅ All MT5 calls now run on one pinned thread.** The library binds the terminal to
   whichever thread called `initialize()` first, but our RPC server answers each request
   on a new thread — so the *second* order would have failed. `mt5_service.py` now
   funnels every handler call through a single worker (ping still answers outside it, so
   a wedged terminal still reports liveness). A test asserts all calls share one thread.
3. **✅ Orders carry a magic number** (`MT5_MAGIC_NUMBER`). MT5 reports magic 0 for
   hand-placed trades, so without one our position list included the account owner's own
   trades — and `close_position` could have closed them. Positions are now filtered to
   ours by default (`MT5_ONLY_OWN_POSITIONS`), and closing a foreign position is refused.
   They hit exactly this: 15 manual silver trades filed against a gold-only strategy.
4. **✅ Broker rejections explain themselves.** Retcodes 10016/10018/10019/10027/10030
   now return a readable reason — `10027` ("AutoTrading disabled") is the one they hit on
   first live use.
5. **✅ Credentials are whitespace-stripped.** MT5 matches server names letter-for-letter
   including spaces; a stored trailing space cost them days of misdiagnosis.

Still worth knowing if we ever run live: MT5 auto-updates itself past what the Python
package can drive (`-10004`), and MetaQuotes enforces a server-side minimum build, so
pinning "buys months, not years" — keep the package current instead. And our unit→lot
conversion already does the right thing (round down, reject below minimum); their sizing
disaster is the evidence for why it should stay that way.

## 9. What we should deliberately not copy

Their cloud fleet, autoscaler, billing, referral payouts, multi-tenant credential
encryption and ops alerting are all excellent and all irrelevant to a final-year
project. The scope of this project is one strategy, measured honestly. Their platform
is the answer to a different question.

---

**Caveat on sourcing.** `gadel-engine`'s own documentation warns that it drifts, and
several claims above carry their own "stale — corrected" markers in the original files.
Where a correction exists, the corrected value is used. Architecture, risk controls,
test counts and the no-ML finding were read from the **code**; results, history and
verdicts come from their docs and changelog. Numbers here are theirs, not independently
reproduced by us. Their GX strategy EA source lives in another repo and was not read,
so anything about its internals is second-hand. It is a private sibling project — a
source of engineering lessons, not an academically citable reference.
