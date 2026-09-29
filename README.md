# Forecast-vintage datasets: UK OBR and US CBO

A harmonized, validated panel of official fiscal forecasts with one row per
(source × series × target period × vintage). Each row carries its revision,
outturns, raw and policy-adjusted errors, and the forecasters' own attribution of
each revision to policy, the economy, outturn data, classification and modelling.
The repository also holds a dated document inventory, with leakage rules, for
text-based studies of forecast efficiency.

## Sources

- **UK Office for Budget Responsibility (OBR)**:
  - Historical Official Forecasts Database (HOFD): 33 OBR vintages 2010–2026 and 73
    HM Treasury vintages back to 1970;
  - Forecast Revisions Database;
  - Policy Measures Database;
  - the receipts tables of every Economic and Fiscal Outlook (EFO);
  - Forecast Evaluation Reports.
- **US Congressional Budget Office (CBO)**:
  [`US-CBO/eval-projections`](https://github.com/US-CBO/eval-projections) (117
  baselines 1982–2026), Budget and Economic Outlooks, Monthly Budget Reviews and
  accuracy reports.

The extraction plan is in [`Claude.md`](Claude.md). Each stage writes a note to
[`notes/extraction/`](notes/extraction/) covering what it did, its findings, open
questions and its gate result.

## Status

| Stage | Content | Status |
|---|---|---|
| E0 | Inventory and vintage calendar | done. OBR gate passed; CBO date gate failed (CBO lists pre-2000 reports by month only). [note](notes/extraction/E0-inventory.md) |
| E1 | OBR forecasts and outturns | done. 26,423 cells; chart-copy check 99.4% (the failures are errors in the copies). [note](notes/extraction/E1-obr-forecasts.md) |
| E2 | OBR attribution and policy measures | done, awaiting crosswalk review; 94.8% of consistency checks pass (gate 95%). [note](notes/extraction/E2-obr-attribution.md) |
| E3 | CBO data and replication | done. CBO's published errors reproduced exactly. [note](notes/extraction/E3-cbo.md) |
| E4 | Harmonized cells, policy adjustment | done. Identity holds to 1e-12. [note](notes/extraction/E4-cells.md) |
| E5 | Stylized facts, efficiency tests | done, awaiting review. [note](notes/extraction/E5-stylized-facts.md) |
| E6–E9 | Case selection, text, linking, data card | not started (E6 needs the E5 review) |

## Data

| Path | Content | Format |
|---|---|---|
| `tables/` | series, vintages, forecasts, outturns, attribution, policy measures, cells; one file per source | Parquet, with `<table>.schema.yaml` |
| `stats/` | checks per stage, CBO replication, stylized facts, efficiency tests, calibration targets | CSV / JSON |
| `inventory/` | provenance of every raw file, document list, vintage calendar | CSV |
| `crosswalks/` | PMD events → vintages, PMD heads → series, attribution labels → categories | CSV (for review) |

Each schema file states the type, unit and sign convention of every column.
Conventions: error = forecast − outturn (positive = over-forecast); revision =
new − previous (positive = raised); logs only for strictly positive level series.

Raw downloads (about 200 MB) are not committed. Every raw file is listed in
[`inventory/sources.csv`](inventory/sources.csv) with its original URL, retrieval
time and SHA-256, so a re-download can be checked byte for byte
(`python -m fvd.audit_raw`).

## Reproducing

```sh
python -m venv .venv
.venv/Scripts/activate            # Windows; use .venv/bin/activate elsewhere
pip install -e .
python -m fvd.e0_inventory        # sources, documents, vintage calendar
python -m fvd.e0_factcheck        # plan section 5 facts against the files
python -m fvd.e1_obr_forecasts    # OBR forecasts and outturns
python -m fvd.e2_frd_pmd          # FRD attribution, PMD measures, crosswalks
python -m fvd.manual              # record the hand-downloaded files (see Access)
python -m fvd.e2_efo_tables       # EFO receipts attribution
python -m fvd.e3_cbo              # CBO tables and replication
python -m fvd.e4_cells            # harmonized cells, policy adjustment
python -m fvd.e5_stylized_facts   # stylized facts and tests
python -m fvd.e6_cases select     # cases, controls, random sample (after `register`)
python -m fvd.r1_pilot plan       # R1: pilot cases and corpus (then `register`)
python -m fvd.r1_documents fetch  # R1: download the pilot documents; then `extract`
python -m fvd.r1_link             # R1: series dictionary and links; `post-hoc` for cause texts
python -m fvd.r1_pilot register-queries   # R1: fix dictionary, causes and queries
python -m fvd.r1_runs run         # R1: retrieval runs; then `pool` for labelling
```

