# Plan: public forecast-vintage datasets — extraction and case preparation

Status: draft for review by Teo.
Source facts in this plan were checked against downloaded files on 26 September 2026 unless marked **(verify)**. They are a starting point, not ground truth: re-check each one in the files before relying on it.

---
## 1. What this extraction is for

### 1.1 The research question

An expert forecaster revises its forecast of the same target many times before the outcome is known. The questions are whether the evidence that explains an error can be found, and whether the later revisions, and the final error, can be predicted from information available when each forecast was made:

0. Retrieval: can passages that explain a forecast error be found among the documents available before the forecast, and how much harder is this when the cause is unknown (prospective query) than when it is known (retrospective query)?
1. from the numbers alone (the history of forecasts and revisions),
2. from the text the forecaster had published by that date, and
3. for errors nobody anticipated: was the cause absent from every document available beforehand, or present and not acted on?

A forecast is called efficient if its errors cannot be predicted from information available when it was made. The standard tests (bias, Mincer–Zarnowitz, autocorrelation of revisions as in Nordhaus 1987, and regression of errors on revisions as in Coibion & Gorodnichenko 2015) cover point 1. Points 0, 2 and 3 need dated text and post-hoc explanations aligned to the same forecast cells, which is what this plan builds. Point 1 serves as the numbers-only baseline that text-based results must improve on.

### 1.2 What the data must contain

For each forecaster:

1. **Forecast vintages**: many forecasts of the same target period, each with an exact publication date.
2. **Outturns** for the target periods.
3. **A hierarchy**: component series that add up to a total.
4. **Revision attribution**: the forecaster's own split of each revision into causes (policy decisions, economic determinants, calibration to new outturn data, classification changes, other).
5. **Dated forecaster text** at each vintage explaining the forecast and what changed.
6. **Post-hoc text** explaining the errors after the outcome was known. This is used as ground truth for causes and never as an input.

### 1.3 Why these two sources, and why a common schema

The motivating application is a confidential corporate forecasting process with the same structure: business units re-forecast a hierarchical total every quarter, the total is built from component drivers, finance teams write dated narratives, and post-hoc explanations exist. That data cannot be published.

The public datasets extracted here carry the publishable results. A synthetic generator, planned separately, will write the same tables. All code must therefore work on a common schema that assumes nothing specific to one source: target periods may be annual or quarterly, the hierarchy may have any depth, and the set of attribution categories differs by source.

Two public forecasters have the required structure:

- **UK Office for Budget Responsibility (OBR)**: forecasts at each fiscal event (about twice a year) since June 2010, with HM Treasury forecasts of aggregates going back to 1970.
- **US Congressional Budget Office (CBO)**: baseline projections since 1982, usually two or three per year.

### 1.4 What this plan delivers

1. A harmonized, validated panel of forecast cells (source × series × target period × vintage) with revisions, errors, horizons and attribution.
2. Descriptive statistics and numbers-only predictability tests, also saved as calibration targets for the synthetic generator.
3. A pre-registered set of cases (large, persistent errors), matched controls (well-forecast trajectories) and a random sample.
4. For every case, control and sampled trajectory: the documents available at each vintage, the passages that mention the series and target period, and the post-hoc passages that explain the outcome.
5. A data card documenting provenance, licences, known issues and leakage rules.

### 1.5 Out of scope

- Any hosted or paid language-model call. Local, zero-cost embedding models for retrieval baselines are allowed (D16). Exception: labelling crosswalk rows with Jev (TypeSafe) and a second model, following `crosswalks/codebook.md`, with every call recorded (D20, D21). Every stage in this plan is zero-cost. Linking text to series is deterministic here; model-based linking belongs in a later plan with its own cost gate.
- Forecasting or error-prediction models beyond the descriptive regressions in stage E5.
- The synthetic generator.
- Text not written by the forecaster, such as central bank reports, statistical releases and news (decision D10).

---

## 2. Working rules

- **One stage at a time.** At the end of each stage, write the stage note (template in section 12), report the gate result, and stop. Do not start the next stage until Teo confirms.
- **Raw files are immutable.** Never modify or overwrite a raw download. Store every raw file with its source URL, retrieval timestamp and content hash, plus its last-modified date where the source reports one.
- **Verify before stating.** Every statement about a source's content in a note must be checked in the downloaded file. Where this plan and the file disagree, the file wins, and the disagreement is recorded in the stage note.
- **Schema files.** Every derived table has a schema file stating the unit and sign convention of each numeric column.
- **Open decisions are Teo's.** The agent does not resolve the decisions in section 10. If a stage needs one, implement the stated default behind a single switch, record that the default was used, and flag it in the stage note.
- **Reproduce the source's own numbers.** Where a source publishes its own statistics, reproducing them is the test of the parser (gates in E2 and E3).
- **Be polite to sources.** Throttle requests, identify the client in each request, and cache everything. Some sources refuse anonymous automated requests. If a request is refused, record it and retry with an identified request before concluding a file is unavailable.
- **Do not construct URLs.** Build document lists from the sources' own listing pages; URL patterns for older publications differ from recent ones.

### 2.1 Working with Teo (for any Claude session, local or remote)

- **Autonomy.** Work through a stage without check-ins; stop at the review points and gates the plan defines. When reporting back, give an intuitive summary of what is done and a clear list of what is needed from Teo.
- **Git.** Logical commits with clear messages. Commit locally; `git push` only when Teo asks for that push. Side tasks (e.g. stepping back to an earlier stage) go on their own branch, merged into `main` and then into the stage branch. Never stage files another session left uncommitted.
- **Public repository.** Only cleaned, reproducible work is committed: no scratch files, no raw data (`raw/` is gitignored).
- **OBR and CBO access.** obr.uk and cbo.gov serve a browser challenge to every script. Never bypass it. `fvd.http` uses Wayback Machine captures of the same URL, or a content-verified capture of the same document under another archived URL, and integrity-checks every download. For a file the archive never saved, ask Teo to download it in a browser into `raw/manual/` (R1 pilot: `raw/manual/pilot/<doc_id>.<ext>`, recorded by `python -m fvd.r1_documents manual`).
- **Current status.** The stage in progress and its open questions are in its note under `notes/extraction/` (R1: `notes/extraction/R1-retrieval-pilot.md`).

