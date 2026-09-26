# Forecast-vintage datasets: UK OBR and US CBO

A harmonized, validated panel of official fiscal forecasts, one row per
(source × series × target period × vintage), with revisions, outturns, errors
and the forecasters' own attribution of each revision. It also holds a dated
document inventory, with leakage rules, for text-based studies of forecast
efficiency.

Sources:

- **UK Office for Budget Responsibility (OBR)**: Historical Official Forecasts
  Database, Forecast Revisions Database, Policy Measures Database, Economic and
  Fiscal Outlooks and Forecast Evaluation Reports.
- **US Congressional Budget Office (CBO)**:
  [`US-CBO/eval-projections`](https://github.com/US-CBO/eval-projections),
  Budget and Economic Outlooks and accuracy reports.

The full extraction plan is in [`Claude.md`](Claude.md). Stage notes are in
[`notes/extraction/`](notes/extraction/).

## Status

| Stage | Content | Status |
|---|---|---|
| E0 | Inventory and vintage calendar | done; OBR gate passed, CBO date gate failed (see [note](notes/extraction/E0-inventory.md)) |
| E1–E9 | see plan | not started |

## Reproducing

```sh
python -m venv .venv
.venv/Scripts/activate        # Windows; use .venv/bin/activate elsewhere
pip install -e .
python -m fvd.e0_inventory    # downloads raw files into raw/ and writes inventory/
python -m fvd.e0_factcheck    # checks the plan's source facts against the files
```

## Layout

| Path | Content |
|---|---|
| `src/fvd/` | extraction code, one module per stage (`e0_*`, `e1_*`, ...) plus shared parsers |
| `inventory/` | provenance of raw files, document list, vintage calendar |
| `notes/extraction/` | one note per stage: what was done, findings, open questions, gate result |
| `raw/` | downloads (not committed; reproducible from `inventory/sources.csv`) |

Every table has a `<table>.schema.yaml` next to it stating the type, unit and sign
convention of each column.

Raw downloads are not committed. Every raw file is listed in
[`inventory/sources.csv`](inventory/sources.csv) with its original URL,
retrieval time and SHA-256, so a re-download can be checked byte for byte.

### A note on access

`obr.uk` (Cloudflare) and `cbo.gov` (DataDome) answer every scripted request
with a browser challenge, however the client identifies itself. This project
does not try to get past those challenges. After one identified request has
been refused, files from those hosts are taken from the
[Internet Archive Wayback Machine](https://web.archive.org/) capture of the
same original URL. The capture timestamp and the original server's
`Last-Modified` header are recorded for each file (`via = wayback` in
`inventory/sources.csv`).

## Licences

- OBR material: © Crown copyright, reused under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
- CBO material: US federal government work, in the public domain.
- Code in this repository: MIT (see `LICENSE`).
