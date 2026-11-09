"""One suppression definition, two executors: numpy for the agent and SQL for the warehouse must agree."""

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mailagent import rules, settings
from mailworld.market import Market


def test_numpy_and_sql_agree_on_every_company():
    duckdb = pytest.importorskip("duckdb")
    m = Market("dev", size=20_000)
    uni = m.universe("2026-01-17")
    # make every rule bite somewhere
    uni["days_since_last_letter"] = np.where(np.arange(m.n) % 7 == 0, 30, uni["days_since_last_letter"])
    uni["days_since_holdout"] = np.where(np.arange(m.n) % 11 == 0, 10, uni["days_since_holdout"])
    uni["letters_last_365"] = np.where(np.arange(m.n) % 13 == 0, 6, uni["letters_last_365"])
    uni["open_application"] = np.arange(m.n) % 17 == 0
    uni["days_since_decline"] = np.where(np.arange(m.n) % 19 == 0, 20, uni["days_since_decline"])
    mask = rules.evaluate(uni)
    assert all(v > 0 for v in rules.reasons(mask).values()), rules.reasons(mask)
    import pandas as pd

    df = pd.DataFrame({k: v for k, v in uni.items()})
    con = duckdb.connect()
    con.register("stg_companies", df)
    sql = rules.sql_model().replace("{{ ref('stg_companies') }}", "stg_companies")
    out = con.execute(sql + " order by company_id").fetchdf()
    assert (out["suppression_mask"].to_numpy() == mask).all()


def test_holdouts_stay_out_of_the_next_rounds():
    """The first version mailed held-out businesses in the next round, halving the measured lift."""
    ids = [r["id"] for r in settings.suppressions()]
    rule = next(r for r in settings.suppressions() if r["id"] == "recent_holdout")
    assert "recent_holdout" in ids
    assert rule["value"] >= settings.agent()["round"]["attribution_window_days"]


def test_generated_dbt_model_is_current():
    model = Path(settings.ROOT / "warehouse" / "models" / "mail_universe.sql")
    assert model.read_text() == rules.sql_model()


@pytest.mark.skipif(shutil.which("dbt") is None, reason="dbt not installed")
def test_dbt_build_on_duckdb(tmp_path):
    r = subprocess.run(
        [sys.executable, str(settings.ROOT / "scripts" / "dbt_check.py"), str(tmp_path)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
