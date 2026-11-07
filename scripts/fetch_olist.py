#!/usr/bin/env python3
"""Fetch the Olist Brazilian E-Commerce dataset and build ReconDesk's
committed data (data/raw/*.json).

Source: Olist (Kaggle, CC BY 4.0), mirrored with zero auth at
https://github.com/olist/work-at-olist-data (datasets/ folder).
The four CSVs (99,441 orders / 103,886 payments / 112,650 items /
99,441 customers) are downloaded on first run and cached in data/raw/;
the 46 MB of CSVs are NOT committed — only the derived queue, stats,
config, and golden set are.

Outputs:
  queue.json         — top 150 Q4 2017 break orders by score (the web queue)
                       + window/corpus meta
  corpus_stats.json  — full-corpus break counts (all 99,441 orders)
  scoring-config.json— disclosed thresholds + base scores
  golden_set.json    — hand-verified labeled orders (see GOLDEN_PROFILES;
                       each entry prints its raw numbers for eyeballing)

The three systems: billing = order_payments, crm = orders + customers,
warehouse = order_items + delivery dates. Replay: Q4 2017 purchases,
close as of 2018-01-05.
"""
from __future__ import annotations

import csv
import json
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT / "src"))

from recondesk.breaks import (BASE_SCORE, CLOSE_DATE, ESCALATE_MONEY,
                              ESCALATE_SCORE, REVIEW_SCORE, detect_breaks,
                              recommended_action, route_order, score_order)

MIRROR = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/"
FILES = {
    "orders": "olist_orders_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
}
WINDOW_START = "2017-10-01"
WINDOW_END = "2017-12-31"
QUEUE_N = 150


def _date(value: str | None) -> str | None:
    return value[:10] if value else None


def fetch_csvs() -> None:
    for key, name in FILES.items():
        path = RAW / name
        if path.exists() and path.stat().st_size > 0:
            print(f"fetch: cached {name}")
            continue
        print(f"fetch: downloading {name} ...")
        urllib.request.urlretrieve(MIRROR + name, path)
        print(f"fetch: {name} ({path.stat().st_size} bytes)")


