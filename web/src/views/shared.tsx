import { useState } from "react";
import type { Break, OrderRow, Route } from "../types";
import { BREAK_NAMES, brl } from "../rules";

const ROUTE_CLASS: Record<Route, string> = {
  ESCALATE: "bad",
  REVIEW: "warn",
  MONITOR: "ok",
};

export function RouteBadge({ route }: { route: Route }) {
  return <span className={`pill ${ROUTE_CLASS[route]}`}>{route}</span>;
}

export function ScoreBar({ value }: { value: number }) {
  const cls = value >= 75 ? "bad" : value >= 40 ? "warn" : "ok";
  return (
    <span className="confbar" title={`${value}`}>
      <span className="confbar-track">
        <span className={`confbar-fill ${cls}`} style={{ width: `${Math.min(100, value)}%` }} />
      </span>
      <span className="confbar-num">{value}</span>
    </span>
  );
}

function BreakRow({ b }: { b: Break }) {
  return (
    <div className="clause-row">
      <div className="clause-head">
        <b>
          {b.code} — {BREAK_NAMES[b.code]}
        </b>
        <span className="pill warn">{b.code}</span>
      </div>
      <div className="muted small">{b.detail}</div>
    </div>
  );
}

export function OrderCard({ o }: { o: OrderRow }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card match-card">
      <div className="match-head">
        <span className="req-id">#{o.order_id.slice(0, 8)}</span>
        <RouteBadge route={o.route} />
        <ScoreBar value={o.score} />
        <span className="pill neutral">
          {o.break_codes.join(" + ")}
        </span>
        <span className="pill gate">human gate required</span>
      </div>
      <p className="req-text">
        <b>
          {o.status} · {o.customer_state ?? "—"} · purchased {o.purchase_date}
        </b>
      </p>
      <div className="muted small" style={{ marginBottom: 8 }}>
        Billing {brl(o.totals.paid)} vs warehouse {brl(o.totals.invoiced)} — delta{" "}
        {o.totals.delta >= 0 ? "+" : "-"}
        {brl(Math.abs(o.totals.delta))} · {o.money_at_stake > 0 ? `${brl(o.money_at_stake)} at stake` : "no money at stake"}
      </div>
      <div className="action-line">
        <b>Recommended action:</b> {o.action.replace(/_/g, " ")} — {o.instruction}
      </div>
      <button className="btn" style={{ marginTop: 10 }} onClick={() => setOpen(!open)}>
        {open ? "Hide three-system review" : `Show three-system review (${o.breaks.length} break${o.breaks.length === 1 ? "" : "s"})`}
      </button>
      {open && (
        <div style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th>System</th>
                <th>What it says</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><b>Billing</b></td>
                <td>
                  {o.billing.payments.length} payment{o.billing.payments.length === 1 ? "" : "s"} totalling{" "}
                  {brl(o.billing.total_paid)} (
                  {o.billing.payments.map((p) => `${p.type} ×${p.installments}`).join(", ") || "none"})
                </td>
              </tr>
              <tr>
                <td><b>Order book</b></td>
                <td>
                  status {o.status} · purchased {o.crm.purchase}
                  {o.crm.approved ? ` · approved ${o.crm.approved}` : ""} · estimated delivery{" "}
                  {o.crm.estimated_delivery ?? "—"}
                </td>
              </tr>
              <tr>
                <td><b>Warehouse</b></td>
                <td>
                  {o.warehouse.items.length} item{o.warehouse.items.length === 1 ? "" : "s"} totalling{" "}
                  {brl(o.warehouse.items_total)} (incl. freight)
                  {o.warehouse.delivered_carrier ? ` · to carrier ${o.warehouse.delivered_carrier}` : ""}{" "}
                  {o.warehouse.delivered_customer ? `· to customer ${o.warehouse.delivered_customer}` : ""}
                </td>
              </tr>
            </tbody>
          </table>
          {o.breaks.map((b) => (
            <BreakRow key={b.code} b={b} />
          ))}
          <div className="muted small" style={{ margin: "8px 0" }}>
            Score {o.score} ={" "}
            {o.score_parts.map((p) => `${p.code} ${p.base}${p.extra ? `+${p.extra}` : ""}`).join(" + ")} (capped at 100).
          </div>
          {o.correction_draft.length > 0 && (
            <div className="card" style={{ marginTop: 12, background: "#fbfcfe" }}>
              <h3 style={{ marginTop: 0 }}>Correction draft — pending human approval</h3>
              <p className="muted small">
                Nothing here is posted or sent. A person reviews each draft, edits as needed, and
                approves before anything hits the ledger or the customer.
              </p>
              <ol className="answer-text" style={{ paddingLeft: 20 }}>
                {o.correction_draft.map((d) => (
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
        </div>
      )}
    </div>
  );
}
