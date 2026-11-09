"""Build the warehouse models with dbt on DuckDB over a simulated universe and compare with the agent's rules.

python scripts/dbt_check.py <work dir>
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from mailagent import rules  # noqa: E402
from mailworld.market import Market  # noqa: E402


def main(work: Path) -> int:
    work.mkdir(parents=True, exist_ok=True)
    db = work / "wh.duckdb"
    uni = Market("dev", size=5_000).universe("2026-01-17")
    con = duckdb.connect(str(db))
    con.register("df", pd.DataFrame(uni))
    con.execute("create or replace table companies as select * from df")
    con.close()
    env = {**os.environ, "DMA_DUCKDB_PATH": str(db)}
    cmd = [
        "dbt",
        "build",
        "--project-dir",
        str(ROOT / "warehouse"),
        "--profiles-dir",
        str(ROOT / "warehouse"),
        "--target-path",
        str(work / "target"),
        "--log-path",
        str(work / "logs"),
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    print(r.stdout[-3000:])
    if r.returncode:
        print(r.stderr[-2000:])
        return r.returncode
    con = duckdb.connect(str(db))
    got = con.execute("select suppression_mask from mail_universe order by company_id").fetchdf()
    want = rules.evaluate(uni)
    same = (got["suppression_mask"].to_numpy() == want).all()
    print("dbt and the agent agree on every company:", bool(same))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dma-dbt")))