---

## 3. Terms

- **Target period**: the period being forecast. UK fiscal years run April–March (e.g. 2025-26), US fiscal years October–September, and some economy series are calendar years.
- **Vintage**: one publication of a full set of forecasts, identified by its exact publication date.
- **Cell**: one forecast value for (source, series, target period, vintage).
- **Horizon h**: months from the vintage's publication date to the end of the target period.
- **Cell role**, which depends on the target period relative to the publication date:
  - `past`: the target period has ended (h < 0). The value is an estimate of outturn, not a forecast.
  - `in_progress`: the target period has started but not ended.
  - `future`: the target period has not started.
- **Revision**: the change in the forecast of the same series and target period between a vintage and the previous vintage that forecast that target.
- **Outturn**: the realized value. Two versions are kept:
  - `latest`: as published at retrieval.
  - `first_estimate`: the earliest published estimate after the period ended.
- **Attribution**: the forecaster's own published split of a revision into causes.
- **Policy-adjusted error**: the error after removing the effect of policy decisions announced after the vintage, which the forecaster was not asked to predict.
- **Trajectory**: all cells for one (source, series, target period), ordered by vintage date.
- **Case**: a trajectory selected because its errors were large and persistent.
- **Control**: a trajectory selected because its errors stayed small, matched to a case.

---

## 4. Sign and unit conventions (fixed for all derived tables)

### 4.1 Definitions

- **Error**: `e = forecast − outturn`. Positive means over-forecast.
- **Revision**: `r_v = F_v − F_prev(v)`. Positive means the forecast was raised.
- **Log versions**: for strictly positive level series, also store `log(F/A)` and `log(F_v / F_prev(v))`.
- **Identity** that must hold for every cell: `e_v = e_last − Σ r_u`, summed over all vintages u after v up to the last vintage before outturn. Check it in E4.
- **Balance series** (borrowing, deficit, current budget) can change sign. Never take logs of them. Store them in the source unit and, where the source provides it, as per cent of GDP.
- **Units**: store the source unit and a harmonized unit (billions of local currency). Never mix currencies in one computation.

### 4.2 Source conventions to convert (verify each)

- **CBO replication code**: projection error = (projection + subsequent legislative changes) − actual. The sign is flipped for the deficit. Positive means revenue or outlays were over-projected.
- **OBR Policy Measures Database**: positive = gain to the Exchequer (raises receipts or lowers spending). Values are in £ million.
- **OBR Forecast Revisions Database**: revisions are to public sector net borrowing (PSNB). A receipts upgrade lowers borrowing, so it appears with a negative sign in the "of which: receipts" rows. Convert to the receipts convention before comparing with receipts series.
- **OBR EFO receipts tables** ("changes since the previous forecast"): positive = receipts raised.
- **OBR Historical Official Forecasts Database**: £ billion for receipts, spending and borrowing; per cent of GDP on the sheets without "£"; per cent change on a year earlier for most economy series.

---

## 5. Sources

### 5.1 OBR Historical Official Forecasts Database (HOFD)

**The file**
- One workbook, updated after each fiscal event.
- The file name on the OBR site has not always matched the content: a file named for March 2025 contained vintages through March 2026. Identify the content by the vintage labels inside the file, not by the file name.

**Sheet layout** (verified for VAT, £PSCR and CPI)
- Title row, unit row, blank row.
- Header row: "Back to contents", then the target periods.
- One row per vintage, labelled "Month YYYY".
- A blank row, then an "Outturn data*" row, then the footnote "*as available at last forecast".

**Coverage**
- About 33 OBR vintages, from June 2010 to March 2026.
- Aggregate sheets go further back with HM Treasury forecasts. The contents sheet lists PSNB from April 1970, and current receipts and total managed expenditure from March 1990.
- Component sheets start in June 2010.

**Series**
- Aggregates: PSNB (£ and % of GDP), current receipts, total managed expenditure, cyclically adjusted balances, net debt, net financial liabilities, net investment, current budget.
- About 30 receipts components: income tax (with PAYE and self-assessed sheets), NICs, VAT, onshore corporation tax, oil and gas, fuel, business rates, CGT, IHT, property transaction taxes, stamp duty on shares, tobacco, alcohol (with spirits, wine, beer and cider), VED, VAT refunds, council tax, APD, insurance premium tax, climate change levy, bank levy, licence fee, ETS, electricity generator levy, CBAM, vaping duty, Scottish taxes, health and social care levy.
- About 30 spending lines.
- About 40 economy series, on a calendar-year basis.

**Sheet variants and memo rows**
- Sheets with the suffix " (2)" are chart-data copies starting in 2008-09. Use the unsuffixed sheets, which hold the full history, and use the "(2)" sheets only as a cross-check.
- Some sheets contain memo rows ("Memo: restated March 2019 forecast", "Memo: supplementary March 2020 forecast"). Treat them as separate flagged vintages (D14).

**Caveats**
- The contents sheet states that forecasts reflect the definitions and classifications in use at the time of each forecast.
- The £PSCR sheet warns that the latest outturn may differ substantially from historical forecasts because of later classification changes. E4 handles this.
- The outturn row holds only the latest outturn. First estimates must be reconstructed (D4).

### 5.2 OBR Forecast Revisions Database (FRD)

