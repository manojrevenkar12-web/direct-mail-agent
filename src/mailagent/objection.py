"""Objections to direct marketing must reach operations every time, so a rule finds them as well as the model.

In the evaluation the simulated model missed about one objection in twelve; a missed objection means a business
that said stop gets another letter. This is one place where a for-loop beats the agent, so both run.
"""

from __future__ import annotations

import re

PATTERNS = [
    r"\bdo(?:es)? not want (?:any )?(?:more )?letters\b",
    r"\bdon't want (?:any )?(?:more )?letters\b",
    r"\bstop (?:sending|the) letters\b",
    r"\bremove (?:us|them|me) from (?:your|the) mailing\b",
    r"\bunsubscribe\b",
    r"\bno more (?:mail|letters)\b",
]
RX = re.compile("|".join(PATTERNS), re.IGNORECASE)


def is_objection(text: str) -> bool:
    return bool(RX.search(text))
