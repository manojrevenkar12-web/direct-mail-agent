from mailagent import brief


def stats():
    return {
        "round": 4,
        "letters": 199_812,
        "holdout": 22_201,
        "cost": 109_896.6,
        "budget": 110000.0,
        "holdout_share_pct": 10.0,
        "expected_incremental_value": 412_000.0,
        "cells_mailed": 10,
        "checks_passed": 8,
        "checks_total": 8,
        "creative_shares_pct": {"FLEXI-A": 40.0, "FLEXI-B": 60.0},
        "excluded_sectors": [],
        "directions_applied": [],
        "directions_not_applied": [
            {"kind": "set_budget", "sender": "a", "why": "budget £180,000 is above the £150,000 cap"}
        ],
        "anomalies": [],
        "drop_date": "2026-04-20",
    }


def test_every_figure_must_be_a_plan_figure():
    s = stats()
    ok = "Round 4 drops on 2026-04-20: 199,812 letters, 22,201 held out (10.0%), £109,896.60 of £110,000."
    assert brief.verify(ok, s) == []
    bad = "Round 4: 213,799 letters."
    assert brief.verify(bad, s) == ["213,799"]
    assert brief.verify("The £180,000 request was above the £150,000 cap.", s) == []


def test_template_always_passes():
    s = stats()
    assert brief.verify(brief.template(s), s) == []
