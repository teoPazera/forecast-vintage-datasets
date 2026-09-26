# E2: OBR attribution and policy measures

Run: `python -m fvd.e2_frd_pmd`, then `python -m fvd.e2_efo_tables` (26 September 2026).

## 1. Question

Can the OBR's own attribution of forecast revisions be put on the common schema?
- at aggregate level (Forecast Revisions Database, FRD);
- for individual taxes (the receipts tables of each EFO);
- together with the costings of individual policy measures (Policy Measures
  Database, PMD).

And are these tables consistent with the HOFD forecasts parsed in E1?

## 2. What I did

- **FRD** (`fvd.e2_frd_pmd`)
  - All 34 blocks of both revision sheets (£ billion and % of GDP) were parsed.
    Each row is tagged with its place in the decomposition:
    `total`, `policy`, `policy/receipts`, `policy/spending`, `classification`,
    `underlying`, `underlying/receipts`, `underlying/debt_interest`,
    `underlying/non_interest_spending`.
  - Label variants are read as the same row: "Underlying1", "Underlying2",
    "of which policy" (March 2019).
  - PSNB attribution is stored in the FRD's own convention (positive = borrowing
    raised).
  - The receipts rows are also stored as attribution for £PSCR with the sign flipped
    (plan 4.2), and the spending rows for £TME. PSCR and TME classification changes
    come from the FRD's "Classifications and one-offs" sheet, which records each
    aggregate in its own convention.
- **Intermediate forecast.** The FRD measures November 2020 against the July 2020
  fiscal sustainability report scenario ("FSR+SEU 2020"), not against March 2020.
  That forecast is stored as the intermediate vintage `obr_2020-07_fsr`, dated
  14 July 2020 from the OBR's own page (`tables/vintages/OBR_intermediate.parquet`).
- **PMD.** Tax Measures and Spending Measures were parsed.
  - The workbook is read with cell formatting so that "extrapolated beyond the
    original scorecard period" can be read from the shading key (fill `FFE1E9EE`,
    Notes row 11).
  - Values are kept in £ million in the PMD sign (gain to the Exchequer), and also
    stored in £ billion in the affected series' convention: tax gain = receipts up,
    spending gain = spending down.
- **Crosswalks** (defaults, written before any outcome was looked at; plan 8.6). Each
  file has `confidence` and `reviewed` columns:
  - `crosswalks/pmd_events.csv`: each OBR-era event maps to the EFO published with
    it; pre-2010 Budgets and PBRs map to HM Treasury vintages by rule.
  - `crosswalks/pmd_heads.csv`: tax and spending heads to HOFD sheets.
  - `crosswalks/attribution_labels.csv`: every FRD, CBO and EFO attribution label to
    a D3 category.
