"""Golden-set eval: the hand-labeled orders in data/raw/golden_set.json
carry their expected break codes, route, and action (labels verified by
direct computation on the Olist rows, not by the engine under test).

The break rules are exact comparisons, not tuned thresholds, so this eval
is a regression check on the implementation: routing accuracy should be
1.000. Any miss is a bug, not a calibration result, and is listed.
"""
from __future__ import annotations

from .breaks import detect_breaks, recommended_action, route_order, score_order
from .data import load_golden


def evaluate(config: dict | None = None) -> dict:
    golden = load_golden()
    total = len(golden["orders"])
    code_correct = 0
    route_correct = 0
    action_correct = 0
    misses = []
    for entry in golden["orders"]:
        order = entry["order"]
        breaks = detect_breaks(order)
        codes = sorted(b["code"] for b in breaks)
        score, _ = score_order(order, breaks)
        route = route_order(order, breaks, score)
        action, _ = recommended_action(order, breaks)
        ok_codes = codes == sorted(entry["expected_codes"])
        ok_route = route == entry["expected_route"]
        ok_action = action == entry["expected_action"]
        code_correct += ok_codes
        route_correct += ok_route
        action_correct += ok_action
        if not (ok_codes and ok_route and ok_action):
            misses.append({
                "order_id": order["order_id"],
                "expected_codes": entry["expected_codes"],
                "got_codes": codes,
                "expected_route": entry["expected_route"],
                "got_route": route,
                "expected_action": entry["expected_action"],
                "got_action": action,
                "note": entry.get("note", ""),
            })
    return {
        "golden_n": total,
        "code_accuracy": round(code_correct / total, 3) if total else 0,
        "route_accuracy": round(route_correct / total, 3) if total else 0,
        "action_accuracy": round(action_correct / total, 3) if total else 0,
        "misses": misses,
    }
