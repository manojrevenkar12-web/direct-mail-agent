"""UK limited companies, how each would behave with and without a letter, and what the results tables would show.

Every business has a 60-day probability of applying anyway (search, brokers, word of mouth) and a separate amount a
letter adds. The response model scores the two together, because it was trained on businesses that were mailed;
it cannot tell a business that would have applied anyway from one the letter persuaded. That gap is what the
holdout cells exist to measure.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from datetime import date
from functools import cache

import numpy as np

from mailagent import settings
from mailagent.mailfile import MailFile
from mailagent.optimise import cell_name

TYPES = ["ltd", "llp", "sole", "partnership"]
STATUS = ["active", "dormant", "dissolved", "liquidation"]
NEVER = -100_000
EPOCH = date(2026, 1, 1)


@cache
def config() -> dict:
    return tomllib.loads((settings.CONFIG / "world.toml").read_text())


def day(iso: str) -> int:
    return (date.fromisoformat(iso) - EPOCH).days


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


@dataclass
class Applications:
    company: list[np.ndarray] = field(default_factory=list)
    day: list[np.ndarray] = field(default_factory=list)
    mail_caused: list[np.ndarray] = field(default_factory=list)
    mailcode: list[np.ndarray] = field(default_factory=list)
    funded: list[np.ndarray] = field(default_factory=list)
    fund_day: list[np.ndarray] = field(default_factory=list)
    value: list[np.ndarray] = field(default_factory=list)

    def add(self, **kw):
        for k, v in kw.items():
            getattr(self, k).append(v)

    def arrays(self) -> dict[str, np.ndarray]:
        out = {}
        for k in ("company", "day", "mail_caused", "mailcode", "funded", "fund_day", "value"):
            xs = getattr(self, k)
            out[k] = np.concatenate(xs) if xs else np.zeros(0)
        return out


class Market:
    def __init__(self, scenario: str = "dev", size: int | None = None, seed_offset: int = 0):
        cfg = config()
        self.sc = {**cfg["scenario"][scenario]}
        self.sc["seed"] = self.sc["seed"] + 1000 * seed_offset
        self.scenario = scenario
        self.b, u = cfg["behaviour"], cfg["universe"]
        n = size or u["size"]
        self.n = n
        rng = np.random.default_rng(self.sc["seed"])
        self.rng = rng
        self.company_id = np.arange(10_000_000, 10_000_000 + n, dtype=np.int64)
        self.company_type = rng.choice(TYPES, n, p=list(u["company_type"].values())).astype("<U11")
        self.status = rng.choice(STATUS, n, p=list(u["status"].values())).astype("<U11")
        sectors = list(u["sectors"])
        self.sector = rng.choice(sectors, n, p=list(u["sectors"].values())).astype("<U21")
        self.age0 = np.maximum(1, rng.lognormal(math.log(u["age_median_months"]), 0.9, n)).astype(int)
        self.gone_away = rng.random(n) < u["gone_away"]
        self.mps_director = rng.random(n) < u["mps_director"]
        self.objected = rng.random(n) < u["objected"]

        sneed = np.zeros(n)
        for name, v in u["sector_need"].items():
            sneed[self.sector == name] = v
        young = (self.age0 < 24).astype(float) * 0.4
        need = rng.normal(0, 1, n) + sneed + young
        intent = 0.3 * need + rng.normal(0, 0.95, n)
        quality = rng.normal(0, 1, n) - 0.2 * need
        b = self.b
        self.p0 = sigmoid(b["organic_intercept"] + b["need_coef"] * need + b["intent_coef"] * intent)
        self.uplift = (
            b["uplift_scale"]
            * sigmoid(b["uplift_need"] * need + b["uplift_intent"] * intent - 1.0)
            * rng.gamma(2.0, 0.5, n)
        )
        self.approve = sigmoid(b["approve_intercept"] + quality)
        self.value = b["value_median"] * np.exp(b["value_sigma"] * rng.normal(0, 1, n) + 0.25 * quality)
        self.value_noise = rng.lognormal(0, 0.3, n)
        s = cfg["scores"]
        self._resp_noise = rng.normal(0, 1, n)
        self._val_noise = rng.normal(0, 1, n)
        self.s_cfg = s

        # state
        self.existing_customer = rng.random(n) < u["existing_customer"] * (1 + 3 * self.p0 / self.p0.mean()) / 4
        self.open_until = np.full(n, NEVER)
        self.decline_day = np.full(n, NEVER)
        self.letters: dict[int, np.ndarray] = {}  # round -> company rows mailed
        self.mailed_mask: dict[int, np.ndarray] = {}  # round -> file positions actually mailed
        self.files: dict[int, MailFile] = {}
        self.file_rows: dict[int, np.ndarray] = {}
        self.withdrawn: dict[int, np.ndarray] = {}
        self.apps = Applications()
        self.objection_queue: list[tuple[int, int, bool]] = []  # (row, day, by_email)
        self.pending_suppression: list[tuple[int, int]] = []  # (row, effective day)
        self.simulated_through = -1
        self.events = {(e["round"], e["kind"]): e for e in self.sc["events"]}
        self.truth_rounds: dict[int, dict] = {}
        self.cell_inc: dict[int, dict[str, tuple[float, int]]] = {}

    # -- scenario helpers ---------------------------------------------------------------------------------------
    def event(self, r: int, kind: str) -> bool:
        return (r, kind) in self.events

    def model_version(self, r: int) -> str:
        upd = [e["round"] for e in self.sc["events"] if e["kind"] == "model_update"]
        return "response-v7" if upd and r >= upd[0] else "response-v6"

    def season(self, r: int) -> float:
        return config()["seasonality"]["months"][settings.drop_date(r).month - 1]

    def round_of_day(self, d: int) -> int:
        first = day(settings.agent()["round"]["first_drop"])
        return (d - first) // settings.agent()["round"]["cadence_days"] + 1

    # -- what the warehouse shows -------------------------------------------------------------------------------
    def _apply_state(self, d: int) -> None:
        for row, eff in self.pending_suppression:
            if eff <= d:
                self.objected[row] = True
        self.pending_suppression = [(r, e) for r, e in self.pending_suppression if e > d]

    def universe(self, as_of: str) -> dict[str, np.ndarray]:
        d = day(as_of)
        self._apply_state(d)
        a = self.apps.arrays()
        customer = self.existing_customer.copy()
        open_app = np.zeros(self.n, dtype=bool)
        decline = np.full(self.n, NEVER)
        if a["company"].size:
            comp = a["company"].astype(int)
            done = a["funded"].astype(bool) & (a["fund_day"] <= d)
            customer[comp[done]] = True
            decided = a["day"] + self.b["decision_days"]
            pending = (a["day"] <= d) & (decided > d)
            open_app[comp[pending]] = True
            dec = (~a["funded"].astype(bool)) & (decided <= d)
            np.maximum.at(decline, comp[dec], decided[dec].astype(int))
        last_letter = np.full(self.n, NEVER)
        count365 = np.zeros(self.n, dtype=int)
        for r, rows in self.letters.items():
            dd = day(settings.iso(settings.drop_date(r)))
            if dd <= d:
                np.maximum.at(last_letter, rows, dd)
                if d - dd < 365:
                    count365[rows] += 1
        last_hold = np.full(self.n, NEVER)
        for r, f in self.files.items():
            dd = day(settings.iso(settings.drop_date(r)))
            if dd <= d:
                np.maximum.at(last_hold, self.file_rows[r][f.arm == 0], dd)
        months = (d // 30) if d > 0 else 0
        return {
            "company_id": self.company_id,
            "company_type": self.company_type,
            "status": self.status,
            "sector": self.sector,
            "age_months": self.age0 + months,
            "existing_customer": customer,
            "open_application": open_app,
            "days_since_decline": np.where(decline == NEVER, 9999, d - decline),
            "objected": self.objected.copy(),
            "gone_away": self.gone_away,
            "mps_director": self.mps_director,
            "days_since_last_letter": np.where(last_letter == NEVER, 9999, d - last_letter),
            "letters_last_365": count365,
            "days_since_holdout": np.where(last_hold == NEVER, 9999, d - last_hold),
        }

    def scores(self, ids: np.ndarray, as_of: str) -> tuple[np.ndarray, np.ndarray, str]:
        r = self.round_of_day(day(as_of) + settings.agent()["round"]["plan_days_before_drop"])
        version = self.model_version(r)
        s = self.s_cfg
        p = np.clip(self.p0 + self.uplift, 1e-6, 1 - 1e-6)
        logit = np.log(p / (1 - p))
        if version == "response-v7":
            resp = sigmoid(logit + s["v7_shift"] + s["v7_noise"] * self._resp_noise)
        else:
            resp = sigmoid(logit + s["response_noise"] * self._resp_noise)
        val = self.approve * self.value * np.exp(s["value_noise"] * self._val_noise)
        rows = ids - self.company_id[0]
        return resp[rows], val[rows], version

    # -- the round happens --------------------------------------------------------------------------------------
    def print_and_drop(self, r: int, f: MailFile | None, withdraw: np.ndarray | None = None) -> dict:
        """Letters land on the drop date; then the 28 days until the next round play out."""
        cfg = config()
        rng = np.random.default_rng([self.sc["seed"], r, 99])
        d0 = day(settings.iso(settings.drop_date(r)))
        season = self.season(r)
        mailed = np.zeros(0, dtype=int)
        truth = {
            "letters": 0,
            "exp_incremental_value": 0.0,
            "breaches": {},
            "mail_caused_funded": 0,
            "mail_caused_value": 0.0,
            "spend": 0.0,
        }
        if f is not None:
            rows = f.company_id - self.company_id[0]
            arm = f.arm.astype(bool)
            if withdraw is not None and withdraw.size:
                arm = arm & ~np.isin(f.company_id, withdraw)
            self.files[r] = f
            self.file_rows[r] = rows
            self.mailed_mask[r] = arm
            mailed = rows[arm]
            self.letters[r] = mailed
            truth["breaches"] = self._breaches(mailed, d0)
        # organic applications for everyone eligible to apply this period
        u = self.universe(settings.iso(settings.drop_date(r)))
        can = (
            (self.status == "active")
            & ~u["existing_customer"]
            & ~u["open_application"]
            & (u["days_since_decline"] >= 90)
            & np.isin(self.company_type, ["ltd", "llp"])
        )
        p_period = 1 - (1 - np.clip(self.p0 * season, 0, 0.9)) ** (28 / 60)
        org = can & (rng.random(self.n) < p_period)
        org_day = d0 + rng.integers(0, 28, self.n)
        # mail-driven
        mail_hit = np.zeros(self.n, dtype=bool)
        mail_day = np.zeros(self.n, dtype=int)
        eff = np.zeros(self.n)
        if mailed.size:
            effect = np.array([cfg["creatives"][c]["effect"] for c in f.creatives])
            cr = f.creative[arm]
            prior = np.zeros(self.n, dtype=int)
            for rr, rows_r in self.letters.items():
                if rr < r and d0 - day(settings.iso(settings.drop_date(rr))) <= 180:
                    prior[rows_r] += 1
            mult = effect[cr] * self.b["fatigue"] ** prior[mailed] * season
            if self.event(r + 1, "competitor_offer"):  # noticed when the next round is planned
                mult = mult * 0.3
            pushed = [e["sector"] for e in self.sc["inbox"] if e["kind"] == "search_fyi" and e["round"] == r]
            if pushed:
                mult = mult * np.where(np.isin(self.sector[mailed], pushed), 0.7, 1.0)
            eff[mailed] = np.clip(self.uplift[mailed] * mult, 0, 0.5)
            hit = rng.random(mailed.size) < eff[mailed]
            hit &= can[mailed]
            mail_hit[mailed[hit]] = True
            delay = np.clip(
                rng.lognormal(math.log(self.b["mail_delay_median_days"]), self.b["mail_delay_sigma"], mailed.size),
                0,
                59,
            ).astype(int)
            mail_day[mailed] = d0 + delay
            # expected incremental value of the letters sent (the truth the evaluation scores)
            p_org60 = np.clip(self.p0[mailed] * season, 0, 0.9)
            truth["exp_incremental_value"] = float(
                (
                    eff[mailed]
                    * (1 - p_org60)
                    * can[mailed]
                    * self.approve[mailed]
                    * self.credit(r)
                    * self.value[mailed]
                ).sum()
            )
            inc = eff[mailed] * (1 - p_org60) * can[mailed]
            mcell = f.cell[arm]
            self.cell_inc[r] = {
                cell_name(int(c)): (float(inc[mcell == c].sum()), int((mcell == c).sum())) for c in np.unique(mcell)
            }
            truth["letters"] = int(mailed.size)
            truth["spend"] = mailed.size * settings.agent()["economics"]["cost_per_letter"]
        mail_only = mail_hit & ~org
        apply = org | mail_only
        idx = np.flatnonzero(apply)
        a_day = np.where(mail_only[idx], mail_day[idx], org_day[idx])
        mc = mail_only[idx]
        code = np.where(
            mc, rng.random(idx.size) < self._mailcode_use(r), rng.random(idx.size) < self.b["mailcode_use_organic"]
        ) & np.isin(idx, mailed)
        funded = rng.random(idx.size) < self.approve[idx] * self.credit(r)
        fd = a_day + rng.integers(self.b["fund_delay_days"][0], self.b["fund_delay_days"][1] + 1, idx.size)
        val = np.where(funded, self.value[idx] * self.value_noise[idx], 0.0)
        self.apps.add(company=idx, day=a_day, mail_caused=mc, mailcode=code, funded=funded, fund_day=fd, value=val)
        truth["mail_caused_funded"] = int((mc & funded).sum())
        truth["mail_caused_value"] = float(val[mc & funded].sum())
        truth["attributed_funded"] = int((funded & np.isin(idx, mailed)).sum())
        # objections from the letters
        if mailed.size:
            obj = mailed[rng.random(mailed.size) < self.b["objection_rate"]]
            by_email = rng.random(obj.size) < self.b["objection_by_email"]
            for row, em in zip(obj, by_email):
                od = d0 + int(rng.integers(3, 25))
                self.objection_queue.append((int(row), od, bool(em)))
                if not em:
                    self.pending_suppression.append((int(row), od + 3))  # the CRM path: operations within days
        self.truth_rounds[r] = truth
        return truth

    def _mailcode_use(self, r: int) -> float:
        return 0.08 if self.event(r + 1, "tracking_break") else self.b["mailcode_use_mail"]

    def credit(self, r: int) -> float:
        return 1.0

    def _breaches(self, mailed: np.ndarray, d0: int) -> dict[str, int]:
        """Letters that went to someone they must not reach, judged on the true state at the drop date."""
        objected_now = self.objected.copy()
        for row, od, _ in self.objection_queue:
            if od <= d0:
                objected_now[row] = True
        return {
            "objected": int(objected_now[mailed].sum()),
            "mps_director": int(self.mps_director[mailed].sum()),
            "gone_away": int(self.gone_away[mailed].sum()),
            "not_active": int((self.status[mailed] != "active").sum()),
            "not_corporate": int((~np.isin(self.company_type[mailed], ["ltd", "llp"])).sum()),
        }

    def route_objection(self, row: int, at: int) -> None:
        self.pending_suppression.append((row, at + 2))

    # -- results tables -----------------------------------------------------------------------------------------
    def snapshot(self, as_of: str, outage: bool = False) -> dict:
        d = day(as_of)
        a = self.apps.arrays()
        rows_out = []
        window = settings.agent()["round"]["attribution_window_days"]
        comp = a["company"].astype(int) if a["company"].size else np.zeros(0, int)
        for r, f in sorted(self.files.items()):
            d0 = day(settings.iso(settings.drop_date(r)))
            if d0 > d or d - d0 > 200:
                continue
            age = min(d - d0, window)
            obs = (a["day"] >= d0) & (a["day"] < d0 + age) & (a["day"] <= d) if comp.size else np.zeros(0, bool)
            rows = self.file_rows[r]
            mailed = self.mailed_mask[r]
            groups = {}
            for cell in np.unique(f.cell):
                in_cell = f.cell == cell
                for k, cr in enumerate(f.creatives):
                    groups[(cell, "mail", cr)] = rows[in_cell & mailed & (f.creative == k)]
                groups[(cell, "holdout", "")] = rows[in_cell & (f.arm == 0)]
            pos = np.full(self.n, -1)
            for gi, (_, members) in enumerate(groups.items()):
                pos[members] = gi
            g_app = pos[comp[obs]] if comp.size else np.zeros(0, int)
            o_day = (a["day"][obs] - d0).astype(int) if comp.size else np.zeros(0, int)
            o_code = a["mailcode"][obs].astype(bool) if comp.size else np.zeros(0, bool)
            o_f = (a["funded"][obs].astype(bool) & (a["fund_day"][obs] <= d)) if comp.size else np.zeros(0, bool)
            o_v = a["value"][obs] if comp.size else np.zeros(0)
            for gi, ((cell, name, cr), members) in enumerate(groups.items()):
                if members.size == 0:
                    continue
                m = g_app == gi
                hist = np.bincount(np.clip(o_day[m] // 5, 0, 11), minlength=12)
                rows_out.append(
                    {
                        "round": r,
                        "cell": cell_name(int(cell)),
                        "arm": name,
                        "creative": cr,
                        "n": int(members.size),
                        "apps": int(m.sum()),
                        "mailcode_apps": int((m & o_code).sum()),
                        "funded": int((m & o_f).sum()),
                        "funded_value": round(float(o_v[m & o_f].sum()), 2),
                        "age_days": int(age),
                        "day_hist": hist.tolist(),
                    }
                )
        expected = len(rows_out)
        if outage:
            keep = np.random.default_rng([self.sc["seed"], d]).random(len(rows_out)) < 0.55
            rows_out = [x for x, k in zip(rows_out, keep) if k]
        return {"as_of": as_of, "rows": rows_out, "expected_rows": expected}

    # -- truth for the evaluation -------------------------------------------------------------------------------
    def cell_truth(self, upto: int, half_life: float) -> dict[str, float]:
        """True incremental 60-day application rate per letter in each cell, weighted over rounds the way the
        learner weights them (rounds before `upto`)."""
        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for r, cells in self.cell_inc.items():
            if r >= upto:
                continue
            w = 0.5 ** ((upto - r) / half_life)
            for c, (inc, n) in cells.items():
                num[c] = num.get(c, 0.0) + w * inc
                den[c] = den.get(c, 0.0) + w * n
        return {c: num[c] / den[c] for c in num if den[c] > 0}