- Sheets: "Revisions (Per cent of GDP)", "Revisions (£ billion)" and "Classifications and one-offs".
- One block per vintage, starting November 2010. Each block contains the total revision to PSNB by target fiscal year, then:
  - Policy, of which receipts and of which spending;
  - Classifications and one-offs;
  - Underlying, of which receipts, debt interest and non-interest spending.
- Attribution here is at aggregate level only. Component-level attribution comes from the EFO tables (5.4).
- The PMD notes state that the full decomposition covering all government decisions has been produced since March 2016. Check how the earlier blocks were constructed and flag any difference.

### 5.3 OBR Policy Measures Database (PMD)

**Contents**
- Sheets: Tax Measures (about 2,600 rows since 1970), Tax Summary, Spending Measures (since June 2010), Spending Summary, Borrowing Summary.
- Tax Measures columns: Event, Measure description, Tax head, then one column per fiscal year from 1970-71 to 2030-31. Values are in £ million; positive = gain to the Exchequer.

**Crosswalks needed** (Teo reviews both)
- *Events*: about 85 events, named after the fiscal event (e.g. "Budget 2010 #2", "Autumn Budget 2024", "Spring Forecast 2026"). Map each to an HOFD vintage label (e.g. "June 2010", "October 2024", "March 2026").
- *Tax heads*: about 62 raw labels, inconsistent in case and naming ("Business Rates" / "Business rates", "income tax" / "Income tax", "Fuel Duty" / "Fuel duty"). They also differ from the HOFD sheet names ("Corporation tax (onshore)" versus the "Onshore" sheet). Map each to an HOFD series.

**Limitations stated in the Notes sheet**
- Only the original costing is recorded; costings are never updated afterwards.
- Costings beyond the original five-year scorecard period are extended using nominal GDP growth.
- Only direct effects are included. Indirect macroeconomic effects appear in the EFOs and in the FRD totals.
- Disaggregation by individual tax starts with the June 2010 Budget.

### 5.4 OBR Economic and Fiscal Outlook (EFO) documents

**What exists**
- One EFO per vintage, published on the day of the fiscal event: a report (PDF) and a "charts and tables" download.
- Formats differ over time. In March 2026 the charts-and-tables download was a zip containing one workbook per chapter; earlier formats may differ **(verify)**.
- Chapter numbering has changed over time. In March 2026 receipts are chapter 3.

**Component-level attribution tables in the receipts chapter** (verified for March 2026)
- *Table 3.2, "Receipts: changes since the November 2025 forecast"*: the previous forecast, the current forecast and the difference. The difference is split two ways:
  - by type: underlying forecast differences, PSNB-neutral differences, and the direct effect of Government decisions;
  - by tax head.
- *One table per major tax* (non-SA income tax and NICs, SA income tax, VAT, onshore corporation tax, CGT), splitting the change into drivers. For example:
  - VAT: household and government consumption, VAT base re-allocation, calibration to outturn, other.
  - PAYE income tax and NICs: calibration to outturn, employment and earnings forecast, error correction, other.
- Driver labels vary across vintages. Harmonizing them is decision D3.

**Revised files**
- In the March 2026 zip, the chapter 4 workbook has a later modification date (17 March) than the other files (3 March).
- Record the modification date of every file, and treat a revised file as available only from its modification date.

**Publication dates**
- Take them from the OBR landing pages.
- A third-party calendar lists 26 March 2026 for the March 2026 EFO, while the OBR site and the file dates show 3 March 2026. Do not use any calendar other than the primary source.

**Landing pages**
- URL patterns differ for older EFOs; some guessed URLs return 404.
- Build the list from the OBR publications listing.

### 5.5 OBR Forecast Evaluation Reports (FER)

- Published annually since October 2011. Landing pages were verified for October 2011, October 2017 and June 2026.
- Each includes the report and charts and tables. Recent years also include supplementary economy and fiscal tables.
- **Use**: post-hoc explanations of errors by component. Label documents only; never an input.

### 5.6 Other OBR dated text (verify)

- A monthly commentary on the public sector finances release compares year-to-date outturn with the latest forecast.
- If its archive is complete, it is the closest public equivalent to in-period results narratives.
- Inventory it in E0. Whether to include it is decision D9.

### 5.7 CBO eval-projections repository

- Public repository `US-CBO/eval-projections`. Its data, code and documentation are in the public domain in the US.

**Input files**
- `baselines.csv`
  - Columns: component (revenue, outlay, deficit, debt), category, subcategory, baseline_date, Spring_flag, Winter_flag, projected_fiscal_year, projected_year_number (−1 to 11), value ($ billion).
  - 117 baseline dates, from 1982-02 to 2026-02.
  - Revenue: 7 categories (individual income, corporate income, payroll, excise, estate and gift, customs, miscellaneous) plus a total, each with about 108 vintages.
  - Outlays: Discretionary (defense, nondefense), Mandatory (Social Security, Medicare, Medicaid, other, Fannie Mae/Freddie Mac), Net interest.
- `baseline_changes.csv`
  - Columns: change date, change_category (Legislative, Economic, Technical), projected fiscal year, value, by component and category.
  - About 120 change dates in total; about 105 for each revenue category.
- `actuals.csv` (1982–2025) and `actual_GDP.csv`.

**Points to verify**
- `baseline_date` is month-level, with the day set to 01. Exact publication dates must come from cbo.gov (D5).
- CBO's own evaluations use one baseline per year: Winter for revenue, Spring for the other components. This plan keeps all baselines and carries the flags.
- Some baselines have neither flag set (e.g. 2020-09). Find out what they are **(verify)**.
- Verify the meaning of `projected_year_number` −1 and 0 against `projected_fiscal_year` and `baseline_date`.
- Find out which previous baseline each change date is measured against **(verify)**. The number of change dates (about 120) differs from the number of baseline dates (117).

**Replication target**
- `output_data/` holds CBO's computed errors and summary statistics. Reproducing them is the gate in E3.

### 5.8 CBO documents