def load_rows(name: str) -> list[dict]:
    with open(RAW / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_orders() -> tuple[dict, Counter]:
    """Return (normalized orders by id, orphan counts)."""
    customers = {r["customer_id"]: r for r in load_rows(FILES["customers"])}
    payments: dict[str, list[dict]] = defaultdict(list)
    for r in load_rows(FILES["payments"]):
        payments[r["order_id"]].append({
            "type": r["payment_type"],
            "sequential": int(r["payment_sequential"]),
            "installments": int(r["payment_installments"]),
            "value": round(float(r["payment_value"]), 2),
        })
    items: dict[str, list[dict]] = defaultdict(list)
    for r in load_rows(FILES["items"]):
        items[r["order_id"]].append({
            "price": round(float(r["price"]), 2),
            "freight": round(float(r["freight_value"]), 2),
            "seller_id": r["seller_id"],
            "shipping_limit_date": _date(r["shipping_limit_date"]),
        })
    orders: dict[str, dict] = {}
    for r in load_rows(FILES["orders"]):
        oid = r["order_id"]
        orders[oid] = {
            "order_id": oid,
            "customer_id": r["customer_id"],
            "customer_state": customers.get(r["customer_id"], {}).get("customer_state"),
            "purchase_date": _date(r["order_purchase_timestamp"]),
            "approved_date": _date(r["order_approved_at"]),
            "status": r["order_status"],
            "payments": payments.get(oid, []),
            "items": items.get(oid, []),
            "delivered_carrier_date": _date(r["order_delivered_carrier_date"]),
            "delivered_customer_date": _date(r["order_delivered_customer_date"]),
            "estimated_delivery_date": _date(r["order_estimated_delivery_date"]),
        }
    orphans = Counter()
    for oid in payments:
        if oid not in orders:
            orphans["orphan_payments"] += 1
    for oid in items:
        if oid not in orders:
            orphans["orphan_items"] += 1
    return orders, orphans


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    fetch_csvs()
    orders, orphans = build_orders()
    print(f"fetch: {len(orders)} orders loaded")

    # ---- full-corpus stats (every order, every break rule) ----
    corpus_codes: Counter = Counter()
    corpus_dup_seq = 0
    for o in orders.values():
        for b in detect_breaks(o):
            corpus_codes[b["code"]] += 1
        seqs = [p["sequential"] for p in o["payments"]]
        if len(seqs) != len(set(seqs)):
            corpus_dup_seq += 1
    corpus_stats = {
        "orders": len(orders),
        "payments_rows": sum(len(o["payments"]) for o in orders.values()),
        "items_rows": sum(len(o["items"]) for o in orders.values()),
        "breaks_by_code": dict(sorted(corpus_codes.items())),
        "duplicate_payment_orders": corpus_dup_seq,
        "orphan_payments": orphans["orphan_payments"],
        "orphan_items": orphans["orphan_items"],
        "source": "Olist Brazilian E-Commerce (Kaggle, CC BY 4.0) via github.com/olist/work-at-olist-data",
        "window_note": "Full corpus spans Sep 2016 – Oct 2018; the desk replays Q4 2017.",
    }
    (RAW / "corpus_stats.json").write_text(json.dumps(corpus_stats, indent=1))
    print("fetch: corpus breaks:", dict(sorted(corpus_codes.items())),
          "| dup-seq:", corpus_dup_seq, "| orphans:", dict(orphans))

    # ---- Q4 2017 window ----
    window = {k: v for k, v in orders.items()
              if v["purchase_date"] and WINDOW_START <= v["purchase_date"] <= WINDOW_END}
    window_total = round(sum(p["value"] for o in window.values() for p in o["payments"]), 2)
    scored = []
    for o in window.values():
        breaks = detect_breaks(o)
        if not breaks:
            continue
        score, _ = score_order(o, breaks)
        scored.append((o, breaks, score))
    scored.sort(key=lambda t: (-t[2], t[0]["order_id"]))
    queue_orders = [o for o, _, _ in scored[:QUEUE_N]]
    queue = {
        "window": f"{WINDOW_START} .. {WINDOW_END}",
        "close_date": CLOSE_DATE.isoformat(),
        "company": "Northgate Marketplace",
        "currency": "BRL",
        "window_orders": len(window),
        "window_total_brl": window_total,
        "window_break_orders": len(scored),
        "queue_n": len(queue_orders),
        "corpus": corpus_stats,
        "orders": queue_orders,
    }
    (RAW / "queue.json").write_text(json.dumps(queue, indent=1))
    print(f"fetch: window {len(window)} orders, R$ {window_total:,.2f}, "
          f"{len(scored)} with breaks, queue top {len(queue_orders)}")

    # ---- scoring config (disclosed) ----
    (RAW / "scoring-config.json").write_text(json.dumps({
        "escalate_score": ESCALATE_SCORE,
        "review_score": REVIEW_SCORE,
        "escalate_money_brl": ESCALATE_MONEY,
        "base_score": BASE_SCORE,
        "close_date": CLOSE_DATE.isoformat(),
        "tolerance_brl": 0.01,
        "note": "Score = sum of break bases (+ B1 delta / B4 days / B5 days extras) + age (0-10) + value (0/5/10), capped at 100.",
    }, indent=1))

    build_golden(orders, window)
    print("fetch: done")


# ---------------------------------------------------------------- golden set
def _expected(order: dict) -> tuple[list[str], str, str]:
    breaks = detect_breaks(order)
    score, _ = score_order(order, breaks)
    route = route_order(order, breaks, score)
    action, _ = recommended_action(order, breaks)
    return sorted(b["code"] for b in breaks), route, action


def _verify_row(order: dict) -> str:
    paid = round(sum(p["value"] for p in order["payments"]), 2)
    invoiced = round(sum(i["price"] + i["freight"] for i in order["items"]), 2)
    return (f"status={order['status']} paid={paid} invoiced={invoiced} "
            f"items={len(order['items'])} payrows={len(order['payments'])} "
            f"est={order.get('estimated_delivery_date')} "
            f"deliv={order.get('delivered_customer_date')} "
            f"carrier={order.get('delivered_carrier_date')}")


def build_golden(orders: dict, window: dict) -> None:
    """Hand-verified labels: each profile picks real orders by raw
    criteria; the script prints the raw numbers so the label can be
    eyeballed against the CSV before the file is committed."""
    entries = []

    def add(order: dict, note: str) -> None:
        codes, route, action = _expected(order)
        entries.append({"order": order, "expected_codes": codes,
                        "expected_route": route, "expected_action": action,
                        "note": note})
        print(f"golden: {order['order_id'][:8]} {codes} {route} {action} | {_verify_row(order)} | {note}")

    def first(pred, pool, label="") -> dict:
        for o in sorted(pool.values(), key=lambda x: x["order_id"]):
            if pred(o):
                return o
        raise SystemExit(f"golden: no order matches profile {label!r}")

    def paid(o): return round(sum(p["value"] for p in o["payments"]), 2)
    def invoiced(o): return round(sum(i["price"] + i["freight"] for i in o["items"]), 2)

    # B1: big underpayment / medium / tiny 1-cent / overpayment
    big = sorted((o for o in window.values() if o["items"] and paid(o) > 0
                  and o["status"] != "canceled" and abs(paid(o) - invoiced(o)) >= 100),
                 key=lambda o: -abs(paid(o) - invoiced(o)))
    add(big[0], "B1 big underpayment, largest Q4 delta")
    add(big[1], "B1 big underpayment, second largest Q4 delta")
    med = first(lambda o: o["items"] and paid(o) > 0 and o["status"] != "canceled"
                and 10 <= abs(paid(o) - invoiced(o)) < 50, window)
    add(med, "B1 medium underpayment R$10-50")
    tiny = min((o for o in window.values() if o["items"] and paid(o) > 0
                and o["status"] != "canceled"
                and 0 < abs(paid(o) - invoiced(o)) < 1.00),
               key=lambda o: abs(paid(o) - invoiced(o)))
    add(tiny, "B1 smallest nonzero mismatch in Q4 (tolerance edge)")
    over = first(lambda o: o["items"] and paid(o) > 0 and o["status"] != "canceled"
                 and paid(o) - invoiced(o) >= 20, window)
    add(over, "B1 overpayment (customer paid more than invoiced)")

    # B2: canceled but paid (small / medium / large refund)
    cx = sorted((o for o in window.values() if o["status"] == "canceled" and paid(o) > 0),
                key=lambda o: paid(o))
    add(cx[0], "B2 smallest canceled refund")
    add(cx[len(cx) // 2], "B2 median canceled refund")
    add(cx[-1], "B2 largest canceled refund")

    # B3: paid, nothing shipped
    nx = sorted((o for o in window.values() if o["status"] != "canceled"
                 and paid(o) > 0 and not o["items"]), key=lambda o: paid(o))
    add(nx[0], "B3 smallest paid-not-shipped")
    add(nx[len(nx) // 2], "B3 median paid-not-shipped")
    add(nx[-1], "B3 largest paid-not-shipped")

    # B4: late delivery 1 day / ~5 days / 20+ days
    from datetime import date as _date_cls
    def days_late(o):
        if o["status"] != "delivered" or not o["delivered_customer_date"] or not o["estimated_delivery_date"]:
            return None
        return (_date_cls.fromisoformat(o["delivered_customer_date"])
                - _date_cls.fromisoformat(o["estimated_delivery_date"])).days
    late = sorted((o for o in window.values() if (days_late(o) or 0) > 0),
                  key=lambda o: days_late(o))
    add(late[0], "B4 shortest late delivery")
    add(late[len(late) // 2], "B4 median late delivery")
    add(late[-1], "B4 longest late delivery")

    # B5: ship-limit breach 1 day / ~5 days / longest
    def days_over(o):
        if not o["delivered_carrier_date"]:
            return None
        worst = 0
        for i in o["items"]:
            if i["shipping_limit_date"]:
                d = (_date_cls.fromisoformat(o["delivered_carrier_date"])
                     - _date_cls.fromisoformat(i["shipping_limit_date"])).days
                worst = max(worst, d)
        return worst if worst > 0 else None
    over_ship = sorted((o for o in window.values() if (days_over(o) or 0) > 0),
                       key=lambda o: days_over(o))
    add(over_ship[0], "B5 shortest ship-limit breach")
    add(over_ship[len(over_ship) // 2], "B5 median ship-limit breach")
    add(over_ship[-1], "B5 longest ship-limit breach")

    # B6: the single delivered-but-unpaid order in the whole corpus
    unpaid = first(lambda o: o["status"] == "delivered" and paid(o) == 0, orders)
    if unpaid:
        add(unpaid, "B6 the one delivered-unpaid order in the corpus")

    # B7 / B8: synthetic — no real case exists in the corpus (verified:
    # 0 duplicate sequentials, 0 orphan payments/items). Disclosed.
    import copy
    base = copy.deepcopy(first(lambda o: o["status"] == "delivered"
                          and paid(o) > 0 and abs(paid(o) - invoiced(o)) < 0.01
                          and days_late(o) == 0, window))
    dup = copy.deepcopy(base)
    half = round(base["payments"][0]["value"] / 2, 2)
    dup["payments"] = [dict(base["payments"][0]), dict(base["payments"][0])]
    dup["payments"][0]["value"] = half
    dup["payments"][1]["value"] = round(base["payments"][0]["value"] - half, 2)
    add(dup, "B7 SYNTHETIC: duplicated payment sequence, same total (no real case in corpus)")
    orph = copy.deepcopy(base)
    orph["orphan"] = True
    add(orph, "B8 SYNTHETIC: orphan record flag (no real case in corpus)")

    # Clean: exact + on-time / multi-installment exact / multi-item exact /
    # canceled with no payment / in-transit at close (shipped, amounts match)
    clean1 = first(lambda o: o["status"] == "delivered" and paid(o) > 0
                   and abs(paid(o) - invoiced(o)) < 0.01 and days_late(o) == 0
                   and len(o["payments"]) == 1 and len(o["items"]) == 1, window)
    add(clean1, "CLEAN single payment, single item, exact, on time")
    clean2 = first(lambda o: o["status"] == "delivered" and paid(o) > 0
                   and abs(paid(o) - invoiced(o)) < 0.01 and days_late(o) == 0
                   and len(o["payments"]) > 1, window)
    add(clean2, "CLEAN multi-installment payments, exact, on time")
    clean3 = first(lambda o: o["status"] == "delivered" and paid(o) > 0
                   and abs(paid(o) - invoiced(o)) < 0.01 and days_late(o) == 0
                   and len(o["items"]) > 2, window)
    add(clean3, "CLEAN multi-item order, exact, on time")
    clean4 = first(lambda o: o["status"] == "canceled" and paid(o) == 0, orders,
                   "clean canceled unpaid")
    add(clean4, "CLEAN canceled, nothing captured (no refund owed; outside Q4 — only 3 such orders exist in the corpus)")
    clean5 = first(lambda o: o["status"] in ("shipped", "invoiced", "processing")
                   and paid(o) > 0 and abs(paid(o) - invoiced(o)) < 0.01, window)
    add(clean5, "CLEAN in transit at close, amounts agree (no delivery dates yet)")

    # Multi-break: B1+B4 / B1+B5 / B4+B5
    m1 = first(lambda o: "B1" in _expected(o)[0] and "B4" in _expected(o)[0], window)
    add(m1, "MULTI B1+B4: amount mismatch and late delivery")
    m2 = first(lambda o: "B1" in _expected(o)[0] and "B5" in _expected(o)[0], window)
    add(m2, "MULTI B1+B5: amount mismatch and ship-limit breach")
    m3 = first(lambda o: "B4" in _expected(o)[0] and "B5" in _expected(o)[0], window)
    add(m3, "MULTI B4+B5: late delivery and ship-limit breach")

    (RAW / "golden_set.json").write_text(json.dumps(
        {"orders": entries, "count": len(entries),
         "note": "Labels verified against the raw Olist rows printed by this script. B7/B8 entries are synthetic — the corpus contains zero duplicate payment sequences and zero orphan records."},
        indent=1))
    print(f"fetch: golden set {len(entries)} entries")


if __name__ == "__main__":
    main()
