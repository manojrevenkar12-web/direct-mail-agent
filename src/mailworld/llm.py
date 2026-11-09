"""A simulated language model with the mistakes real ones make, at configurable rates.

It reads the truth of each email (it lives on the truth side), and gets it wrong as often as config/world.toml
says: misread figures, the wrong sector, following an instruction in an untrusted email, trusting a spoofed sender,
missing an objection, a wrong figure in the brief. The agent is also run against Claude (mailagent.claude); this
stand-in makes the guardrails' effect measurable and repeatable.
"""

from __future__ import annotations

import json

import numpy as np

from mailagent import settings
from mailagent.schema import Directive, InboxReading, Message, Route, Triage, Usage
from mailworld.market import config

CAUSE_OF = {
    "mail_code_share_fell": "tracking_break",
    "feed_rows_missing": "feed_outage",
    "score_distribution_moved": "model_update",
}
EVENT_CAUSE = {
    "tracking_break": "tracking_break",
    "feed_outage": "feed_incomplete",
    "model_update": "model_shift",
    "competitor_offer": "response_drop",
}
CAUSES = ["tracking_break", "feed_incomplete", "model_shift", "response_drop", "noise"]


def true_cause(anomaly: str, events: set[str]) -> str:
    if anomaly in CAUSE_OF:
        ev = CAUSE_OF[anomaly]
        return EVENT_CAUSE[ev] if ev in events else "noise"
    if "competitor_offer" in events:
        return "response_drop"
    if "feed_outage" in events:
        return "feed_incomplete"
    return "noise"


class SimulatedReader:
    def __init__(self, truth: dict[str, dict], events: set[str], seed: int):
        self.truth, self.events = truth, events
        self.p = config()["llm"]
        self.rng = np.random.default_rng(seed)
        self.calls = 0

    def _usage(self, n_in: int, n_out: int) -> Usage:
        self.calls += 1
        sys = self.p["system_tokens"]
        return Usage(
            input_tokens=n_in + (sys if self.calls == 1 else 0),
            output_tokens=n_out,
            cache_read_tokens=0 if self.calls == 1 else sys,
        )

    def read_inbox(self, messages: list[Message], context: dict) -> tuple[InboxReading, Usage]:
        p, rng = self.p, self.rng
        dirs, routes = [], []
        for m in messages:
            t = self.truth[m.id]
            kind = t["kind"]
            if kind == "objection":
                if rng.random() < p["p_route"]:
                    routes.append(Route(message_id=m.id, owner_role="operations", reason="objection to mail"))
                continue
            if kind in ("agency_volume", "spoofed_budget"):
                follow = p["p_follow_injection"] if kind == "agency_volume" else p["p_follow_spoof"]
                if rng.random() < follow:
                    dirs += [Directive(message_id=m.id, **d) for d in t["tempting"]]
                else:
                    routes.append(
                        Route(
                            message_id=m.id,
                            owner_role="head_of_direct_acquisition",
                            reason="asks for a change nobody with authority has made",
                        )
                    )
                continue
            if kind == "sales_ask":
                if rng.random() < p["p_route"]:
                    routes.append(
                        Route(
                            message_id=m.id,
                            owner_role="head_of_direct_acquisition",
                            reason="a question for whoever sets the commercial direction",
                        )
                    )
                continue
            for d in t["expect"]:
                pk = {
                    "set_budget": "p_budget",
                    "exclude_sector": "p_sector",
                    "creative_min_share": "p_creative",
                    "pause_round": "p_pause",
                }[d["kind"]]
                if rng.random() < p[pk]:
                    dirs.append(Directive(message_id=m.id, **d))
                    continue
                wrong = dict(d)
                if d["kind"] == "set_budget":
                    wrong["value"] = round(d["value"] * float(rng.choice([0.1, 1.1, 10.0])), 2)
                elif d["kind"] == "exclude_sector":
                    others = [s for s in settings.agent()["sectors"] if s != d["sector"]]
                    wrong["sector"] = str(rng.choice(others))
                elif d["kind"] == "creative_min_share":
                    wrong["value"] = round(d["value"] / 10, 4)
                else:
                    continue  # a missed pause: no direction at all
                dirs.append(Directive(message_id=m.id, **wrong))
        n_in = p["tokens_per_message"] * len(messages) + len(json.dumps(context, default=str)) // 4
        n_out = p["tokens_per_direction_out"] * (len(dirs) + len(routes)) + 40
        return InboxReading(directives=dirs, routes=routes), self._usage(n_in, n_out)

    def triage(self, anomalies: list[dict], evidence: dict, owners: dict) -> tuple[list[Triage], Usage]:
        out = []
        for a in anomalies:
            cause = true_cause(a["anomaly"], self.events)
            if self.rng.random() >= self.p["p_triage"]:
                cause = str(self.rng.choice([c for c in CAUSES if c != cause]))
            owner = owners.get(cause, "head_of_direct_acquisition") if cause != "noise" else "none"
            out.append(
                Triage(
                    anomaly=a["anomaly"],
                    cause=cause,
                    owner_role=owner,
                    explanation=f"{a['anomaly']} looks like {cause.replace('_', ' ')} given the evidence",
                )
            )
        n_in = 400 + len(json.dumps(evidence)) // 4
        return out, self._usage(n_in, 120 * len(out) + 30)

    def write_brief(self, stats: dict, attempt: int) -> tuple[str, Usage]:
        s = stats
        letters = s["letters"]
        if self.rng.random() < self.p["p_brief_wrong_number"]:
            letters = int(letters * 1.07) + 1
        lines = [
            f"Round {s['round']} drops on {s['drop_date']}. The file has {letters:,} letters and {s['holdout']:,} "
            f"businesses held out ({s['holdout_share_pct']}%) to measure what mail adds.",
            f"It costs £{s['cost']:,.2f} against a budget of £{s['budget']:,.0f}, and the expected incremental "
            f"funded value is £{s['expected_incremental_value']:,.0f}.",
            f"{s['checks_passed']} of {s['checks_total']} checks passed.",
        ]
        for d in s["directions_applied"]:
            lines.append(f"Applied: {d['kind'].replace('_', ' ')} from {d.get('sender', 'a colleague')}.")
        for d in s["directions_not_applied"]:
            lines.append(f"Not applied: {d['kind'].replace('_', ' ')} from {d.get('sender')}, because {d['why']}.")
        for a in s["anomalies"]:
            if a.get("cause") and a["cause"] != "noise":
                lines.append(
                    f"{a['anomaly'].replace('_', ' ').capitalize()}: likely {a['cause'].replace('_', ' ')}"
                    f", sent to {a['owner_role'].replace('_', ' ')}."
                )
        text = "\n".join(lines)
        return text, self._usage(500 + len(json.dumps(stats, default=str)) // 4, len(text) // 4)
