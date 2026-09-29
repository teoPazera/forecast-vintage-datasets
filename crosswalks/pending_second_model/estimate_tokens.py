"""Estimate input tokens for the current second-model requests without an LLM call."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
STATES = HERE / "states.jsonl"
NONE = "none"
SYSTEM = "Classify the supplied tax-forecast row. Follow the requested output format exactly."


def allowed_answers(s: dict) -> list[str]:
    return [*s["options"], NONE]


def static_context(s: dict) -> str:
    q = s["question"]
    taxonomy = {"instructions": q["instructions"], "categories": q["criteria"], "none": {
        "what": "Use only when none of the listed categories adequately describes the row.",
        "do_not_use_for": "ordinary uncertainty; choose the best listed category when one fits.",
    }}
    return (
        "Classification instructions and taxonomy (identical for every row):\n"
        + json.dumps(taxonomy, ensure_ascii=False)
        + "\n\nThink through the evidence privately. Do not report your reasoning. "
        + "Reply with JSON only, exactly in the form {\"answer\": \"<category>\"}. "
        + f"The answer must be exactly one of: {allowed_answers(s)}.\n\n"
        + "Row-specific state:\n"
    )


def messages(s: dict) -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": static_context(s) + json.dumps(s["state"], ensure_ascii=False)}]


def token_count(tokenizer, request: list[dict[str, str]]) -> int:
    return sum(len(tokenizer.encode(message["content"])) for message in request)


def request_bytes(request: list[dict[str, str]]) -> int:
    return len(json.dumps({"messages": request}, ensure_ascii=False).encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", default="cl100k_base", help="tiktoken encoding (default: cl100k_base)")
    parser.add_argument("--model", default=None, help="use tiktoken's mapping for this model")
    parser.add_argument("--output", type=Path, default=None, help="write detailed JSON report")
    args = parser.parse_args()
    try:
        import tiktoken
    except ImportError:
        sys.exit("Install tiktoken to run this estimator.")
    try:
        tokenizer = tiktoken.encoding_for_model(args.model) if args.model else tiktoken.get_encoding(args.tokenizer)
    except KeyError:
        sys.exit(f"No tiktoken mapping for {args.model!r}; pass --tokenizer explicitly.")

    rows = [json.loads(line) for line in STATES.read_text(encoding="utf-8").splitlines() if line.strip()]
    requests = [messages(row) for row in rows]
    tokens = [token_count(tokenizer, request) for request in requests]
    bytes_ = [request_bytes(request) for request in requests]
    print(f"Rows / planned API calls: {len(rows):,}")
    print(f"Tokenizer: {tokenizer.name}")
    print("Scope: message-content tokens only; excludes provider-specific chat envelope and generated output.")
    print(f"Input-content tokens: total {sum(tokens):,}; min/mean/max {min(tokens):,}/{mean(tokens):.1f}/{max(tokens):,}")
    print(f"Exact request JSON bytes: total {sum(bytes_):,}; min/mean/max {min(bytes_):,}/{mean(bytes_):.1f}/{max(bytes_):,}")
    if args.output:
        args.output.write_text(json.dumps({
            "rows": len(rows), "calls": len(rows), "tokenizer": tokenizer.name,
            "scope": "message-content tokens; excludes endpoint-specific chat envelope and generated output",
            "input_content_tokens": tokens, "request_json_bytes": bytes_,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"Detailed report written to {args.output}")


if __name__ == "__main__":
    main()
