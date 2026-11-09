"""RESULTS.md and the console's data, generated from reports/*.json. CI fails if either is stale."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "today": "Today's process: top of the response score, one house letter, a person builds the file",
    "for_loop": "A for-loop: the agent's code without a model (a person types the directions into a form)",
    "agent": "The agent",
    "agent_no_delay": "The agent, counting applications per letter (no delay adjustment)",
    "agent_no_holdout": "The agent without the measurement holdout",
    "agent_cell_holdouts": "The agent ranking cells by holdout-measured lift (10% holdouts)",
    "unguarded_llm": "The same model with no checks on its directions and no file checks",
}
ORDER = list(NAMES)


def load(name: str) -> dict | None:
    p = ROOT / "reports" / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def m(s: dict, k: str) -> float:
    v = s[k]
    return v["mean"] if isinstance(v, dict) else v


def gbp(x: float) -> str:
    return f"£{x:,.0f}"


def table(rep: dict) -> list[str]:
    P = rep["policies"]
    out = [
        "| Policy | Incremental profit (12 rounds) | vs today | Seeds better | Letters"
        " | Letters to people who must not get one | Person-minutes a round | Model cost a round |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in ORDER:
        if p not in P:
            continue
        s, v = P[p]["summary"], P[p]["vs_today"]
        lo, hi = s["profit"]["min"], s["profit"]["max"]
        out.append(
            f"| {NAMES[p]} | {gbp(m(s, 'profit'))} ({gbp(lo)}–{gbp(hi)}) | {v['profit_rel_mean']:+.1%} | "
            f"{v['seeds_better'] if p != 'today' else '–'} of {rep['seeds']} | {m(s, 'letters'):,.0f} | "
            f"{m(s, 'breach_letters'):,.0f} | {m(s, 'person_minutes_per_round'):.0f} | "
            f"£{m(s, 'llm_gbp_per_round'):.2f} |"
        )
    return out


def console(dev: dict, held: dict, sample: dict) -> dict:
    a = held["agent_seed0"]
    last = next(r for r in reversed(a["rounds"]) if r["letters"] > 0)
    P = held["policies"]
    return {
        "split": "heldout2",
        "seeds": held["seeds"],
        "round": {
            k: last[k]
            for k in (
                "round",
                "drop_date",
                "letters",
                "holdout",
                "spend",
                "budget",
                "excluded_sectors",
                "creative_shares",
                "anomalies",
                "directions",
                "plan_cells",
                "exp_incremental_value",
            )
        },
        "rounds": [
            {
                k: r[k]
                for k in (
                    "round",
                    "drop_date",
                    "letters",
                    "spend",
                    "exp_incremental_value",
                    "attributed_funded",
                    "mail_caused_funded",
                    "person_minutes",
                    "person_tasks",
                    "paused",
                )
            }
            for r in a["rounds"]
        ],
        "today": held["today_seed0"],
        "policies": [
            {
                "id": p,
                "name": NAMES[p],
                "profit": m(P[p]["summary"], "profit"),
                "profit_min": P[p]["summary"]["profit"]["min"],
                "profit_max": P[p]["summary"]["profit"]["max"],
                "vs_today": P[p]["vs_today"]["profit_rel_mean"],
                "breaches": m(P[p]["summary"], "breach_letters"),
                "minutes": m(P[p]["summary"], "person_minutes_per_round"),
            }
            for p in ORDER
            if p in P
        ],
        "agent": {
            k: (m(P["agent"]["summary"], k) if P["agent"]["summary"].get(k) is not None else None)
            for k in (
                "model_read_correct",
                "directions_correct",
                "directions_stopped",
                "wrong_effects",
                "anomaly_real_detected",
                "anomaly_real_diagnosed",
                "anomaly_false_alarms",
                "anomaly_false_dismissed",
                "events_missed",
                "person_tasks_per_round",
                "llm_gbp_per_round",
                "measured_vs_true",
                "matchback_vs_true",
                "brief_retries",
                "brief_fallbacks",
            )
        },
        "dev_vs_today": dev["policies"]["agent"]["vs_today"]["profit_rel_mean"],
        "sample": sample,
    }


def sample_round() -> dict:
    """One real round of the agent on a small market, for the console: brief, checks, directions, decision record."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    import numpy as np

    from agentrt.approvals import Person
    from agentrt.store import connect
    from mailagent import settings
    from mailagent.agent import RoundAgent
    from mailworld.adapters import World, ports
    from mailworld.llm import SimulatedReader
    from mailworld.market import Market

    world = World(Market("dev", size=80_000))
    truth: dict = {}
    agent = RoundAgent(connect(), reader=SimulatedReader(truth, set(), seed=5), **ports(world))
    head = Person("sam.head", "head_of_direct_acquisition")
    out = None
    for r in (1, 2):
        for msg, t in world.inbox_for(r):
            truth[msg.id] = t
        out = agent.plan_round(r)
        if r == 1:
            agent.approvals.decide(out.approval_id, person=head, approve=True, at=settings.iso(settings.plan_date(r)))
            sub = agent.release(out)
            world.m.print_and_drop(r, out.file, np.asarray(sub["withdraw"], dtype=np.int64))
    entries = agent.ledger.entries("round-02")
    return {
        "round": out.round,
        "drop_date": out.plan.drop_date,
        "sha256": out.file.sha256,
        "brief": out.brief,
        "checks": [c.model_dump() for c in out.checks],
        "plan": {k: v for k, v in out.plan.model_dump().items() if k not in ("band_edges",)},
        "directions": [
            {k: d.get(k) for k in ("kind", "sender", "sender_role", "applied", "why", "value", "sector", "quote")}
            for d in out.directions
            if d["kind"] != "none"
        ],
        "anomalies": out.anomalies,
        "suppressed": out.suppressed,
        "eligible": out.eligible,
        "ledger": [{k: e[k] for k in ("seq", "at", "actor", "kind", "reason", "hash")} for e in entries],
        "ledger_intact": agent.ledger.verify()[0],
    }


