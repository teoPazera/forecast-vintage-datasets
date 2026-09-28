"""Spot-check of rows settled by agreement (Teo's amendment, step 6, first half).

    python -m fvd.spot_check          # writes crosswalks/spot_check.csv
    python -m fvd.spot_check score [file]   # compares the answers with the settled mappings

Draws 20 rows, labels and heads together, uniformly from all rows settled by
agreement (keyword rules + Jev, D20), with a fixed recorded seed. The file shows
each row with its context and no answer: neither the current mapping nor Jev's.
The second-model half of the spot-check is drawn after the merge.
"""

from __future__ import annotations

import json
import random
import sys

import pandas as pd

from .jev_label import states
from .paths import CROSSWALKS

SEED = 20260929
N = 20
OUT = CROSSWALKS / "spot_check.csv"
DRAW = CROSSWALKS / "llm" / "spot_check_draw.json"


def settled() -> dict[str, str]:
    """(crosswalk, key) of every settled row -> its current mapping."""
    lab = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    hd = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    out = {("attribution_labels", r.label_key): r.category
           for r in lab[lab.status == "settled_agreement"].itertuples()}
    out.update({("pmd_heads", f"{r.measure_type}|{r.head_raw}"): r.hofd_sheet or "(none)"
                for r in hd[hd.status == "settled_agreement"].itertuples()})
    return out


def build() -> None:
    S = {(s["crosswalk"], s["key"]): s for s in states().values()}
    pool = sorted(settled())
    draw = random.Random(SEED).sample(pool, N)
    rows = []
    for n, k in enumerate(draw, start=1):
        st = S[k]["state"]
        if k[0] == "attribution_labels":
            context = (f"Table: {st['table_title']}. Section: {st['section']}."
                       + (f" Group heading above: {st['group_heading_above']}." if st.get("group_heading_above", "(none)") != "(none)" else "")
                       + " Rows: " + " | ".join(st["table_rows"]))
            rows.append({"n": n, "kind": "label", "row": st["label"], "context": context,
                         "answer_with": "a category from codebook.md section 2.3"})
        else:
            context = f"{st['head_type']}. Measures: {st['number_of_measures']}. Largest: " + " | ".join(st["largest_measures"][:4])
            rows.append({"n": n, "kind": "head", "row": st["head"], "context": context,
                         "answer_with": "a series code from crosswalks/llm/series_codes.csv, or (none)"})
    pd.DataFrame(rows).assign(your_answer="", comment="").to_csv(OUT, index=False)
    DRAW.write_text(json.dumps({"seed": SEED, "n": N, "pool": len(pool),
                                "rows": [{"n": i + 1, "crosswalk": c, "key": key} for i, (c, key) in enumerate(draw)]},
                               indent=1, ensure_ascii=False))
    print(f"{N} of {len(pool)} settled rows -> {OUT.name} (seed {SEED})")


def score(path=OUT) -> None:
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    draw = {str(x["n"]): x for x in json.loads(DRAW.read_text(encoding="utf-8"))["rows"]}
    cur = settled()
    agree = 0
    for r in d.itertuples():
        k = draw[r.n]
        mine = r.your_answer.split(":")[0].strip()
        now = cur.get((k["crosswalk"], k["key"]), "?")
        ok = mine == now
        agree += ok
        print(f"{r.n:>2} {'ok ' if ok else 'DIFF'} {r.row!r}: you {mine!r}, settled {now!r}")
    print(f"{agree} of {len(d)} agree")


if __name__ == "__main__":
    if sys.argv[1:2] == ["score"]:
        score(*sys.argv[2:3])
    else:
        build()