- **EFO tables.**
  - The charts-and-tables workbooks of every EFO were downloaded (`fvd.efo_tables`).
    Where the OBR's own link was never archived, the same workbook was taken from
    another archived URL on obr.uk or its former domains. It was accepted only if its
    file name names the same month, year and part (chapter, annex, fiscal/economy)
    and it opens with several "Table/Chart" sheets.
  - Every sheet was read with a generic table reader (`fvd.e2_efo_tables`) and
    classified by title into three kinds:
    - receipts by type ("sources of change to the receipts forecast", "Receipts:
      changes since …");
    - receipts by tax head;
    - per-tax driver tables ("Key changes to the VAT forecast since …", "VAT: changes
      since …").
  - Row roles (forecast level, change, subtotal, driver, memo) come from the labels.
    Each "Change since …" row governs the driver rows below it, which gives each row
    its own previous forecast.
- **Defaults taken.** D3 categories by keyword (`default_category`). The FRD's
  "underlying" cannot be split into D3 categories and gets its own value,
  `underlying_unsplit`. PSNB-neutral items are mapped to `modelling_other`.
- **Files written:**
  - `tables/attribution/OBR_FRD.parquet` and `OBR_EFO.parquet`;
  - `tables/policy_measures/OBR.parquet`;
  - `tables/series/OBR_derived.parquet`: three income-tax aggregates that EFO tables
    report and the HOFD does not hold as sheets;
  - the three crosswalks;
  - `stats/e2_checks/`.

## 3. Findings

**FRD** (`stats/e2_checks/summary_frd_pmd.json`)

- 34 blocks, November 2010 to March 2026, including "March 2019 restated" and
  "FSR+SEU 2020"; 4,379 attribution rows.
- **Block totals vs the HOFD.** The FRD block total equals the change in HOFD £PSNB
  between consecutive vintages in **181 of 181** comparable cells
  (`frd_vs_hofd.csv`).
  - The tolerance is 0.1 plus half the last published digit of each HOFD value,
    because the HOFD rounds early OBR vintages to whole £ billion (e.g. 2011-12: 116,
    117).
  - At a flat 0.1 the match is 161 of 187.
  - November 2020 is compared through the FSR scenario (March 2020 → FSR → November
    2020).
- **Restated March 2019 block.** It is all zeros, while the HOFD memo row sits
  £18–21bn above March 2019. The FRD records that restatement on its Classifications
  sheet ("Various changes"), not as a revision block. These 6 cells are reported
  separately.
- **Parts vs totals.** Policy + classification + underlying = total within 0.1 in 180
  of 182 cells (`frd_parts_sum.csv`).
- **Label drift inside the FRD.** From October 2021 the block reads "Underlying2" and
  includes classification changes (FRD footnote 2), so classification cannot be
  separated after that date. Policy rows extend one year beyond the total in autumn
  blocks: that is the revision relative to the pre-measures forecast (FRD note *),
  flagged `pre_measures_year`.

**PMD**

- 73,450 cells from 4,522 measures; 48,902 cells are shaded as extrapolated.
- **Events.** All 85 events map to a vintage. The 33 events since June 2010 cover
  all 33 OBR vintages one to one.
- **Heads** (94 in total):
  - tax: 28 exact, 3 assumed (stamp duty → property transaction taxes, bank
    surcharge → onshore CT, energy profits levy → oil and gas), 31 with no HOFD
    series;
  - spending: 10 exact, 6 assumed, 16 with no HOFD series.

**EFO receipts tables** (`stats/e2_checks/summary_efo_tables.json`,
`efo_table_coverage.csv`)

- **Workbooks.** 92 of 97 workbooks retrieved, 6 of them via verified alternate
  captures. Not available anywhere in the archive: March 2011 and December 2014
  (single workbooks), October 2018 fiscal, and two parts without receipts tables.
- **Coverage.** Receipts tables were found for 29 of the 33 regular OBR vintages.
  None for June 2010 (the first OBR forecast, which has no "changes since" tables) or
  for the three missing workbooks. There are no per-tax driver tables in November
  2020 or November 2022.
- **Per-tax driver tables.** 94 tables:
  - onshore CT 24;
  - VAT 22;
  - income tax and NICs 12 (to 2016), then non-SA income tax and NICs 12;
  - SA income tax 10;
  - property transaction taxes 7;
  - CGT 2, NICs 2, non-SA income tax 2, fuel 1.
- **Other tables.** 23 receipts-by-type tables and 32 receipts-by-head tables.
- **Attribution.** 6,221 rows with 527 distinct labels. Default categories: 249
  modelling/other, 153 economic determinants, 81 policy, 41 calibration to outturn,
  3 classification.
- **Consistency checks:**
  - **Forecast levels vs the HOFD** (0.05 + 0.5% of the value): **95.6%** of 1,505
    cells pass (current forecast 96.4%, previous 94.8%). Single-tax tables for SA IT,
    NICs, CGT, property taxes and fuel match 100%, VAT 98% and onshore CT 92%.
  - **"Non-SA income tax".** It is *not* the HOFD's PAYE sheet: there is a steady gap
    of about £8bn. It equals income tax minus self-assessed income tax, which matches
    100%.
  - **Where levels fail:** combined income tax + NICs tables before 2017 (90%),
    non-SA income tax + NICs (94%), onshore CT (92%), and total receipts in December
    2013 and March 2014. There, "current receipts" in the
    EFO table is about £12bn below the HOFD's £PSCR; the table uses a different
    receipts measure.
  - **Drivers add up to the stated change** (0.1 × number of rows): **92.0%** of
    1,039 checks.
    - 85.7% pass using the groupings the tables mark ("of which:" lines and indented
      labels).
    - The other 6.3 points pass only when groupings are inferred from sums, because
      some tables indent sub-items by formatting alone. The `nesting` column of
      `efo_driver_sums.csv` says which applied.
    - Remaining failures are mostly receipts-by-type tables whose totals include
      items not listed as rows (e.g. "Total (including indirect effects)").
  - **EFO "direct effect of Government decisions" rows vs PMD costings** of the same
    event (the E4 cross-check): within 0.1 in 99 of 151 cells; median absolute
    difference £0.02bn (`efo_direct_effects_vs_pmd.csv`).

## 4. Open questions

1. **Review of the three crosswalks** (gate item).
   - Most uncertain: pre-2010 event → HM Treasury vintage (rule-based), the three
     assumed tax heads, and the keyword-based D3 categories of 527 EFO labels.
   - For example, "Outturn receipts and modelling" and "IT and NICs receipts and
     modelling" mix calibration with modelling. They are mapped to
     `calibration_to_outturn` and flagged in the `note` column.
2. **D3 for the FRD.** The FRD's "underlying" is kept as `underlying_unsplit`. Should
   it be split with the EFO receipts-by-type tables where they exist (receipts only),
   or left as is?
3. **Plan vs files:**
   - Receipts are chapter 4 of the EFO until 2019 and in 2023–25, and chapter 3 in
     2020–22 and 2026. Tables are located by title, so chapter numbering does not
     matter.
   - The PMD notes do not say the full decomposition starts in March 2016 (E0 F5).
4. **HOFD "June 2010" mapping** (E0 open question 2). The pre-budget and Budget
   forecasts both have archived reports. This E2 run does not compare values with
   them, because neither has a charts-and-tables workbook with "changes since"
   tables. It remains open for E7, where the report text can be read.

## 5. Implications for the thesis

- **Component-level attribution exists for the main taxes across most vintages.**
  - VAT, onshore CT and income tax + NICs are covered from 2010 to 2026 (with the
    gaps above);
  - SA income tax and property taxes from 2017.
  - The case packs (E8) will carry, per vintage, the OBR's own split of each revision
    into economy, outturn calibration, modelling and policy.
- **Driver labels change over time** (e.g. "Latest receipts data", "Outturn receipts
  and modelling", "Calibration to outturn"). The harmonized categories depend on the
  label crosswalk, so the crosswalk review matters for every attribution result in
  E5.
- **Aggregate attribution is exact.** The FRD reproduces the HOFD's PSNB revisions,
  which makes it a sound basis for policy-adjusted aggregate errors (E4).

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| ≥ 95% of matched cells pass the checks | levels 1,438 / 1,505; driver sums 956 / 1,039; FRD totals 181 / 181; combined 2,575 / 2,725 = **94.5%** | **fail** (narrowly). Causes identified: different receipts definitions in two tables and totals that include unlisted items. No parsing errors found in the single-tax tables |
| Event crosswalk covers every event since June 2010 | 33 / 33 events → 33 / 33 OBR vintages | **pass** |
| Coverage of per-tax driver tables reported by vintage and tax | `stats/e2_checks/efo_table_coverage.csv` | **pass** |
| Teo reviews the three crosswalks | pending | **open** |
