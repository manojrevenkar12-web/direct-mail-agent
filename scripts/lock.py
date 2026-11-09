"""Pin everything that decides a held-out result before it runs.

python scripts/lock.py write <split>    # once, after the development run
python scripts/lock.py verify <split>   # scripts/evaluate.py <split> refuses to run unless this passes

A split is spent once it has run. config/heldout.lock pinned v1, which ran on `heldout`; the fixed agent was pinned
in config/heldout2.lock before it ran on `heldout2`.
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


def lock_path(split: str) -> Path:
    return ROOT / "config" / f"{split}.lock"


def lines() -> list[str]:
    return [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}" for p in PINNED]


def main(cmd: str, split: str = "heldout2") -> int:
    LOCK = lock_path(split)
    if cmd == "write":
        if LOCK.exists():
            sys.exit(f"{LOCK.name} exists; the {split} split is spent once it has been pinned")
        LOCK.write_text(
            f"# sha256 of every file that decides the {split} result, pinned before the {split} run\n"
            + "\n".join(lines())
            + "\n"
        )
        print(f"pinned {len(PINNED)} files")
        return 0
    if not LOCK.exists():
        print("no lock yet")
        return 1
    text = LOCK.read_text().splitlines()
    want = [x for x in text if x and not x.startswith(("#", "amended "))]
    # an amendment replaces a pinned hash after the run, with the reason, for changes that cannot move a result
    # (each one is proven by re-running the split and getting the same report byte for byte)
    for a in (x for x in text if x.startswith("amended ")):
        _, old, new, path = a.split()[:4]
        want = [new + "  " + path if w == old + "  " + path else w for w in want]
    diff = sorted(set(want) ^ set(lines()))
    for d in diff:
        print("changed:", d)
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "verify", sys.argv[2] if len(sys.argv) > 2 else "heldout2"))
