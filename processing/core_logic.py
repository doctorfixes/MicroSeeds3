def compute_decision(data):
    high_energy = data["pumping_kwh"] > 40
    return {
        "block": data["block"],
        "high_energy": high_energy,
        "recommended_window": "04:00–05:00"
    }
