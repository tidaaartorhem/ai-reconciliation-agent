"""ReconDesk LangGraph pipeline.

StateGraph: intake -> reconcile -> score_breaks -> route -> draft_correction
             -> gate

- intake:           load the Q4 2017 break queue + scoring config.
- reconcile:        detect_breaks() per order (breaks.py): billing vs
                    warehouse amounts, canceled-paid, paid-not-shipped,
                    late delivery, ship-limit breach, unpaid delivery,
                    duplicate payment, orphan records.
- score_breaks:     0-100 score with disclosed parts; money at stake.
- route:            ESCALATE / REVIEW / MONITOR (disclosed bars).
- draft_correction: one recommended action per order + human-gated
                    correction drafts (journal lines / chase notes).
- gate:             export pack; every correction is a draft pending
                    human approval; nothing is posted or sent.
"""
from __future__ import annotations

from typing import Any

from .breaks import (correction_draft, detect_breaks, money_at_stake,
                     recommended_action, route_order, score_order)
from .data import load_config, load_queue


def node_intake(state: dict) -> dict:
    queue = load_queue()
    return {
        **state,
        "orders": queue["orders"],
        "queue_meta": {k: v for k, v in queue.items() if k != "orders"},
        "config": load_config(),
    }


def node_reconcile(state: dict) -> dict:
    reconciled = []
    for o in state["orders"]:
        breaks = detect_breaks(o)
        reconciled.append({**o, "breaks": breaks,
                           "break_codes": [b["code"] for b in breaks]})
    return {**state, "orders": reconciled}


def node_score_breaks(state: dict) -> dict:
    scored = []
    for o in state["orders"]:
        score, parts = score_order(o, o["breaks"])
        scored.append({**o, "score": score, "score_parts": parts,
                       "money_at_stake": money_at_stake(o, o["breaks"])})
    return {**state, "orders": scored}


def node_route(state: dict) -> dict:
    routed = []
    for o in state["orders"]:
        routed.append({**o, "route": route_order(o, o["breaks"], o["score"])})
    return {**state, "orders": routed}


def node_draft_correction(state: dict) -> dict:
    drafted = []
    for o in state["orders"]:
        action, instruction = recommended_action(o, o["breaks"])
        drafted.append({**o, "action": action, "instruction": instruction,
                        "correction_draft": correction_draft(o, o["breaks"])})
    return {**state, "orders": drafted}


def node_gate(state: dict) -> dict:
    pack = []
    for o in state["orders"]:
        paid = round(sum(p["value"] for p in o["payments"]), 2)
        invoiced = round(sum(i["price"] + i["freight"] for i in o["items"]), 2)
        pack.append({
            "order_id": o["order_id"],
            "customer_id": o["customer_id"],
            "customer_state": o["customer_state"],
            "purchase_date": o["purchase_date"],
            "status": o["status"],
            "billing": {"payments": o["payments"], "total_paid": paid},
            "crm": {"status": o["status"], "purchase": o["purchase_date"],
                    "approved": o.get("approved_date"),
                    "estimated_delivery": o.get("estimated_delivery_date")},
            "warehouse": {"items": o["items"], "items_total": invoiced,
                          "delivered_carrier": o.get("delivered_carrier_date"),
                          "delivered_customer": o.get("delivered_customer_date")},
            "totals": {"paid": paid, "invoiced": invoiced,
                       "delta": round(paid - invoiced, 2)},
            "breaks": o["breaks"],
            "break_codes": o["break_codes"],
            "score": o["score"],
            "score_parts": o["score_parts"],
            "money_at_stake": o["money_at_stake"],
            "route": o["route"],
            "action": o["action"],
            "instruction": o["instruction"],
            "correction_draft": o["correction_draft"],
            "pending_approval": True,
        })
    return {**state, "export_pack": pack}


NODES = [node_intake, node_reconcile, node_score_breaks,
         node_route, node_draft_correction, node_gate]


def build_graph():
    """Return a compiled LangGraph StateGraph; fall back to a sequential
    runner when langgraph is not installed (same node order, same state)."""
    try:
        from langgraph.graph import StateGraph  # type: ignore

        g: Any = StateGraph(dict)
        prev = None
        for fn in NODES:
            name = fn.__name__.replace("node_", "")
            g.add_node(name, fn)
            if prev:
                g.add_edge(prev, name)
            else:
                g.set_entry_point(name)
            prev = name
        g.add_edge(prev, "__end__")
        return g.compile()
    except ImportError:
        return None


def run() -> dict:
    graph = build_graph()
    if graph is not None:
        return graph.invoke({})
    state: dict = {}
    for fn in NODES:
        state = fn(state)
    return state
