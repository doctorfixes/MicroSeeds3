"""
fallback_mode.py
================
Fallback Intelligence Mode for MicroSeeds.

When a block's reliability score falls below the low-confidence threshold
(score < 60), the system switches to fallback mode.  In this mode the
system uses:

  1. Historical patterns (rolling averages over a look-back window).
  2. District-level averages (peer-block medians).
  3. ET-window + timing heuristics.
  4. Salinity-risk heuristics.

Fallback mode also reduces trigger sensitivity to prevent false MicroSeeds.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .reliability_score import THRESHOLD_LOW, BlockScore


class FallbackMode:
    """
    Produce a "best estimate" DataFrame when the source data is unreliable.

    Parameters
    ----------
    lookback_window : int
        Number of intervals to use when computing historical rolling averages.
    trigger_sensitivity_factor : float
        Multiplicative factor applied to signal thresholds in fallback mode.
        Values < 1 reduce sensitivity (fewer false triggers).  Default 0.7.
    et_window : tuple[int, int] | None
        ``(start_hour, end_hour)`` of the valid ET irrigation window.
    salinity_high_pressure_threshold : float
        Pressure quantile (0–1) above which salinity risk is flagged.
    """

    def __init__(
        self,
        lookback_window: int = 24,
        trigger_sensitivity_factor: float = 0.70,
        et_window: Optional[tuple[int, int]] = None,
        salinity_high_pressure_threshold: float = 0.90,
    ) -> None:
        self.lookback_window = lookback_window
        self.trigger_sensitivity_factor = trigger_sensitivity_factor
        self.et_window = et_window
        self.salinity_high_pressure_threshold = salinity_high_pressure_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_activate(self, score: BlockScore) -> bool:
        """Return ``True`` if the block score is below the low-confidence threshold."""
        return score.composite < THRESHOLD_LOW

    def apply(
        self,
        df: pd.DataFrame,
        score: BlockScore,
        district_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Return an imputed/smoothed DataFrame using fallback heuristics.

        Parameters
        ----------
        df :
            Raw (possibly noisy / incomplete) block DataFrame.
        score :
            :class:`~microseeds.reliability_score.BlockScore` for this block.
        district_df :
            Optional district-wide DataFrame (same columns) used to derive
            district-level averages.

        Returns
        -------
        pd.DataFrame
            A DataFrame with imputed values and added metadata columns:
            ``_fallback_active``, ``_fallback_source``.
        """
        if df.empty:
            return df.copy()

        result = df.copy()
        numeric_cols = result.select_dtypes(include=[np.number]).columns.tolist()
        # Strip any internal metadata columns that may have been added by the pipeline
        numeric_cols = [c for c in numeric_cols if not c.startswith("_")]

        for col in numeric_cols:
            result[col] = self._impute_column(result[col], district_df, col)

        result["_fallback_active"] = self.should_activate(score)
        result["_fallback_source"] = "historical_patterns"
        if district_df is not None:
            result["_fallback_source"] = "district_average+historical"

        result["_trigger_sensitivity"] = self.trigger_sensitivity_factor

        # ET-window annotation
        if self.et_window is not None and isinstance(result.index, pd.DatetimeIndex):
            start_h, end_h = self.et_window
            result["_in_et_window"] = result.index.hour.isin(
                range(start_h, end_h + 1)
            )

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _impute_column(
        self,
        series: pd.Series,
        district_df: Optional[pd.DataFrame],
        col: str,
    ) -> pd.Series:
        """
        Fill NaN values in *series* using (in priority order):
          1. Rolling historical mean over *lookback_window* intervals.
          2. District-level median for the same column (if available).
          3. Forward-fill then backward-fill as a last resort.
        """
        result = series.copy()

        # Step 1 – rolling historical mean (only uses past values → causal)
        historical_fill = (
            result.fillna(method="ffill")  # avoid look-ahead before rolling
            .rolling(window=self.lookback_window, min_periods=1)
            .mean()
        )
        result = result.where(result.notna(), historical_fill)

        # Step 2 – district-level median
        if district_df is not None and col in district_df.columns:
            district_median = district_df[col].median()
            result = result.fillna(district_median)

        # Step 3 – ffill / bfill
        result = result.ffill().bfill()

        return result

    def adjusted_threshold(self, base_threshold: float) -> float:
        """Return the threshold adjusted for fallback sensitivity reduction."""
        return base_threshold * self.trigger_sensitivity_factor
