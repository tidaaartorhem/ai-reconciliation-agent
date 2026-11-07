"""Load the ReconDesk queue + config (data/raw/*.json, written by
scripts/fetch_olist.py from the real Olist CSVs)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"


def _load(name: str) -> dict:
    return json.loads((RAW / name).read_text())


def load_queue() -> dict:
    return _load("queue.json")


def load_config() -> dict:
    return _load("scoring-config.json")


def load_golden() -> dict:
    return _load("golden_set.json")


def load_corpus_stats() -> dict:
    return _load("corpus_stats.json")