def main() -> None:
    dev, v1, held = load("dev"), load("heldout"), load("heldout2")
    lines = [
        "# Results",
        "",
        "Generated by `scripts/report.py` from `reports/*.json`; do not edit. Every number is a mean over 5 market"
        " seeds of 12 monthly rounds (about 2.3 million letters a year), against the simulated market's truth."
        " The market,"
        " the people in the loop and the model's error rates are simulations: see the README for what that does and"
        " does not show.",
        "",
    ]
    for name, rep, note in (
        ("Held-out (`heldout2`, run once after `config/heldout2.lock`)", held, "The reported result."),
        ("Development (`dev`, where everything was tuned)", dev, ""),
    ):
        if not rep:
            continue
        lines += [f"## {name}", "", note, ""] if note else [f"## {name}", ""]
        lines += table(rep)
        a = rep["policies"]["agent"]["summary"]
        lines += [
            "",
            f"- The model read {m(a, 'model_read_correct'):.1%} of emails right first time. The checks stopped "
            f"{m(a, 'directions_stopped'):.1f} directions a year (misread figures, a spoofed sender, an agency asking "
            f"to ignore suppressions); after the Head of Direct Acquisition answered the agent's questions, "
            f"{m(a, 'directions_correct'):.0%} of emails had the right effect and {m(a, 'wrong_effects'):.0f} reached "
            "a plan wrongly.",
            f"- Anomalies: {m(a, 'anomaly_real_detected'):.1f} real incidents detected a year, "
            f"{m(a, 'anomaly_real_diagnosed'):.1f} diagnosed and routed to the right owner; "
            f"{m(a, 'anomaly_false_alarms'):.1f} false alarms, {m(a, 'anomaly_false_dismissed'):.1f} dismissed by the "
            f"model without bothering anyone; {m(a, 'events_missed'):.1f} incidents missed.",
            f"- What mail was worth: the agent's 5% holdout put the applications mail caused at "
            f"{m(a, 'measured_vs_true'):.2f}× the truth; counting every application from a mailed business (matchback) "
            f"put it at {m(a, 'matchback_vs_true'):.1f}×.",
            f"- A person was needed {m(a, 'person_tasks_per_round'):.1f} times a round besides the approval; the brief "
            f"needed a second attempt {m(a, 'brief_retries'):.1f} times a year and fell back to the template "
            f"{m(a, 'brief_fallbacks'):.0f} times.",
            "",
        ]
    if v1:
        P = v1["policies"]
        lines += [
            "## The first held-out run (`heldout`, spent)",
            "",
            "The first version ran once on `heldout` (`config/heldout.lock`, commit 427c438) and earned "
            f"{P['agent']['vs_today']['profit_rel_mean']:+.1%} over today's process, against "
            f"{P['agent_matchback']['vs_today']['profit_rel_mean']:+.1%} for learning without holdouts. Two design "
            "flaws, both mine: every cell started from the same prior, ignoring the existing predictive models (in "
            "round 1 it filled the cells the models rank lowest), and cells kept only for learning had about 110 "
            "held-out businesses, too few to tell anything at application rates under 1%, so a good cell written off "
            "early never came back. The fix starts every cell from the models' prediction, ranks by the mailed arm "
            "and keeps a small holdout for measurement. Because the fix was found on `heldout`, that split is spent; "
            "`heldout2` was defined before the fixed agent ran on anything but `dev`.",
            "",
        ]
    (ROOT / "RESULTS.md").write_text("\n".join(lines))
    if dev and held:
        out = ROOT / "web" / "public" / "data" / "console.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        data = console(dev, held, sample_round())
        out.write_text(json.dumps(data, indent=1, sort_keys=True, default=float) + "\n")
    print("wrote RESULTS.md")


if __name__ == "__main__":
    main()
