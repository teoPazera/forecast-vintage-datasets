# Second model for the pending attribution labels

This folder is self-contained. It runs on any machine with Python 3.10 or later and git, and needs nothing else from the repository.

## Getting it onto the other machine

```
git clone https://github.com/teoPazera/forecast-vintage-datasets.git
cd forecast-vintage-datasets/crosswalks/pending_second_model
```

The clone has no raw data (it is not in the repository), and this folder does not need any.

## What it does

The OBR explains each revision of its receipts forecast in tables whose rows are causes ("Average earnings", "Latest receipts data", "Scorecard measures"). The dataset sorts each row wording into one of seven categories (`crosswalks/codebook.md`, section 2). Most wordings were settled when the keyword rules and Jev (TypeSafe) agreed with confidence of at least 0.7 (plan D20). The rows in `states.jsonl` were not: the two disagreed, Jev was unsure, the label contains a negation, or the row is a group heading.

`run_second_model.py` asks a second model the same question Jev was asked, with the same context and options, for each of those rows. It does not see the keyword mapping or Jev's answer.

## Files

| File | Contents |
|---|---|
| `states.jsonl` | One row per pending label: `id`, `key`, `state` (the label, its section, the table title and the table's rows, without numbers), `question` (instructions and a description of each option) and `options` |
| `run_second_model.py` | The runner |
| `requirements.txt` | `system-one-adapter[openai]` 0.2.1 (TypeSafe's adapter for LLM endpoints) and `openai` (tested with 3.20) |
| `.env.example` | The three settings the runner reads |
| `results.jsonl` | Written by the runner |

## How to run

```
python -m venv .venv
.venv\Scripts\activate            (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            (Linux/macOS: cp .env.example .env)
```

Fill in `.env`: the endpoint's base URL (OpenAI-compatible, e.g. `https://api.openai.com/v1` or a local server), the model name and the key. Then:

```
python run_second_model.py --limit 3     # check the first rows look sensible
python run_second_model.py               # label the rest
```

The runner prints which path it used:

- `adapter_structured`: the adapter with the endpoint's structured output (preferred);
- `adapter_prompted`: the adapter asking for JSON in the prompt, when the endpoint rejects structured output;
- `direct`: the same question and options sent straight to the endpoint, when the adapter cannot use it. Confidence is then computed from the returned probabilities with TypeSafe's documented approximation.

Each row also gets one separate call asking for a one-sentence reason. If a row fails, it is skipped with a message; run the script again to retry only the missing rows.

## What to send back

`results.jsonl`, one line per row: `id`, `key`, `answer`, `probabilities`, `confidence`, `reason`, `model_name`, `model_version` (as the endpoint reports it), `endpoint` (host only), `path` and `timestamp`.

First check that every row is there: the script prints `nothing to do: 213 of 213 rows already in results.jsonl` when run again. Then, from this folder:

```
git add results.jsonl
git commit -m "Second-model answers for the pending attribution labels"
git push
```

`.env` is ignored by git and is never committed; `git status` should list only `results.jsonl`. On the main machine, `git pull` and then `python -m fvd.merge_second_model` (see the repository README).

## Choosing the model

Any OpenAI-compatible endpoint works. The point of the second model (plan D21) is an independent second opinion, so use a capable general model from a different provider than TypeSafe. The runner records the model name, the version the endpoint reports and the endpoint's host with every row. The full run is 213 rows × 2 calls, each call a few thousand tokens.
