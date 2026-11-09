"""Code notices that something looks wrong; deciding what it is and who should look is the model's job.

The last round is compared with earlier rounds cell by cell and at the same age, so a change in the mix of cells
mailed, or in how far into the window the results are, does not look like an anomaly.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from mailagent import settings
from mailagent.learning import BUCKET_DAYS


def psi(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    edges = np.quantile(b, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    pa = np.histogram(a, edges)[0] / a.size + 1e-6
    pb = np.histogram(b, edges)[0] / b.size + 1e-6
    return float(((pa - pb) * np.log(pa / pb)).sum())


def _early(row: dict, buckets: int) -> int:
    return int(sum(row["day_hist"][:buckets]))


def detect(
    *,
    feed: dict,
    score_now: np.ndarray,
    score_last: np.ndarray | None,
    current_round: int,
) -> tuple[list[dict], dict]:
    """Returns the anomalies and the evidence the model may read (aggregates only)."""
    cfg = settings.agent()["anomaly"]
    found, ev = [], {}
    completeness = len(feed["rows"]) / feed["expected_rows"] if feed["expected_rows"] else 1.0
    ev["feed_completeness"] = round(completeness, 3)
    if completeness < cfg["feed_completeness_min"]:
        found.append({"anomaly": "feed_rows_missing", "metric": round(completeness, 3)})

    mail = [r for r in feed["rows"] if r["arm"] == "mail"]
    last = [r for r in mail if r["round"] == current_round - 1]
    hist = [r for r in mail if r["round"] < current_round - 1]
    if last and hist and completeness >= cfg["feed_completeness_min"]:
        buckets = max(1, last[0]["age_days"] // BUCKET_DAYS)
        rate, share = defaultdict(lambda: [0.0, 0.0]), defaultdict(lambda: [0.0, 0.0])
        for r in hist:
            # recent rounds weigh most: repeat letters and the season move response slowly, an incident does not
            w = 0.5 ** (current_round - 2 - r["round"])
            rate[r["cell"]][0] += w * _early(r, buckets)
            rate[r["cell"]][1] += w * r["n"]
            share[r["cell"]][0] += w * r["mailcode_apps"]
            share[r["cell"]][1] += w * r["apps"]
        cells = defaultdict(lambda: [0, 0, 0, 0])
        for r in last:
            cells[r["cell"]][0] += r["n"]
            cells[r["cell"]][1] += _early(r, buckets)
            cells[r["cell"]][2] += r["mailcode_apps"]
            cells[r["cell"]][3] += r["apps"]
        known = [c for c in cells if rate[c][1] > 0 and share[c][1] > 0]
        observed = sum(cells[c][1] for c in known)
        expected = sum(cells[c][0] * rate[c][0] / rate[c][1] for c in known)
        codes = sum(cells[c][2] for c in known)
        codes_expected = sum(cells[c][3] * share[c][0] / share[c][1] for c in known)
        if expected > 0:
            ratio = observed / expected
            z = (observed - expected) / np.sqrt(expected)
            ev.update(
                last_round_apps_early=observed,
                last_round_expected_early=round(expected, 1),
                last_round_ratio=round(ratio, 3),
                last_round_z=round(float(z), 2),
            )
            if ratio < cfg["response_ratio_alert"] and z < cfg["response_z_alert"]:
                found.append({"anomaly": "applications_below_expected", "metric": round(ratio, 3)})
        if codes_expected > 5:
            ratio = codes / codes_expected
            ev["mailcode_ratio_last_round"] = round(ratio, 3)
            if ratio < cfg["tracking_share_drop"]:
                found.append({"anomaly": "mail_code_share_fell", "metric": round(ratio, 3)})

    if score_last is not None:
        p = psi(score_now, score_last)
        ev["response_score_psi"] = round(p, 3)
        if p > cfg["score_psi_alert"]:
            found.append({"anomaly": "score_distribution_moved", "metric": round(p, 3)})
    return found, ev
