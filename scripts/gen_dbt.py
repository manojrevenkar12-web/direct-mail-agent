"""Write warehouse/models/mail_universe.sql from config/suppressions.yaml (tests fail if it is stale)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mailagent.rules import sql_model  # noqa: E402

(ROOT / "warehouse" / "models" / "mail_universe.sql").write_text(sql_model())
print("wrote warehouse/models/mail_universe.sql")
