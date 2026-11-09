"""The agent's ports, implemented over the simulated market."""

from __future__ import annotations

import numpy as np

from mailagent import settings
from mailagent.schema import Message
from mailworld import inbox
from mailworld.market import Market, day


class World:
    """Everything the evaluation wires into one agent run, plus the truth it scores against."""

    def __init__(self, market: Market):
        self.m = market
        self.messages: dict[int, list[tuple[Message, dict]]] = {}
        self.submissions: list[dict] = []

    # ports -------------------------------------------------------------------------------------------------
    def universe(self, as_of: str) -> dict[str, np.ndarray]:
        return self.m.universe(as_of)

    def scores(self, ids: np.ndarray, as_of: str):
        return self.m.scores(ids, as_of)

    def snapshot(self, as_of: str) -> dict:
        r = self.m.round_of_day(day(as_of) + settings.agent()["round"]["plan_days_before_drop"])
        return self.m.snapshot(as_of, outage=self.m.event(r, "feed_outage"))

    def inbox_for(self, r: int) -> list[tuple[Message, dict]]:
        if r not in self.messages:
            self.messages[r] = inbox.build(self.m, r)
        return self.messages[r]

    def messages_between(self, since: str, until: str) -> list[Message]:
        r = self.m.round_of_day(day(until) + settings.agent()["round"]["plan_days_before_drop"])
        return [m for m, _ in self.inbox_for(r)]

    def creatives(self, as_of: str):
        return inbox.creatives(as_of)

    def submit(self, *, round: int, sha256: str, letters: int, mail_codes: list[str], withdraw: list[int]) -> dict:
        self.submissions.append({"round": round, "sha256": sha256, "letters": letters, "withdraw": len(withdraw)})
        return {"job": f"PH-{round:02d}-{sha256[:8]}", "letters": letters - len(withdraw), "withdraw": withdraw}


class _Port:
    def __init__(self, w: World, method: str):
        self.w, self.method = w, method


class Warehouse(_Port):
    def universe(self, as_of):
        return self.w.universe(as_of)


class Models(_Port):
    def scores(self, ids, as_of):
        return self.w.scores(ids, as_of)


class Results(_Port):
    def snapshot(self, as_of):
        return self.w.snapshot(as_of)


class Inbox(_Port):
    def messages(self, since, until):
        return self.w.messages_between(since, until)


class Register(_Port):
    def creatives(self, as_of):
        return self.w.creatives(as_of)


class Printer(_Port):
    def submit(self, **kw):
        return self.w.submit(**kw)


def ports(w: World) -> dict:
    return {
        "warehouse": Warehouse(w, ""),
        "models": Models(w, ""),
        "results": Results(w, ""),
        "inbox": Inbox(w, ""),
        "register": Register(w, ""),
        "printer": Printer(w, ""),
    }
