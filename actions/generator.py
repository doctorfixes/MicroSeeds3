from .microseed import MicroSeed
from .explanation import build_explanation
from config import DEFAULT_MM, ENERGY_SAVING_PCT, SALINITY_TREND_DAYS


def build_action(decision):
    explanation = build_explanation(
        energy_saving_pct=ENERGY_SAVING_PCT,
        salinity_trend_days=SALINITY_TREND_DAYS,
    )
    action = MicroSeed(
        block=decision["block"],
        window=decision["recommended_window"],
        mm=DEFAULT_MM,
        explanation=explanation,
    )
    print(f"[ACTION] {action}")
    return action
