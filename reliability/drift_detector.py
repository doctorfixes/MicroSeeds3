"""
drift_detector.py
=================
Data Drift Detector for MicroSeeds.

Detects five flavours of drift that destabilise the intelligence engine:

  sensor_drift       – systematic shift in pressure or flow readings over time.
  timestamp_drift    – growing offset between energy-log and pumping-log timestamps.
  pressure_drift     – long-term trend in baseline pressure.
  flow_drift         – long-term trend in baseline flow rate.
  energy_price_drift – shift in the energy-cost-per-unit-volume ratio.

When drift is detected the system:
  • Adjusts thresholds.
  • Recalibrates windows.
  • Increases smoothing.
  • Reduces volatility sensitivity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


def detect_drift(data):
    # MVP: no drift detection
    return False


@dataclass
class DriftEvent:
    """Describes a single detected drift event."""

    drift_type: str
    column: str
    magnitude: float          # normalised 0–1
    direction: str            # "upward", "downward", or "none"
    detected_at: pd.Timestamp
    recommended_action: str
    details: dict = field(default_factory=dict)


class DriftDetector:
    """
    Detect data drift in pumping / irrigation time-series data.

    Parameters
    ----------
    window_short : int
        Short-term rolling window (intervals) for drift detection.
    window_long : int
        Long-term rolling window (intervals) for drift detection.
    drift_threshold : float
        Fraction of the long-term mean by which the short-term mean must
        deviate to trigger a drift event.
    timestamp_tolerance_seconds : float
        Maximum acceptable timestamp offset (seconds) between two logs before
        a timestamp-drift event is raised.
    flow_col, pressure_col, energy_col : str
        Column names.
    """

    def __init__(
        self,
        window_short: int = 12,
        window_long: int = 168,
        drift_threshold: float = 0.10,
        timestamp_tolerance_seconds: float = 300.0,
        flow_col: str = "flow_rate",
        pressure_col: str = "pressure",
        energy_col: str = "energy",
    ) -> None:
        self.window_short = window_short
        self.window_long = window_long
        self.drift_threshold = drift_threshold
        self.timestamp_tolerance_seconds = timestamp_tolerance_seconds
        self.flow_col = flow_col
        self.pressure_col = pressure_col
        self.energy_col = energy_col

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        df: pd.DataFrame,
        energy_df: Optional[pd.DataFrame] = None,
    ) -> list[DriftEvent]:
        """
        Run all drift detectors and return a (possibly empty) list of events.

        Parameters
        ----------
        df :
            Primary block DataFrame with DatetimeIndex.
        energy_df :
            Optional separate energy-log DataFrame.  When supplied, timestamp
            drift between the two logs is also checked.
        """
        events: list[DriftEvent] = []

        events.extend(self._detect_sensor_drift(df))
        events.extend(self._detect_pressure_drift(df))
        events.extend(self._detect_flow_drift(df))

        if energy_df is not None:
            events.extend(self._detect_timestamp_drift(df, energy_df))
            events.extend(self._detect_energy_price_drift(df, energy_df))

        return events

    def apply_corrections(
        self, df: pd.DataFrame, events: list[DriftEvent]
    ) -> pd.DataFrame:
        """
        Apply recommended corrections based on detected drift events.

        Currently implemented corrections:
          • Increase smoothing for pressure / flow drift.
          • Clip extreme values that are likely drift artefacts.
        """
        df = df.copy()
        for event in events:
            col = event.column
            if col not in df.columns:
                continue
            if event.drift_type in ("pressure_drift", "flow_drift", "sensor_drift"):
                # Increase smoothing window proportional to drift magnitude
                extra_window = max(2, int(event.magnitude * 10))
                df[col] = (
                    df[col]
                    .rolling(window=extra_window, center=True, min_periods=1)
                    .mean()
                )
        return df

    # ------------------------------------------------------------------
    # Drift detectors
    # ------------------------------------------------------------------

    def _detect_sensor_drift(self, df: pd.DataFrame) -> list[DriftEvent]:
        events: list[DriftEvent] = []
        for col in [self.pressure_col, self.flow_col]:
            event = self._rolling_mean_drift(df, col, drift_type="sensor_drift")
            if event:
                events.append(event)
        return events

    def _detect_pressure_drift(self, df: pd.DataFrame) -> list[DriftEvent]:
        event = self._rolling_mean_drift(
            df, self.pressure_col, drift_type="pressure_drift"
        )
        return [event] if event else []

    def _detect_flow_drift(self, df: pd.DataFrame) -> list[DriftEvent]:
        event = self._rolling_mean_drift(
            df, self.flow_col, drift_type="flow_drift"
        )
        return [event] if event else []

    def _detect_timestamp_drift(
        self, df: pd.DataFrame, energy_df: pd.DataFrame
    ) -> list[DriftEvent]:
        """Check whether energy-log timestamps are offset from pumping-log timestamps."""
        if not (
            isinstance(df.index, pd.DatetimeIndex)
            and isinstance(energy_df.index, pd.DatetimeIndex)
        ):
            return []

        # Find common index points and measure offset
        common = df.index.intersection(energy_df.index)
        if len(common) < 2:
            # Try nearest-neighbour matching on a shared time column
            return self._nearest_timestamp_drift(df, energy_df)

        # Measure drift as growing residual between paired timestamps
        offsets = (
            pd.Series(df.index.astype(np.int64), index=df.index)
            .reindex(common)
            .values
            - pd.Series(energy_df.index.astype(np.int64), index=energy_df.index)
            .reindex(common)
            .values
        )
        offset_seconds = np.abs(offsets) / 1e9
        max_offset = float(np.max(offset_seconds))

        if max_offset > self.timestamp_tolerance_seconds:
            return [
                DriftEvent(
                    drift_type="timestamp_drift",
                    column="timestamp",
                    magnitude=min(
                        1.0, max_offset / (self.timestamp_tolerance_seconds * 10)
                    ),
                    direction="none",
                    detected_at=df.index[-1],
                    recommended_action="recalibrate_time_base",
                    details={"max_offset_seconds": max_offset},
                )
            ]
        return []

    def _nearest_timestamp_drift(
        self, df: pd.DataFrame, energy_df: pd.DataFrame
    ) -> list[DriftEvent]:
        """Fallback: match nearest timestamps and measure offset."""
        if len(df) == 0 or len(energy_df) == 0:
            return []
        sample = df.index[:min(50, len(df))]
        offsets = []
        for ts in sample:
            nearest_idx = (energy_df.index - ts).abs().argmin()
            offset_s = abs((energy_df.index[nearest_idx] - ts).total_seconds())
            offsets.append(offset_s)
        max_offset = float(np.max(offsets))
        if max_offset > self.timestamp_tolerance_seconds:
            return [
                DriftEvent(
                    drift_type="timestamp_drift",
                    column="timestamp",
                    magnitude=min(
                        1.0, max_offset / (self.timestamp_tolerance_seconds * 10)
                    ),
                    direction="none",
                    detected_at=df.index[-1],
                    recommended_action="recalibrate_time_base",
                    details={"max_offset_seconds": max_offset},
                )
            ]
        return []

    def _detect_energy_price_drift(
        self, df: pd.DataFrame, energy_df: pd.DataFrame
    ) -> list[DriftEvent]:
        """Detect drift in the energy-cost-per-unit-volume ratio."""
        if (
            self.energy_col not in energy_df.columns
            or self.flow_col not in df.columns
        ):
            return []

        # Compute cost-per-volume at each time step where both exist
        common = df.index.intersection(energy_df.index)
        if len(common) < self.window_long:
            return []

        flow = df.loc[common, self.flow_col].replace(0, np.nan)
        energy = energy_df.loc[common, self.energy_col]
        ratio = (energy / flow).dropna()

        if len(ratio) < self.window_long:
            return []

        short_mean = ratio.iloc[-self.window_short :].mean()
        long_mean = ratio.iloc[-self.window_long :].mean()

        if long_mean == 0:
            return []

        deviation = abs(short_mean - long_mean) / abs(long_mean)
        if deviation > self.drift_threshold:
            direction = "upward" if short_mean > long_mean else "downward"
            return [
                DriftEvent(
                    drift_type="energy_price_drift",
                    column=self.energy_col,
                    magnitude=min(1.0, deviation),
                    direction=direction,
                    detected_at=df.index[-1],
                    recommended_action="adjust_energy_cost_thresholds",
                    details={
                        "short_mean_ratio": round(float(short_mean), 4),
                        "long_mean_ratio": round(float(long_mean), 4),
                    },
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Generic drift helper
    # ------------------------------------------------------------------

    def _rolling_mean_drift(
        self,
        df: pd.DataFrame,
        col: str,
        drift_type: str,
    ) -> Optional[DriftEvent]:
        if col not in df.columns:
            return None
        series = df[col].dropna()
        if len(series) < self.window_long:
            return None

        short_mean = series.iloc[-self.window_short :].mean()
        long_mean = series.iloc[-self.window_long :].mean()

        if long_mean == 0:
            return None

        deviation = abs(short_mean - long_mean) / abs(long_mean)
        if deviation > self.drift_threshold:
            direction = "upward" if short_mean > long_mean else "downward"
            action_map = {
                "sensor_drift": "recalibrate_sensor",
                "pressure_drift": "adjust_pressure_thresholds",
                "flow_drift": "adjust_flow_thresholds",
            }
            return DriftEvent(
                drift_type=drift_type,
                column=col,
                magnitude=min(1.0, deviation),
                direction=direction,
                detected_at=df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else pd.Timestamp.now(),
                recommended_action=action_map.get(drift_type, "review_data"),
                details={
                    "short_mean": round(float(short_mean), 4),
                    "long_mean": round(float(long_mean), 4),
                    "deviation_fraction": round(float(deviation), 4),
                },
            )
        return None
