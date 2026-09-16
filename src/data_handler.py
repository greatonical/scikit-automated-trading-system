"""DataHandler — Module 1 (README §10 step 1).

Connects to Yahoo Finance via `yfinance`, fetches OHLCV for the configured Forex
pairs at 1h and 4h, caches to `data/`, and returns clean pandas DataFrames.

Data-source reality (documented deviation): the README data spec (§5) asks for
1h/4h candles spanning 2019–2024, but Yahoo Finance only serves intraday (<=1h)
data for ~the last 730 days. So for intraday timeframes we fetch the DEEPEST
window Yahoo allows and LOG the actual coverage. The 4h timeframe is built by
resampling the (cached) 1h series at load time, because yfinance has no native
4h interval; it is never cached separately, so it always shares the 1h window
and futures volume. All timestamps are normalised to UTC (Yahoo serves spot FX
in Europe/London time). Every parameter (pairs, timeframes, window, dates) comes
from config/settings.py — no magic numbers here (README §12).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

# Canonical OHLCV column order used throughout the engine.
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class DataHandler:
    """Fetch, cache, and serve OHLCV Forex data from Yahoo Finance.

    The handler is deliberately thin and side-effect-light: it knows how to get
    bars for one (pair, timeframe) and how to cache them. Higher layers
    (Preprocessor, Backtester) consume the returned DataFrames.
    """

    def __init__(
        self,
        pairs: dict[str, str] | None = None,
        timeframes: list[str] | None = None,
        cache_dir: Path | None = None,
        cache_enabled: bool | None = None,
        use_futures_volume: bool | None = None,
    ) -> None:
        self.pairs = pairs if pairs is not None else settings.PAIRS
        self.timeframes = timeframes if timeframes is not None else settings.TIMEFRAMES
        self.cache_dir = cache_dir if cache_dir is not None else settings.DATA_DIR
        self.cache_enabled = (
            cache_enabled if cache_enabled is not None else settings.CACHE_ENABLED
        )
        self.use_futures_volume = (
            use_futures_volume
            if use_futures_volume is not None
            else settings.USE_FUTURES_VOLUME
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_data(
        self,
        pair: str,
        timeframe: str,
        *,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Return a clean OHLCV DataFrame for one pair/timeframe.

        Loads from cache when available unless ``force_refresh`` is set. On a
        cache miss it fetches from Yahoo, cleans, caches, and returns. A derived
        timeframe (e.g. 4h) is resampled from its base timeframe's data (so
        ``force_refresh`` on 4h refreshes the 1h base).

        The returned frame has a UTC ``DatetimeIndex`` (sorted, unique) and
        exactly the columns in :data:`OHLCV_COLUMNS`.
        """
        self._validate(pair, timeframe)
        base_tf, resample_rule = settings.TIMEFRAME_FETCH[timeframe]

        if resample_rule:
            # Derived timeframe: rebuilt from the base series every time and never
            # cached itself, so it can't drift out of sync with the base.
            base = self.get_data(
                pair, base_tf, use_cache=use_cache, force_refresh=force_refresh
            )
            if base.empty:
                return base
            df = self._clean(self._resample(base, resample_rule))
            self._check_volume(df, pair, timeframe)
            return df

        cache_path = self._cache_path(pair, timeframe)

        if use_cache and not force_refresh and cache_path.exists():
            logger.info("Loading %s %s from cache: %s", pair, timeframe, cache_path.name)
            df = self._load_cache(cache_path)
            self._check_volume(df, pair, timeframe)
            return df

        df = self._fetch(pair, timeframe)
        df = self._clean(df)

        if df.empty:
            logger.warning("No data returned for %s %s", pair, timeframe)
            return df
        self._check_volume(df, pair, timeframe)

        start, end = df.index.min(), df.index.max()
        logger.info(
            "Fetched %s %s: %d rows, actual coverage %s -> %s",
            pair,
            timeframe,
            len(df),
            start.date(),
            end.date(),
        )

        if self.cache_enabled and use_cache:
            self._save_cache(df, cache_path)

        return df

    def get_all(
        self, *, force_refresh: bool = False
    ) -> dict[tuple[str, str], pd.DataFrame]:
        """Fetch every configured (pair, timeframe) combination.

        With ``force_refresh``, each base series is downloaded once per pair even
        though derived timeframes (4h) are rebuilt from it.
        """
        out: dict[tuple[str, str], pd.DataFrame] = {}
        for pair in self.pairs:
            refreshed: set[str] = set()
            for tf in self.timeframes:
                base_tf = settings.TIMEFRAME_FETCH[tf][0]
                force = force_refresh and base_tf not in refreshed
                out[(pair, tf)] = self.get_data(pair, tf, force_refresh=force)
                if force:
                    refreshed.add(base_tf)
        return out

    # ------------------------------------------------------------------ #
    # Fetching
    # ------------------------------------------------------------------ #
    def _fetch(self, pair: str, timeframe: str) -> pd.DataFrame:
        """Download raw bars from Yahoo Finance for one BASE pair/timeframe.

        Derived timeframes (4h) are resampled in :meth:`get_data`, not here.
        Intraday requests are clamped to Yahoo's ~730-day window.
        """
        ticker = self.pairs[pair]
        fetch_interval, _ = settings.TIMEFRAME_FETCH[timeframe]

        start, end = self._resolve_window(fetch_interval)
        logger.info(
            "Requesting %s (%s) interval=%s start=%s end=%s",
            pair,
            ticker,
            fetch_interval,
            start.date(),
            end.date(),
        )

        raw = self._download(ticker, start, end, fetch_interval)
        raw = self._normalise_columns(raw)

        # Spot FX reports volume=0; substitute real CME futures volume so the
        # +1.5 volume gate has genuine institutional-participation signal.
        if self.use_futures_volume and not raw.empty and pair in settings.VOLUME_SOURCE:
            raw = self._merge_futures_volume(raw, pair, fetch_interval, start, end)

        return raw

    def _merge_futures_volume(
        self,
        spot: pd.DataFrame,
        pair: str,
        fetch_interval: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Replace spot's (zero) Volume with timestamp-aligned futures volume.

        Price stays exactly the spot EUR/USD / GBP/USD series the report studies;
        only the Volume column is swapped for the matching CME futures volume.
        On any failure (empty fetch, no overlap) we keep spot volume and log it.
        """
        vol_ticker = settings.VOLUME_SOURCE[pair]
        try:
            fut = self._download(vol_ticker, start, end, fetch_interval)
            fut = self._normalise_columns(fut)
        except Exception as exc:  # pragma: no cover - network/edge guard
            logger.warning("Futures volume fetch failed for %s (%s): %s",
                           pair, vol_ticker, exc)
            return spot

        if fut.empty or "Volume" not in fut.columns:
            logger.warning(
                "No futures volume for %s (%s); keeping spot volume.",
                pair, vol_ticker,
            )
            return spot

        out = spot.copy()
        # Align futures volume onto spot timestamps. reindex keeps spot's index
        # (its price rows); missing futures bars -> 0 (no reported activity).
        aligned = fut["Volume"].reindex(out.index)
        matched = int(aligned.notna().sum())
        out["Volume"] = aligned.fillna(0.0)
        logger.info(
            "Merged futures volume %s -> %s: %d/%d spot rows matched a futures bar.",
            vol_ticker, pair, matched, len(out),
        )
        return out

    def _download(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> pd.DataFrame:
        """Thin wrapper around yfinance.download (isolated for test mocking)."""
        import yfinance as yf

        return yf.download(
            tickers=ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
        )

    def _resolve_window(self, interval: str) -> tuple[datetime, datetime]:
        """Compute the (start, end) datetimes to request.

        For intraday intervals, clamp the start to Yahoo's INTRADAY_MAX_DAYS
        window measured back from now. For daily-or-coarser, use the full
        configured HISTORY_START..HISTORY_END span.
        """
        end = datetime.now(timezone.utc)
        if interval in settings.INTRADAY_INTERVALS:
            earliest = end - timedelta(days=settings.INTRADAY_MAX_DAYS)
            configured_start = self._parse_date(settings.HISTORY_START)
            start = max(earliest, configured_start)
            if start > earliest:
                # configured start is within the window; honour it
                start = configured_start
            else:
                start = earliest
            return start, end

        start = self._parse_date(settings.HISTORY_START)
        end = self._parse_date(settings.HISTORY_END)
        return start, end

    @staticmethod
    def _parse_date(value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # ------------------------------------------------------------------ #
    # Cleaning / shaping
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Flatten yfinance's (sometimes MultiIndex) columns to OHLCV names."""
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        df = df.copy()
        # yfinance returns a MultiIndex (field, ticker) for single tickers in
        # newer versions; collapse to the field level.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Keep only the OHLCV fields we care about, in canonical order.
        present = [c for c in OHLCV_COLUMNS if c in df.columns]
        df = df[present]
        return df

    @staticmethod
    def _utc_index(index) -> pd.DatetimeIndex:
        """Return ``index`` as a UTC DatetimeIndex (a naive index is taken as UTC).

        Yahoo serves spot FX in Europe/London time; everything downstream (time
        features, daily-loss day boundaries, 4h buckets) assumes UTC.
        """
        if not isinstance(index, pd.DatetimeIndex):
            return pd.to_datetime(index, utc=True)
        if index.tz is None:
            return index.tz_localize("UTC")
        return index.tz_convert("UTC")

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sort, de-duplicate, drop empty rows, normalise the index to UTC."""
        if df.empty:
            return df

        df = df.copy()
        df.index = self._utc_index(df.index)

        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]

        # Drop rows with no Close (dead bars). Volume NaNs -> 0 (FX often 0).
        if "Close" in df.columns:
            df = df.dropna(subset=["Close"])
        if "Volume" in df.columns:
            df["Volume"] = df["Volume"].fillna(0)

        # Forward-fill the occasional missing OHLC field, then drop any residue.
        ohlc = [c for c in ["Open", "High", "Low", "Close"] if c in df.columns]
        df[ohlc] = df[ohlc].ffill()
        df = df.dropna(subset=ohlc)

        return df

    @staticmethod
    def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Resample lower-interval bars up to ``rule`` (e.g. '4h') OHLCV-correctly."""
        agg = {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
        agg = {k: v for k, v in agg.items() if k in df.columns}
        out = df.resample(rule).agg(agg)
        return out.dropna(subset=["Close"]) if "Close" in out.columns else out.dropna()

    # ------------------------------------------------------------------ #
    # Caching
    # ------------------------------------------------------------------ #
    def _cache_path(self, pair: str, timeframe: str) -> Path:
        ext = "parquet" if settings.CACHE_FORMAT == "parquet" else "csv"
        return self.cache_dir / f"{pair}_{timeframe}.{ext}"

    def _save_cache(self, df: pd.DataFrame, path: Path) -> None:
        try:
            if path.suffix == ".parquet":
                df.to_parquet(path)
            else:
                df.to_csv(path)
            logger.debug("Cached %d rows -> %s", len(df), path.name)
        except Exception as exc:  # pragma: no cover - cache is best-effort
            logger.warning("Failed to cache %s: %s", path.name, exc)
            # Fall back to CSV if parquet engine is unavailable.
            if path.suffix == ".parquet":
                df.to_csv(path.with_suffix(".csv"))

    @classmethod
    def _load_cache(cls, path: Path) -> pd.DataFrame:
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = cls._utc_index(df.index)
        return df

    # ------------------------------------------------------------------ #
    # Data-quality guard
    # ------------------------------------------------------------------ #
    @staticmethod
    def _check_volume(df: pd.DataFrame, pair: str, timeframe: str) -> None:
        """Warn when too few bars carry volume — the volume gate would be dead."""
        if df.empty or "Volume" not in df.columns:
            return
        nonzero = float((df["Volume"] > 0).mean())
        if nonzero < settings.MIN_NONZERO_VOLUME_FRACTION:
            logger.warning(
                "%s %s: only %.0f%% of bars have nonzero volume (expected >= %.0f%%). "
                "The volume gate will rarely or never fire. Stale cache or failed "
                "futures-volume merge? Re-fetch with force_refresh=True.",
                pair, timeframe, nonzero * 100,
                settings.MIN_NONZERO_VOLUME_FRACTION * 100,
            )

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def _validate(self, pair: str, timeframe: str) -> None:
        if pair not in self.pairs:
            raise ValueError(
                f"Unknown pair {pair!r}. Configured pairs: {list(self.pairs)}"
            )
        if timeframe not in settings.TIMEFRAME_FETCH:
            raise ValueError(
                f"Unknown timeframe {timeframe!r}. "
                f"Configured: {list(settings.TIMEFRAME_FETCH)}"
            )
