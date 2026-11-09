export type Check = { check: string; passed: boolean; detail: string };
export type Direction = {
  kind: string;
  sender?: string;
  sender_role?: string;
  applied: boolean;
  why: string;
  value?: number | null;
  sector?: string | null;
  quote?: string | null;
};
export type Anomaly = { anomaly: string; cause?: string | null; owner_role: string; explanation?: string };
export type CellPlan = { cell: string; available: number; letters: number; holdout: number; value_per_letter: number };
export type LedgerEntry = { seq: number; at: string; actor: string; kind: string; reason: string; hash: string };

export type Sample = {
  round: number;
  drop_date: string;
  sha256: string;
  brief: string | null;
  checks: Check[];
  plan: {
    letters: number;
    holdout: number;
    cost: number;
    budget: number;
    holdout_share: number;
    cells: CellPlan[];
    creative_shares: Record<string, number>;
    excluded_sectors: string[];
    expected_incremental_value: number;
    paused: boolean;
  };
  directions: Direction[];
  anomalies: Anomaly[];
  suppressed: Record<string, number>;
  eligible: number;
  ledger: LedgerEntry[];
  ledger_intact: boolean;
};

export type Policy = {
  id: string;
  name: string;
  profit: number;
  profit_min: number;
  profit_max: number;
  vs_today: number;
  breaches: number;
  minutes: number;
};

export type RoundRow = {
  round: number;
  drop_date: string;
  letters: number;
  spend: number;
  exp_incremental_value: number;
  attributed_funded: number;
  mail_caused_funded: number;
  person_minutes: number;
  paused: boolean;
};

export type ConsoleData = {
  seeds: number;
  sample: Sample;
  policies: Policy[];
  rounds: RoundRow[];
  agent: Record<string, number | null>;
  dev_vs_today: number;
};
