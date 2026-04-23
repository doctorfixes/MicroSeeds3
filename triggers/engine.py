def should_trigger(decision):
    fired = decision["high_energy"]
    print(f"[TRIGGER] fired={fired}")
    return fired
