"""Label crosswalk rows with Jev (TypeSafe System One), following crosswalks/codebook.md.

    python -m fvd.jev_label pilot          # the 10 pilot rows (crosswalks/llm/pilot_ids.json)
    python -m fvd.jev_label run L0001 ...  # given rows
    python -m fvd.jev_label all            # every row without a result for its current state

One request per row, several questions evaluated in parallel on the same state:

- `category` (labels) or `series` (heads): a direct Choice over the codebook's
  options. Its probabilities give the top two answers and the confidence used
  for routing.
- Narrow yes/no questions (Nouls), one per semantic test in codebook rules
  A3-A11 and B3. Code applies the codebook's rule order to them
  (`rule_category`), so policy stays in code and each answer can be traced to
  the rule that decided it. Tests a regular expression can do (section
  headings, "PSNB-neutral", "standard rated share") are done in code.

Results are appended to crosswalks/llm/jev_results.jsonl with the versioned
model id, token usage and a timestamp. The key is read from TYPESAFE_API_KEY
(environment or .env) and never written anywhere.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

from .paths import CROSSWALKS, ROOT

LLM = CROSSWALKS / "llm"
RESULTS = LLM / "jev_results.jsonl"
MODEL = "jev-latest"   # the response records the versioned id that answered
YES = 0.5

# --- labels: the direct Choice (codebook 2.3, with the rule boundaries as not_for) ---
CATEGORY = {
    "instructions": {
        "question": ("The OBR explains why its tax receipts forecast changed since its previous "
                     "forecast. Each row of its table is one cause. Which category describes the "
                     "cause in the row `label`?"),
        "context": ("`section` is the heading the row sits under. `group_heading_above` is the "
                    "subtotal row the row belongs to, which acts as its heading. `table_rows` lists "
                    "the whole table; the row to label starts with '>>'. A row tagged 'group "
                    "heading' is the total of the rows beneath it."),
    },
    "criteria": {
        "policy": {
            "what": "The effect of government decisions announced at this fiscal event.",
            "includes": ["scorecard and non-scorecard measures", "direct and indirect effects of "
                         "government decisions", "devolved administration decisions",
                         "named measures under a government-decisions heading"],
            "not_for": "Re-estimates (recostings) of measures announced at earlier events.",
        },
        "economic_determinants": {
            "what": "Changes to the OBR's economy forecast that move the tax base.",
            "includes": ["earnings, wages, employment, self-employment income",
                         "consumption, investment, company profits",
                         "property prices and transactions, equity prices, interest rates, "
                         "exchange rates, oil and gas prices and production",
                         "inflation, GDP, population, productivity, hours, unemployment",
                         "'economic determinants', 'determinants', 'market assumptions', "
                         "'tax base'"],
            "not_for": "Effective tax rates, which are modelling.",
        },
        "calibration_to_outturn": {
            "what": "New data on actual receipts or outturn that arrived since the previous forecast.",
            "includes": ["'outturn', 'receipts data', 'latest receipts', 'liabilities data'",
                         "surpluses or shortfalls in recent months' receipts",
                         "receipts of a completed year",
                         "labels that mention outturn or receipts together with modelling"],
        },
        "classification_one_offs": {
            "what": "Statistical classification or accounting-treatment changes, and one-off items.",
            "includes": ["reclassifications", "new items brought into the receipts measure",
                         "litigation, fines, one-off dividends, one-off compensation or repayments"],
        },
        "modelling_other": {
            "what": "Model changes, forecaster judgement and anything that is not another cause.",
            "includes": ["recostings of measures announced at earlier events",
                         "effective tax rates and 'pre-measures' factors",
                         "error correction", "PSNB-neutral items",
                         "the standard-rated share, unless the label names an economic cause of the "
                         "change (saying what the share is of, e.g. 'of consumer spending', is not a cause)",
                         "residuals and 'other' outside a policy or determinants heading"],
        },
        "underlying_unsplit": {
            "what": "Not a cause: the whole non-policy change reported as one number.",
            "examples": ["Underlying forecast differences"],
        },
        "by_tax_head": {
            "what": "Not a cause: one tax in a split of the change by tax rather than by cause.",
            "examples": ["Value added tax, under a 'By tax head' heading"],
        },
    },
}

# --- labels: narrow tests, each tied to a codebook rule ---
LABEL_NOULS = {
    "data": ("A3", "Does `label` refer to new data on actual tax receipts, outturn or liabilities? "
                   "For example 'outturn', 'receipts data', 'latest receipts', the receipts of a named "
                   "past year, or a surplus or shortfall in recent months' receipts."),
    "modelling": ("A3/A5", "Does `label` also mention modelling, judgement, methodology or 'other' changes?"),
    "recost": ("A4", "Does `label` describe a re-estimate (a recosting or revised costing) of a policy "
                     "measure announced at an earlier fiscal event?"),
    "decision": ("2.3", "Does `label` describe government decisions or policy measures themselves, for "
                        "example 'scorecard measures', 'effect of Government decisions' or a named tax "
                        "measure?"),
    "economy": ("A5", "Does `label` name a variable from the economy forecast (earnings, employment, "
                      "consumption, investment, profits, prices, inflation, property or equity markets, "
                      "interest rates, exchange rates, oil and gas, GDP, productivity, population, "
                      "unemployment), or say 'economic determinants', 'determinants', 'market "
                      "assumptions' or 'tax base'?"),
    "etr": ("A6", "Does `label` refer to an effective tax rate (ETR) or 'pre-measures' factors?"),
    "one_off": ("A7", "Does `label` describe a one-off item such as litigation, fines, a one-off "
                      "dividend, or a one-off compensation or repayment?"),
    "classification": ("2.3", "Does `label` describe a statistical classification or accounting-treatment "
                              "change, or a new item brought into the receipts measure?"),
    "tax_only": ("A9", "Does `label` only name a tax or receipts stream (such as 'VAT' or 'Council tax') "
                       "without saying what caused the change?"),
    "unsplit": ("2.3", "Is `label` the whole non-policy (underlying) change reported as a single number, "
                       "rather than one cause?"),
    "other": ("A8", "Is `label` a generic remainder such as 'Other', 'Residual', 'Other factors' or "
                    "'Other changes'?"),
}

# every government-decisions heading says "decisions"; "By policy and forecast
# differences" names a split, not a cause (E2 note, correction of 27 September)
GOV = re.compile(r"decisions", re.I)
DET = re.compile(r"economic determinant", re.I)
BYTAX = re.compile(r"by tax head", re.I)
PSNB = re.compile(r"psnb.?neutral", re.I)
SRS = re.compile(r"standard.rated share|\bsrs\b", re.I)
# A11 (clarified 28 Sep): economic only when the label names a cause of the change
SRS_CAUSE = re.compile(r"\b(effect|impact)\b", re.I)


def rule_category(label: str, section: str, n: dict[str, bool], group: str = "") -> tuple[str, str, dict]:
    """Codebook 2.4, applied in order to the Noul answers. Returns the category,
    the rule that decided it, and the flags. A row inside a group takes the group
    heading as its section (A2b)."""
    flags = {"mixed": False, "psnb_neutral": bool(PSNB.search(label))}
    if group and group != "(none)" and (section == "(none)" or not GOV.search(section)):
        section = group
    if GOV.search(section):
        return (*(("modelling_other", "A1+A4") if n["recost"] else ("policy", "A1")), flags)
    if BYTAX.search(section):
        return "by_tax_head", "A1", flags
    if n["unsplit"]:
        return "underlying_unsplit", "2.3", flags
    if n["data"]:
        flags["mixed"] = n["modelling"] or n["economy"]
        return "calibration_to_outturn", "A3", flags
    if n["recost"]:
        return "modelling_other", "A4", flags
    if DET.search(section):
        return (*(("modelling_other", "A1+A6") if n["etr"] else ("economic_determinants", "A1")), flags)
    if n["decision"]:
        return "policy", "2.3", flags
    if flags["psnb_neutral"]:
        return "modelling_other", "A10", flags
    if SRS.search(label):
        cause = n["economy"] and SRS_CAUSE.search(label)
        return (*(("economic_determinants", "A11") if cause else ("modelling_other", "A11")), flags)
    if n["etr"]:
        return "modelling_other", "A6", flags
    if n["one_off"] or n["classification"]:
        return "classification_one_offs", "A7" if n["one_off"] else "2.3", flags
    if n["economy"]:
        if n["modelling"]:
            flags["mixed"] = True
            return "modelling_other", "A5", flags
        return "economic_determinants", "A5", flags
    if n["tax_only"]:
        return "modelling_other", "A9", flags
    if n["other"]:
        return "modelling_other", "A8", flags
    return "modelling_other", "2.3", flags


# --- heads ---
def head_questions(state: dict) -> dict:
    from typesafe_sdk import Choice, Noul
    crit = {code: name for code, name in state["candidate_series"].items()}
    crit["(none)"] = "No listed series covers this head; the measures count only in the aggregate."
    return {
        "series": Choice(
            instructions={
                "question": ("Policy measures with the head `head` are subtracted from one tax or "
                             "spending forecast series. Which of the series covers what `head` covers?"),
                "rules": ["Choose the series that covers exactly what the head covers.",
                          "If the head is part of what one series covers (a surcharge, a sub-levy, a "
                          "component forecast inside that series), choose that series.",
                          "If the head covers several series, choose the dominant series only if all "
                          "of `largest_measures` fall in it; otherwise choose (none).",
                          "Benefits and tax credits belong to welfare spending unless a finer series fits."],
            },
            criteria=crit),
        "broad": Noul(instructions="Does `head` cover taxes or spending that belong to more than one "
                                   "of the series in `candidate_series`?"),
    }


def label_questions() -> dict:
    from typesafe_sdk import Choice, Noul
    q = {"category": Choice(instructions=CATEGORY["instructions"], criteria=CATEGORY["criteria"])}
    q.update({k: Noul(instructions=text) for k, (_, text) in LABEL_NOULS.items()})
    return q


def _load_key() -> None:
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        m = re.match(r"\s*TYPESAFE_API_KEY\s*=\s*['\"]?([^'\"\s]+)", line)
        if m:
            os.environ["TYPESAFE_API_KEY"] = m.group(1)


def states() -> dict[str, dict]:
    out = {}
    for f in ("states_labels.jsonl", "states_heads.jsonl"):
        for line in open(LLM / f, encoding="utf-8"):
            s = json.loads(line)
            out[s["id"]] = s
    return out


def state_hash(s: dict) -> str:
    """Identifies the exact state a result answered; results for an older state are stale."""
    import hashlib
    return hashlib.sha256(json.dumps(s["state"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def latest_results() -> dict[str, dict]:
    """The latest result per row id whose state is still current."""
    S, out = states(), {}
    if RESULTS.exists():
        for line in open(RESULTS, encoding="utf-8"):
            r = json.loads(line)
            if r["id"] in S and r.get("state_hash") == state_hash(S[r["id"]]):
                out[r["id"]] = r
    return out


async def label_one(client, s: dict) -> dict:
    r = await client.system_one(state=s["state"], questions=label_questions(), model=MODEL)
    a = r.answers
    nouls = {k: a[k].noul for k in LABEL_NOULS}
    cat, rule, flags = rule_category(s["state"]["label"], s["state"]["section"],
                                     {k: v >= YES for k, v in nouls.items()},
                                     s["state"].get("group_heading_above", ""))
    probs = dict(sorted(a["category"].probabilities.items(), key=lambda x: -x[1]))
    return {"choice": a["category"].choice, "probabilities": probs,
            "confidence": a["category"].confidence, "nouls": nouls,
            "rule_category": cat, "rule": rule, **flags,
            "group_heading_of": s.get("group_heading_of"),
            "model": r.model, "usage": r.usage.model_dump()}


async def head_one(client, s: dict) -> dict:
    r = await client.system_one(state=s["state"], questions=head_questions(s["state"]), model=MODEL)
    a = r.answers
    probs = dict(sorted(a["series"].probabilities.items(), key=lambda x: -x[1]))
    return {"choice": a["series"].choice, "probabilities": probs,
            "confidence": a["series"].confidence, "nouls": {"broad": a["broad"].noul},
            "flag": a["broad"].noul >= YES, "model": r.model, "usage": r.usage.model_dump()}


def run(ids: list[str], parallel: int = 8) -> list[dict]:
    """Ask Jev about the given rows, `parallel` requests at a time (the SDK retries
    rate limits with backoff). Each result is appended as soon as it arrives."""
    import asyncio

    from typesafe_sdk import AsyncTypeSafeClient
    _load_key()
    S = states()
    out: list[dict] = []

    async def main() -> None:
        sem = asyncio.Semaphore(parallel)
        async with AsyncTypeSafeClient() as client:
            with open(RESULTS, "a", encoding="utf-8") as f:
                async def one(i: str) -> None:
                    s = S[i]
                    async with sem:
                        res = await (label_one if s["crosswalk"] == "attribution_labels" else head_one)(client, s)
                    rec = {"id": i, "crosswalk": s["crosswalk"], "key": s["key"], "state_hash": state_hash(s),
                           "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **res}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    out.append(rec)
                await asyncio.gather(*(one(i) for i in ids))

    asyncio.run(main())
    order = {i: n for n, i in enumerate(ids)}
    return sorted(out, key=lambda r: order[r["id"]])


def report(recs: list[dict]) -> None:
    """Each answer next to the current (keyword) mapping."""
    import pandas as pd
    lab = pd.read_csv(CROSSWALKS / "attribution_labels.csv", dtype=str, keep_default_na=False)
    heads = pd.read_csv(CROSSWALKS / "pmd_heads.csv", dtype=str, keep_default_na=False)
    cur = {**dict(zip(lab.label_key, lab.category)),
           **dict(zip(heads.measure_type + "|" + heads.head_raw, heads.hofd_sheet.replace("", "(none)")))}
    S = states()
    tok = 0
    for r in recs:
        st = S[r["id"]]["state"]
        name = st.get("label") or st.get("head")
        (c1, p1), (c2, p2) = list(r["probabilities"].items())[:2]
        print(f"\n{r['id']}  {name!r}  [{st.get('section', st.get('head_type', ''))}]")
        print(f"  keyword mapping : {cur.get(r['key'], '?')}")
        print(f"  Jev choice      : {c1} ({p1:.2f}), then {c2} ({p2:.2f}); confidence {r['confidence']:.2f}")
        if "rule_category" in r:
            fired = [k for k, v in r["nouls"].items() if v >= YES]
            flags = [k for k in ("mixed", "psnb_neutral") if r.get(k)]
            print(f"  Jev rule path   : {r['rule_category']} by {r['rule']}; yes to: {', '.join(fired) or 'none'}"
                  + (f"; flags: {', '.join(flags)}" if flags else ""))
            if r.get("group_heading_of"):
                print(f"  group heading   : total of the next {r['group_heading_of']} rows (A2, resolved in code)")
        else:
            print(f"  broad head      : {r['nouls']['broad']:.2f}")
        tok += r["usage"]["input_tokens"]
    print(f"\nmodel {recs[0]['model']}; {tok:,} input tokens")


if __name__ == "__main__":
    if sys.argv[1:2] == ["pilot"]:
        report(run(json.loads((LLM / "pilot_ids.json").read_text())["ids"]))
    elif sys.argv[1:2] == ["run"]:
        report(run(sys.argv[2:]))
    elif sys.argv[1:2] == ["all"]:
        # every row without a result for its current state; rerunnable after an interruption
        done = latest_results()
        todo = [i for i in states() if i not in done]
        recs = run(todo)
        print(f"{len(recs)} rows labelled, {len(done)} already current; model "
              f"{recs[0]['model'] if recs else '-'}; {sum(r['usage']['input_tokens'] for r in recs):,} input tokens")
    else:
        sys.exit(__doc__)
