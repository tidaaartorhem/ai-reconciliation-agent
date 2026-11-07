export type Route = "ESCALATE" | "REVIEW" | "MONITOR";
export type BreakCode = "B1" | "B2" | "B3" | "B4" | "B5" | "B6" | "B7" | "B8";

export interface Payment {
  type: string;
  sequential: number;
  installments: number;
  value: number;
}

export interface Item {
  price: number;
  freight: number;
  seller_id: string;
  shipping_limit_date: string | null;
}

/** Normalized flat order — the shape the Python engine and the TS mirror share. */
export interface FlatOrder {
  order_id: string;
  customer_id: string;
  customer_state: string | null;
  purchase_date: string | null;
  approved_date?: string | null;
  status: string;
  payments: Payment[];
  items: Item[];
  delivered_carrier_date: string | null;
  delivered_customer_date: string | null;
  estimated_delivery_date: string | null;
  orphan?: boolean;
}

export interface Break {
  code: BreakCode;
  detail: string;
  delta?: number;
  refund_owed?: number;
  amount_at_risk?: number;
  days_late?: number;
  days_over?: number;
}

export interface ScorePart {
  code: string;
  base: number;
  extra: number;
  subtotal: number;
}

export interface CorrectionDraft {
  code: string;
  kind: "journal" | "chase" | "sla_note";
  title: string;
  lines: string[];
  note: string;
}

export interface OrderRow {
  order_id: string;
  customer_id: string;
  customer_state: string | null;
  purchase_date: string | null;
  status: string;
  billing: { payments: Payment[]; total_paid: number };
  crm: {
    status: string;
    purchase: string | null;
    approved: string | null;
    estimated_delivery: string | null;
  };
  warehouse: {
    items: Item[];
    items_total: number;
    delivered_carrier: string | null;
    delivered_customer: string | null;
  };
  totals: { paid: number; invoiced: number; delta: number };
  breaks: Break[];
  break_codes: BreakCode[];
  score: number;
  score_parts: ScorePart[];
  money_at_stake: number;
  route: Route;
  action: string;
  instruction: string;
  correction_draft: CorrectionDraft[];
  pending_approval: boolean;
}

export interface CorpusStats {
  orders: number;
  payments_rows: number;
  items_rows: number;
  breaks_by_code: Record<string, number>;
  duplicate_payment_orders: number;
  orphan_payments: number;
  orphan_items: number;
  source: string;
  window_note: string;
}

export interface Findings {
  close_date: string;
  window: string;
  queue_orders: number;
  window_orders: number;
  window_total_brl: number;
  window_break_orders: number;
  breaks_by_code: Record<string, number>;
  routes: Record<string, number>;
  actions: Record<string, number>;
  money_at_stake_brl: number;
  money_by_code_brl: Record<string, number>;
  corpus: CorpusStats;
  top_breaks: {
    order_id: string;
    score: number;
    route: Route;
    break_codes: BreakCode[];
    money_at_stake: number;
    status: string;
  }[];
  estimated_hours: number;
}

export interface Summary {
  findings: Findings;
  eval: {
    golden_n: number;
    code_accuracy: number;
    route_accuracy: number;
    action_accuracy: number;
  };
  eval_misses: {
    order_id: string;
    expected_codes: string[];
    got_codes: string[];
    expected_route: string;
    got_route: string;
    expected_action: string;
    got_action: string;
    note: string;
  }[];
  config: {
    escalate_score: number;
    review_score: number;
    escalate_money_brl: number;
    base_score: Record<string, number>;
    close_date: string;
    tolerance_brl: number;
    note: string;
  };
  company: string;
  queue_meta: {
    window: string;
    close_date: string;
    company: string;
    currency: string;
    window_orders: number;
    window_total_brl: number;
    window_break_orders: number;
    queue_n: number;
    corpus: CorpusStats;
  };
  data_note: string;
}

export interface BreakRule {
  code: BreakCode;
  name: string;
  systems: string;
  what: string;
}

export interface Breakbook {
  breaks: BreakRule[];
}

export interface TestVector {
  label: string;
  order: FlatOrder;
  expected_codes: BreakCode[];
  expected_score: number;
  expected_route: Route;
  expected_action: string;
}

export interface Stamp {
  repo: string;
  git_sha: string;
  built_utc: string;
  pipeline: string;
}

export interface ReconDeskData {
  summary: Summary;
  orders: OrderRow[];
  breakbook: Breakbook;
  vectors: { vectors: TestVector[] };
  stamp: Stamp | null;
}
