"""Planning a round is arithmetic, so it is code.

Cells are quantile bands of the response model score crossed with value tiers of the value model score. For each
cell the posterior gives the incremental funded value per letter. Every cell first gets a fixed learning sample, so
the learner never goes blind where it is unsure; then the budget fills cells in order of posterior mean value, while
the mean beats the cost of a letter.

The first version ranked cells by one Thompson draw each. At 200,000 letters a round that is too much exploration:
one unlucky draw sent 51,000 letters to a low-value cell. Thompson sampling is kept where it fits (choosing between
creatives, see creative_shares); the bulk allocation uses the mean.
"""

from __future__ import annotations

import numpy as np

from mailagent import learning, settings
from mailagent.schema import CellPlan

MIN_LETTERS = 100


def cell_edges(response: np.ndarray, value: np.ndarray, eligible: np.ndarray) -> tuple[list[float], float]:
    cfg = settings.agent()["cells"]
    r = response[eligible]
    qs = np.linspace(0, 1, cfg["response_bands"] + 1)[1:-1]
    edges = np.quantile(r, qs).tolist() if r.size else [0.0] * len(qs)
    vedge = float(np.median(value[eligible])) if r.size else 0.0
    return edges, vedge


def assign_cells(response: np.ndarray, value: np.ndarray, edges: list[float], vedge: float) -> np.ndarray:
    band = np.searchsorted(np.asarray(edges), response, side="right")
    tier = (value > vedge).astype(int)
    return band * 10 + tier  # 0..41; name with cell_name()


def cell_name(code: int) -> str:
    return f"b{code // 10 + 1}v{code % 10 + 1}"


def allocate(
    posts: dict[str, dict],
    available: dict[str, int],
    *,
    budget: float,
    holdout_share: float,
    rng: np.random.Generator,
) -> list[CellPlan]:
    lim, cost = settings.agent()["limits"], settings.agent()["economics"]["cost_per_letter"]
    min_cell = settings.agent()["cells"]["min_cell_letters"]
    capacity = int(min(budget / cost, lim["max_letters"]))
    draws = {}
    for c in available:
        post = posts.get(c) or learning.prior_cell()
        draws[c] = (
            float(learning.sample_value(post, rng)),
            float((learning.sample_value(post, rng, 2000) > cost).mean()),
            learning.mean_value(post),
        )
    order = sorted(available, key=lambda c: -draws[c][2])
    plans, left = [], capacity
    # keep the minimum learning sample in every cell first, then fill by the draw
    base = {c: min(min_cell, int(available[c] * (1 - holdout_share)), left) for c in order}
    left -= sum(base.values())
    if left < 0:
        base = {c: 0 for c in order}
        left = capacity
    for c in order:
        sampled, p_prof, mean = draws[c]
        letters = base[c]
        if mean > cost and left > 0:
            extra = min(int(available[c] * (1 - holdout_share)) - letters, left)
            letters += max(extra, 0)
            left -= max(extra, 0)
        if letters < MIN_LETTERS:
            letters = 0  # too few to print or to learn from
        hold = round(letters * holdout_share / (1 - holdout_share)) if holdout_share > 0 else 0
        plans.append(
            CellPlan(
                cell=c,
                available=available[c],
                letters=letters,
                holdout=hold,
                value_per_letter=round(mean, 4),
                p_profitable=round(p_prof, 3),
                sampled_net=round(sampled - cost, 4),
            )
        )
    return sorted(plans, key=lambda p: p.cell)


def creative_shares(
    creative_posts: dict[str, list[float]],
    approved: list[str],
    min_shares: dict[str, float],
    rng: np.random.Generator,
) -> dict[str, float]:
    """Share per approved creative: the probability it is best, a floor while it is learned, and the directions'
    minimums."""
    if not approved:
        return {}
    floor = settings.agent()["limits"]["min_creative_share"]
    prior = list(settings.agent()["learning"]["prior_mail"])
    draws = np.stack([rng.beta(*(creative_posts.get(c) or prior), size=4000) for c in approved])
    p_best = np.bincount(draws.argmax(0), minlength=len(approved)) / draws.shape[1]
    shares = {c: max(float(p), floor) for c, p in zip(approved, p_best)}
    for c, s in min_shares.items():
        if c in shares:
            shares[c] = max(shares[c], s)
    fixed = {c: s for c, s in min_shares.items() if c in shares}
    rest = [c for c in shares if c not in fixed]
    left = max(1.0 - sum(fixed.values()), 0.0)
    total_rest = sum(shares[c] for c in rest)
    out = dict(fixed)
    for c in rest:
        out[c] = left * shares[c] / total_rest if total_rest else 0.0
    total = sum(out.values())
    return {c: round(v / total, 4) for c, v in out.items()}
