"""Building the mailing file from the plan, and the checks it must pass before anyone is asked to approve it.

Selection inside a cell is random (a keyed hash of company and round), so the holdout is a fair comparison and the
same plan always yields the same file. The file's sha256 is what a person approves and what the printer receives.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from mailagent import rules, settings
from mailagent.optimise import assign_cells, cell_name
from mailagent.schema import Check, Creative, Plan


def keyed_hash(ids: np.ndarray, salt: int) -> np.ndarray:
    """splitmix64 of id xor salt: a stable pseudo-random order."""
    with np.errstate(over="ignore"):
        x = ids.astype(np.uint64) ^ np.uint64(salt & 0xFFFFFFFFFFFFFFFF)
        x = x + np.uint64(0x9E3779B97F4A7C15)
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


@dataclass
class MailFile:
    round: int
    company_id: np.ndarray
    cell: np.ndarray  # cell code
    arm: np.ndarray  # 1 = mail, 0 = holdout
    creative: np.ndarray  # index into creatives, -1 for holdout
    creatives: list[str]

    @property
    def sha256(self) -> str:
        h = hashlib.sha256()
        h.update(f"round={self.round};creatives={','.join(self.creatives)};".encode())
        for a in (self.company_id, self.cell, self.arm, self.creative):
            h.update(np.ascontiguousarray(a.astype(np.int64)).tobytes())
        return h.hexdigest()

    @property
    def letters(self) -> int:
        return int(self.arm.sum())

    def mail_codes(self) -> list[str]:
        return sorted(
            {
                f"R{self.round:02d}-{self.creatives[k]}-{cell_name(int(c))}"
                for c, k in zip(self.cell[self.arm == 1], self.creative[self.arm == 1])
            }
        )


def build(
    plan: Plan,
    universe: dict[str, np.ndarray],
    response: np.ndarray,
    value: np.ndarray,
    mask: np.ndarray,
    within_cell: str = "random",
) -> MailFile:
    ids = universe["company_id"]
    eligible = (mask == 0) & ~np.isin(universe["sector"], plan.excluded_sectors)
    cells = assign_cells(response, value, plan.band_edges, plan.value_edge)
    order_key = keyed_hash(ids, plan.round * 7919 + 17)
    creative_key = keyed_hash(ids, plan.round * 104729 + 3)
    creatives = sorted(plan.creative_shares)
    shares = np.array([plan.creative_shares[c] for c in creatives])
    bounds = np.cumsum(shares) / shares.sum() if len(shares) else np.array([])
    out_id, out_cell, out_arm, out_cr = [], [], [], []
    for cp in plan.cells:
        code = _code(cp.cell)
        idx = np.flatnonzero(eligible & (cells == code))
        key = -response[idx] if within_cell == "score" else order_key[idx]
        idx = idx[np.argsort(key, kind="stable")]
        take = idx[: cp.letters + cp.holdout]
        hold, mail = take[: cp.holdout], take[cp.holdout :]
        u = (creative_key[mail] >> np.uint64(11)).astype(np.float64) / float(1 << 53)
        cr = np.searchsorted(bounds, u, side="right") if len(bounds) else np.zeros(len(mail), dtype=int)
        out_id += [ids[mail], ids[hold]]
        out_cell += [np.full(len(mail), code), np.full(len(hold), code)]
        out_arm += [np.ones(len(mail), dtype=np.int8), np.zeros(len(hold), dtype=np.int8)]
        out_cr += [np.minimum(cr, len(creatives) - 1), np.full(len(hold), -1)]
    cat = lambda xs, dt: np.concatenate(xs).astype(dt) if xs else np.zeros(0, dtype=dt)
    return MailFile(
        plan.round,
        cat(out_id, np.int64),
        cat(out_cell, np.int64),
        cat(out_arm, np.int8),
        cat(out_cr, np.int64),
        creatives,
    )


def _code(name: str) -> int:
    b, v = name[1:].split("v")
    return (int(b) - 1) * 10 + int(v) - 1


def check(
    f: MailFile,
    plan: Plan,
    universe: dict[str, np.ndarray],
    creatives: list[Creative],
    *,
    budget_cap: float,
) -> list[Check]:
    """Hard rules the model cannot change. Run on the file, against the universe as it is at check time."""
    lim, cost = settings.agent()["limits"], settings.agent()["economics"]["cost_per_letter"]
    ids = universe["company_id"]
    sorter = np.argsort(ids, kind="stable")
    rows = sorter[np.searchsorted(ids, f.company_id, sorter=sorter)] if f.company_id.size else np.zeros(0, int)
    mailed = rows[f.arm == 1]
    mask = rules.evaluate({k: v[mailed] for k, v in universe.items()}) if mailed.size else np.zeros(0, np.int64)
    hit = rules.reasons(mask) if mailed.size else {}
    bad = {k: v for k, v in hit.items() if v}
    by_code = {c.code: c for c in creatives}
    used = {f.creatives[k] for k in set(f.creative[f.arm == 1].tolist())}
    unapproved = sorted(
        c
        for c in used
        if c not in by_code or not by_code[c].approved or (by_code[c].approved_until or "") < plan.drop_date
    )
    excluded = int(np.isin(universe["sector"][mailed], plan.excluded_sectors).sum()) if mailed.size else 0
    spend = f.letters * cost
    checks = [
        Check(check="suppressions", passed=not bad, detail=f"suppressed records in the mailed arm: {bad or 'none'}"),
        Check(
            check="budget",
            passed=spend <= plan.budget + 1e-6 and plan.budget <= budget_cap,
            detail=f"£{spend:,.2f} against a £{plan.budget:,.0f} budget (cap £{budget_cap:,.0f})",
        ),
        Check(check="capacity", passed=f.letters <= lim["max_letters"], detail=f"{f.letters:,} letters"),
        Check(
            check="creatives_approved",
            passed=not unapproved,
            detail=f"unapproved or expiring before the drop: {unapproved or 'none'}",
        ),
        Check(check="excluded_sectors", passed=excluded == 0, detail=f"{excluded} letters to excluded sectors"),
        Check(
            check="no_duplicates",
            passed=len(np.unique(f.company_id)) == len(f.company_id),
            detail=f"{len(f.company_id) - len(np.unique(f.company_id))} duplicates",
        ),
        Check(
            check="matches_plan",
            passed=f.letters == sum(c.letters for c in plan.cells)
            and int((f.arm == 0).sum()) == sum(c.holdout for c in plan.cells),
            detail="file totals equal the plan",
        ),
    ]
    held = [(c.holdout, c.letters) for c in plan.cells if c.letters > 0]
    ok = all(
        lim["min_holdout_share"] - 0.005 <= h / (h + m) <= lim["max_holdout_share"] + 0.005 for h, m in held if h + m
    )
    checks.append(
        Check(
            check="holdout",
            passed=ok or plan.holdout_share == 0,
            detail=f"holdout share {plan.holdout_share:.0%} in every mailed cell",
        )
    )
    return checks
