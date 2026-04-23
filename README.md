# MicroSeeds3

An end-to-end MicroSeed irrigation intelligence loop.

## Quickstart

```bash
git clone https://github.com/doctorfixes/MicroSeeds3
cd MicroSeeds3
pip install -r requirements.txt
python main.py
```

## Structure

```
MicroSeeds3/
├── main.py          # Orchestrator — runs the full loop once
├── config.py        # Centralized constants (thresholds, windows, defaults)
├── inputs/          # Data ingestion (adapter.py)
├── processing/      # Decision logic (core_logic.py)
├── triggers/        # Trigger evaluation (engine.py)
├── actions/         # MicroSeed construction (microseed.py, explanation.py, generator.py)
├── delivery/        # Output channel (channel.py)
├── feedback/        # Response logging (collector.py)
├── microseeds/      # Advanced pipeline components (drift, reliability, cleaning)
└── tests/           # Test suite (test_walk.py)
```

## Running tests

```bash
pytest
```

