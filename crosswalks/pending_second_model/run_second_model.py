"""Label the pending crosswalk rows with a second model.

Each pending row is sent once to an OpenAI-compatible endpoint.  The model is
asked to reason privately and return exactly one category (or ``none`` when no
category fits).  Results are appended to ``results.jsonl`` so interrupted runs
resume without repeating completed calls.

    python run_second_model.py --show-prompt  # inspect locally; no API call
    python run_second_model.py --limit 1      # small live probe
    python run_second_model.py                # remaining rows
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
NONE = "none"


class InvalidAnswer(ValueError):
    """The endpoint returned text that is not one of the allowed categories."""


def load_config() -> dict[str, str]:
    """Read a folder-local .env, or the repository-root .env as a fallback."""
    envs = (HERE / ".env", HERE.parent.parent / ".env")
    for env in envs:
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                os.environ.setdefault(m.group(1), m.group(2).strip("'\""))
    cfg = {k: os.environ.get(f"SECOND_MODEL_{k}", "") for k in ("BASE_URL", "NAME", "API_KEY")}
    missing = [f"SECOND_MODEL_{k}" for k, value in cfg.items() if not value]
    if missing:
        locations = ", ".join(str(path) for path in envs)
        sys.exit(f"Set {', '.join(missing)} in one of: {locations} (see .env.example).")
    return cfg


def allowed_answers(s: dict) -> list[str]:
    return [*s["options"], NONE]


def static_context(s: dict) -> str:
    """The invariant prefix, deliberately before the row-specific state.

    Keeping this byte-for-byte identical across calls gives a cache-capable
    provider the best chance to reuse its prompt prefix.
    """
    q = s["question"]
    allowed = allowed_answers(s)
    taxonomy = {"instructions": q["instructions"], "categories": q["criteria"], "none": {
        "what": "Use only when none of the listed categories adequately describes the row.",
        "do_not_use_for": "ordinary uncertainty; choose the best listed category when one fits.",
    }}
    return (
        "Classification instructions and taxonomy (identical for every row):\n"
        + json.dumps(taxonomy, ensure_ascii=False)
        + "\n\nProvide few sentences of reasoning. "
        + "Reply with JSON only, exactly in the form "
        + "{\"reasoning\": \"<few sentences causally deciding what is the label>\", \"answer\": \"<category>\"}. "
        + f"The answer must be exactly one of: {allowed}.\n\n"
        + "Row-specific state:\n"
    )


def classification_messages(s: dict) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "Classify the supplied tax-forecast row. Follow the requested output format exactly.",
        },
        {"role": "user", "content": static_context(s) + json.dumps(s["state"], ensure_ascii=False)},
    ]


def _json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise InvalidAnswer(f"no JSON object in answer: {text[:200]!r}")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise InvalidAnswer(f"malformed JSON answer: {text[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise InvalidAnswer(f"JSON answer is not an object: {parsed!r}")
    return parsed


def parse_response(text: str, s: dict) -> dict[str, str]:
    try:
        parsed = _json(text)
        answer = parsed.get("answer")
        reasoning = parsed.get("reasoning")
        if not isinstance(answer, str) or answer not in allowed_answers(s):
            raise InvalidAnswer(
                f"answer must be exactly one of {allowed_answers(s)!r}; received {answer!r}"
            )
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise InvalidAnswer("response must contain a non-empty string field 'reasoning'")
        reasoning = " ".join(reasoning.split())
        if len(reasoning.split()) > 60:
            raise InvalidAnswer(f"reasoning exceeds 60 words ({len(reasoning.split())})")
        return {"answer": answer, "reasoning": reasoning}
    except InvalidAnswer as exc:
        exc.raw_response = text
        raise


def usage_dict(usage) -> dict | None:
    """Keep provider usage, including cached-token details if it exposes them."""
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump(exclude_none=True)
    if isinstance(usage, dict):
        return usage
    return {key: value for key, value in vars(usage).items() if not key.startswith("_") and value is not None}


def ask(client, cfg: dict[str, str], s: dict) -> dict:
    """Make the single classification call for a row."""
    response = client.chat.completions.create(model=cfg["NAME"], messages=classification_messages(s))
    print(response)
    parsed = parse_response(response.choices[0].message.content or "", s)
    return {
        **parsed,
        "model_version": response.model,
        "usage": usage_dict(getattr(response, "usage", None)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="classify at most this many rows")
    ap.add_argument("--show-prompt", action="store_true", help="print the first row's exact request and output contract, then exit")
    args = ap.parse_args()

    rows = [json.loads(line) for line in STATES.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.show_prompt:
        sample = rows[0]
        print(json.dumps({
            "sample_id": sample["id"],
            "classification_request": {"model": "SECOND_MODEL_NAME", "messages": classification_messages(sample)},
            "classification_response_contract": {
                "answer": f"exactly one of {allowed_answers(sample)!r}",
                "reasoning": "one or two concise sentences, maximum 60 words",
                "examples": [
                    {"reasoning": "The row sits under the economic-determinant section and identifies a tax-base driver.", "answer": "economic_determinants"},
                    {"reasoning": "The row does not fit any defined causal or non-cause category.", "answer": "none"},
                ],
                "constraints": ["JSON only", "answer and reasoning fields only", "no probabilities"],
            },
            "stored_result_format": {
                "id": sample["id"], "key": sample["key"], "answer": "one allowed category or none",
                "reasoning": "few sentences providing causal reasoning for given label",
                "model_name": "string", "model_version": "string or null",
                "usage": "provider usage object or null", "endpoint": "host name",
                "timestamp": "UTC ISO-8601 timestamp",
            },
        }, ensure_ascii=False, indent=2))
        return

    cfg = load_config()
    from openai import OpenAI
    client = OpenAI(base_url=cfg["BASE_URL"], api_key=cfg["API_KEY"])

    done = set()
    if RESULTS.exists():
        done = {json.loads(line)["id"] for line in RESULTS.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [s for s in rows if s["id"] not in done][:args.limit]
    if not todo:
        print(f"nothing to do: {len(done)} of {len(rows)} rows already in {RESULTS.name}")
        return

    print(f"path: direct; {len(todo)} rows to classify")
    with RESULTS.open("a", encoding="utf-8") as handle:
        for s in todo:
            try:
                result = ask(client, cfg, s)
            except Exception as exc:  # retry missing rows on a later run
                print(f"{s['id']}: failed ({type(exc).__name__}: {exc})")
                raw = getattr(exc, "raw_response", None)
                if raw is not None:
                    print(f"{s['id']}: raw response: {raw}")
                print(f"{s['id']}: rerun to retry")
                continue
            record = {
                "id": s["id"], "key": s["key"], **result,
                "model_name": cfg["NAME"], "endpoint": urlparse(cfg["BASE_URL"]).netloc,
                "path": "direct", "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"{s['id']}: {result['answer']}")


if __name__ == "__main__":
    main()
