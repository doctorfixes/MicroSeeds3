from config import HIGH_ENERGY_THRESHOLD, DEFAULT_WINDOW


def compute_decision(data):
    high_energy = data["pumping_kwh"] > HIGH_ENERGY_THRESHOLD
    decision = {
        "block": data["block"],
        "high_energy": high_energy,
        "recommended_window": DEFAULT_WINDOW,
    }
    print(f"[DECISION] {decision}")
    return decision
