"""What crosses a boundary: messages in, directions and triage out of the model, the plan, the file checks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DirectiveKind = Literal[
    "set_budget", "exclude_sector", "creative_min_share", "pause_round", "override_suppression", "set_volume"
]
Cause = Literal["tracking_break", "feed_incomplete", "model_shift", "response_drop", "noise"]


class Message(BaseModel):
    id: str
    received: str
    sender: str
    sender_role: str  # from the staff directory, looked up by the mail system
    authenticated: bool  # the mail system verified the sender (DMARC pass, internal domain)
    subject: str
    body: str


class Directive(BaseModel):
    message_id: str
    kind: DirectiveKind
    value: float | None = None
    sector: str | None = None
    creative: str | None = None
    quote: str = Field(description="the exact sentence in the message that gives this direction")


class Route(BaseModel):
    message_id: str
    owner_role: str
    reason: str


class InboxReading(BaseModel):
    directives: list[Directive] = []
    routes: list[Route] = []


class Triage(BaseModel):
    anomaly: str
    cause: Cause
    owner_role: str
    explanation: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def __add__(self, o: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + o.input_tokens,
            output_tokens=self.output_tokens + o.output_tokens,
            cache_read_tokens=self.cache_read_tokens + o.cache_read_tokens,
        )


class Creative(BaseModel):
    code: str
    product: str
    approved: bool
    approved_until: str | None = None
    compliance_ref: str | None = None


class CellPlan(BaseModel):
    cell: str
    available: int
    letters: int
    holdout: int
    value_per_letter: float  # posterior mean incremental funded value per letter
    p_profitable: float
    sampled_net: float


class Plan(BaseModel):
    round: int
    drop_date: str
    budget: float
    letters: int
    holdout: int
    cost: float
    holdout_share: float
    cells: list[CellPlan]
    creative_shares: dict[str, float]
    excluded_sectors: list[str]
    model_version: str
    band_edges: list[float]
    value_edge: float
    expected_incremental_value: float
    paused: bool = False
    notes: list[str] = []


class Check(BaseModel):
    check: str
    passed: bool
    detail: str
