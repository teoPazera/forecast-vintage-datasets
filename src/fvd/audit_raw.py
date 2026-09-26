"""Check every stored raw file against its manifest row and for integrity.

Run:  python -m fvd.audit_raw [--fix]

Reports files whose SHA-256 differs from the manifest (should never happen:
raw files are immutable) and files that fail the integrity check (truncated
captures). With --fix, broken files are marked invalid in the manifest and
removed, so the next fetch tries another capture.
"""

from __future__ import annotations

import sys

from .http import check_integrity, invalidate, load_sources, sha256_file
from .paths import ROOT


def main(fix: bool = False) -> int:
    bad = 0
    for rel, row in load_sources().items():
        if row["status"] != "200":
            continue
        p = ROOT / rel
        if not p.exists():
            print(f"MISSING  {rel}")
            continue
        if sha256_file(p) != row["sha256"]:
            print(f"CHANGED  {rel}")
            bad += 1
            continue
        problem = check_integrity(p)
        if problem:
            bad += 1
            print(f"BROKEN   {rel}: {problem}")
            if fix:
                invalidate(p, problem)
    print(f"{bad} problem files")
    return bad


if __name__ == "__main__":
    main(fix="--fix" in sys.argv)