- The Budget and Economic Outlook, usually published in January; its update, usually in August; and updated budget projections, usually in March. Most of these describe the differences from the previous projections, including an appendix attributing changes to legislative, economic and technical causes **(verify per document)**.
- Monthly Budget Review, published monthly. The archive goes back to at least 1999 **(verify)**.
- Post-hoc documents: the annual "The Accuracy of CBO's Budget Projections for Fiscal Year YYYY", "An Evaluation of CBO's Past Revenue Projections", and the other evaluation reports listed in the repository README. Label documents only.

---

## 6. Target data model

Every table carries a `source` column. Formats are decision D15. Every table has a schema file next to it.

- **vintages**
  - `source`, `vintage_id`, `label` (as the source writes it)
  - `publication_date` (exact day), `date_certainty` (exact / month-only)
  - `forecaster` (HM Treasury / OBR / CBO), `flags` (memo, supplementary, season flags)
  - `primary_document_id`
- **series**
  - `source`, `series_id`, `name`, `parent_series_id` (hierarchy)
  - `family` (D7), `unit`, `kind` (level / balance / rate)
  - `period_type` (UK fiscal year / US fiscal year / calendar year)
  - `first_vintage_id`, `last_vintage_id`, `notes`
- **forecasts**
  - `source`, `series_id`, `target_period`, `vintage_id`
  - `value_source_unit`, `value`
  - `cell_role`, `horizon_months`, `origin` (sheet or file and row)
- **outturns**
  - `source`, `series_id`, `target_period`, `value_latest`, `value_first_estimate`
  - `first_estimate_vintage_id`, `origin`
- **attribution**
  - `source`, `series_id` (component or aggregate), `target_period`, `vintage_id`, `previous_vintage_id`
  - `category_raw` (label as published), `category` (harmonized, D3), `value` (receipts or series convention)
  - `origin` (document, table number, row)
- **policy_measures**
  - `source`, `event_raw`, `vintage_id`, `measure`
  - `head_raw`, `series_id`, `target_period`
  - `value` (harmonized unit, convention of the affected series), `extrapolated` (true / false)
- **documents**
  - `doc_id`, `source`, `doc_type` (forecast_narrative / forecast_tables / in_period_commentary / post_hoc_evaluation / other)
  - `title`, `url`, `publication_date`, `last_modified`, `available_from`
  - `vintage_id` (if the document belongs to a vintage), `hash`, `extraction_status`, `extraction_quality`
- **passages**
  - `doc_id`, `passage_id`, `section_path`, `page`, `kind` (paragraph / box / table / footnote), `text`
- **links**
  - `passage_id`, `series_id`, `target_period`
  - `link_type` (explicit name / synonym / table reference / relative period resolved)
  - `ambiguous` (true / false)
  - links records topical relevance (series and target period named). It does not record whether a passage explains an error; that is recorded in qrels.
- **cells** (derived)
  - Everything in **forecasts**, plus the previous vintage and its value.
  - Revision and log revision.
  - Errors against both outturns, in raw and policy-adjusted form, plus log versions.
  - Normalized errors (E6).
  - Flags: classification break, memo vintage, episode window.
- **cases**, **controls**, **random_sample**
  - Trajectory identifiers plus the selection statistics defined in E6.
- **qrels**
  - `case_trajectory_id`, `vintage_id`, `passage_id`
  - `mentions_cause` (yes / partial / no)
  - `acted_on` (forecaster states it adjusted for it / states it did not / not stated)
  - `cause_id`, `labeller`, `label_date`, `pooled_from` (list of runs)
- **causes**
  - `case_trajectory_id`, `cause_id`
  - `cause_text` (short, written by Teo from the post-hoc passage), `post_hoc_passage_id`
  - `attribution_category` (harmonized, D3, where the attribution tables support it)

---

## 7. Stages

Stages run in the order listed. Case selection (E6) happens before any text is extracted or linked (R1, E7, E8), so that the selection cannot be influenced by what the documents say.

### E0 — Inventory and vintage calendar

**Tasks**
1. Download the HOFD, FRD and PMD workbooks and the CBO repository. Record provenance for each.
2. List every EFO and FER landing page from the OBR publications listing, with all files per page. Inventory the monthly public finances commentary (5.6).
3. List every CBO Budget and Economic Outlook, update, March projection, Monthly Budget Review and evaluation report from cbo.gov.
4. Build the vintage calendar:
   - Each HOFD vintage label → EFO landing page → exact publication date.
   - Each CBO `baseline_date` → publication → exact date, or flag it as month-only.
5. Check every source fact in section 5 against the files. List the confirmations and the discrepancies.

**Artifacts**: `inventory/sources`, `inventory/vintage_calendar`, `inventory/documents`, `notes/extraction/E0-inventory.md`.

**Gate**
- Every OBR vintage in the HOFD has an EFO with an exact publication date.
- At least 90% of CBO baselines have an exact publication date; the rest are flagged.

**Kill condition**: if the EFO report is unavailable for more than 3 OBR vintages, stop and report.

### E1 — OBR forecasts and outturns

**Tasks**
1. Parse every unsuffixed HOFD sheet into **forecasts** and **outturns**.
2. Tag the forecaster: HM Treasury before June 2010, OBR from June 2010.
3. Tag `cell_role` and compute `horizon_months` using the UK fiscal year for fiscal series and the calendar year for economy series.
4. Keep memo rows as separate flagged vintages.
5. Build the receipts and spending hierarchies:
   - Current receipts → major heads.
   - Income tax → PAYE and self-assessed.
   - Alcohol → spirits, wine, beer and cider.
6. Compute the residual (total minus the sum of listed components) per vintage and target.
7. Record when each component first appears. Several were introduced later: health and social care levy, electricity generator levy, CBAM, vaping duty.
8. Cross-check each unsuffixed sheet against its "(2)" copy on the overlapping range.

