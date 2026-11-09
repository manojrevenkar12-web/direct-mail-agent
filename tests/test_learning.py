"""Results arrive late; the learner must not mistake 'not arrived yet' for 'did not respond'."""

import numpy as np

from mailagent import learning


def rows_for(round_no, age, n=20_000, rate_mail=0.010, rate_hold=0.005, seed=0, cell="b3v2"):
    rng = np.random.default_rng(seed + round_no)
    out = []
    for arm, rate, size in (("mail", rate_mail, n), ("holdout", rate_hold, n // 9)):
        total = rng.binomial(size, rate)
        if arm == "mail":
            days = np.clip(rng.lognormal(np.log(11), 0.6, total), 0, 59)
        else:
            days = rng.uniform(0, 60, total)
        seen = days[days < age]
        hist = np.bincount((seen // 5).astype(int), minlength=12)[:12]
        out.append(
            {
                "round": round_no,
                "cell": cell,
                "arm": arm,
                "creative": "FLEXI-A" if arm == "mail" else "",
                "n": size,
                "apps": int(seen.size),
                "mailcode_apps": 0,
                "funded": int(seen.size * 0.5),
                "funded_value": float(seen.size * 0.5 * 400),
                "age_days": int(age),
                "day_hist": hist.tolist(),
            }
        )
    return out


def test_delay_adjustment_removes_the_recent_round_bias():
    rows = []
    for r in (1, 2, 3):  # complete rounds in another cell teach the arrival curve
        rows += rows_for(r, 60, cell="b1v1")
    for r, age in ((4, 47), (5, 19)):  # this cell has only been mailed recently
        rows += rows_for(r, age)
    adj = learning.posteriors(rows, 6, "incremental")["cells"]["b3v2"]
    raw = learning.posteriors(rows, 6, "response_no_delay")["cells"]["b3v2"]
    m_adj = adj["mail"][0] / sum(adj["mail"])
    m_raw = raw["mail"][0] / sum(raw["mail"])
    assert abs(m_adj - 0.010) < 0.0012
    assert m_raw < m_adj - 0.0008  # counting per letter understates recent rounds


def test_matchback_credits_mail_with_applications_that_would_have_happened():
    rows = []
    for r in (1, 2, 3):
        rows += rows_for(r, 60)
    hold = learning.posteriors(rows, 4, "incremental")["cells"]["b3v2"]
    mb = learning.posteriors(rows, 4, "response")["cells"]["b3v2"]
    assert learning.mean_value(mb) > 1.6 * learning.mean_value(hold)


def test_prior_until_rounds_are_complete():
    rows = rows_for(1, 19)
    assert learning.estimate_delay(rows)["mail"] == learning.prior_cdf("mail")
