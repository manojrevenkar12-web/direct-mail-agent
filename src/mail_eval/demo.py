"""A few rounds, printed: what the agent read, what it planned, what the brief said, what the person approved.

dma demo [--rounds N] [--size N] [--model sim|claude]
"""

from __future__ import annotations

import argparse

from agentrt.approvals import Person
from agentrt.store import connect
from mailagent import settings
from mailagent.agent import RoundAgent
from mailworld.adapters import World, ports
from mailworld.llm import SimulatedReader
from mailworld.market import Market


def demo(rounds: int = 3, size: int = 200_000, model: str = "sim") -> None:
    market = Market("dev", size=size)
    world = World(market)
    truth: dict = {}
    if model == "claude":
        from mailagent.claude import ClaudeReader

        reader = ClaudeReader()
    else:
        reader = SimulatedReader(truth, set(), seed=1)
    agent = RoundAgent(connect(), reader=reader, **ports(world))
    for r in range(1, rounds + 1):
        for m, t in world.inbox_for(r):
            truth[m.id] = t
        out = agent.plan_round(r)
        print(f"\n=== round {r}, drop {out.plan.drop_date} ===")
        for d in out.directions:
            if d["kind"] != "none":
                print(f"  {'applied' if d['applied'] else 'not applied':12s} {d['kind']:20s} {d.get('why', '')}")
        for a in out.anomalies:
            print(f"  anomaly {a['anomaly']}: {a.get('cause')} -> {a['owner_role']}")
        print(f"  plan: {out.plan.letters:,} letters, {out.plan.holdout:,} held out, £{out.plan.cost:,.0f}")
        print("  checks:", ", ".join(f"{c.check}={'ok' if c.passed else 'FAIL'}" for c in out.checks))
        print("  brief:", (out.brief or "").replace("\n", "\n         "))
        if out.approval_id:
            agent.approvals.decide(
                out.approval_id,
                person=Person("sam.head", "head_of_direct_acquisition"),
                approve=True,
                at=settings.iso(settings.plan_date(r)),
            )
            sub = agent.release(out)
            print("  printer:", sub and sub["job"], "withdrawn", len(sub["withdraw"]) if sub else 0)
            market.print_and_drop(r, out.file if sub else None, None)


def cli(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="dma")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--rounds", type=int, default=3)
    d.add_argument("--size", type=int, default=200_000)
    d.add_argument("--model", choices=["sim", "claude"], default="sim")
    a = p.parse_args(argv)
    demo(rounds=a.rounds, size=a.size, model=a.model)


if __name__ == "__main__":
    cli()
