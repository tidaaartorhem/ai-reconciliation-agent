# ReconDesk — the three-system reconciliation desk

**Live demo:** https://ai-reconciliation-agent.web.app
**Repo:** https://github.com/tidaaartorhem/ai-reconciliation-agent

Every marketplace runs on three systems that never quite agree: billing says the customer
paid R$368.70, the warehouse invoiced R$700.00, and the order book says the order was
delivered on time. Nobody notices until month-end close, when someone in finance spends
days hunting the breaks across three exports that disagree on amounts, dates, and IDs —
and the breaks that cost real money (a canceled order never refunded, a payment captured
for goods that never shipped) hide among thousands of one-cent rounding differences and
late deliveries that cost nothing.

ReconDesk is the reconciliation desk for Northgate Marketplace, a fictional online
marketplace operator. A LangGraph pipeline (intake → reconcile → score → route → draft →
gate) compares billing, the order book, and the warehouse order by order for the Q4 2017
close, finds the breaks, scores them, and drafts the correction — a journal entry, a
refund, or a warehouse chase note. Every correction is a human-gated draft. Nothing is
posted or sent.

## What it found (Q4 2017 close, as of 2018-01-05)

- **17,848 orders, R$2,852,962.16** in the quarter. **2,702 orders (15.1%)** have at least
  one break. The web queue is the top 150 by score.
- **R$39,549.47 at stake** in the queue: 27 ESCALATE, 123 REVIEW, 0 MONITOR.
- **74 canceled orders were paid and never refunded — R$17,671.22 owed back**, including
  one R$1,395.76 cancellation. 67 orders were paid but never shipped — R$21,588.45 at
  risk, including one R$1,643.64 order. 8 amount mismatches total R$289.80.
- The full 99,441-order corpus tells the other story: **6,534 late deliveries** and
  **5,662 ship-limit breaches** — service breaks that score low because no money moves on
  them — against 637 amount mismatches, 622 canceled-paid, 611 paid-not-shipped, and
  exactly **one** delivered-but-unpaid order. Zero duplicate payments, zero orphan records:
  the ledger is clean on both axes, and the engine still checks them on every order.
- No order reaches the 75-point escalation bar — all 27 escalations come from the money
  rule (a B2/B3 break holding ≥ R$500). That is the point: a R$1,395.76 unrefunded
  cancellation outranks a one-cent mismatch, however the points add up.
- Estimated close effort: **37.5 hours** at 15 minutes per break order.

## How it works

Eight break rules (B1–B8), all exact comparisons on cent-rounded BRL — no LLM calls:

| Break | Rule | Base |
| --- | --- | --- |
| B1 Amount mismatch | \|billing − warehouse invoice\| ≥ R$0.01, payment exists, order not canceled | 10 + min(25, \|delta\|×2), +5 if ≥ R$10 |
| B2 Canceled but paid | status canceled, payment captured | 45 |
| B3 Paid but never shipped | payment captured, zero warehouse items | 40 |
| B4 Late delivery | delivered after the estimated date | 8 + min(12, days late) |
| B5 Shipped after the limit date | to carrier after a seller shipping-limit date | 5 + min(10, days over) |
| B6 Delivered but unpaid | delivered, no payment captured | 45 |
| B7 Duplicate payment | same payment sequence twice on one order | 30 |
| B8 Orphan record | payment/item with no matching order | 25 |

Score = sum of break bases and extras + age (1 per 30 days open, capped at 10) + value
(≥ R$500 → 5, ≥ R$2,000 → 10), capped at 100. Route: score ≥ 75 → ESCALATE; a B2/B3
break holding ≥ R$500 → ESCALATE; score ≥ 40 → REVIEW; otherwise MONITOR. One
recommended action per order, from the highest-priority break (money first: B2 → B3 →
B6 → B7 → B1 → B4 → B5 → B8). B1 is suppressed on canceled orders (the refund
supersedes the mismatch) and on unpaid deliveries (that is B6), so one money problem is
never counted twice.

The UI has four tabs: the break queue (filter by route, break type, or search), the
breakbook (all 8 rules with queue and corpus counts), paste-an-order (the same
reconcile/score/route runs in the browser via the TypeScript mirror), and methodology.

## Data

Real data only: the [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(Kaggle, CC BY 4.0), via the zero-auth mirror at
`github.com/olist/work-at-olist-data` — 99,441 orders, 103,886 payment rows, 112,650
item rows, 99,441 customers. Billing = `order_payments`, order book = `orders` +
`customers`, warehouse = `order_items` + delivery dates. The desk replays Q4 2017
purchases with the close as of 2018-01-05. Northgate Marketplace is fictional; the Olist
rows are real. The 46 MB of source CSVs are not committed — `scripts/fetch_olist.py`
downloads them and derives the committed `data/raw/*.json` (queue, corpus stats,
scoring config, golden set).

## Evaluation

- **Golden set:** 28 hand-labeled orders (labels verified against the raw Olist rows
  printed by the fetch script): break-code accuracy **1.000**, route accuracy **1.000**,
  action accuracy **1.000**. The rules are exact comparisons, not tuned thresholds, so
  this is a regression check on the implementation — any miss would be a bug, not a
  calibration result.
- **Shared Python/TS contract:** `data/test-vectors.json` carries 12 vectors (one per
  break profile + clean cases + synthetic B7/B8 edges). The Python engine and the
  in-browser TypeScript mirror agree on all 12 — codes, scores, routes, and actions.
- **Tests:** 18/18 pytest, 21/21 vitest green.

## Caveats, kept honest

- The queue is money-weighted by design: B2/B3 breaks score 40–45, so the top 150 is
  mostly refunds and warehouse chases. The late-delivery story lives in the corpus
  counts, not the queue.
- B1's median Q4 mismatch is a single cent — most amount breaks are rounding noise
  between systems, not fraud. The score reflects that: a R$0.01 delta routes MONITOR.
- B7/B8 have zero real cases in the corpus. Their golden-set and test-vector entries are
  synthetic and labeled as such.
- A few orders delivered after the close date (one 153 days late). They are scored as the
  data states them — the close is a replay date, not a filter.
- Money is BRL throughout. The B6 golden entry is the single delivered-unpaid order in
  the corpus, from 2016; the B2/B3 medians come from Q4.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/fetch_olist.py   # downloads Olist CSVs, builds data/raw/*.json
.venv/bin/python -m pytest tests/ -q     # 18 passed
.venv/bin/python scripts/build_web.py    # runs the LangGraph pipeline, writes web payloads
cd web && npm run build                  # tsc + prepare-public + vite build
```

Deploy: `firebase deploy --only hosting` (site `ai-reconciliation-agent`,
project `portfolio-3da31`).

## Stack

Python + LangGraph (StateGraph with a sequential fallback when langgraph is not
installed) · TypeScript + React + Vite · Firebase Hosting · zero LLM calls.
