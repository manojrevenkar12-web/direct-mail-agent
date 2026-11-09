"""Pin everything that decides the held-out result before it runs.

python scripts/lock.py write    # once, after the development run
python scripts/lock.py verify   # scripts/evaluate.py heldout refuses to run unless this passes
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED = sorted(
    [
        *(ROOT / "src" / "agentrt").rglob("*.py"),
        *(ROOT / "src" / "mailagent").rglob("*.py"),
        *(ROOT / "src" / "mailworld").rglob("*.py"),
        *(ROOT / "src" / "mail_eval").rglob("*.py"),
        *(ROOT / "config").glob("*.toml"),
        ROOT / "config" / "suppressions.yaml",
        ROOT / "scripts" / "evaluate.py",
        ROOT / "reports" / "dev.json",
    ]
)
LOCK = ROOT / "config" / "heldout.lock"


def lines() -> list[str]:
    return [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}" for p in PINNED]


def main(cmd: str) -> int:
    if cmd == "write":
        if LOCK.exists():
            sys.exit("config/heldout.lock exists; the held-out split is spent once it has been pinned")
        LOCK.write_text(
            "# sha256 of every file that decides the held-out result, pinned before the held-out run\n"
            + "\n".join(lines())
            + "\n"
        )
        print(f"pinned {len(PINNED)} files")
        return 0
    if not LOCK.exists():
        print("no lock yet")
        return 1
    want = [x for x in LOCK.read_text().splitlines() if x and not x.startswith("#")]
    diff = sorted(set(want) ^ set(lines()))
    for d in diff:
        print("changed:", d)
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "verify"))
