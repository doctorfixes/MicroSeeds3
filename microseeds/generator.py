from .schema import MicroSeed
from .explanation_builder import build_explanation
from config import DEFAULT_MM

def generate_microseed(decision):
    return MicroSeed(
        block=decision["block"],
        window=decision["recommended_window"],
        mm=DEFAULT_MM,
        explanation=build_explanation()
    )
