"""
cleaner.py
==========
Data cleaning for MicroSeeds.

MVP entry point: clean_data(data) – returns data unchanged.
Full implementation: CleaningPipeline – three-layer data cleaning pipeline
for pumping / irrigation time-series data.

Layer 1 — Structural Cleaning
  • Fill missing timestamps to a uniform time grid.
  • Align logs to a unified time base (forward-fill then linear interpolation).
  • Remove physically impossible values (replace with NaN).
  • Flag rows that appear to have been manually edited.

Layer 2 — Behavioural Cleaning
  • Detect and remove pump warm-up periods (first N minutes after start).
  • Remove pressure spikes via rolling-median deviation.
  • Smooth flow anomalies with an adaptive rolling window.

Layer 3 — Model-Aware Cleaning
  • Use the system's stability model to detect impossible patterns.
  • Cross-validate against evapotranspiration (ET) and timing windows.
  • Reject data that contradicts physical reality.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_FREQ: str = "1h"
WARMUP_PERIODS: int = 3          # number of intervals after pump start to drop
PRESSURE_SPIKE_WINDOW: int = 5   # rolling window for spike detection (intervals)
PRESSURE_SPIKE_THRESHOLD: float = 3.0  # ×MAD to classify as spike
FLOW_SMOOTH_WINDOW: int = 3      # rolling window for flow smoothing


def clean_data(data):
    # MVP: return data unchanged
    return data


class CleaningPipeline:
    """
    Apply three sequential cleaning layers to a block DataFrame.

    Parameters
    ----------
    expected_freq : str
        Expected pandas offset alias for the time series (e.g. ``"1h"``).
    flow_col, pressure_col, energy_col : str
        Column names.
    flow_bounds, pressure_bounds, energy_bounds : tuple[float, float]
        ``(min, max)`` plausible physical values.  Readings outside these
        are replaced with NaN in Layer 1.
    warmup_periods : int
        Number of intervals to treat as pump warm-up and remove.
    pressure_spike_window : int
        Rolling window size (number of rows) for pressure-spike detection.
    pressure_spike_threshold : float
        How many median-absolute-deviations above the rolling median counts
        as a spike.
    flow_smooth_window : int
        Rolling window for flow smoothing.
    et_window : tuple[int, int] | None
        ``(start_hour, end_hour)`` valid ET irrigation window.  Readings
        outside this window are flagged in Layer 3.
    """

    def __init__(
        self,
        expected_freq: str = DEFAULT_FREQ,
        flow_col: str = "flow_rate",
        pressure_col: str = "pressure",
        energy_col: str = "energy",
        flow_bounds: tuple[float, float] = (0.0, 500.0),
        pressure_bounds: tuple[float, float] = (0.0, 20.0),
        energy_bounds: tuple[float, float] = (0.0, 1_000.0),
        warmup_periods: int = WARMUP_PERIODS,
        pressure_spike_window: int = PRESSURE_SPIKE_WINDOW,
        pressure_spike_threshold: float = PRESSURE_SPIKE_THRESHOLD,
        flow_smooth_window: int = FLOW_SMOOTH_WINDOW,
        et_window: Optional[tuple[int, int]] = None,
    ) -> None:
        self.expected_freq = expected_freq
        self.flow_col = flow_col
        self.pressure_col = pressure_col
        self.energy_col = energy_col
        self.flow_bounds = flow_bounds
        self.pressure_bounds = pressure_bounds
        self.energy_bounds = energy_bounds
        self.warmup_periods = warmup_periods
        self.pressure_spike_window = pressure_spike_window
        self.pressure_spike_threshold = pressure_spike_threshold
        self.flow_smooth_window = flow_smooth_window
        self.et_window = et_window

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run all three cleaning layers and return the cleaned DataFrame.

        A ``_layer`` column is added to show which layer last touched each row.
        A ``_manual_edit`` boolean column flags suspected manual edits.
        """
        if df.empty:
            return df.copy()

        df = self._layer1_structural(df)
        df = self._layer2_behavioural(df)
        df = self._layer3_model_aware(df)
        return df

    # ------------------------------------------------------------------
    # Layer 1 — Structural Cleaning
    # ------------------------------------------------------------------

    def _layer1_structural(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 1a. Ensure DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            raise TypeError("DataFrame must have a DatetimeIndex.")

        # 1b. Fill missing timestamps (reindex to uniform grid)
        full_range = pd.date_range(
            start=df.index.min(),
            end=df.index.max(),
            freq=self.expected_freq,
        )
        df = df.reindex(full_range)

        # 1c. Align / interpolate numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        df[numeric_cols] = (
            df[numeric_cols]
            .interpolate(method="time")
            .ffill()
            .bfill()
        )

        # 1d. Remove impossible values
        for col, bounds in [
            (self.flow_col, self.flow_bounds),
            (self.pressure_col, self.pressure_bounds),
            (self.energy_col, self.energy_bounds),
        ]:
            if col in df.columns:
                mask = (df[col] < bounds[0]) | (df[col] > bounds[1])
                df.loc[mask, col] = np.nan

        # 1e. Detect manual edits (round numbers with suspicious regularity)
        df["_manual_edit"] = False
        for col in [self.flow_col, self.pressure_col]:
            if col in df.columns:
                series = df[col].dropna()
                if len(series) == 0:
                    continue
                # Heuristic: more than 30 % of values are exact integers → flagged
                round_frac = (series == series.round(0)).sum() / len(series)
                if round_frac > 0.30:
                    df["_manual_edit"] = True

        df["_layer"] = "structural"
        return df

    # ------------------------------------------------------------------
    # Layer 2 — Behavioural Cleaning
    # ------------------------------------------------------------------

    def _layer2_behavioural(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 2a. Detect pump warm-up: flow transitions from 0 → non-zero
        if self.flow_col in df.columns:
            flow = df[self.flow_col].fillna(0)
            pump_start = (flow > 0) & (flow.shift(1) == 0)
            warmup_mask = pd.Series(False, index=df.index)
            for start_idx in df.index[pump_start]:
                loc = df.index.get_loc(start_idx)
                end_loc = min(loc + self.warmup_periods, len(df))
                warmup_mask.iloc[loc:end_loc] = True
            df.loc[warmup_mask, self.flow_col] = np.nan

        # 2b. Remove pressure spikes via rolling-median MAD
        if self.pressure_col in df.columns:
            pressure = df[self.pressure_col].copy()
            rolling_med = pressure.rolling(
                window=self.pressure_spike_window, center=True, min_periods=1
            ).median()
            deviation = (pressure - rolling_med).abs()
            mad = deviation.rolling(
                window=self.pressure_spike_window, center=True, min_periods=1
            ).median()
            spike_mask = deviation > self.pressure_spike_threshold * (mad + 1e-9)
            df.loc[spike_mask, self.pressure_col] = np.nan

        # 2c. Smooth flow anomalies with a rolling mean
        if self.flow_col in df.columns:
            df[self.flow_col] = (
                df[self.flow_col]
                .rolling(
                    window=self.flow_smooth_window, center=True, min_periods=1
                )
                .mean()
            )

        df["_layer"] = "behavioural"
        return df

    # ------------------------------------------------------------------
    # Layer 3 — Model-Aware Cleaning
    # ------------------------------------------------------------------

    def _layer3_model_aware(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 3a. Reject data where flow is non-zero but pressure is zero (impossible)
        if self.flow_col in df.columns and self.pressure_col in df.columns:
            impossible = (df[self.flow_col].fillna(0) > 0) & (
                df[self.pressure_col].fillna(0) <= 0
            )
            df.loc[impossible, [self.flow_col, self.pressure_col]] = np.nan

        # 3b. Cross-validate against ET timing window
        if self.et_window is not None and isinstance(df.index, pd.DatetimeIndex):
            start_h, end_h = self.et_window
            outside_window = ~df.index.hour.isin(range(start_h, end_h + 1))
            # Flag (do not delete) — irrigation outside ET window is suspicious
            df["_outside_et_window"] = outside_window
        else:
            df["_outside_et_window"] = False

        # 3c. Detect salinity-risk heuristic: low flow + high pressure
        if self.flow_col in df.columns and self.pressure_col in df.columns:
            flow_low = df[self.flow_col].fillna(0) < (
                df[self.flow_col].quantile(0.10) + 1e-9
            )
            pressure_high = df[self.pressure_col].fillna(0) > (
                df[self.pressure_col].quantile(0.90) - 1e-9
            )
            df["_salinity_risk"] = flow_low & pressure_high
        else:
            df["_salinity_risk"] = False

        df["_layer"] = "model_aware"
        return df