**Artifacts**: `tables/series`, `tables/vintages`, `tables/forecasts`, `tables/outturns` (OBR part), `notes/extraction/E1-obr-forecasts.md`.

**Gate**
- Every sheet is parsed, and the vintage count per sheet matches the labels in the sheet.
- The "(2)" cross-check agrees to within 0.05 on every overlapping cell.
- The hierarchy residual is reported per vintage, and any residual jump larger than 1% of the total is listed.

### E2 — OBR attribution and policy measures

**Tasks**
1. Parse the FRD into **attribution** at aggregate level. Convert its signs to the receipts convention where receipts rows are used.
2. Parse the PMD into **policy_measures**. Build the event and tax-head crosswalks (5.3) as separate reviewed files, and mark values that are extrapolated beyond the original five-year scorecard.
3. For each EFO, locate the receipts chapter tables:
   - the table of receipts changes since the previous forecast, overall and by tax head;
   - the per-tax driver tables.
4. Parse all of them into **attribution** with the raw labels. Handle format and chapter-number changes across years, and record which vintages have which tables.
5. Build the attribution-label crosswalk to harmonized categories (D3) as a reviewed file.

**Consistency checks**
- For each vintage, the "current forecast" row in the EFO tables matches the HOFD value for the same series and target, within rounding (0.05 plus 0.5% of the value).
- The "previous forecast" row matches the HOFD value of the previous vintage, within the same tolerance.
- The attribution rows sum to the stated difference, within 0.1 × the number of rows.
- The FRD total revision equals the HOFD PSNB difference between consecutive vintages, within 0.1.

**Artifacts**: `tables/attribution` (OBR part), `tables/policy_measures`, `crosswalks/pmd_events`, `crosswalks/tax_heads`, `crosswalks/attribution_labels`, `notes/extraction/E2-obr-attribution.md`.

**Gate**
- At least 95% of the matched cells pass the checks above.
- The event crosswalk covers every event since June 2010.
- Coverage of the per-tax driver tables is reported by vintage and by tax.
- Teo reviews the three crosswalks.

### E3 — CBO forecasts, outturns and attribution, with replication

**Tasks**
1. Load the four CSVs into the common tables.
2. Attach exact publication dates from E0.
3. Tag `cell_role` and `horizon_months` using the US fiscal year.
4. Check the hierarchy identities:
   - revenue total = sum of the 7 categories;
   - outlays total = discretionary + mandatory + net interest;
   - discretionary = defense + nondefense;
   - mandatory = sum of its subcategories.

   Report the residuals.
5. Establish how `baseline_changes` relates to consecutive baselines: whether the previous baseline plus the legislative, economic and technical changes equals the current baseline, and relative to which previous baseline. Load the changes into **attribution** with categories Legislative / Economic / Technical.
6. Replication: recompute CBO's projection errors and summary statistics with CBO's own definition (5.7 and 4.2) and compare them with the files in `output_data/`.

**Artifacts**: the CBO parts of all tables, `stats/cbo_replication`, `notes/extraction/E3-cbo.md`.

**Gate**
- The replicated errors match CBO's output files to within 0.01 for every row.
- The baseline-plus-changes relation holds within 0.5 ($ billion) for at least 95% of category-years, or the actual relation is documented.

**Kill condition**: if replication fails and the cause cannot be found, stop and report.

### E4 — Harmonized cell table, policy adjustment and checks

**Tasks**
1. Build **cells**. For each cell: the previous vintage for the same target and its value, the revision, the log revision, the errors against both outturns, and the log errors.
2. Policy adjustment (both variants stored; the choice is D2):
   - *CBO*: adjusted forecast = forecast + the sum of legislative changes dated after the vintage, following CBO's method.
   - *OBR aggregates*: remove the FRD "Policy" and "Classifications and one-offs" revisions that occurred after the vintage.
   - *OBR components*: remove the PMD direct effects of measures announced after the vintage for that tax head. Cross-check against the "direct effect of Government decisions" rows in the EFO tables where they exist. Flag that indirect effects are missing.
3. Reconstruct first-estimate outturns (default in D4).
4. Detect classification breaks. Flag a trajectory when the latest outturn lies outside the range of all its vintages by more than 3 × the series' median absolute revision, and the FRD or the EFO tables record a classification change for that series and period. List the flagged trajectories for Teo.
5. Tag the episode windows (D8).
6. Check the identity in 4.1 for every cell.

**Artifacts**: `tables/cells`, `tables/outturns` (with first estimates), `notes/extraction/E4-cells.md`.

**Gate**
- The identity holds to floating-point precision for every cell.
- The share of flagged cells is reported by series and by source.

### E5 — Stylized facts and numbers-only predictability

All statistics are computed per source and per series family, for raw and policy-adjusted errors, and by horizon bucket (D6).

**Statistics**
- *Bias*: mean error, with standard errors clustered by target period. Cells for the same target period across vintages are strongly dependent.
- *Mincer–Zarnowitz*: regress outturn on forecast per horizon bucket, and test intercept 0 and slope 1.
- *Revision autocorrelation* (Nordhaus): the correlation between consecutive revisions of the same target, and the share of consecutive revisions with the same sign (compared with 50% under efficiency).
- *Error on revision* (Coibion–Gorodnichenko): regress `e_v` on `r_v`. Their convention is error = actual − forecast, so their positive coefficient appears as a negative coefficient here. State this in the output.
- *Attribution shares*: the share of the absolute revision from each harmonized category, by horizon bucket. Also test whether the "calibration to outturn" revisions at vintage v are predictable from the revisions at earlier vintages.
- *Episode sensitivity*: all of the above with and without the episode windows.

**Reporting requirements**
- Report sample sizes everywhere: the number of complete target periods per series is small, especially for OBR.
- Save a machine-readable file of calibration targets for the synthetic generator: error standard deviation by horizon bucket, revision autocorrelation, same-sign share and bias, per source and series family.

