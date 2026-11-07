"""Tests for the ReconDesk pipeline: engine rules, graph end-to-end,
golden-set eval, and the shared Python/TS test-vectors contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recondesk import eval as rd_eval  # noqa: E402
from recondesk.breaks import (BREAKS, detect_breaks, money_at_stake,  # noqa: E402
                              recommended_action, route_order, score_order)
from recondesk.data import load_config, load_golden, load_queue  # noqa: E402
from recondesk.graph import run  # noqa: E402
from recondesk.report import findings  # noqa: E402


def _order(**over) -> dict:
    base = {
        "order_id": "test-order-1",
        "customer_id": "cust-1",
        "customer_state": "SP",
        "purchase_date": "2017-11-15",
        "approved_date": "2017-11-15",
        "status": "delivered",
        "payments": [{"type": "credit_card", "sequential": 1, "installments": 1, "value": 100.00}],
        "items": [{"price": 90.00, "freight": 10.00, "seller_id": "s1",
                   "shipping_limit_date": "2017-11-20"}],
        "delivered_carrier_date": "2017-11-18",
        "delivered_customer_date": "2017-11-25",
        "estimated_delivery_date": "2017-11-25",
    }
    base.update(over)
    return base


def test_clean_order_has_no_breaks():
    assert detect_breaks(_order()) == []


def test_b1_underpayment_and_score():
    o = _order(payments=[{"type": "credit_card", "sequential": 1, "installments": 1, "value": 80.00}])
    breaks = detect_breaks(o)
    assert [b["code"] for b in breaks] == ["B1"]
    assert breaks[0]["delta"] == -20.00
    score, parts = score_order(o, breaks)
    # base 10 + min(25, 20*2)=25 + 5 (>= R$10) + age 1 (51 days -> 1) = 41
    assert score == 41
    assert route_order(o, breaks, score) == "REVIEW"
    action, _ = recommended_action(o, breaks)
    assert action == "POST_CORRECTION"


def test_b1_overpayment_draft_is_refund_payable():
    from recondesk.breaks import correction_draft
    o = _order(payments=[{"type": "credit_card", "sequential": 1, "installments": 1, "value": 120.00}])
    breaks = detect_breaks(o)
    assert [b["code"] for b in breaks] == ["B1"]
    draft = correction_draft(o, breaks)
    assert draft[0]["title"] == "Correcting journal — over-collection"
    assert "refunds payable" in draft[0]["lines"][1].lower()


def test_b1_ignored_when_canceled_or_unpaid():
    # Canceled: the refund (B2) supersedes the mismatch.
    o = _order(status="canceled")
    assert [b["code"] for b in detect_breaks(o)] == ["B2"]
    # Unpaid delivery: B6 only, not a phantom B1 on the full invoice.
    o = _order(payments=[])
    assert [b["code"] for b in detect_breaks(o)] == ["B6"]


def test_b2_canceled_paid_refund_owed():
    o = _order(status="canceled")
    breaks = detect_breaks(o)
    assert breaks[0]["code"] == "B2" and breaks[0]["refund_owed"] == 100.00
    assert money_at_stake(o, breaks) == 100.00
    action, _ = recommended_action(o, breaks)
    assert action == "ISSUE_REFUND"


def test_b2_large_refund_escalates():
    o = _order(status="canceled",
               payments=[{"type": "credit_card", "sequential": 1, "installments": 1, "value": 600.00}],
               items=[{"price": 550.00, "freight": 50.00, "seller_id": "s1",
                       "shipping_limit_date": "2017-11-20"}])
    breaks = detect_breaks(o)
    score, _ = score_order(o, breaks)
    assert route_order(o, breaks, score) == "ESCALATE"


def test_b3_paid_not_shipped():
    o = _order(status="unavailable", items=[])
    breaks = detect_breaks(o)
    assert [b["code"] for b in breaks] == ["B3"]
    assert money_at_stake(o, breaks) == 100.00


def test_b4_late_delivery_days():
    o = _order(delivered_customer_date="2017-11-28")
    breaks = detect_breaks(o)
    assert [b["code"] for b in breaks] == ["B4"]
    assert breaks[0]["days_late"] == 3


def test_b5_ship_limit_breach():
    o = _order(delivered_carrier_date="2017-11-22")
    breaks = detect_breaks(o)
    assert [b["code"] for b in breaks] == ["B5"]
    assert breaks[0]["days_over"] == 2


def test_b7_duplicate_sequence():
    o = _order(payments=[
        {"type": "credit_card", "sequential": 1, "installments": 1, "value": 50.00},
        {"type": "credit_card", "sequential": 1, "installments": 1, "value": 50.00},
    ])
    assert [b["code"] for b in detect_breaks(o)] == ["B7"]


def test_b8_orphan_flag():
    o = _order(orphan=True)
    assert [b["code"] for b in detect_breaks(o)] == ["B8"]


def test_score_caps_at_100():
    o = _order(purchase_date="2017-10-01",
               payments=[{"type": "credit_card", "sequential": 1, "installments": 1, "value": 5000.00}],
               items=[{"price": 4900.00, "freight": 100.00, "seller_id": "s1",
                       "shipping_limit_date": "2017-10-05"}],
               delivered_carrier_date="2017-12-20",
               delivered_customer_date="2018-01-04",
               estimated_delivery_date="2017-10-20")
    # Fabricated worst case: every break at max extras + max age/value.
    fabricated = [
        {"code": "B1", "delta": -5000.00},
        {"code": "B2", "refund_owed": 5000.00},
        {"code": "B3", "amount_at_risk": 5000.00},
        {"code": "B4", "days_late": 90},
        {"code": "B5", "days_over": 90},
        {"code": "B6", "amount_at_risk": 5000.00},
        {"code": "B7"},
        {"code": "B8"},
    ]
    score, _ = score_order(o, fabricated)
    assert score == 100
    # And the real engine never exceeds the cap either.
    breaks = detect_breaks(o)
    real_score, _ = score_order(o, breaks)
    assert real_score <= 100


def test_queue_loads_and_has_breaks():
    q = load_queue()
    assert q["queue_n"] == len(q["orders"]) == 150
    assert q["window_orders"] == 17848
    assert q["window_break_orders"] == 2702
    assert all(detect_breaks(o) for o in q["orders"])


def test_golden_set_eval_is_perfect():
    ev = rd_eval.evaluate(load_config())
    assert ev["golden_n"] == 28
    assert ev["code_accuracy"] == 1.0
    assert ev["route_accuracy"] == 1.0
    assert ev["action_accuracy"] == 1.0
    assert ev["misses"] == []


def test_golden_set_covers_every_break_code():
    golden = load_golden()
    seen = set()
    for e in golden["orders"]:
        seen.update(e["expected_codes"])
    assert {"B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"} <= seen
    assert any(e["expected_codes"] == [] for e in golden["orders"])


def test_graph_runs_end_to_end():
    state = run()
    assert len(state["export_pack"]) == 150
    assert all(o["pending_approval"] for o in state["export_pack"])
    assert all(o["route"] in ("ESCALATE", "REVIEW", "MONITOR") for o in state["export_pack"])
    assert all(o["correction_draft"] or o["break_codes"] == [] for o in state["export_pack"])
    f = findings(state)
    assert f["queue_orders"] == 150
    assert f["window_break_orders"] == 2702
    assert f["money_at_stake_brl"] > 0
    assert set(f["routes"]) <= {"ESCALATE", "REVIEW", "MONITOR"}


def test_breakbook_covers_eight_rules():
    assert len(BREAKS) == 8
    assert sorted(BREAKS) == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8"]


def test_test_vectors_match_engine():
    """The shared contract: every committed test vector must reproduce
    exactly under the Python engine (the TS mirror is checked by vitest)."""
    web_vectors = ROOT / "web" / "public" / "data" / "test-vectors.json"
    if not web_vectors.exists():
        pytest.skip("web payload not built yet (run scripts/build_web.py)")
    vectors = json.loads(web_vectors.read_text())["vectors"]
    assert len(vectors) == 12
    labels = {v["label"] for v in vectors}
    assert labels == {"B1-big", "B2-large-refund", "B3-large-at-risk", "B4-very-late",
                      "B5-only", "B1+B4-multi", "B4+B5-multi",
                      "CLEAN-single", "CLEAN-multi-pay",
                      "B7-synthetic", "B8-synthetic", "B6-only-real"}
    for v in vectors:
        breaks = detect_breaks(v["order"])
        score, _ = score_order(v["order"], breaks)
        action, _ = recommended_action(v["order"], breaks)
        assert sorted(b["code"] for b in breaks) == sorted(v["expected_codes"]), v["label"]
        assert score == v["expected_score"], v["label"]
        assert route_order(v["order"], breaks, score) == v["expected_route"], v["label"]
        assert action == v["expected_action"], v["label"]
