"""Write the pending attribution labels for the second model (plan D21).

    python -m fvd.second_model_package   # writes crosswalks/pending_second_model/states.jsonl

One line per pending label: its id, the same state and category question Jev
received (codebook section 2), and the options. The current mapping and Jev's
answers are left out, so the second model labels blind. The rest of the
package (run_second_model.py, README.md, requirements.txt, .env.example) is
standalone and imports nothing from this repository.
"""

from __future__ import annotations

import json

import pandas as pd

from .jev_label import CATEGORY, states
from .paths import CROSSWALKS

PKG = CROSSWALKS / "pending_second_model"


def main() -> None:
    cw = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    pending = set(cw[(cw.source_table == "EFO") & (cw.status == "pending")].label_key)
    rows = [s for s in states().values() if s["crosswalk"] == "attribution_labels" and s["key"] in pending]
    with open(PKG / "states.jsonl", "w", encoding="utf-8") as f:
        for s in sorted(rows, key=lambda s: s["id"]):
            f.write(json.dumps({"id": s["id"], "key": s["key"], "state": s["state"],
                                "question": CATEGORY, "options": list(CATEGORY["criteria"])},
                               ensure_ascii=False) + "\n")
    print(f"{len(rows)} pending labels -> {(PKG / 'states.jsonl').relative_to(CROSSWALKS.parent)}")


if __name__ == "__main__":
    main()
