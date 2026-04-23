def build_explanation(energy_saving_pct: int, salinity_trend_days: int) -> str:
    return (
        f"Early AM cuts energy ~{energy_saving_pct}% "
        f"+ breaks {salinity_trend_days}-day salinity trend."
    )
