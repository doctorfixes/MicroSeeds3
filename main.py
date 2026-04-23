from ingestion.pumping_adapter import get_pumping_log
from reliability.cleaner import clean_data
from intelligence.integrated_trigger import should_trigger
from intelligence.stability_model import compute_decision
from microseeds.generator import generate_microseed
from delivery.sms_adapter import deliver_sms
from feedback.loop_logger import log_feedback

def run_once():
    print("\n=== MicroSeeds Intelligence Engine (MVP) ===")

    raw = get_pumping_log()
    print("[INPUT]", raw)

    cleaned = clean_data(raw)
    print("[CLEANED]", cleaned)

    decision = compute_decision(cleaned)
    print("[DECISION]", decision)

    if not should_trigger(decision):
        print("[TRIGGER] No MicroSeed fired.")
        return

    microseed = generate_microseed(decision)
    print("[MICROSEED]", microseed)

    deliver_sms(microseed)
    log_feedback(microseed, "simulated_ok")

if __name__ == "__main__":
    run_once()
