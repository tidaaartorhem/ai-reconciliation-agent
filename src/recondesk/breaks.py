"""ReconDesk break engine — deterministic three-system reconciliation.

Three systems, one order:
  billing   — the payments ledger (olist_order_payments_dataset)
  crm       — the order book (olist_orders_dataset + customers)
  warehouse — fulfilment (olist_order_items_dataset + delivery dates)

Break rules (all exact comparisons on cent-rounded BRL values; no LLM):
  B1 AMOUNT_MISMATCH    sum(payments) != sum(item price + freight), |delta| >= 0.01
                        (only when a payment exists and the order is not
                        canceled — a canceled order is B2, an unpaid delivery B6)
  B2 CANCELED_PAID      order canceled but payment was captured (refund owed)
  B3 PAID_NOT_SHIPPED   payment captured, no warehouse items at all
  B4 LATE_DELIVERY      delivered to customer after the estimated date
  B5 SHIP_LIMIT_BREACH  handed to carrier after a seller shipping-limit date
  B6 UNPAID_DELIVERY    delivered but no payment captured
  B7 DUPLICATE_PAYMENT  the same payment_sequential twice on one order
  B8 ORPHAN_RECORD      a payment/item whose order_id is in no system
                        (corpus-level check; reported in the summary)

Score 0-100 (disclosed additive parts, capped at 100):
  base by break type + value factor + age factor (days from purchase to
  the close date). Route: ESCALATE >= 75 (or B2/B3 holding >= R$500),
  REVIEW >= 40, else MONITOR. One recommended action per order, taken
  from its highest-priority break. Every correction is a human-gated
  draft; nothing is posted.
"""
from __future__ import annotations

from datetime import date

CENT = 0.01
CLOSE_DATE = date(2018, 1, 5)  # Q4 2017 close, five days after quarter end

BREAKS = {
    "B1": {"code": "B1", "name": "Amount mismatch",
           "systems": "billing vs warehouse",
           "what": "The payments ledger and the warehouse invoice disagree on the order total by at least one cent."},
    "B2": {"code": "B2", "name": "Canceled but paid",
           "systems": "crm vs billing",
           "what": "The order was canceled, but the payment was captured and never refunded."},
    "B3": {"code": "B3", "name": "Paid but never shipped",
           "systems": "billing vs warehouse",
           "what": "Money was captured and the order book has the order, but the warehouse has no items for it at all."},
    "B4": {"code": "B4", "name": "Late delivery",
           "systems": "warehouse vs crm",
           "what": "The customer received the order after the estimated delivery date the order book promised."},
    "B5": {"code": "B5", "name": "Shipped after the limit date",
           "systems": "warehouse vs crm",
           "what": "The parcel reached the carrier after the seller's shipping-limit date for one of its items."},
    "B6": {"code": "B6", "name": "Delivered but unpaid",
           "systems": "crm vs billing",
           "what": "The order was delivered, but the payments ledger has no payment for it."},
    "B7": {"code": "B7", "name": "Duplicate payment",
           "systems": "billing",
           "what": "The same payment sequence number appears twice on one order — the customer may have been charged twice."},
    "B8": {"code": "B8", "name": "Orphan record",
           "systems": "billing / warehouse vs crm",
           "what": "A payment or an item references an order_id that exists in no other system."},
}

# Base score per break type. B1 scales with the size of the delta (see below).
BASE_SCORE = {"B1": 10, "B2": 45, "B3": 40, "B4": 8, "B5": 5, "B6": 45, "B7": 30, "B8": 25}

# Priority order for the single recommended action (money first).
PRIORITY = ["B2", "B3", "B6", "B7", "B1", "B4", "B5", "B8"]

ESCALATE_SCORE = 75
REVIEW_SCORE = 40
ESCALATE_MONEY = 500.0  # B2/B3 holding this much or more escalates regardless of score


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _money(value) -> float:
    return round(float(value), 2)


def totals(order: dict) -> dict:
    """Billing vs warehouse totals for one normalized order."""
    paid = _money(sum(p["value"] for p in order.get("payments", [])))
    items_price = _money(sum(i["price"] for i in order.get("items", [])))
    freight = _money(sum(i["freight"] for i in order.get("items", [])))
    invoiced = _money(items_price + freight)
    return {"paid": paid, "items_price": items_price, "freight": freight,
            "invoiced": invoiced, "delta": _money(paid - invoiced)}


