from inputs.adapter import get_input
from processing.core_logic import compute_decision
from triggers.engine import should_trigger
from actions.generator import build_action
from delivery.channel import deliver
from feedback.collector import record_feedback


def run_once():
    data = get_input()
    decision = compute_decision(data)

    if not should_trigger(decision):
        print("No MicroSeed triggered.")
        return

    action = build_action(decision)
    deliver(action)
    record_feedback(action)


if __name__ == "__main__":
    run_once()
