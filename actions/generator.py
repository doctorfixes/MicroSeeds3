def build_action(decision):
    return {
        "block": decision["block"],
        "window": decision["recommended_window"],
        "message": (
            f"Irrigate {decision['block']} at {decision['recommended_window']}. "
            "Early AM cuts energy ~15%."
        )
    }
