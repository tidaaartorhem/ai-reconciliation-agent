import { useMemo, useState } from "react";
import {
  brl,
  correctionDraft,
  detectBreaks,
  recommendedAction,
  routeOrder,
  scoreOrder,
  totals,
} from "../rules";
import type { FlatOrder, ReconDeskData } from "../types";
import { RouteBadge, ScoreBar } from "./shared";

/** Paste-an-order: runs the same reconcile + score + route in the browser (TS mirror). */
export default function PasteView({ data }: { data: ReconDeskData }) {
  const [status, setStatus] = useState("delivered");
  const [paid, setPaid] = useState("100.00");
  const [invoiced, setInvoiced] = useState("100.00");
  const [freight, setFreight] = useState("10.00");
  const [items, setItems] = useState("1");
  const [purchase, setPurchase] = useState("2017-11-15");
  const [estimated, setEstimated] = useState("2017-11-25");
  const [delivered, setDelivered] = useState("2017-11-25");
  const [carrier, setCarrier] = useState("2017-11-18");
  const [shipLimit, setShipLimit] = useState("2017-11-20");
  const [dupSeq, setDupSeq] = useState(false);
  const [ran, setRan] = useState(false);

  const order: FlatOrder | null = useMemo(() => {
    const paidN = parseFloat(paid);
    const invN = parseFloat(invoiced);
    const freightN = parseFloat(freight);
    const itemsN = parseInt(items, 10);
    if ([paidN, invN, freightN, itemsN].some((n) => Number.isNaN(n))) return null;
    const price = Math.max(0, invN - freightN);
    const payments =
      paidN > 0
        ? dupSeq
          ? [
              { type: "credit_card", sequential: 1, installments: 1, value: Math.round((paidN / 2) * 100) / 100 },
              { type: "credit_card", sequential: 1, installments: 1, value: Math.round((paidN - paidN / 2) * 100) / 100 },
            ]
          : [{ type: "credit_card", sequential: 1, installments: 1, value: paidN }]
        : [];
    return {
      order_id: "pasted-order",
      customer_id: "pasted-customer",
      customer_state: "SP",
      purchase_date: purchase || null,
      status,
      payments,
      items:
        itemsN > 0
          ? [{ price: Math.round(price * 100) / 100, freight: freightN, seller_id: "seller-1", shipping_limit_date: shipLimit || null }]
          : [],
      delivered_carrier_date: carrier || null,
      delivered_customer_date: delivered || null,
      estimated_delivery_date: estimated || null,
    };
  }, [status, paid, invoiced, freight, items, purchase, estimated, delivered, carrier, shipLimit, dupSeq]);

  const result = useMemo(() => {
    if (!ran || !order) return null;
    const breaks = detectBreaks(order);
    const { score, parts } = scoreOrder(order, breaks);
    const route = routeOrder(order, breaks, score);
    const [action, instruction] = recommendedAction(order, breaks);
    return { breaks, score, parts, route, action, instruction, drafts: correctionDraft(order, breaks), totals: totals(order) };
  }, [ran, order]);

  return (
    <div>
      <div className="card">
        <h2>Paste an order</h2>
        <p className="muted">
          Enter one order&rsquo;s three-system numbers and the in-browser engine — the exact
          TypeScript mirror of the Python pipeline, verified against {data.vectors.vectors.length}{" "}
          shared test vectors — reconciles it, scores it, and drafts the correction. Try the
          defaults (a clean order), then change the billing total to 80.00 to see an amount
          mismatch, set status to canceled to see a refund break, or set items to 0 to see a
          paid-not-shipped break.
        </p>
        <div className="paste-form">
          <label>
            Order status
            <select value={status} onChange={(e) => { setStatus(e.target.value); setRan(false); }}>
              {["delivered", "shipped", "invoiced", "processing", "approved", "canceled", "unavailable", "created"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <div className="filter-row">
            <label>
              Billing total paid (R$)
              <input type="number" step="0.01" value={paid} onChange={(e) => setPaid(e.target.value)} />
            </label>
            <label>
              Warehouse invoice total (R$)
              <input type="number" step="0.01" value={invoiced} onChange={(e) => setInvoiced(e.target.value)} />
            </label>
            <label>
              of which freight (R$)
              <input type="number" step="0.01" value={freight} onChange={(e) => setFreight(e.target.value)} />
            </label>
            <label>
              Item lines
              <input type="number" step="1" min="0" value={items} onChange={(e) => setItems(e.target.value)} />
            </label>
          </div>
          <div className="filter-row">
            <label>
              Purchase date
              <input type="date" value={purchase} onChange={(e) => setPurchase(e.target.value)} />
            </label>
            <label>
              Estimated delivery
              <input type="date" value={estimated} onChange={(e) => setEstimated(e.target.value)} />
            </label>
            <label>
              Delivered to customer
              <input type="date" value={delivered} onChange={(e) => setDelivered(e.target.value)} />
            </label>
          </div>
          <div className="filter-row">
            <label>
              Delivered to carrier
              <input type="date" value={carrier} onChange={(e) => setCarrier(e.target.value)} />
            </label>
            <label>
              Seller shipping-limit date
              <input type="date" value={shipLimit} onChange={(e) => setShipLimit(e.target.value)} />
            </label>
            <label className="check">
              <input type="checkbox" checked={dupSeq} onChange={(e) => setDupSeq(e.target.checked)} />
              Duplicate payment sequence
            </label>
          </div>
          <div>
            <button className="btn primary" onClick={() => order && setRan(true)}>
              Reconcile it
            </button>
          </div>
        </div>
      </div>

      {ran && result && (
        <div className="card match-card">
          <div className="match-head">
            <RouteBadge route={result.route} />
            <ScoreBar value={result.score} />
            <span className="pill neutral">
              {result.breaks.length === 0 ? "clean" : result.breaks.map((b) => b.code).join(" + ")}
            </span>
            <span className="pill gate">human gate required</span>
          </div>
          <div className="match-body">
            <div className="muted small">
              Billing {brl(result.totals.paid)} vs warehouse {brl(result.totals.invoiced)} — delta{" "}
              {result.totals.delta >= 0 ? "+" : "-"}
              {brl(Math.abs(result.totals.delta))}. Score {result.score} ={" "}
              {result.parts.length > 0
                ? result.parts.map((p) => `${p.code} ${p.base}${p.extra ? `+${p.extra}` : ""}`).join(" + ")
                : "no breaks"} (capped at 100).
            </div>
            {result.breaks.length === 0 ? (
              <p className="answer-text">
                The three systems agree on this order. File it with the close — one clean order
                does not clear the book, but this one needs no correction.
              </p>
            ) : (
              <>
                {result.breaks.map((b) => (
                  <div className="clause-row" key={b.code}>
                    <div className="clause-head">
                      <b>{b.code}</b>
                      <span className="pill warn">{b.code}</span>
                    </div>
                    <div className="muted small">{b.detail}</div>
                  </div>
                ))}
                {result.drafts.length > 0 && (
                  <div className="card" style={{ marginTop: 12, background: "#fbfcfe" }}>
                    <h3 style={{ marginTop: 0 }}>Correction draft — pending human approval</h3>
                    <ol className="answer-text" style={{ paddingLeft: 20 }}>
                      {result.drafts.map((d) => (
                        <li key={d.code} style={{ marginBottom: 8 }}>
                          <b>{d.title}</b>
                          {d.lines.map((ln, i) => (
                            <div key={i} className="mono small">{ln}</div>
                          ))}
                          <div className="muted">{d.note}</div>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </>
            )}
            <div className="action-line">
              <b>Recommended action:</b> {result.action.replace(/_/g, " ")} — {result.instruction}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
