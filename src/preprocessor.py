"""Preprocessor — Module 2 (README §10 step 2).

Takes clean OHLCV from the DataHandler and produces the model-ready feature
matrix, labels, and the chronological train/test split.

Two directions must be kept straight to avoid data leakage (README §5):

* **Z-Score features look BACKWARD.** The rolling mean/std at row *t* use only
  rows up to and including *t* (`pandas.rolling` is inherently trailing). No
  future information enters a feature.
* **The label looks FORWARD.** Class 1 (bullish continuation) is defined by
  ``LABEL_METHOD``: "triple_barrier" (default — long-side take-profit hit before
  stop-loss within ``TRIPLE_BARRIER_MAX_HOLD`` bars) or "next_candle" (Close rises
  over the next ``LABEL_HORIZON`` candle(s)). This is the target, never an input
  feature — so the model never sees the future it's asked to predict.

The split is strictly **chronological with no shuffling** (README §5/§6): the
first ``TRAIN_TEST_SPLIT_RATIO`` of rows (by time) are training, the rest are
the hold-out test set. Shuffling a time-series would train on the future.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import settings
from src.risk_manager import dynamic_stop_pct

logger = logging.getLogger(__name__)


class Preprocessor:
    """Feature engineering + labelling + chronological split."""

    def __init__(
        self,
        zscore_window: int | None = None,
        feature_columns: list[str] | None = None,
        label_horizon: int | None = None,
        split_ratio: float | None = None,
        label_method: str | None = None,
        tp_pct: float | None = None,
        sl_pct: float | None = None,
        max_hold: int | None = None,
        label_dynamic_sl: bool | None = None,
    ) -> None:
        self.zscore_window = (
            zscore_window if zscore_window is not None else settings.ZSCORE_WINDOW
        )
        self.feature_columns = (
            feature_columns
            if feature_columns is not None
            else list(settings.FEATURE_COLUMNS)
        )
        self.label_horizon = (
            label_horizon if label_horizon is not None else settings.LABEL_HORIZON
        )
        self.split_ratio = (
            split_ratio if split_ratio is not None else settings.TRAIN_TEST_SPLIT_RATIO
        )
        # Label method + triple-barrier params (TP/SL reuse the risk config so
        # labels match the trades the RiskManager will actually take).
        self.label_method = (
            label_method if label_method is not None else settings.LABEL_METHOD
        )
        self.tp_pct = tp_pct if tp_pct is not None else settings.DEFAULT_TAKE_PROFIT_PCT
        self.sl_pct = sl_pct if sl_pct is not None else settings.DEFAULT_STOP_LOSS_PCT
        self.max_hold = (
            max_hold if max_hold is not None else settings.TRIPLE_BARRIER_MAX_HOLD
        )
        self.label_dynamic_sl = (
            label_dynamic_sl if label_dynamic_sl is not None
            else settings.LABEL_DYNAMIC_SL
        )
        if not 0.0 < self.split_ratio < 1.0:
            raise ValueError("split_ratio must be in (0, 1)")
        if self.label_method not in ("next_candle", "triple_barrier"):
            raise ValueError(
                f"label_method must be 'next_candle' or 'triple_barrier', "
                f"got {self.label_method!r}"
            )

    # ------------------------------------------------------------------ #
    # Z-Score features (trailing/backward-looking)
    # ------------------------------------------------------------------ #
    def add_zscores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Append rolling (trailing) Z-Scores for Close and Volume.

        Z = (x - rolling_mean) / rolling_std, computed over a trailing window
        of ``zscore_window`` rows. Uses sample std (ddof=1) and guards against
        divide-by-zero (flat windows -> Z of 0).
        """
        out = df.copy()
        out["ZScore_Close"] = self._rolling_zscore(out["Close"])
        out["ZScore_Volume"] = self._rolling_zscore(out["Volume"])
        return out

    def _rolling_zscore(self, series: pd.Series) -> pd.Series:
        window = self.zscore_window
        roll = series.rolling(window=window, min_periods=window)
        mean = roll.mean()
        std = roll.std(ddof=1)
        z = (series - mean) / std
        # Flat window -> std 0 -> inf/nan; treat as "no deviation".
        z = z.replace([np.inf, -np.inf], np.nan)
        z = z.where(std != 0, 0.0)
        return z

    # ------------------------------------------------------------------ #
    # Technical indicators (all strictly backward-looking — no leakage)
    # ------------------------------------------------------------------ #
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Append the enabled technical-indicator features (config-toggled)."""
        out = df.copy()
        if settings.USE_RSI:
            out["RSI"] = self._rsi(out["Close"], settings.RSI_PERIOD)
        if settings.USE_MACD:
            macd, signal, hist = self._macd(
                out["Close"], settings.MACD_FAST, settings.MACD_SLOW,
                settings.MACD_SIGNAL,
            )
            out["MACD"] = macd
            out["MACD_Signal"] = signal
            out["MACD_Hist"] = hist
        if settings.USE_ATR:
            out["ATR"] = self._atr(
                out["High"], out["Low"], out["Close"], settings.ATR_PERIOD
            )
        if settings.USE_HTF_TREND:
            dist, up = self._htf_trend(out["Close"], settings.HTF_TREND_WINDOW)
            out["TrendDist"] = dist
            out["TrendUp"] = up
        if settings.USE_TIME_FEATURES:
            # Hours in UTC — the session window below is defined in UTC.
            idx = out.index
            hour = (idx.tz_convert("UTC") if idx.tz is not None else idx).hour
            # Cyclical encoding so 23:00 and 00:00 are "close".
            out["HourSin"] = np.sin(2 * np.pi * hour / 24)
            out["HourCos"] = np.cos(2 * np.pi * hour / 24)
            # London/NY overlap (~12:00–16:00 UTC) — the most active FX window.
            out["SessionOverlap"] = ((hour >= 12) & (hour < 16)).astype("float")
        return out

    @staticmethod
    def _htf_trend(close: pd.Series, window: int):
        """Higher-timeframe trend context from a long moving average (trailing).

        TrendDist = (close − MA) / MA  (how far above/below the long trend, signed)
        TrendUp   = 1.0 if close > MA else 0.0
        The rolling mean uses only past closes, so no lookahead.
        """
        ma = close.rolling(window=window, min_periods=window).mean()
        dist = (close - ma) / ma
        up = (close > ma).astype("float")
        # Where MA is undefined (first window-1 rows), leave dist NaN and up NaN.
        up = up.where(ma.notna(), np.nan)
        return dist, up

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        """Average True Range (volatility), Wilder's smoothing — trailing only.

        True Range = max(high−low, |high−prev_close|, |low−prev_close|).
        ATR = Wilder EMA of TR over ``period``. Uses prev close (a backward shift),
        so no lookahead.
        """
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    @staticmethod
    def _macd(close: pd.Series, fast: int, slow: int, signal: int):
        """MACD line, signal line, histogram (all from trailing EMAs — no leakage).

        MACD line   = EMA(fast) − EMA(slow)
        signal line = EMA(MACD line, signal)
        histogram   = MACD line − signal line
        EMAs are causal (only past data), so no lookahead.
        """
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        """Relative Strength Index (0–100), Wilder's smoothing.

        RSI = 100 − 100 / (1 + RS), where RS = avg gain / avg loss over a trailing
        window. Uses only past closes (the diff and EWM are causal), so no lookahead.
        A flat/zero-loss window -> RSI 100 (or 50 if no movement at all).
        """
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        # Wilder's smoothing = EMA with alpha = 1/period (trailing).
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        # avg_loss == 0 -> rs inf -> rsi 100; both 0 (flat) -> define as neutral 50.
        rsi = rsi.where(avg_loss != 0, 100.0)
        rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
        return rsi

    # ------------------------------------------------------------------ #
    # Labelling (forward-looking target)
    # ------------------------------------------------------------------ #
    def add_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Append the binary target ``Target`` using the configured method."""
        if self.label_method == "triple_barrier":
            return self.add_triple_barrier_labels(df)
        return self.add_next_candle_labels(df)

    def add_next_candle_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Class 1 if Close ``LABEL_HORIZON`` candles ahead is strictly higher.

        The simple original label. Final ``LABEL_HORIZON`` rows have no future and
        are NaN (dropped in :meth:`transform`).
        """
        out = df.copy()
        future_close = out["Close"].shift(-self.label_horizon)
        out["Target"] = (future_close > out["Close"]).astype("float")
        out.loc[future_close.isna(), "Target"] = np.nan
        return out

    def add_triple_barrier_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Class 1 if take-profit is hit BEFORE stop-loss within ``max_hold`` bars.

        For each candle, place an upper barrier (TP) and lower barrier (SL) a fixed
        % from that candle's Close, then walk forward up to ``max_hold`` candles
        (the vertical barrier) and see which is touched first, using each future
        candle's High/Low:
          * TP touched first  -> 1 (win)
          * SL touched first  -> 0 (loss)
          * neither in window -> label by where Close ended vs entry (1 if up else 0)

        This is the long/BUY-side label (the strategy's bullish setup). Features
        stay backward-looking; only the label looks forward (see
        docs/TRIPLE_BARRIER_EXPLAINED.md). Rows without a full forward window are
        NaN and dropped in :meth:`transform`.

        With ``label_dynamic_sl`` on, each candle's stop distance applies the
        RiskManager's dynamic-tightening rule to that candle's (trailing) Volume
        Z-Score, so the labelled stop matches the stop a trade there would get.
        """
        out = df.copy()
        close = out["Close"].to_numpy()
        high = out["High"].to_numpy()
        low = out["Low"].to_numpy()
        n = len(out)
        labels = np.full(n, np.nan)

        # Volatility-scaled barriers (ATR) when enabled, else flat %. Using each
        # candle's OWN ATR (trailing) keeps the label backward-looking for distance.
        use_atr_stops = settings.USE_ATR_STOPS and "ATR" in out.columns
        atr = out["ATR"].to_numpy() if use_atr_stops else None

        vol_z = None
        if self.label_dynamic_sl:
            if "ZScore_Volume" not in out.columns:
                raise KeyError(
                    "label_dynamic_sl needs ZScore_Volume — call add_zscores() first"
                )
            vol_z = out["ZScore_Volume"].to_numpy()

        for i in range(n):
            # Need at least one future bar to resolve a barrier.
            if i + 1 >= n:
                break
            entry = close[i]
            if use_atr_stops and not np.isnan(atr[i]):
                tp = entry + atr[i] * settings.ATR_TP_MULTIPLE
                sl = entry - atr[i] * settings.ATR_SL_MULTIPLE
            else:
                sl_pct = self.sl_pct
                if vol_z is not None and not np.isnan(vol_z[i]):
                    sl_pct = dynamic_stop_pct(
                        self.sl_pct, vol_z[i],
                        settings.DYNAMIC_SL_ZSCORE_TRIGGER,
                        settings.DYNAMIC_SL_TIGHTEN_FACTOR,
                    )
                tp = entry * (1 + self.tp_pct)
                sl = entry * (1 - sl_pct)
            end = min(i + self.max_hold, n - 1)

            outcome = None
            for j in range(i + 1, end + 1):
                hit_tp = high[j] >= tp
                hit_sl = low[j] <= sl
                if hit_tp and hit_sl:
                    # Both in the same bar -> conservative: assume SL first (loss).
                    outcome = 0.0
                    break
                if hit_tp:
                    outcome = 1.0
                    break
                if hit_sl:
                    outcome = 0.0
                    break
            if outcome is None:
                # Vertical barrier: neither hit -> label by final close vs entry.
                outcome = 1.0 if close[end] > entry else 0.0
            labels[i] = outcome

        out["Target"] = labels
        return out

    # ------------------------------------------------------------------ #
    # Full transform
    # ------------------------------------------------------------------ #
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean -> add Z-Scores -> add labels -> drop unusable rows.

        Drops the leading rows that have no full Z-Score window and the trailing
        rows that have no label horizon, then drops any residual NaNs. Returns a
        frame containing the feature columns plus ``Target``, time-ordered.
        """
        if df.empty:
            return df.copy()

        work = df.sort_index()
        work = self.add_zscores(work)
        work = self.add_indicators(work)
        work = self.add_labels(work)

        needed = self.feature_columns + ["Target"]
        missing = [c for c in needed if c not in work.columns]
        if missing:
            raise KeyError(f"Missing required columns after transform: {missing}")

        before = len(work)
        work = work.dropna(subset=needed)
        logger.info(
            "Preprocessed %d -> %d rows (dropped %d for Z-window/label horizon)",
            before,
            len(work),
            before - len(work),
        )
        return work

    # ------------------------------------------------------------------ #
    # Feature/label extraction
    # ------------------------------------------------------------------ #
    def features_and_labels(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Split a transformed frame into (X features, y target)."""
        X = df[self.feature_columns].copy()
        y = df["Target"].astype(int).copy()
        return X, y

    # ------------------------------------------------------------------ #
    # Chronological split (NO shuffling — README §5/§6)
    # ------------------------------------------------------------------ #
    def chronological_split(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Split a (time-ordered) frame into (train, test) by time.

        First ``split_ratio`` of rows -> train; remainder -> test. No shuffling.
        The split index is computed by position on the time-sorted frame, so
        every training timestamp precedes every test timestamp.
        """
        if df.empty:
            return df.copy(), df.copy()

        ordered = df.sort_index()
        split_idx = int(len(ordered) * self.split_ratio)
        # Guarantee at least one row on each side when possible.
        split_idx = max(1, min(split_idx, len(ordered) - 1))

        train = ordered.iloc[:split_idx]
        test = ordered.iloc[split_idx:]

        logger.info(
            "Chronological split: %d train (%s -> %s) | %d test (%s -> %s)",
            len(train),
            train.index.min(),
            train.index.max(),
            len(test),
            test.index.min(),
            test.index.max(),
        )
        return train, test

    def prepare(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
        """End-to-end: transform, chronological split, return X/y for each side.

        Returns ``(X_train, y_train, X_test, y_test)``. The split is done on the
        fully-transformed frame so train and test share the same feature schema,
        with every train timestamp strictly before every test timestamp.
        """
        transformed = self.transform(df)
        train_df, test_df = self.chronological_split(transformed)
        X_train, y_train = self.features_and_labels(train_df)
        X_test, y_test = self.features_and_labels(test_df)
        return X_train, y_train, X_test, y_test
