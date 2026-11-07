import type { ReconDeskData } from "../types";
import { brl } from "../rules";

/** Methodology: disclosed weights, thresholds, data provenance, caveats. */
export default function MethodologyView({ data }: { data: ReconDeskData }) {
  const f = data.summary.findings;
  const cfg = data.summary.config;
  const ev = data.summary.eval;
  const corpus = f.corpus;
  return (
    <div>
      <div className="card">
        <h2>Methodology</h2>
        <p className="muted">
          Everything on this page is disclosed: how each break is found, how an order is scored,
          where the data came from, and what the numbers do and do not prove.
        </p>
        <h3>How a break is found</h3>
        <p>
          Each of the 8 rules is an exact comparison across the three systems, on cent-rounded
          BRL. B1 fires when billing and warehouse totals differ by ≥ R$0.01 (and a payment
          exists and the order is not canceled — a canceled order is B2, an unpaid delivery is
          B6, so one money problem is never counted twice). B4/B5 compare dates, not amounts.
          B7 checks for a repeated payment sequence; B8 flags records with no matching order.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>Break</th>
              <th>Base score</th>
              <th>Extra</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>B1 Amount mismatch</td><td>10</td><td>+ min(25, |delta| × 2), +5 if |delta| ≥ R$10</td></tr>
            <tr><td>B2 Canceled but paid</td><td>45</td><td>—</td></tr>
            <tr><td>B3 Paid but never shipped</td><td>40</td><td>—</td></tr>
            <tr><td>B4 Late delivery</td><td>8</td><td>+ min(12, days late)</td></tr>
            <tr><td>B5 Shipped after the limit date</td><td>5</td><td>+ min(10, days over)</td></tr>
            <tr><td>B6 Delivered but unpaid</td><td>45</td><td>—</td></tr>
            <tr><td>B7 Duplicate payment</td><td>30</td><td>—</td></tr>
            <tr><td>B8 Orphan record</td><td>25</td><td>—</td></tr>
            <tr><td>Age (purchase → close {cfg.close_date})</td><td>0–10</td><td>+1 per 30 days open, capped at 10</td></tr>
            <tr><td>Value (amount paid)</td><td>0 / 5 / 10</td><td>≥ R$500 → 5 · ≥ R$2,000 → 10</td></tr>
          </tbody>
        </table>
        <h3>How an order is routed</h3>
        <p>
          Score = sum of break bases and extras + age + value, capped at 100. Route: score ≥{" "}
          {cfg.escalate_score} → ESCALATE · a B2 or B3 break holding ≥ {brl(cfg.escalate_money_brl)}{" "}
          → ESCALATE · score ≥ {cfg.review_score} → REVIEW · otherwise MONITOR. No order in this
          queue reaches the 75-point bar — all {f.routes.ESCALATE ?? 0} escalations come from the
          money rule, which is the point: a R$1,395.76 unrefunded cancellation outranks a
          one-cent mismatch, however the points add up. One recommended action per order, from
          the highest-priority break (money first: B2 → B3 → B6 → B7 → B1 → B4 → B5 → B8).
          Estimated close effort: {f.estimated_hours} hours at 15 minutes per break order.
        </p>
        <h3>Golden-set evaluation</h3>
        <p>
          {ev.golden_n} hand-labeled orders, read from the actual Olist rows: break-code accuracy{" "}
          {Math.round(ev.code_accuracy * 100)}%, route accuracy {Math.round(ev.route_accuracy * 100)}%,
          action accuracy {Math.round(ev.action_accuracy * 100)}%. The rules are exact
          comparisons, not tuned thresholds, so this eval is a regression check on the
          implementation — any miss would be a bug, not a calibration result.{" "}
          {data.summary.eval_misses.length === 0
            ? "No misses on the golden set."
            : `${data.summary.eval_misses.length} misses, listed in the repo README.`}
        </p>
        <h3>Data provenance</h3>
        <p>
          {corpus.source}. Full corpus: {corpus.orders.toLocaleString("en-US")} orders,{" "}
          {corpus.payments_rows.toLocaleString("en-US")} payment rows,{" "}
          {corpus.items_rows.toLocaleString("en-US")} item rows. {corpus.window_note} The desk
          replays Q4 2017 purchases ({f.window_orders.toLocaleString("en-US")} orders,{" "}
          {brl(f.window_total_brl)}) with the close as of {f.close_date}; the web queue is the
          top {f.queue_orders} break orders by score. Northgate Marketplace is fictional; the
          Olist rows are real.
        </p>
        <h3>Caveats, kept honest</h3>
        <ul className="answer-text">
          <li>
            The queue is money-weighted by design: B2/B3 breaks score 40–45, so the top 150 is
            mostly refunds and paid-not-shipped orders ({f.actions.ISSUE_REFUND ?? 0} refunds,{" "}
            {f.actions.CHASE_WAREHOUSE ?? 0} warehouse chases). The full corpus tells the other
            story: {corpus.breaks_by_code.B4?.toLocaleString("en-US")} late deliveries and{" "}
            {corpus.breaks_by_code.B5?.toLocaleString("en-US")} ship-limit breaches — service
            breaks that score low because no money moves on them.
          </li>
          <li>
            B1&rsquo;s median mismatch in Q4 is a single cent — most amount breaks are rounding
            noise between systems, not fraud. The score reflects that: a R$0.01 delta scores
            10 + age, which routes MONITOR.
          </li>
          <li>
            The corpus contains exactly one delivered-but-unpaid order (B6) and zero duplicate
            payments or orphan records. Those rules are still checked on every order; their
            golden-set entries are synthetic and labeled as such.
          </li>
          <li>
            Delivery dates after the close date exist in the data (a few orders delivered in
            2018, one 153 days late). They are scored as the data states them — the close is a
            replay date, not a filter.
          </li>
          <li>
            Zero LLM calls. The Python pipeline and the in-browser TypeScript mirror agree on all{" "}
            {data.vectors.vectors.length} shared test vectors.
          </li>
        </ul>
      </div>
    </div>
  );
}
