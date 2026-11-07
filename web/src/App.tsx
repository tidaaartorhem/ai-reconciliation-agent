import { useState } from "react";
import { useReconDeskData } from "./data";
import QueueView from "./views/QueueView";
import BreakbookView from "./views/BreakbookView";
import PasteView from "./views/PasteView";
import MethodologyView from "./views/MethodologyView";
import "./styles.css";

const REPO_URL = "https://github.com/tidaaartorhem/ai-reconciliation-agent";
const LIVE_URL = "https://ai-reconciliation-agent.web.app";

type Tab = "queue" | "breakbook" | "paste" | "methodology";

const TABS: { id: Tab; label: string }[] = [
  { id: "queue", label: "Break queue" },
  { id: "breakbook", label: "Breakbook" },
  { id: "paste", label: "Paste an order" },
  { id: "methodology", label: "Methodology" },
];

export default function App() {
  const { data, error } = useReconDeskData();
  const [tab, setTab] = useState<Tab>("queue");

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>
            <span className="mark">Rc</span>ReconDesk
          </h1>
          <p className="sub">
            The three-system reconciliation desk for Northgate Marketplace: billing, order book,
            and warehouse, compared order by order for the Q4 2017 close. Every break gets a
            score, a route, and a human-gated correction draft — nothing is posted without
            approval.
          </p>
          <div className="badges">
            <span className="badge neutral">
              <a href={REPO_URL} target="_blank" rel="noreferrer">
                GitHub repo
              </a>
            </span>
            <span className="badge neutral">
              <a href={LIVE_URL} target="_blank" rel="noreferrer">
                Live site
              </a>
            </span>
          </div>
        </div>
      </header>

      <div className="disclosure banner">
        <b>Deterministic, no LLM.</b> Each break is an exact comparison: billing total vs
        warehouse invoice, canceled vs captured, paid vs shipped, delivered vs promised. Order
        score 0–100 (break bases + age + value, capped at 100). Route: score ≥75 ESCALATE · a
        canceled-paid or paid-not-shipped break holding ≥ R$500 ESCALATE · score ≥40 REVIEW ·
        otherwise MONITOR. The in-browser reconciler mirrors the Python pipeline exactly.
      </div>

      {error && <div className="card error">Failed to load data: {error}</div>}
      {!data && !error && <div className="card">Loading…</div>}

      {data && (
        <>
          <div className="stat-row">
            {(
              [
                ["ESCALATE", "bad", data.summary.findings.routes.ESCALATE ?? 0],
                ["REVIEW", "warn", data.summary.findings.routes.REVIEW ?? 0],
                ["MONITOR", "ok", data.summary.findings.routes.MONITOR ?? 0],
              ] as const
            ).map(([label, cls, n]) => (
              <div className="card stat" key={label}>
                <div className="stat-num">{n}</div>
                <div className={`pill ${cls}`}>{label}</div>
              </div>
            ))}
            <div className="card stat">
              <div className="stat-num">
                R$ {data.summary.findings.money_at_stake_brl.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="muted small">
                money at stake across the {data.summary.findings.queue_orders}-order queue
              </div>
            </div>
            <div className="card stat">
              <div className="stat-num">{data.summary.findings.window_break_orders.toLocaleString("en-US")}</div>
              <div className="muted small">
                of {data.summary.findings.window_orders.toLocaleString("en-US")} Q4 2017 orders
                have at least one break ({((data.summary.findings.window_break_orders / data.summary.findings.window_orders) * 100).toFixed(1)}%)
              </div>
            </div>
            <div className="card stat">
              <div className="stat-num">{data.summary.findings.estimated_hours}h</div>
              <div className="muted small">estimated close effort (15 min per break order)</div>
            </div>
          </div>

          <div className="tabs">
            {TABS.map((t) => (
              <button
                key={t.id}
                className={tab === t.id ? "active" : ""}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "queue" && <QueueView data={data} />}
          {tab === "breakbook" && <BreakbookView data={data} />}
          {tab === "paste" && <PasteView data={data} />}
          {tab === "methodology" && <MethodologyView data={data} />}

          <footer className="footer muted small">
            {data.summary.data_note} Built{" "}
            {data.stamp ? `from ${data.stamp.git_sha} at ${data.stamp.built_utc}` : "locally"} ·
            no LLMs were used.
          </footer>
        </>
      )}
    </div>
  );
}
