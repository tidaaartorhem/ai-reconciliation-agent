"""Headline findings for the Q4 2017 close, computed from the pipeline
state (never hand-typed)."""
from __future__ import annotations

from collections import Counter


def findings(state: dict) -> dict:
    orders = state["export_pack"]
    meta = state["queue_meta"]
    corpus = meta["corpus"]
    by_code: Counter = Counter()
    by_route: Counter = Counter()
    by_action: Counter = Counter()
    money_by_code: Counter = Counter()
    total_at_stake = 0.0
    for o in orders:
        by_route[o["route"]] += 1
        by_action[o["action"]] += 1
        total_at_stake += o["money_at_stake"]
        for b in o["breaks"]:
            by_code[b["code"]] += 1
            if b["code"] == "B1":
                money_by_code["B1"] += abs(o["totals"]["delta"])
            elif b["code"] in ("B2", "B3"):
                money_by_code[b["code"]] += o["totals"]["paid"]
            elif b["code"] == "B6":
                money_by_code["B6"] += o["totals"]["invoiced"]
    top = sorted(orders, key=lambda o: (-o["score"], o["order_id"]))[:5]
    return {
        "close_date": meta["close_date"],
        "window": meta["window"],
        "queue_orders": len(orders),
        "window_orders": meta["window_orders"],
        "window_total_brl": meta["window_total_brl"],
        "window_break_orders": meta["window_break_orders"],
        "breaks_by_code": dict(sorted(by_code.items())),
        "routes": dict(sorted(by_route.items())),
        "actions": dict(sorted(by_action.items())),
        "money_at_stake_brl": round(total_at_stake, 2),
        "money_by_code_brl": {k: round(v, 2) for k, v in sorted(money_by_code.items())},
        "corpus": corpus,
        "top_breaks": [
            {"order_id": o["order_id"], "score": o["score"], "route": o["route"],
             "break_codes": o["break_codes"], "money_at_stake": o["money_at_stake"],
             "status": o["status"]}
            for o in top
        ],
        "estimated_hours": round(len(orders) * 0.25, 1),
    }
