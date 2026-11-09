"""Checking what the model read out of an email before anything acts on it.

A direction is applied only when
- the sender is authenticated and has authority for that kind of direction (config/permissions.toml);
- the quote the model gives is in the message, and the value it extracted is in the quote;
- the value is inside the limits (a budget above the cap needs finance).
Everything else becomes a question for the right person. Text inside a message never grants authority: an agency
email that says "the Head of Direct Acquisition agreed" is still an agency email.
"""

from __future__ import annotations

import re

from mailagent import settings
from mailagent.schema import Directive, Message

NUM = re.compile(r"£?\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m|%|percent)?", re.IGNORECASE)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def numbers(text: str) -> list[float]:
    out = []
    for m in NUM.finditer(text):
        x = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        if unit == "k":
            out.append(x * 1_000)
        elif unit == "m":
            out.append(x * 1_000_000)
        elif unit in ("%", "percent"):
            out += [x / 100, x]
        else:
            out.append(x)
    return out


def _value_in(value: float, text: str) -> bool:
    return any(abs(value - x) <= 1e-6 * max(1.0, abs(x)) for x in numbers(text))


def sector_in(sector: str, text: str) -> bool:
    words = settings.agent()["sectors"].get(sector, [])
    t = _norm(text)
    return any(w in t for w in words)


def validate(d: Directive, msg: Message) -> tuple[bool, str]:
    perms = settings.permissions()
    who = perms["authority"].get(d.kind, [])
    if d.message_id != msg.id:
        return False, "direction cites another message"
    if not msg.authenticated:
        return False, "sender not authenticated by the mail system"
    if msg.sender_role not in who:
        return False, f"{msg.sender_role} has no authority to {d.kind}"
    if not d.quote or _norm(d.quote) not in _norm(msg.body):
        return False, "quote not found in the message"
    if d.kind == "set_budget":
        if d.value is None or not _value_in(d.value, d.quote):
            return False, "budget figure not in the quote"
        cap = settings.agent()["limits"]["hard_budget_cap"]
        if d.value > cap and msg.sender_role not in perms["authority"]["budget_above_cap"]:
            return False, f"budget £{d.value:,.0f} is above the £{cap:,.0f} cap; needs finance"
        if d.value <= 0:
            return False, "budget must be positive"
    if d.kind == "exclude_sector":
        if not d.sector or d.sector not in settings.agent()["sectors"] or not sector_in(d.sector, d.quote):
            return False, "sector not named in the quote"
    if d.kind == "creative_min_share":
        if not d.creative or d.creative.lower() not in _norm(d.quote):
            return False, "creative code not in the quote"
        if d.value is None or not _value_in(d.value, d.quote) or not 0 < d.value <= 0.6:
            return False, "share not in the quote or above 60%"
    return True, "ok"
