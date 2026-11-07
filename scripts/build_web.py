#!/usr/bin/env python3
"""Build script: runs the ReconDesk pipeline and assembles the web payload.

Writes web/public/data/*.json:
  summary.json      - headline findings + golden-set eval + scoring disclosure
  orders.json       - per-order export pack (breaks, score, route, drafts)
  breakbook.json    - the B1-B8 break rules
  test-vectors.json - shared Python/TS reconciler contract (12 vectors)
Exits non-zero if the pipeline produced no orders.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "public" / "data"
RAW = ROOT / "data" / "raw"


def fail(msg: str) -> None:
    print(f"build_web: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from recondesk import eval as rd_eval
    from recondesk.breaks import BREAKS, detect_breaks, route_order, score_order
    from recondesk.data import load_queue
    from recondesk.graph import run
    from recondesk.report import findings

    state = run()
    if not state["export_pack"]:
        fail("pipeline produced no orders")

    f = findings(state)
    ev = rd_eval.evaluate(state["config"])
    queue = load_queue()

    pack_by_id = {p["order_id"]: p for p in state["export_pack"]}
    raw_by_id = {o["order_id"]: o for o in queue["orders"]}

    # 12 test vectors: one per break code + clean cases + synthetic edges.
    # Each vector carries the full normalized order so the TS mirror can
    # re-run detection and must agree exactly on codes/score/route/action.
    wanted: dict[str, dict] = {}
    for p in state["export_pack"]:
        codes = p["break_codes"]
        if codes == ["B1"] and abs(p["totals"]["delta"]) >= 100 and "B1-big" not in wanted:
            wanted["B1-big"] = p
        elif codes == ["B2"] and p["totals"]["paid"] >= 1000 and "B2-large-refund" not in wanted:
            wanted["B2-large-refund"] = p
        elif codes == ["B3"] and p["totals"]["paid"] >= 1000 and "B3-large-at-risk" not in wanted:
            wanted["B3-large-at-risk"] = p
        if len(wanted) == 3:
            break
    missing = {"B1-big", "B2-large-refund", "B3-large-at-risk"} - set(wanted)
    if missing:
        fail(f"missing queue vectors: {sorted(missing)}")

    vectors: list[tuple] = [(label, p) for label, p in wanted.items()]
    # The remaining vectors come from the golden set: SLA-only breaks score
    # too low to make the top-150 queue, so the queue cannot source them.
    golden = json.loads((RAW / "golden_set.json").read_text())
    for entry in golden["orders"]:
        note = entry["note"]
        if note.startswith("B4 longest"):
            vectors.append(("B4-very-late", None, entry["order"]))
        elif note.startswith("B5 shortest"):
            vectors.append(("B5-only", None, entry["order"]))
        elif note.startswith("MULTI B1+B4"):
            vectors.append(("B1+B4-multi", None, entry["order"]))
        elif note.startswith("MULTI B4+B5"):
            vectors.append(("B4+B5-multi", None, entry["order"]))
        elif note.startswith("CLEAN single"):
            vectors.append(("CLEAN-single", None, entry["order"]))
        elif note.startswith("CLEAN multi-installment"):
            vectors.append(("CLEAN-multi-pay", None, entry["order"]))
        elif note.startswith("B7 SYNTHETIC"):
            vectors.append(("B7-synthetic", None, entry["order"]))
        elif note.startswith("B8 SYNTHETIC"):
            vectors.append(("B8-synthetic", None, entry["order"]))
        elif note.startswith("B6 the one"):
            vectors.append(("B6-only-real", None, entry["order"]))

    out_vectors = []
    for item in vectors:
        if len(item) == 2:
            label, p = item
            order = raw_by_id[p["order_id"]]
            out_vectors.append({
                "label": label, "order": order,
                "expected_codes": p["break_codes"],
                "expected_score": p["score"],
                "expected_route": p["route"],
                "expected_action": p["action"],
            })
        else:
            label, _, order = item
            breaks = detect_breaks(order)
            score, _ = score_order(order, breaks)
            from recondesk.breaks import recommended_action
            action, _ = recommended_action(order, breaks)
            out_vectors.append({
                "label": label, "order": order,
                "expected_codes": sorted(b["code"] for b in breaks),
                "expected_score": score,
                "expected_route": route_order(order, breaks, score),
                "expected_action": action,
            })

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / "summary.json").write_text(json.dumps({
        "findings": f,
        "eval": {k: v for k, v in ev.items() if k != "misses"},
        "eval_misses": ev["misses"],
        "config": state["config"],
        "company": state["queue_meta"]["company"],
        "queue_meta": state["queue_meta"],
        "data_note": ("Three systems from the real Olist Brazilian E-Commerce "
                      "dataset (Kaggle, CC BY 4.0): billing = order_payments, "
                      "order book = orders + customers, warehouse = order_items "
                      "plus delivery dates. Full corpus: 99,441 orders. The desk "
                      "replays Q4 2017 purchases (17,848 orders, R$ 2,852,962.16) "
                      "with the close as of 2018-01-05; the web queue is the top "
                      "150 break orders by score. B7/B8 have zero real cases in "
                      "the corpus, so their golden-set and vector entries are "
                      "synthetic and labeled as such. Money is BRL."),
    }, indent=1))
    (WEB_DATA / "orders.json").write_text(json.dumps(state["export_pack"], indent=1))
    (WEB_DATA / "breakbook.json").write_text(json.dumps(
        {"breaks": [BREAKS[c] for c in sorted(BREAKS)]}, indent=1))
    (WEB_DATA / "test-vectors.json").write_text(json.dumps({"vectors": out_vectors}, indent=1))
    print(f"build_web: {len(state['export_pack'])} orders, {len(out_vectors)} vectors -> {WEB_DATA}")


if __name__ == "__main__":
    main()