**Artifacts**: `stats/stylized_facts`, `stats/efficiency_tests`, `stats/calibration_targets`, `notes/extraction/E5-stylized-facts.md`.

**Gate**: report only. Teo reviews the results before case selection.

### E6 — Case scoring and selection (pre-registered)

The selection rule and thresholds are written to `cases/preregistration.md` and hashed before any selection is run. They are not changed after R1 starts. Any later change is logged as a deviation, with its reason.

**Scoring**
1. Error basis: log error for level series; error in per cent of GDP for balance series. Policy-adjusted by default (D2).
2. Scale:
   - `σ(series, horizon bucket) = 1.4826 × median |e − median(e)|`, computed leave-one-target-out: exclude the trajectory's own target period.
   - If fewer than 8 target periods are available, shrink towards the pooled σ of the series family, with weight n/8 on the series' own σ.
3. `z_v = e_v / σ`.
4. *Run*: consecutive vintages of the same trajectory with the same sign and `|z_v| ≥ z*`. Only `in_progress` and `future` cells count.
5. *Case score*: the sum of `|z_v|` over the longest qualifying run. A trajectory is eligible if the run length is at least 2.
6. Record for every trajectory:
   - the onset vintage (the first vintage of the run);
   - the correction vintage (the first vintage at which the forecast has moved at least half of the way from its onset value toward the outturn);
   - the lead-time window: the vintages from onset to correction.

**Selection**
- *Cases*: the top K per source by score. At most 3 per episode window and at most 2 per series family per target period. Exclude trajectories flagged for a classification break (D13).
- *Controls*: for each case, up to 2 trajectories with max `|z_v| < z_low` across all vintages, from the same series family, with a target period within ±2 years and similar horizon coverage.
- *Random sample*: M trajectories drawn uniformly from all eligible trajectories regardless of score, using a fixed, recorded seed. Needed for base rates and false-alarm estimates later.
- Defaults (D8): `z* = 1.5`, `z_low = 0.5`, K = 15 per source, M = 30 per source.

**Artifacts**: `cases/preregistration.md` (plus hash), `cases/cases`, `cases/controls`, `cases/random_sample`, `notes/extraction/E6-cases.md`.

**Gate**
- The pre-registration file was written and hashed before selection.
- Counts are reported per stratum (source, family, episode) for cases, controls and the random sample.
- The number of distinct target periods among cases, controls and the random sample is reported per source.

### R1 — Retrieval pilot

**Purpose**: measure whether retrieving error-explaining passages is hard, before full extraction.

**Pilot selection** (written into `pilot/preregistration.md` and hashed before any text is extracted): from the E6 cases, the top P per source by case score among cases whose target period is covered by at least one post-hoc document according to the E0 inventory metadata (not its text). Default P = 3 (D17). The corpus window (D18) and the pool depth (D19) are written into the same file.

E0 did not record which target periods a post-hoc document covers. R1 derives this from the inventory's titles and publication dates only (for example, the fiscal year named in a CBO accuracy report, or the year evaluated by an FER), and writes the rule and its result into `pilot/preregistration.md`.

**Tasks**
1. Implement the E7 extraction code and run it only on the documents needed for the pilot cases: all documents available before each vintage in the case's lead-time window (section 8 rules) and inside the corpus window (D18), plus the post-hoc documents for the target period. E7 later reuses the code and skips these documents.
2. Build the E8 series dictionary and the E8 deterministic series-and-period linking, but only for the pilot series. E8 later reuses and extends them to all series. Section 8 rule 6 applies: the dictionary is built from series names and the forecaster's own terminology, not from case outcomes.
3. Teo writes one short `cause_text` per cause from the post-hoc passages (**causes** table).
4. Queries, fixed in `pilot/preregistration.md` before any retrieval run:
   - prospective: template from series name, series synonyms (E8 dictionary), and target period only;
   - retrospective: `cause_text`.
