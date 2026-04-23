"""
MicroSeeds Data Reliability MVP
================================
A foundation layer for reliable, predictable, low-noise pumping/irrigation
data that the MicroSeeds intelligence engine can trust.

Modules
-------
reliability_score   – Compute a 0–100 reliability score per block.
cleaning_pipeline   – 3-layer data cleaning (Structural → Behavioral → Model-Aware).
fallback_mode       – Fallback intelligence when data is missing or unreliable.
drift_detector      – Detect sensor, timestamp, pressure, flow, and energy drift.
report              – Generate district-facing weekly reliability reports.
"""

from .reliability_score import ReliabilityScorer
from .cleaning_pipeline import CleaningPipeline
from .fallback_mode import FallbackMode
from .drift_detector import DriftDetector
from .report import ReliabilityReport

__all__ = [
    "ReliabilityScorer",
    "CleaningPipeline",
    "FallbackMode",
    "DriftDetector",
    "ReliabilityReport",
]
