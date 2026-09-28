"""Label the pending crosswalk rows with a second model (plan D21).

Standalone: needs only the files in this folder and the packages in
requirements.txt. Nothing is imported from the pipeline.

    pip install -r requirements.txt
    copy .env.example .env        # then fill in the three SECOND_MODEL_ values
    python run_second_model.py --limit 3   # try a few rows first
    python run_second_model.py             # every row not yet in results.jsonl

For each row in states.jsonl the script asks the category question through the
System One Adapter (TypeSafe's system-one-adapter package), which sends the same
state, question and options Jev received to the OpenAI-compatible endpoint in
.env and returns a probability for every option. If the endpoint rejects
structured output, the adapter retries with prompted JSON; if the adapter cannot
use the endpoint at all, the script asks the endpoint directly with the same
question and options. A second, separate call per row asks for a one-sentence
reason. Results are appended to results.jsonl, one line per row, so an
interrupted run can be restarted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
STATES = HERE / "states.jsonl"
RESULTS = HERE / "results.jsonl"


def load_config() -> dict[str, str]:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                os.environ.setdefault(m.group(1), m.group(2).strip("'\""))
    cfg = {k: os.environ.get(f"SECOND_MODEL_{k}", "") for k in ("BASE_URL", "NAME", "API_KEY")}
    missing = [f"SECOND_MODEL_{k}" for k, v in cfg.items() if not v]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in {env} (see .env.example).")
    return cfg


def confidence(probs: dict[str, float]) -> float:
    """1 when all probability is on one option, 0 when it is spread evenly (the
    approximation TypeSafe documents). Used only on the direct path; the adapter
    returns its own confidence."""
    k, p = len(probs), max(probs.values())
    return max(0.0, min(1.0, (k * p - 1) / (k - 1))) if k > 1 else 1.0


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError(f"no JSON in answer: {text[:200]!r}")
    return json.loads(m.group(0))


class Adapter:
    """The category question through system-one-adapter."""

    def __init__(self, cfg: dict[str, str], structured: bool) -> None:
        from system_one_adapter import SystemOneAdapterClient
        from system_one_adapter.providers.openai import OpenAIProvider
        self.path = "adapter_structured" if structured else "adapter_prompted"
        self.provider = OpenAIProvider(cfg["NAME"], base_url=cfg["BASE_URL"], api_key=cfg["API_KEY"],
                                       api="chat_completions")
        self.client = SystemOneAdapterClient(structured_outputs=structured, llm_answer_mode="probabilities",
                                             normalize_probabilities=True, n_retry_malformed_structure=2)

    def ask(self, s: dict) -> dict:
        from system_one_adapter import Choice
        q = s["question"]
        r = self.client.system_one(state=s["state"], model=self.provider,
                                   questions={"category": Choice(instructions=q["instructions"],
                                                                 criteria=q["criteria"])})
        a = r.answers["category"]
        version = None
        for att in (getattr(r, "debug", None) or {}).get("llm_attempts", []):
            version = (att.get("debug_info") or {}).get("model") or version
        return {"answer": a.choice, "probabilities": dict(a.probabilities), "confidence": a.confidence,
                "model_version": version}


class Direct:
    """The same question and options, asked directly (for endpoints the adapter cannot use)."""

    path = "direct"

    def __init__(self, client, cfg: dict[str, str]) -> None:
        self.client, self.name = client, cfg["NAME"]

    def ask(self, s: dict) -> dict:
        q = s["question"]
        options = list(q["criteria"])
        body = {"state": s["state"], "instructions": q["instructions"], "options": q["criteria"]}
        msgs = [
            {"role": "system", "content": "You answer a classification question about the given state. "
                                          "Reply with JSON only."},
            {"role": "user", "content": json.dumps(body, ensure_ascii=False) +
             '\n\nReturn {"probabilities": {<option>: <probability>, ...}} with every option in '
             f"{options}, the probabilities summing to 1."},
        ]
        r = self.client.chat.completions.create(model=self.name, messages=msgs)
        j = _json(r.choices[0].message.content)
        raw = j.get("probabilities", j)
        probs = {o: max(float(raw.get(o, 0) or 0), 0.0) for o in options}
        total = sum(probs.values())
        if total <= 0:
            raise ValueError(f"no probabilities in answer: {j}")
        probs = {o: p / total for o, p in probs.items()}
        return {"answer": max(probs, key=probs.get), "probabilities": probs,
                "confidence": confidence(probs), "model_version": r.model}


def reason(client, name: str, s: dict, answer: str) -> str:
    """A separate call: one sentence on why the chosen option fits."""
    q = s["question"]
    body = {"state": s["state"], "instructions": q["instructions"], "options": q["criteria"]}
    msgs = [{"role": "system", "content": "Answer in exactly one sentence."},
            {"role": "user", "content": json.dumps(body, ensure_ascii=False) +
             f"\n\nThe chosen option is '{answer}'. In one sentence, say why it fits the row "
             "`label` better than the other options."}]
    r = client.chat.completions.create(model=name, messages=msgs)
    return " ".join((r.choices[0].message.content or "").split())


def choose_path(cfg: dict[str, str], openai_client, probe: dict):
    """Adapter with structured output, then adapter with prompted JSON, then direct."""
    errors = []
    for structured in (True, False):
        try:
            a = Adapter(cfg, structured)
            first = a.ask(probe)
            return a, first
        except Exception as e:   # noqa: BLE001 - any failure means: try the next path
            errors.append(f"adapter structured={structured}: {type(e).__name__}: {e}")
    d = Direct(openai_client, cfg)
    try:
        return d, d.ask(probe)
    except Exception as e:  # noqa: BLE001
        errors.append(f"direct: {type(e).__name__}: {e}")
        sys.exit("No path worked for the first row:\n  " + "\n  ".join(errors))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="label at most this many rows")
    args = ap.parse_args()
    cfg = load_config()
    from openai import OpenAI
    oc = OpenAI(base_url=cfg["BASE_URL"], api_key=cfg["API_KEY"])

    rows = [json.loads(line) for line in STATES.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = set()
    if RESULTS.exists():
        done = {json.loads(line)["id"] for line in RESULTS.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [s for s in rows if s["id"] not in done][: args.limit]
    if not todo:
        print(f"nothing to do: {len(done)} of {len(rows)} rows already in {RESULTS.name}")
        return

    asker, first = choose_path(cfg, oc, todo[0])
    print(f"path: {asker.path}; {len(todo)} rows to label")
    with open(RESULTS, "a", encoding="utf-8") as f:
        for n, s in enumerate(todo):
            try:
                res = first if n == 0 else asker.ask(s)
                why = reason(oc, cfg["NAME"], s, res["answer"])
            except Exception as e:  # noqa: BLE001 - record and continue; rerun picks it up
                print(f"{s['id']}: failed ({type(e).__name__}: {e}); rerun to retry")
                continue
            rec = {"id": s["id"], "key": s["key"], **res, "reason": why,
                   "model_name": cfg["NAME"], "endpoint": urlparse(cfg["BASE_URL"]).netloc,
                   "path": asker.path, "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{s['id']}: {res['answer']} ({res['confidence']:.2f})")


if __name__ == "__main__":
    main()