5. Runs, each restricted per vintage to passages with `available_from` strictly before the vintage publication date (with the section 8 rule 3 exception for the forecaster's own narrative at that vintage):
   - topical filter: E8 deterministic series-and-period linking, ranked by publication date, newest first. It does not use the query, so it is run and reported once per vintage, not per query type;
   - BM25;
   - one local dense embedding model (D16).

   Save the top 50 per query and vintage.
6. Pooling: Teo labels the union of the top N of every run (D19), plus any passages he finds by manual search (marked as such), into **qrels**.
7. Metrics per source and query type:
   - recall@5, @10 and @50 against the pool;
   - rank of the first relevant passage;
   - share of topical links with `mentions_cause` = yes;
   - earliest vintage in the lead-time window at which a relevant passage exists and at which one is retrieved in the top 10.

**Artifacts**: `pilot/preregistration.md` (plus hash), `pilot/queries`, `pilot/runs`, `tables/causes`, `tables/qrels`, `stats/retrieval_pilot`, `notes/extraction/R1-retrieval-pilot.md`.

**Gate**: report only. The note must state, per source:
- the difference in recall@10 between retrospective and prospective queries;
- the number of labelled passages;
- the number of distinct target periods among the pilot cases.

It must state that recall is measured against a pool and is an upper bound. Stop for Teo's review before E7.

### E7 — Document acquisition and text extraction

**Tasks**
1. Download every inventoried document.
2. Extract text with page numbers and section structure. Keep boxes, tables and footnotes as separate passage kinds, and link tables to the structured values from E2 where possible.
3. Record extraction quality per document: characters per page, empty pages, pages that need OCR.
4. De-duplicate documents, and record corrections and later modification dates.
5. Assign `available_from` to every document according to the rules in section 8.

Documents already extracted in R1 are not extracted again; the same extraction code is used.

**Artifacts**: `raw/documents/`, `text/passages`, the `documents` table updated, `notes/extraction/E7-documents.md`.

**Gate**
- At least 95% of documents have non-empty text on at least 95% of pages.
- Teo checks a sample of 10 pages per decade against the originals.

### E8 — Linking and case packs

**Linking** (deterministic only, no language model)
1. Series dictionaries per source, containing names and synonyms. For example: "PAYE", "pay as you earn", "income tax and NICs"; "individual income taxes"; "onshore corporation tax", "CT".
2. Target-period mentions:
   - explicit ones: "2025-26", "2025–26", "fiscal year 2025", "FY2025";
   - relative ones: "this year", "next year", resolved against the publication date and marked `ambiguous`.
3. Table references (e.g. "Table 3.5"), linked to the attribution rows they describe.

The dictionaries and linking code built for the pilot series in R1 are reused and extended to all series.

**Case packs**: one directory per case, control and random-sample trajectory, containing:
- the trajectory table: vintages, forecasts, revisions, raw and policy-adjusted errors, z, and cell roles;
- attribution per vintage;
- the policy measures announced after each vintage that affect the series;
- the documents available at each vintage (following section 8), with their linked passages;
- the post-hoc passages (FER, CBO accuracy and evaluation reports) linked to the series and target period;
- a manifest with hashes.

**Linking quality**: Teo hand-labels a sample of 50 linked passages and 50 unlinked passages from the same documents. Report precision on the linked sample and the miss rate on the unlinked sample.

**Artifacts**: `text/links`, `cases/packs/<trajectory_id>/`, `notes/extraction/E8-links-and-packs.md`.

**Gate**
- Linking precision is at least 0.8 on the labelled sample, or the result is reported and the stage stops.
- The share of cases with at least one linked post-hoc passage is reported. Cases without one are listed.

### E9 — Freeze and data card

**Tasks**
1. Freeze a versioned release: the hash of every raw file and table, row counts, and schema files.
2. Write `DATA_CARD.md`, covering:
   - what each source is and consists of;
   - licences: OBR material under the UK Open Government Licence, with the required attribution statement; CBO material in the US public domain;
   - known issues: classification changes, extrapolated costings, missing indirect policy effects, latest-only outturns, month-only dates;
   - the leakage rules in section 8;
   - the list of documents with publication dates, so that later experiments can restrict inputs to documents published after a given language model's training cutoff.

**Gate**: Teo signs off the data card.

---

## 8. Leakage rules

1. A document's `available_from` is its publication date. For a revised file it is the modification date. If only the month is known, use the last day of that month.
2. A document may be an input for a prediction made at vintage v only if its `available_from` is strictly before the publication date of v.
3. **Exception for the forecaster's own narrative at v** (the EFO or Budget and Economic Outlook of that vintage): it describes forecast v and is published with it. It may be an input for predicting revisions after v and the eventual error of forecast v. It must never be treated as information that forecast v failed to use.
4. Post-hoc documents (FER, CBO accuracy and evaluation reports) are labels only. They must never appear in an input set.
5. Outturns: at vintage v, only outturn estimates published before v may be used as inputs. The latest outturn is used only to compute errors.
6. Crosswalks and dictionaries must not be built by looking at case outcomes.
7. Case selection (E6) is fixed before any text extraction (R1, E7).
8. In R1, cause texts and retrospective queries are built from post-hoc documents by construction. They are used only to measure retrieval difficulty, never as inputs to a prediction.

---

## 9. Checks that must be reported together in the final note

- Row counts per table and per source.
- The share of cells passing each consistency check (E1–E4).
- The CBO replication result.
- Attribution coverage by vintage and series.
- Classification-break flags by series.
- Case, control and random-sample counts per stratum.
- R1 recall results by source and query type, and qrels counts.
- Extraction quality and linking precision.
- Every default taken for an open decision.

---

## 10. Open decisions (Teo decides; defaults in brackets)

"Decided" marks a decision Teo has taken. On 29 September 2026 Teo accepted the recommendations put to him after E5, which are recorded under D1, D2, D3, D5, D7, D8, D11–D13 and D22.

- **D1** Outturn used for errors: latest or first estimate. [Store both; latest is the primary.] Decided: latest is the primary; first estimate for robustness.
- **D2** Raw or policy-adjusted errors for case selection. [Policy-adjusted.] Decided: policy-adjusted; raw errors kept for robustness. Known limits: OBR components lose only the direct effects of measures, and OBR aggregate classification changes can be removed only up to October 2021.
- **D3** Harmonized attribution categories. [policy / economic determinants / calibration to outturn / classification and one-offs / modelling and other. CBO maps Legislative→policy, Economic→economic determinants, Technical→modelling and other.] Decided: the FRD's "underlying" stays one unsplit category (the EFO per-tax tables give the split). CBO revenue, and the CBO deficit that includes it, are left out of the attribution shares, because they are split into economic and technical causes only from 2024; they are kept for errors and cases.
- **D4** How to reconstruct first-estimate outturns. [The value in the `past` column of the first vintage published after the period ended.]
- **D5** Uncertain publication dates. [Last day of the month; flag the vintage.] Decided: last day of the month; the date of CBO's testimony on the outlook that month is kept as a column where known.
- **D6** Horizon buckets in months. [<0; 0–6; 6–12; 12–24; 24–36; 36+.]
- **D7** Series families for pooling. [OBR: income-based taxes, consumption taxes, capital taxes, business taxes, duties, other receipts, spending by type. CBO: each revenue category is its own family; outlays by category.] Decided: level series are pooled within a family in log errors; balance series (PSNB, deficit) are kept separate, in their own units, and never logged.
- **D8** Thresholds and episode windows. [`z* = 1.5`, `z_low = 0.5`, K = 15, M = 30; episode windows 2008-09 to 2009-10, 2020-21 to 2021-22 and 2022-23, tagged but not excluded.] Decided: the defaults, with at most 3 cases per episode window.
- **D9** Include in-period commentary (OBR monthly public finances commentary, CBO Monthly Budget Review) as dated text. [Inventory in E0, extract in E7, but mark as optional in case packs.]
- **D10** Text not written by the forecaster. [Out of this plan.]
  - Consequence: the document corpus contains only the forecaster's own publications. Evidence before a forecast therefore means what the forecaster itself wrote, not third-party signals. Results from this corpus must be stated with this limitation. E0 must report whether any inventoried documents are written by a third party.
- **D11** Pre-2010 HM Treasury forecasts. [Extract as a separate forecaster; exclude from case selection.] Decided: as the default.
- **D12** Economy series (calendar-year, per cent change). [Extract; exclude from case selection; available as context.] Decided: as the default.
- **D13** Trajectories with classification breaks. [Keep in the data; exclude from case selection.] Decided: as the default.
- **D14** Memo and supplementary vintages. [Keep, flagged; exclude from revision chains.]
- **D15** Storage format of tables. [A columnar format with a schema file next to each table.]
- **D16** Local embedding model for the dense retriever. [Allowed; model chosen by Teo; zero cost; name and version recorded.] Decided (Teo, 29 September 2026): `BAAI/bge-small-en-v1.5`.
- **D17** Number of pilot cases per source. [P = 3.] Decided (Teo, 29 September 2026): P = 3, and distinct: a case is skipped when its series was already taken, or is the parent or child of a taken case's series in the same target period (`pilot/preregistration.md`).
- **D18** Corpus window for each R1 pilot case. [Documents published on or after the publication date of the first vintage that forecast the case's target period, subject at each vintage to the section 8 rules.]
- **D19** Pool depth for R1 labelling. [Top 10 of each run at each vintage; each distinct passage is labelled once per case.]
- **D20** Settling crosswalk rows by agreement. [A row is settled when Jev's top answer equals the keyword mapping, Jev's confidence is at least 0.7, and the label contains no negation (Teo, 28 September 2026). Unsettled PMD heads go to review before E6: on 28 September 2026 a separate Claude session proposed an answer for each of the 35 queued heads, Teo accepted them, and the pipeline session checked the rows marked `check` in the source files and overrode three of them on that evidence (`crosswalks/review_queue_heads_decisions.csv`, which names the labeller and the file each check used). Unsettled attribution labels stay `pending` with the keyword mapping as a provisional value, and every stage that uses them reports how many pending rows it used.]
- **D21** Second model for pending attribution labels. [Pending: to be run on a separate machine; provider and model recorded in `results.jsonl`.] Decided (Teo, 29 September 2026):
  - The second model (`gpt-5.6-luna`, 213 of 213 rows) returned a category and its reasoning, but no probability, so the D20 confidence test could not be applied.
  - 47 labels were settled where the keyword mapping, Jev, the second model and a codebook review by the pipeline session all agreed.
  - The 21 group headings are resolved in E2 by rule A2.
  - The other 155 labels went to `crosswalks/review_queue_labels.csv`. This includes 10 settled labels that rule A3 moved to calibration ("<tax> receipts and modelling", "Other modelling and receipts changes").
  - Teo accepted the codebook review's proposal for all 155 without changing any. They are marked reviewed, and the labeller column says the proposal was accepted.
  - The 7 labels where A3 was read literally ("... receipts" without "data", e.g. "ICC profits and receipts") are the pipeline session's reading, not a decision by Teo. Revisit them before E5 attribution shares are reported.
  - Also found in this review: group-heading rows in `tables/attribution` repeated the sum of the rows beneath them, and E5 counted both. They are now flagged `group_heading`, and E5 counts the rows beneath.
- **D22** Pre-specified numbers-only tests. [Decided (Teo, 29 September 2026): the numbers-only baseline for research question 1 is two tests, by source and series family (balance series one at a time), with episodes included: the same-sign share of consecutive revisions whose later revision falls 12–24 months before the end of the target period (binomial test against 0.5), and the coefficient of policy-adjusted errors on revisions at 12–24 months (Coibion–Gorodnichenko; raw errors for robustness). Both are in `stats/prespecified_tests.csv`. They were chosen after the E5 results had been seen, and this is stated wherever they are reported. The other E5 tests are descriptive.]

---

## 11. Artifacts (names are fixed; later plans refer to them)

```
raw/obr/                  raw/cbo/                 raw/documents/
inventory/sources         inventory/vintage_calendar
inventory/documents
crosswalks/pmd_events     crosswalks/tax_heads     crosswalks/attribution_labels
crosswalks/codebook.md    crosswalks/llm/          crosswalks/review_queue_heads
crosswalks/review_queue_labels                     crosswalks/pending_second_model/
tables/series             tables/vintages          tables/forecasts
tables/outturns           tables/attribution       tables/policy_measures
tables/cells              tables/causes            tables/qrels
stats/cbo_replication     stats/stylized_facts     stats/efficiency_tests
stats/calibration_targets stats/retrieval_pilot
text/passages             text/links
cases/preregistration.md  cases/cases              cases/controls
cases/random_sample       cases/packs/<trajectory_id>/
pilot/preregistration.md  pilot/queries            pilot/runs
notes/extraction/E0-inventory.md … E9-data-card.md
notes/extraction/R1-retrieval-pilot.md
DATA_CARD.md
```

---

## 12. Stage note template

Each stage writes one note to `notes/extraction/`, with these sections:

1. **Question**: what this stage had to establish.
2. **What I did**: the steps taken, the files touched, and the defaults taken for open decisions.
3. **Findings**: numbers first. Each claim points to the file, sheet and row or column it was verified in.
4. **Open questions**: anything the stage could not resolve, including every disagreement between this plan and the source files.
5. **Implications for the thesis**: what the findings change about the research question, the case design or later stages.
6. **Gate result**: pass or fail for each gate criterion, with the measured value.