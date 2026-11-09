"""Learning from results that arrive late.

Applications from a round keep arriving for weeks. When the next round is planned, the last round is only partly
observed, so counting applications per letter would make every recent round look worse than it is. The learner
estimates how much of each arm's eventual response has arrived by a given age (from rounds that are complete) and
divides by that, not by the number of letters.

Two ways to value a cell:
- "response": applications per letter in the mailed arm, times funding and value. It ranks cells well, because it
  is estimated from every letter, but as a measure of what mail is worth it counts businesses that would have applied
  anyway ("matchback").
- "incremental": the mailed arm minus its random holdout. It is what mail is worth, but at application rates under 1%
  a holdout of a few thousand is noisy, and every held-out business is a letter not sent.
The agent ranks by response and measures with a small holdout (see RESULTS.md for why).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np

from mailagent import settings

BUCKET_DAYS = 5
BUCKETS = 12  # 60 days


def _lognormal_cdf(t: float, median: float, sigma: float) -> float:
    if t <= 0:
        return 0.0
    return 0.5 * (1 + math.erf((math.log(t) - math.log(median)) / (sigma * math.sqrt(2))))


def prior_cdf(arm: str) -> list[float]:
    cfg = settings.agent()["learning"]
    window = settings.agent()["round"]["attribution_window_days"]
    edges = [BUCKET_DAYS * k for k in range(BUCKETS + 1)]
    if arm == "holdout":
        return [e / window for e in edges]
    raw = [_lognormal_cdf(e, cfg["delay_prior_median_days"], cfg["delay_prior_sigma"]) for e in edges]
    top = raw[-1]
    # organic applications from mailed companies arrive evenly; mail-driven ones early. Prior: half and half.
    return [0.5 * r / top + 0.5 * e / window for r, e in zip(raw, edges)]


def cdf_at(cdf: list[float], age: float) -> float:
    if age >= BUCKET_DAYS * BUCKETS:
        return 1.0
    k = int(age // BUCKET_DAYS)
    frac = (age - k * BUCKET_DAYS) / BUCKET_DAYS
    return max(1e-6, cdf[k] + frac * (cdf[k + 1] - cdf[k]))


def estimate_delay(rows: list[dict]) -> dict[str, list[float]]:
    """Empirical arrival curves per arm from complete rounds; the prior until enough rounds are complete."""
    cfg = settings.agent()["learning"]
    window = settings.agent()["round"]["attribution_window_days"]
    out = {}
    for arm in ("mail", "holdout"):
        complete = [r for r in rows if r["arm"] == arm and r["age_days"] >= window]
        rounds = {r["round"] for r in complete}
        hist = np.zeros(BUCKETS)
        for r in complete:
            hist += np.asarray(r["day_hist"], dtype=float)
        if len(rounds) < cfg["min_complete_rounds_for_delay"] or hist.sum() < 50:
            out[arm] = prior_cdf(arm)
        else:
            out[arm] = [0.0, *(np.cumsum(hist) / hist.sum()).tolist()]
    return out


def model_priors(response: np.ndarray, value: np.ndarray, codes: np.ndarray, eligible: np.ndarray) -> dict:
    """A prior per cell from the existing predictive models: what they expect a letter to bring."""
    from mailagent.optimise import cell_name

    cfg = settings.agent()["learning"]
    fund_mean = cfg["prior_fund_a"] / (cfg["prior_fund_a"] + cfg["prior_fund_b"])
    out = {}
    for c in np.unique(codes[eligible]):
        sel = eligible & (codes == c)
        m = float(np.clip(response[sel].mean(), 1e-4, 0.5))
        h = m * (1 - cfg["prior_lift_share"])
        wm, wh = cfg["prior_weight_mail"], cfg["prior_weight_holdout"]
        out[cell_name(int(c))] = {
            "mail": [wm * m, wm * (1 - m)],
            "holdout": [wh * h, wh * (1 - h)],
            "fund": [cfg["prior_fund_a"], cfg["prior_fund_b"]],
            "value": float(value[sel].mean()) / fund_mean,
            "matchback": False,
        }
    return out


def posteriors(
    rows: list[dict], current_round: int, mode: str = "response", priors: dict[str, dict] | None = None
) -> dict[str, Any]:
    """Per-cell Beta posteriors for the 60-day application rate of each arm, the funding rate and funded value.

    mode: "response" (the agent), "response_no_delay" (counts per letter, not delay-adjusted), "incremental"
    (mailed arm minus holdout, delay-adjusted).
    """
    cfg = settings.agent()["learning"]
    window = settings.agent()["round"]["attribution_window_days"]
    no_delay = mode.endswith("no_delay")
    delay = estimate_delay(rows) if not no_delay else {"mail": [1.0] * 13, "holdout": [1.0] * 13}
    agg: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"mail": [0.0, 0.0], "holdout": [0.0, 0.0], "fund": [0.0, 0.0], "value": [0.0, 0.0]}
    )
    creatives: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        w = 0.5 ** ((current_round - r["round"]) / cfg["half_life_rounds"])
        frac = 1.0 if no_delay else cdf_at(delay[r["arm"]], r["age_days"])
        n_eff = r["n"] * frac
        cell = agg[r["cell"]]
        cell[r["arm"]][0] += w * r["apps"]
        cell[r["arm"]][1] += w * max(n_eff - r["apps"], 0.0)
        if r["arm"] == "mail":
            creatives[r["creative"]][0] += w * r["apps"]
            creatives[r["creative"]][1] += w * max(n_eff - r["apps"], 0.0)
            if r["age_days"] >= window * 2 // 3:
                cell["fund"][0] += w * r["funded"]
                cell["fund"][1] += w * max(r["apps"] - r["funded"], 0)
                cell["value"][0] += w * r["funded_value"]
                cell["value"][1] += w * r["funded"]
    priors = priors or {}
    out = {}
    for c in set(agg) | set(priors):
        a = agg[c]
        p = priors.get(c) or prior_cell()
        out[c] = {
            "mail": [p["mail"][0] + a["mail"][0], p["mail"][1] + a["mail"][1]],
            "holdout": [p["holdout"][0] + a["holdout"][0], p["holdout"][1] + a["holdout"][1]],
            "fund": [p["fund"][0] + a["fund"][0], p["fund"][1] + a["fund"][1]],
            "value": (p["value"] * cfg["prior_value_weight"] + a["value"][0])
            / (cfg["prior_value_weight"] + a["value"][1]),
            "matchback": mode.startswith("response"),
        }
    return {
        "cells": out,
        "creatives": {k: [cfg["prior_mail"][0] + v[0], cfg["prior_mail"][1] + v[1]] for k, v in creatives.items()},
        "delay": delay,
        "mode": mode,
    }


def prior_cell() -> dict[str, Any]:
    """The prior for a cell the models say nothing about (only used when no scores are available)."""
    cfg = settings.agent()["learning"]
    m = cfg["prior_mail"][0] / sum(cfg["prior_mail"])
    h = m * (1 - cfg["prior_lift_share"])
    return {
        "mail": [cfg["prior_weight_mail"] * m, cfg["prior_weight_mail"] * (1 - m)],
        "holdout": [cfg["prior_weight_holdout"] * h, cfg["prior_weight_holdout"] * (1 - h)],
        "fund": [cfg["prior_fund_a"], cfg["prior_fund_b"]],
        "value": cfg["prior_value"],
        "matchback": False,
    }


def sample_value(post: dict[str, Any], rng: np.random.Generator, size: int | None = None) -> np.ndarray:
    """Incremental funded value per letter, sampled from the posterior."""
    rm = rng.beta(*post["mail"], size=size)
    fund = rng.beta(*post["fund"], size=size)
    if post.get("matchback"):
        lift = rm
    else:
        lift = rm - rng.beta(*post["holdout"], size=size)
    return np.asarray(lift * fund * post["value"])


def mean_value(post: dict[str, Any]) -> float:
    m = post["mail"][0] / sum(post["mail"])
    h = 0.0 if post.get("matchback") else post["holdout"][0] / sum(post["holdout"])
    f = post["fund"][0] / sum(post["fund"])
    return float((m - h) * f * post["value"])
