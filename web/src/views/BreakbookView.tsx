import type { ReconDeskData } from "../types";
import { brl } from "../rules";

/** The breakbook: the 8 break rules, with counts measured on this run. */
export default function BreakbookView({ data }: { data: ReconDeskData }) {
  const f = data.summary.findings;
  const corpus = f.corpus;
  return (
    <div>
      <div className="card">
        <h2>The breakbook</h2>
        <p className="muted">
          Eight ways billing, the order book, and the warehouse disagree — each an exact
          comparison, no judgment calls. Counts are measured on this Q4 2017 queue ({f.queue_orders}{" "}
          orders) and on the full 99,441-order corpus.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>Break</th>
              <th>Systems</th>
              <th>In queue</th>
              <th>In full corpus</th>
              <th>Money (queue)</th>
            </tr>
          </thead>
          <tbody>
            {data.breakbook.breaks.map((r) => (
              <tr key={r.code}>
                <td>
                  <b>{r.name}</b>
                  <div className="muted small">{r.what}</div>
                </td>
                <td>{r.systems}</td>
                <td>{f.breaks_by_code[r.code] ?? 0}</td>
                <td>{corpus.breaks_by_code[r.code] ?? 0}</td>
                <td>{f.money_by_code_brl[r.code] ? brl(f.money_by_code_brl[r.code]) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          B7 (duplicate payment) and B8 (orphan record) have zero real cases in the corpus — the
          ledger is clean on both axes, and the engine still checks them on every order. Their
          golden-set entries are synthetic and labeled as such.
        </p>
      </div>
      {data.breakbook.breaks.map((r) => (
        <div className="card" key={r.code}>
          <div className="match-head">
            <b>
              {r.code} — {r.name}
            </b>
            <span className="pill neutral">{r.systems}</span>
          </div>
          <p>{r.what}</p>
          <p className="muted">
            Queue: {f.breaks_by_code[r.code] ?? 0} orders · full corpus:{" "}
            {corpus.breaks_by_code[r.code] ?? 0} orders
            {f.money_by_code_brl[r.code]
              ? ` · ${brl(f.money_by_code_brl[r.code])} at stake in this queue`
              : ""}
            .
          </p>
        </div>
      ))}
    </div>
  );
}
