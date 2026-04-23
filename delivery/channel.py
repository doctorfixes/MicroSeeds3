def deliver(action):
    message = (
        f"Irrigate {action.block} at {action.window} ({action.mm} mm). "
        f"{action.explanation}"
    )
    print(f"[DELIVERY] {message}")