def detect_breaks(order: dict) -> list[dict]:
    """Return the break list for one normalized order (possibly empty)."""
    t = totals(order)
    status = order.get("status", "")
    breaks: list[dict] = []

    if order.get("items") and t["paid"] > 0 and status != "canceled" and abs(t["delta"]) >= CENT:
        breaks.append({"code": "B1", "delta": t["delta"],
                       "detail": f"Billing R$ {t['paid']:.2f} vs warehouse R$ {t['invoiced']:.2f} (delta R$ {t['delta']:+.2f})."})
    if status == "canceled" and t["paid"] > 0:
        breaks.append({"code": "B2", "refund_owed": t["paid"],
                       "detail": f"Order canceled; R$ {t['paid']:.2f} captured and not refunded."})
    if status not in ("canceled",) and t["paid"] > 0 and not order.get("items"):
        breaks.append({"code": "B3", "amount_at_risk": t["paid"],
                       "detail": f"R$ {t['paid']:.2f} captured; warehouse holds no items for this order."})
    delivered = _parse_date(order.get("delivered_customer_date"))
    estimated = _parse_date(order.get("estimated_delivery_date"))
    if status == "delivered" and delivered and estimated and delivered > estimated:
        days = (delivered - estimated).days
        breaks.append({"code": "B4", "days_late": days,
                       "detail": f"Delivered {days} day(s) after the estimated date ({estimated.isoformat()} -> {delivered.isoformat()})."})
    carrier = _parse_date(order.get("delivered_carrier_date"))
    worst_over = 0
    for item in order.get("items", []):
        limit = _parse_date(item.get("shipping_limit_date"))
        if carrier and limit and carrier > limit:
            worst_over = max(worst_over, (carrier - limit).days)
    if worst_over:
        breaks.append({"code": "B5", "days_over": worst_over,
                       "detail": f"Handed to the carrier {worst_over} day(s) after the seller shipping-limit date."})
    if status == "delivered" and t["paid"] == 0:
        breaks.append({"code": "B6", "amount_at_risk": t["invoiced"],
                       "detail": f"Delivered with no payment; warehouse invoice R$ {t['invoiced']:.2f}."})
    seqs = [p.get("sequential") for p in order.get("payments", [])]
    if len(seqs) != len(set(seqs)):
        breaks.append({"code": "B7", "detail": "A payment sequence number repeats on this order."})
    if order.get("orphan"):
        breaks.append({"code": "B8", "detail": "This record references an order_id found in no other system."})
    return breaks


