from __future__ import annotations

import tomllib
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


@cache
def agent() -> dict[str, Any]:
    return tomllib.loads((CONFIG / "agent.toml").read_text())


@cache
def permissions() -> dict[str, Any]:
    return tomllib.loads((CONFIG / "permissions.toml").read_text())


@cache
def costs() -> dict[str, Any]:
    return tomllib.loads((CONFIG / "costs.toml").read_text())


@cache
def suppressions() -> list[dict[str, Any]]:
    return yaml.safe_load((CONFIG / "suppressions.yaml").read_text())["rules"]


def drop_date(round_no: int) -> date:
    r = agent()["round"]
    return date.fromisoformat(r["first_drop"]) + timedelta(days=r["cadence_days"] * (round_no - 1))


def plan_date(round_no: int) -> date:
    return drop_date(round_no) - timedelta(days=agent()["round"]["plan_days_before_drop"])


def print_date(round_no: int) -> date:
    return drop_date(round_no) - timedelta(days=agent()["round"]["print_days_before_drop"])


def iso(d: date) -> str:
    return d.isoformat()
