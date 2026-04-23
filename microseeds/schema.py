from dataclasses import dataclass

@dataclass
class MicroSeed:
    block: str
    window: str
    mm: float
    explanation: str