The first run downloads from the Internet Archive with throttling and takes a few
hours. Later runs use the local cache.

The crosswalks in `crosswalks/` follow the written standard in
`crosswalks/codebook.md`. Rows are labelled by keyword rules and checked with Jev
(TypeSafe; needs `TYPESAFE_API_KEY` in the environment or `.env`); rows where the
two agree with enough confidence are settled (plan D20), the rest are reviewed:

```sh
python -m fvd.crosswalk_states       # per-row context for the labeller (crosswalks/llm/)
python -m fvd.jev_label all          # Jev's answers, logged in crosswalks/llm/jev_results.jsonl
python -m fvd.jev_route              # settle by agreement; queue the rest
python -m fvd.jev_route apply-heads  # write crosswalks/review_queue_heads_decisions.csv
python -m fvd.second_model_package   # pending labels for the second model (D21)
python -m fvd.merge_second_model     # after crosswalks/pending_second_model/results.jsonl exists
python -m fvd.merge_second_model apply  # write crosswalks/review_queue_labels_decisions.csv
python -m fvd.spot_check             # blind spot-check of settled rows; `score` compares
```

The second model runs on another machine, with only the folder
`crosswalks/pending_second_model/` (see its README). Its `results.jsonl`
comes back through git. Then, here:

1. `python -m fvd.merge_second_model` settles the rows where it agrees and writes
   the rest to `crosswalks/review_queue_labels.csv`;
2. the decided rows go in `crosswalks/review_queue_labels_decisions.csv` (columns
   `key`, `answer`, `labeller`, `comment`), then `python -m fvd.merge_second_model apply`;
3. `python -m fvd.e2_efo_tables`, then `python -m fvd.e5_stylized_facts`, to carry the
   final labels into the attribution table and shares.

Rows marked `reviewed` keep their mapping on reruns. `python -m fvd.review build`
still writes the older review workbook.

### Access

`obr.uk` (Cloudflare) and `cbo.gov` (DataDome) answer every scripted request with a
browser challenge, however the client identifies itself. This project does not try
to get past those challenges.
- **Wayback captures.** After one identified request has been refused, files from
  those hosts are taken from the
  [Internet Archive Wayback Machine](https://web.archive.org/) capture of the same
  original URL. The capture time and the original server's `Last-Modified` header
  are recorded (`via = wayback`).
- **Alternate captures.** Where the source's own link was never archived, the same
  document is taken from another archived URL on the source's current or former
  domain, and only after its content has been checked (`via = wayback-alternate`).
- **Integrity.** Every download is checked for integrity, and truncated captures are
  rejected (`status = invalid`).
- **Manual downloads.** Three EFO workbooks were never archived. They were downloaded
  in a browser from the OBR's own links into `raw/manual/` (`via = manual`). The
  links are listed in [`src/fvd/manual.py`](src/fvd/manual.py). To reproduce, save
  them there before running `python -m fvd.manual`; the SHA-256 in `sources.csv`
  shows whether a new download is the same file.
- **Check against the live site.** The three OBR databases, downloaded in a browser
  on 27 September 2026, are byte-for-byte identical to the archive copies used
  ([`inventory/manual_checks.csv`](inventory/manual_checks.csv)).

## Licences

- OBR material: © Crown copyright, reused under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
  Contains public sector information licensed under the Open Government Licence v3.0.
- CBO material: US federal government work, in the public domain.
- Code in this repository: MIT (see `LICENSE`).
