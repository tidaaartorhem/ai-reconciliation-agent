import { useMemo, useState } from "react";
import type { ReconDeskData, Route } from "../types";
import { OrderCard } from "./shared";

type RouteFilter = "all" | Route;
type BreakFilter = "all" | string;

const ROUTES: Route[] = ["ESCALATE", "REVIEW", "MONITOR"];

/** The break queue: the top 150 Q4 2017 break orders by score. */
export default function QueueView({ data }: { data: ReconDeskData }) {
  const [route, setRoute] = useState<RouteFilter>("all");
  const [code, setCode] = useState<BreakFilter>("all");
  const [query, setQuery] = useState("");

  const codes = useMemo(
    () => [...new Set(data.orders.flatMap((o) => o.break_codes))].sort(),
    [data],
  );

  const shown = data.orders.filter(
    (o) =>
      (route === "all" || o.route === route) &&
      (code === "all" || o.break_codes.includes(code as never)) &&
      (query.trim() === "" ||
        (o.order_id + " " + o.status + " " + (o.customer_state ?? "") + " " + o.action)
          .toLowerCase()
          .includes(query.trim().toLowerCase())),
  );

  return (
    <div>
      <div className="card">
        <h2>Break queue</h2>
        <p className="muted">
          {shown.length} of {data.orders.length} queued orders shown — the highest-scoring breaks
          from {data.summary.findings.window_break_orders.toLocaleString("en-US")} break orders in
          Q4 2017. ESCALATE means money ≥ R$500 on a canceled-paid or paid-not-shipped break (or
          a 75+ score) — refund or chase first. REVIEW means a real break to clear before the
          close. Every correction draft needs human approval — nothing is posted until a person
          signs off.
        </p>
        <div className="filters">
          <div className="seg">
            {(["all", ...ROUTES] as const).map((f) => (
              <button key={f} className={route === f ? "active" : ""} onClick={() => setRoute(f)}>
                {f === "all"
                  ? `All (${data.orders.length})`
                  : `${f} (${data.orders.filter((t) => t.route === f).length})`}
              </button>
            ))}
          </div>
          <div className="filter-row">
            <select value={code} onChange={(e) => setCode(e.target.value)} aria-label="Break filter">
              <option value="all">All break types</option>
              {codes.map((c) => (
                <option key={c} value={c}>
                  {c} — {data.breakbook.breaks.find((b) => b.code === c)?.name ?? c}
                </option>
              ))}
            </select>
            <input
              type="search"
              placeholder="Search orders…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>
      </div>
      {shown.map((o) => (
        <OrderCard key={o.order_id} o={o} />
      ))}
    </div>
  );
}
