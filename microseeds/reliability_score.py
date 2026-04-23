"""
reliability_score.py
====================
Computes a Data Reliability Score (0–100) for each pumping/irrigation block.

Score components (each 0–100, then weighted):

  completeness        – fraction of expected timestamps that are present.
  consistency         – fraction of readings within physically plausible ranges.
  timestamp_alignment – how tightly energy logs and pumping logs share a time base.
  noise_level         – inverse of normalised standard deviation of residuals.
  anomaly_frequency   – inverse of the fraction of anomalous readings detected.

Thresholds
----------
  score < 60   → block receives special handling (fallback mode).
  score > 80   → block is a high-confidence input to the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Plausibility bounds (domain defaults – override via ReliabilityScorer kwargs)
# ---------------------------------------------------------------------------
DEFAULT_FLOW_MIN: float = 0.0       # m³/h
DEFAULT_FLOW_MAX: float = 500.0     # m³/h
DEFAULT_PRESSURE_MIN: float = 0.0   # bar
DEFAULT_PRESSURE_MAX: float = 20.0  # bar
DEFAULT_ENERGY_MIN: float = 0.0     # kWh
DEFAULT_ENERGY_MAX: float = 1_000.0 # kWh per interval

# Score thresholds
THRESHOLD_LOW: int = 60   # below this → fallback mode
THRESHOLD_HIGH: int = 80  # above this → high-confidence input


@dataclass
class BlockScore:
    """Individual dimension scores and the composite reliability score."""

    block_id: str
    completeness: float = 0.0
    consistency: float = 0.0
    timestamp_alignment: float = 0.0
    noise_level: float = 0.0
    anomaly_frequency: float = 0.0
    composite: float = 0.0
    confidence: str = "low"
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.composite >= THRESHOLD_HIGH:
            self.confidence = "high"
        elif self.composite >= THRESHOLD_LOW:
            self.confidence = "medium"
        else:
            self.confidence = "low"


class ReliabilityScorer:
    """
    Compute a Data Reliability Score for a block DataFrame.

    Parameters
    ----------
    expected_freq : str
        Expected pandas offset alias for the time series (e.g. ``"1h"``).
    flow_col : str
        Column name for flow-rate readings.
    pressure_col : str
        Column name for pressure readings.
    energy_col : str
        Column name for energy readings.
    flow_bounds : tuple[float, float]
        ``(min, max)`` plausible flow values.
    pressure_bounds : tuple[float, float]
        ``(min, max)`` plausible pressure values.
    energy_bounds : tuple[float, float]
        ``(min, max)`` plausible energy values.
    weights : dict[str, float]
        Relative weights for the five score dimensions.  They are
        normalised internally so they need not sum to 1.
    """

    # Default dimension weights
    DEFAULT_WEIGHTS: dict[str, float] = {
        "completeness": 0.30,
        "consistency": 0.25,
        "timestamp_alignment": 0.15,
        "noise_level": 0.15,
        "anomaly_frequency": 0.15,
    }

    def __init__(
        self,
        expected_freq: str = "1h",
        flow_col: str = "flow_rate",
        pressure_col: str = "pressure",
        energy_col: str = "energy",
        flow_bounds: tuple[float, float] = (DEFAULT_FLOW_MIN, DEFAULT_FLOW_MAX),
        pressure_bounds: tuple[float, float] = (
            DEFAULT_PRESSURE_MIN,
            DEFAULT_PRESSURE_MAX,
        ),
        energy_bounds: tuple[float, float] = (DEFAULT_ENERGY_MIN, DEFAULT_ENERGY_MAX),
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.expected_freq = expected_freq
        self.flow_col = flow_col
        self.pressure_col = pressure_col
        self.energy_col = energy_col
        self.flow_bounds = flow_bounds
        self.pressure_bounds = pressure_bounds
        self.energy_bounds = energy_bounds
        self._weights = self._normalise_weights(weights or self.DEFAULT_WEIGHTS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, block_id: str, df: pd.DataFrame) -> BlockScore:
        """Return a :class:`BlockScore` for *df*.

        Parameters
        ----------
        block_id :
            Human-readable identifier for the block (e.g. ``"Block-A3"``).
        df :
            DataFrame with a :class:`~pandas.DatetimeIndex` and at least one
            of ``flow_rate``, ``pressure``, or ``energy`` columns.
        """
        if df.empty:
            return BlockScore(block_id=block_id, details={"error": "empty dataframe"})

        completeness = self._completeness(df)
        consistency = self._consistency(df)
        ts_alignment = self._timestamp_alignment(df)
        noise = self._noise_level(df)
        anomaly = self._anomaly_frequency(df)

        composite = round(
            completeness * self._weights["completeness"]
            + consistency * self._weights["consistency"]
            + ts_alignment * self._weights["timestamp_alignment"]
            + noise * self._weights["noise_level"]
            + anomaly * self._weights["anomaly_frequency"],
            2,
        )
        composite = float(np.clip(composite, 0.0, 100.0))

        return BlockScore(
            block_id=block_id,
            completeness=round(completeness, 2),
            consistency=round(consistency, 2),
            timestamp_alignment=round(ts_alignment, 2),
            noise_level=round(noise, 2),
            anomaly_frequency=round(anomaly, 2),
            composite=composite,
            details={
                "expected_freq": self.expected_freq,
                "n_rows": len(df),
            },
        )

    def score_many(
        self, blocks: dict[str, pd.DataFrame]
    ) -> dict[str, BlockScore]:
        """Score multiple blocks at once."""
        return {bid: self.score(bid, df) for bid, df in blocks.items()}

    # ------------------------------------------------------------------
    # Dimension helpers
    # ------------------------------------------------------------------

    def _completeness(self, df: pd.DataFrame) -> float:
        """Fraction of expected timestamps that exist (0–100)."""
        if not isinstance(df.index, pd.DatetimeIndex) or len(df) < 2:
            return 0.0
        full_range = pd.date_range(
            start=df.index.min(),
            end=df.index.max(),
            freq=self.expected_freq,
        )
        if len(full_range) == 0:
            return 100.0
        present = df.index.isin(full_range).sum()
        return float(present / len(full_range) * 100)

    def _consistency(self, df: pd.DataFrame) -> float:
        """Fraction of readings within physically plausible bounds (0–100)."""
        valid_counts: list[float] = []

        for col, bounds in [
            (self.flow_col, self.flow_bounds),
            (self.pressure_col, self.pressure_bounds),
            (self.energy_col, self.energy_bounds),
        ]:
            if col in df.columns:
                series = df[col].dropna()
                if len(series) == 0:
                    continue
                in_range = ((series >= bounds[0]) & (series <= bounds[1])).sum()
                valid_counts.append(float(in_range / len(series) * 100))

        return float(np.mean(valid_counts)) if valid_counts else 100.0

    def _timestamp_alignment(self, df: pd.DataFrame) -> float:
        """How tightly timestamps align to the expected frequency grid (0–100)."""
        if not isinstance(df.index, pd.DatetimeIndex) or len(df) < 2:
            return 0.0
        diffs = df.index.to_series().diff().dropna()
        expected_ns = pd.tseries.frequencies.to_offset(self.expected_freq).nanos
        deviation = (diffs.dt.total_seconds() * 1e9 - expected_ns).abs()
        # Score: fraction of intervals within 5 % of the expected duration
        tolerance = expected_ns * 0.05
        well_aligned = (deviation <= tolerance).sum()
        return float(well_aligned / len(diffs) * 100)

    def _noise_level(self, df: pd.DataFrame) -> float:
        """
        Inverse normalised coefficient-of-variation across numeric columns (0–100).
        Lower CV → higher score.
        """
        cvs: list[float] = []
        for col in [self.flow_col, self.pressure_col, self.energy_col]:
            if col not in df.columns:
                continue
            series = df[col].dropna()
            if len(series) < 2 or series.mean() == 0:
                continue
            cv = series.std() / abs(series.mean())
            cvs.append(cv)

        if not cvs:
            return 100.0

        mean_cv = float(np.mean(cvs))
        # CV of 0 → score 100; CV >= 1 → score 0; linear in between
        score = max(0.0, (1.0 - mean_cv) * 100)
        return float(np.clip(score, 0.0, 100.0))

    def _anomaly_frequency(self, df: pd.DataFrame) -> float:
        """
        Inverse of the fraction of anomalous rows detected via IQR fencing (0–100).
        """
        numeric_cols = [
            c
            for c in [self.flow_col, self.pressure_col, self.energy_col]
            if c in df.columns
        ]
        if not numeric_cols:
            return 100.0

        anomaly_flags = pd.Series(False, index=df.index)
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
            outliers = (series < lower) | (series > upper)
            anomaly_flags = anomaly_flags | outliers.reindex(df.index, fill_value=False)

        anomaly_rate = anomaly_flags.sum() / len(df)
        return float(np.clip((1.0 - anomaly_rate) * 100, 0.0, 100.0))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_weights(w: dict[str, float]) -> dict[str, float]:
        total = sum(w.values())
        if total == 0:
            raise ValueError("Weights must not all be zero.")
        return {k: v / total for k, v in w.items()}
