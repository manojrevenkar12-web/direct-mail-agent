"""What the agent needs from the outside, as protocols. Production adapters: Snowflake (dbt models) for the
universe, iwoca's model service for scores, the results tables, the mail system, the compliance register, the print
house's SFTP. The evaluation wires simulated ones."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from mailagent.schema import Creative, InboxReading, Message, Triage, Usage


class Warehouse(Protocol):
    def universe(self, as_of: str) -> dict[str, np.ndarray]: ...


class Models(Protocol):
    def scores(self, company_ids: np.ndarray, as_of: str) -> tuple[np.ndarray, np.ndarray, str]:
        """(response probability, expected value if funded, model version)."""


class Results(Protocol):
    def snapshot(self, as_of: str) -> dict:
        """{"rows": [aggregate rows], "expected_rows": int}. Aggregates only; no company appears."""


class Inbox(Protocol):
    def messages(self, since: str, until: str) -> list[Message]: ...


class CreativeRegister(Protocol):
    def creatives(self, as_of: str) -> list[Creative]: ...


class Printer(Protocol):
    def submit(self, *, round: int, sha256: str, letters: int, mail_codes: list[str], withdraw: list[int]) -> dict:
        """Send the approved file. `withdraw` lists companies suppressed since approval: the print house drops them,
        the only change allowed after a person approved the file."""


class Reader(Protocol):
    """The language model. It reads and writes text; it never sees a company, and it decides nothing."""

    def read_inbox(self, messages: list[Message], context: dict) -> tuple[InboxReading, Usage]: ...

    def triage(self, anomalies: list[dict], evidence: dict, owners: dict) -> tuple[list[Triage], Usage]: ...

    def write_brief(self, stats: dict, attempt: int) -> tuple[str, Usage]: ...
