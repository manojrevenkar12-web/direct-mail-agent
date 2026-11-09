"""Learning from results that arrive late.

Applications from a round keep arriving for weeks. When the next round is planned, the last round is only partly
observed, so counting applications per letter would make every recent round look worse than it is. The learner
estimates how much of each arm's eventual response has arrived by a given age (from rounds that are complete) and
divides by that, not by the number of letters.

What mail adds is the difference between the mailed arm and its random holdout in the same cell. Counting every
application from a mailed company ("matchback") credits mail with businesses that would have applied anyway; that
variant is here only so the evaluation can show the difference.
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


def posteriors(rows: list[dict], current_round: int, mode: str = "holdout") -> dict[str, Any]:
    """Per-cell Beta posteriors for the 60-day application rate of each arm, the funding rate and funded value.

    mode: "holdout" (delay-adjusted, the agent), "no_delay" (counts per letter), "matchback" (no holdout).
    """
    cfg = settings.agent()["learning"]
    window = settings.agent()["round"]["attribution_window_days"]
    delay = estimate_delay(rows) if mode != "no_delay" else {"mail": [1.0] * 13, "holdout": [1.0] * 13}
    agg: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"mail": [0.0, 0.0], "holdout": [0.0, 0.0], "fund": [0.0, 0.0], "value": [0.0, 0.0]}
    )
    creatives: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        w = 0.5 ** ((current_round - r["round"]) / cfg["half_life_rounds"])
        frac = 1.0 if mode == "no_delay" else cdf_at(delay[r["arm"]], r["age_days"])
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
    out = {}
    for c, a in agg.items():
        out[c] = {
            "mail": [cfg["prior_mail"][0] + a["mail"][0], cfg["prior_mail"][1] + a["mail"][1]],
            "holdout": [cfg["prior_holdout"][0] + a["holdout"][0], cfg["prior_holdout"][1] + a["holdout"][1]],
            "fund": [cfg["prior_fund_a"] + a["fund"][0], cfg["prior_fund_b"] + a["fund"][1]],
            "value": (cfg["prior_value"] * cfg["prior_value_weight"] + a["value"][0])
            / (cfg["prior_value_weight"] + a["value"][1]),
            "matchback": mode == "matchback",
        }
    return {
        "cells": out,
        "creatives": {k: [cfg["prior_mail"][0] + v[0], cfg["prior_mail"][1] + v[1]] for k, v in creatives.items()},
        "delay": delay,
        "mode": mode,
    }


def prior_cell() -> dict[str, Any]:
    cfg = settings.agent()["learning"]
    return {
        "mail": list(cfg["prior_mail"]),
        "holdout": list(cfg["prior_holdout"]),
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
