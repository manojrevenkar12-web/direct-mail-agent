"""Run every policy through the market and write reports/<split>.json.

python scripts/evaluate.py dev         # tune here: configuration, thresholds, priors
python scripts/evaluate.py heldout2    # once, after scripts/lock.py write heldout2; refuses unless the lock verifies
"""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mail_eval.harness import POLICIES, run  # noqa: E402

SEEDS = 5


def one(args: tuple[str, str, int]) -> dict:
    policy, split, seed = args
    res = run(policy, split, seed_offset=seed)
    keep = {"plan_cells"} if (policy == "agent" and seed == 0) else set()
    rounds = [{k: v for k, v in r.items() if k != "plan_cells" or k in keep} for r in res.rounds]
    return {
        "policy": policy,
        "seed": seed,
        "rounds": rounds,
        "calibration": res.calibration,
        "measurement": res.measurement,
        "ledger_intact": res.ledger_intact,
        "printer_duplicates": res.printer_duplicates,
    }


def summarise(runs: list[dict]) -> dict:
    out = {}
    for policy in POLICIES:
        rs = [r for r in runs if r["policy"] == policy]
        per_seed = []
        for r in rs:
            R = r["rounds"]
            spend = sum(x["spend"] for x in R)
            inc = sum(x["exp_incremental_value"] for x in R)
            dirs = [d for x in R for d in x["directions"]]
            model_dirs = [d for d in dirs if "model_read_ok" in d]
            anomalies = [a for x in R for a in x["anomalies"]]
            real = [a for a in anomalies if a["truth"] != "noise"]
            false = [a for a in anomalies if a["truth"] == "noise"]
            per_seed.append(
                {
                    "profit": inc - spend,
                    "incremental_value": inc,
                    "spend": spend,
                    "letters": sum(x["letters"] for x in R),
                    "realised_incremental_value": sum(x["realised_incremental_value"] for x in R),
                    "mail_caused_funded": sum(x["mail_caused_funded"] for x in R),
                    "attributed_funded": sum(x["attributed_funded"] for x in R),
                    "breach_letters": sum(sum(x["breaches"].values()) for x in R),
                    "breaches_by_type": {
                        k: sum(x["breaches"].get(k, 0) for x in R)
                        for k in ("objected", "mps_director", "gone_away", "not_active", "not_corporate")
                    },
                    "withdrawn_at_print": sum(x["withdrawn"] for x in R),
                    "person_minutes_per_round": float(np.mean([x["person_minutes"] for x in R])),
                    "person_tasks_per_round": float(np.mean([x["person_tasks"] for x in R])),
                    "llm_gbp_per_round": float(np.mean([x["llm_gbp"] for x in R])),
                    "directions_correct": float(np.mean([d["correct"] for d in dirs])) if dirs else None,
                    "model_read_correct": float(np.mean([d["model_read_ok"] for d in model_dirs]))
                    if model_dirs
                    else None,
                    "directions_stopped": int(sum(d.get("stopped", 0) for d in dirs)),
                    "wrong_effects": int(sum(1 for d in dirs if not d.get("effect_ok", True))),
                    "messages": len(dirs),
                    "anomaly_real_detected": len(real),
                    "anomaly_real_diagnosed": sum(1 for a in real if a.get("correct")),
                    "anomaly_false_alarms": len(false),
                    "anomaly_false_dismissed": sum(1 for a in false if a.get("correct")),
                    "events_missed": sum(len(x["missed_events"]) for x in R),
                    "brief_fallbacks": sum(1 for x in R if x["brief_fallback"]),
                    "brief_retries": sum(1 for x in R if x["brief_attempts"] > 1),
                    "calibration_coverage": (r["calibration"] or {}).get("coverage"),
                    "measured_vs_true": (r["measurement"] or {}).get("holdout_ratio"),
                    "matchback_vs_true": (r["measurement"] or {}).get("matchback_ratio"),
                    "ledger_intact": r["ledger_intact"],
                    "printer_duplicates": r["printer_duplicates"],
                }
            )
        agg = {}
        for k in per_seed[0]:
            vals = [p[k] for p in per_seed]
            if isinstance(vals[0], (int, float)) and not isinstance(vals[0], bool) and None not in vals:
                a = np.asarray(vals, dtype=float)
                agg[k] = {"mean": float(a.mean()), "min": float(a.min()), "max": float(a.max())}
            elif isinstance(vals[0], dict):
                agg[k] = {kk: float(np.mean([v[kk] for v in vals])) for kk in vals[0]}
            elif isinstance(vals[0], bool):
                agg[k] = all(vals)
            else:
                agg[k] = vals
        out[policy] = {"seeds": per_seed, "summary": agg}
    # paired differences against today's process, seed by seed (same market, same letters' fate)
    base = out["today"]["seeds"]
    for policy in POLICIES:
        d = np.array([p["profit"] - b["profit"] for p, b in zip(out[policy]["seeds"], base)])
        rel = np.array([(p["profit"] - b["profit"]) / b["profit"] for p, b in zip(out[policy]["seeds"], base)])
        out[policy]["vs_today"] = {
            "profit_diff_mean": float(d.mean()),
            "profit_diff_min": float(d.min()),
            "profit_diff_max": float(d.max()),
            "profit_rel_mean": float(rel.mean()),
            "seeds_better": int((d > 0).sum()),
        }
    return out


def main(split: str) -> None:
    if split != "dev":
        if subprocess.run([sys.executable, str(ROOT / "scripts" / "lock.py"), "verify", split]).returncode:
            sys.exit(f"the {split} lock does not verify; the run is refused")
    jobs = [(p, split, s) for s in range(SEEDS) for p in POLICIES]
    # one fresh process per run: a market holds about 600 MB, and reference cycles would keep it alive
    with ProcessPoolExecutor(max_workers=2, max_tasks_per_child=1) as ex:
        runs = list(ex.map(one, jobs))
    report = {
        "split": split,
        "seeds": SEEDS,
        "rounds": len(runs[0]["rounds"]),
        "policies": summarise(runs),
        "agent_seed0": next(r for r in runs if r["policy"] == "agent" and r["seed"] == 0),
        "today_seed0": [
            {k: x[k] for k in ("round", "letters", "spend", "exp_incremental_value", "attributed_funded")}
            for x in next(r for r in runs if r["policy"] == "today" and r["seed"] == 0)["rounds"]
        ],
    }
    path = ROOT / "reports" / f"{split}.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True, default=float) + "\n")
    s = report["policies"]
    for p in POLICIES:
        print(
            f"{p:16s} profit £{s[p]['summary']['profit']['mean']:>12,.0f}"
            f"  vs today {s[p]['vs_today']['profit_rel_mean']:+.1%}"
            f"  breaches {s[p]['summary']['breach_letters']['mean']:>8,.1f}"
            f"  minutes/round {s[p]['summary']['person_minutes_per_round']['mean']:>6.0f}"
        )


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