def _age_points(order: dict) -> int:
    purchase = _parse_date(order.get("purchase_date"))
    if not purchase:
        return 0
    days = max(0, (CLOSE_DATE - purchase).days)
    return min(10, days // 30)


def _value_points(order: dict) -> int:
    paid = totals(order)["paid"]
    if paid >= 2000:
        return 10
    if paid >= 500:
        return 5
    return 0


def score_order(order: dict, breaks: list[dict]) -> tuple[int, list[dict]]:
    """0-100 score with disclosed parts. Returns (score, score_parts)."""
    parts: list[dict] = []
    total = 0
    for b in breaks:
        code = b["code"]
        base = BASE_SCORE[code]
        extra = 0
        if code == "B1":
            extra = min(25, int(abs(b["delta"]) * 2)) + (5 if abs(b["delta"]) >= 10 else 0)
        elif code == "B4":
            extra = min(12, b["days_late"])
        elif code == "B5":
            extra = min(10, b["days_over"])
        parts.append({"code": code, "base": base, "extra": extra,
                      "subtotal": base + extra})
        total += base + extra
    age = _age_points(order)
    value = _value_points(order)
    if age:
        parts.append({"code": "AGE", "base": age, "extra": 0, "subtotal": age})
    if value:
        parts.append({"code": "VALUE", "base": value, "extra": 0, "subtotal": value})
    total += age + value
    return min(100, total), parts


def money_at_stake(order: dict, breaks: list[dict]) -> float:
    """BRL directly at stake: unpaid/owed amounts, else the mismatch delta."""
    t = totals(order)
    codes = {b["code"] for b in breaks}
    if "B2" in codes:
        return t["paid"]
    if "B3" in codes:
        return t["paid"]
    if "B6" in codes:
        return t["invoiced"]
    if "B1" in codes:
        return abs(t["delta"])
    return 0.0


def route_order(order: dict, breaks: list[dict], score: int) -> str:
    codes = {b["code"] for b in breaks}
    if score >= ESCALATE_SCORE:
        return "ESCALATE"
    if codes & {"B2", "B3"} and money_at_stake(order, breaks) >= ESCALATE_MONEY:
        return "ESCALATE"
    if score >= REVIEW_SCORE:
        return "REVIEW"
    return "MONITOR"


def recommended_action(order: dict, breaks: list[dict]) -> tuple[str, str]:
    """(action, one-line instruction) from the highest-priority break."""
    codes = {b["code"] for b in breaks}
    for code in PRIORITY:
        if code not in codes:
            continue
        b = next(x for x in breaks if x["code"] == code)
        t = totals(order)
        if code == "B2":
            return ("ISSUE_REFUND",
                    f"Refund R$ {t['paid']:.2f} to the customer; the order was canceled after capture.")
        if code == "B3":
            return ("CHASE_WAREHOUSE",
                    f"Confirm with the warehouse whether R$ {t['paid']:.2f} of goods shipped; hold any further capture.")
        if code == "B6":
            return ("COLLECT_OR_WRITE_OFF",
                    f"Collect R$ {t['invoiced']:.2f} from the customer, or write it off with approval.")
        if code == "B7":
            return ("REVERSE_DUPLICATE",
                    "Reverse the duplicated payment sequence before the next settlement run.")
        if code == "B1":
            return ("POST_CORRECTION",
                    f"Post the correcting journal below for the R$ {b['delta']:+.2f} difference; do not re-bill the customer.")
        if code == "B4":
            return ("LOG_SLA_BREACH",
                    f"Log the {b['days_late']}-day late delivery; claim the freight credit from the carrier if the contract allows.")
        if code == "B5":
            return ("LOG_SLA_BREACH",
                    f"Log the {b['days_over']}-day ship-limit breach with the seller; no money moves on this break alone.")
        if code == "B8":
            return ("TRACE_ORPHAN",
                    "Trace the orphan record to its source system and re-key it to a real order.")
    return ("NO_ACTION", "The three systems agree; file the order with the close.")


def correction_draft(order: dict, breaks: list[dict]) -> list[dict]:
    """Human-gated correction drafts: journal lines for money breaks,
    chase/SLA notes for the rest. Nothing is posted automatically."""
    drafts: list[dict] = []
    t = totals(order)
    for b in breaks:
        code = b["code"]
        if code == "B1" and abs(b["delta"]) >= CENT:
            d = b["delta"]
            if d > 0:  # paid more than invoiced: over-collection
                drafts.append({"code": "B1", "kind": "journal",
                               "title": "Correcting journal — over-collection",
                               "lines": [f"Dr Cash / clearing R$ {d:.2f}",
                                         f"Cr Customer refunds payable R$ {d:.2f}"],
                               "note": "Customer paid more than the warehouse invoiced. Hold the excess as a refund payable; do not recognize it as revenue."})
            else:  # paid less than invoiced: under-collection
                drafts.append({"code": "B1", "kind": "journal",
                               "title": "Correcting journal — under-collection",
                               "lines": [f"Dr Accounts receivable R$ {abs(d):.2f}",
                                         f"Cr Sales revenue R$ {abs(d):.2f}"],
                               "note": "Customer paid less than the warehouse invoiced. Recognize the receivable; chase only if the amount clears the R$10 materiality bar."})
        elif code == "B2":
            drafts.append({"code": "B2", "kind": "journal",
                           "title": "Refund journal — canceled order",
                           "lines": [f"Dr Refunds payable R$ {t['paid']:.2f}",
                                     f"Cr Cash R$ {t['paid']:.2f}"],
                           "note": "Refund the captured payment in full; attach the cancellation record from the order book."})
        elif code == "B3":
            drafts.append({"code": "B3", "kind": "chase",
                           "title": "Warehouse chase note",
                           "lines": [f"Order {order['order_id'][:8]}…: R$ {t['paid']:.2f} captured, zero items in the warehouse system.",
                                     "Ask: confirm shipment or confirm the order never left the warehouse.",
                                     "If nothing shipped, refund and cancel; if it shipped, re-key the items."],
                           "note": "Do not refund until the warehouse confirms nothing shipped."})
        elif code == "B4":
            drafts.append({"code": "B4", "kind": "sla_note",
                           "title": "Late-delivery SLA note",
                           "lines": [f"Delivered {b['days_late']} day(s) late against the promised date.",
                                     "File with the carrier claim if the freight contract carries a late-delivery credit."],
                           "note": "No ledger entry; this break is service, not money."})
        elif code == "B5":
            drafts.append({"code": "B5", "kind": "sla_note",
                           "title": "Ship-limit breach note",
                           "lines": [f"Parcel reached the carrier {b['days_over']} day(s) after the seller shipping-limit date.",
                                     "Raise with the seller; repeated breaches go on the seller scorecard."],
                           "note": "No ledger entry; this break is service, not money."})
        elif code == "B6":
            drafts.append({"code": "B6", "kind": "journal",
                           "title": "Unpaid delivery — collection or write-off",
                           "lines": [f"Dr Accounts receivable R$ {t['invoiced']:.2f}",
                                     f"Cr Sales revenue R$ {t['invoiced']:.2f}"],
                           "note": "Goods delivered, no payment. Collect, or write off with approval — do not silently absorb it."})
        elif code == "B7":
            drafts.append({"code": "B7", "kind": "journal",
                           "title": "Duplicate payment reversal",
                           "lines": ["Dr Customer refunds payable (duplicated sequence amount)",
                                     "Cr Cash (duplicated sequence amount)"],
                           "note": "Reverse the duplicated sequence at its exact value before the next settlement run."})
    return drafts
