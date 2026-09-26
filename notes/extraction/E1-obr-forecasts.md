# E1: OBR forecasts and outturns

Run: `python -m fvd.e1_obr_forecasts` (26 September 2026).

## 1. Question

Can every series sheet of the Historical Official Forecasts Database be turned into
forecast cells and outturns on the common schema, with vintages, cell roles and
horizons? Does the parsed content agree with the workbook's own chart copies, and
how much of each total do the listed components leave unexplained?

## 2. What I did

- **Parsing.** All 114 unsuffixed series sheets of
  `raw/obr/Historical_official_forecasts_database_Spring_2026.xlsx` were parsed
  (`fvd.e1_obr_forecasts.parse_sheet`):
  - the header row is the one starting "Back to contents";
  - vintage rows are identified by `fvd.hofd.vintage_rows`;
  - outturns come from the "Outturn data*" row;
  - every value keeps its cell reference (`origin`, e.g. `HOFD:VAT!C5`).
- **Vintages.** Vintages come from `inventory/vintage_calendar.csv`. Forecaster: HM
  Treasury before June 2010, OBR from June 2010 (D11 default: kept as a separate
  forecaster).
- **Memo vintage dates** (D14 default: kept, flagged, to be excluded from revision
  chains in E4):
  - the restated March 2019 and supplementary March 2020 forecasts are dated to the
    earlier of their download's first Wayback capture and its `Last-Modified` header.
    Both are upper bounds on publication, so the choice is conservative for leakage;
  - the restated March 2024 forecast (PSNFL sheet only, no download) is dated to the
    October 2024 EFO, the first to use PSNFL as a target (`assumed`).
- **Cell roles and horizons.**
  - Target periods run 1 April to 31 March for UK fiscal years and January to
    December for calendar-year economy series (`fvd.periods`).
  - `horizon_months` = (end of target period − publication date) / (365.25/12 days).
  - HM Treasury vintages are month-only and sit on the last day of their month (D5).
- **Hierarchy** (`fvd.obr_series.HIERARCHY`):
  - current receipts (£PSCR) → the 27 top-level HOFD receipts sheets;
  - income tax → PAYE and self-assessed;
  - alcohol → spirits, wine, beer and cider;
  - TME (£TME) → the 23 spending lines;
  - total welfare → inside and outside the welfare cap.
- **Families** follow the D7 default (`fvd.obr_series.FAMILIES`). Economy series form
  one family (D12: extracted, excluded from case selection later).
- **Chart copies.** Each "(2)" sheet was parsed the same way and compared with its
  unsuffixed sheet on common (vintage, target) cells.
- **Files written:**
  - `tables/{series,vintages,forecasts,outturns}/OBR.parquet`, with schema files
    `tables/*.schema.yaml`;
  - `stats/e1_checks/` (`sheet_counts.csv`, `chart_copy_crosscheck.csv`,
    `hierarchy_residuals.csv`, `hierarchy_residual_jumps.csv`, `non_numeric_cells.csv`,
    `summary.json`).

## 3. Findings

**Row counts** (`stats/e1_checks/summary.json`)

| Table | Rows |
|---|---|
| series | 114 (13 aggregates, 32 receipts, 28 spending, 41 economy) |
| vintages | 109 (33 OBR regular, 3 OBR memo, 73 HM Treasury) |
| forecasts | 26,423 (OBR 23,866; HM Treasury 2,557) |
| outturns | 1,854 |

- **Cell roles:** 18,248 future, 3,878 in progress, 4,297 past. Past cells are
  estimates of outturn, not forecasts (plan section 3).
- **Series kinds:**
  - 12 balances: £PSNB, PSNB, £CB, CB, CACB, CAPSNB, current account (two), output
    gap, inventories, tax litigation, APF;
  - 33 rates;
  - 69 levels.
- **Text in value cells:** 21 cells hold "N/A" instead of a number: world trade,
  euro-area GDP and UK export markets, March 2022 row. The sheets' footnotes say
  these were not updated in March 2022 "due to the rapidly evolving situation"
  (`stats/e1_checks/non_numeric_cells.csv`). They are left out.
- **Late-introduced components:** the first vintage with a value is later than June
  2010 for climate change levy and ETS (March 2011), licence fee (November 2010),
  Scottish taxes (July 2015), health and social care levy (October 2021), electricity
  generator levy (November 2022), CBAM and vaping duty (March 2024)
  (`tables/series/OBR.parquet`, `first_vintage_id`).

**Chart-copy cross-check** (`stats/e1_checks/chart_copy_crosscheck.csv`)

- 2,494 common cells compared; 2,480 (99.4%) agree within 0.05.
- All 14 disagreements are in the chart copies, not the main sheets:
  - **£PSNB, November 2017, 2017-18 to 2022-23:** the main sheet gives 49.9,
    39.5, …, 25.6; the copy gives 45.2, 37.1, …, 21.4. Which is right will be checked
    against the November 2017 EFO tables in E2.
  - **PSNB (% of GDP), March 2017:** every target year in the copy equals 2.634, which
    is a fill error in the copy.
  - **PSNB, November 2023 and March 2024, 2022-23** (a past cell): the copy has 4.83,
    the main sheet 5.03 and 5.04. This looks like an outturn update applied to one
    sheet only.
- The CACB copy has "2023-24" twice in its header. Those cells are not compared.

**Hierarchy residuals** (parent minus the sum of listed children; memo vintages
excluded; `stats/e1_checks/hierarchy_residuals.csv`)

| Parent | Cells | Median residual / parent | Range |
|---|---|---|---|
| Alcohol duties | 232 | 0.0% | ±0.0% |
| Welfare | 168 | 0.0% | ±0.04% |
| Income tax | 232 | −1.0% | −2.3% to +1.8% |
| Current receipts (£PSCR) | 232 | 10.7% | 4.7% to 14.6% |
| TME (£TME) | 232 | 3.1% | −3.0% to 16.7% |

- The £PSCR residual (about a tenth of receipts) is the receipts the HOFD does not list
  as separate sheets. Which lines they are will be read from the EFO receipts table in
  E2.
- The TME residual is spending the HOFD does not list, and it changes with
  classification. It rises from about 1.5% before November 2016 to about 7% from
  October 2018. Those are the vintages where R&D and single-use military expenditure
  moved into DEL (sheet footnotes, November 2016) and Network Rail stopped being
  forecast separately (footnote, October 2018).
- **88 residual jumps larger than 1% of the parent** are listed in
  `stats/e1_checks/hierarchy_residual_jumps.csv`. By parent: IT 15, £PSCR 35, £TME 38.
  Clusters:
  - TME: November 2016 (6), October 2018 (6), November 2025 (6), December 2014 (4);
  - receipts: November 2015 (6), March 2020 (6), November 2010 and December 2012
    (5 each).

## 4. Open questions

1. **Chart-copy disagreements.** The main sheets are treated as correct, and the
   copies are used only as a check (plan 5.1). The £PSNB November 2017 and PSNB 2022-23
   values will be checked against the EFO tables in E2.
2. **Memo vintage dates** are upper bounds (restated March 2019: 17 April 2020;
   supplementary March 2020: 19 April 2020) or assumed (restated March 2024:
   30 October 2024). Both documents are linked from their own EFO landing pages
   (March 2019 and March 2020), which says where they were filed, not when they were
   published. Tighter dates can be read from the documents' text in E7.
3. **Spending hierarchy.** The TME children are the HOFD spending lines, which overlap
   in places:
   - R&D and SUME sit inside DEL from November 2016 but keep their own sheets;
   - the debt-interest sheets are split several ways.

   The residual absorbs the overlaps. A cleaner spending tree needs the EFO's TME
   table, which is available in E2.
4. **Plan vs file:** the plan lists memo rows for March 2019 and March 2020 only. The
   file also has "Memo: restated March 2024 forecast" on the PSNFL sheet (E0 finding
   H8).

## 5. Implications for the thesis

- The OBR panel holds 33 regular vintages, about 30 receipts components and 28
  spending lines. Components introduced after 2010 have short trajectories and will
  add few complete target periods.
- The TME residual moves with classification changes of several per cent of TME.
  Spending-side errors should be read at line level, or after the classification
  adjustment in E4, not from TME alone.
- Receipts components cover about 90% of current receipts. A total-level error can
  therefore be up to about a tenth unexplained by the listed components.

## 6. Gate result

| Criterion | Measured | Result |
|---|---|---|
| Every sheet parsed; vintage count per sheet matches its labels | 114 / 114 sheets; 0 mismatches between label rows with values and parsed vintages (`sheet_counts.csv`) | **pass** |
| "(2)" cross-check within 0.05 on every overlapping cell | 2,480 / 2,494 (99.4%); all 14 failures are errors in the chart copies | **fail** as worded; cause identified, main sheets unaffected |
| Hierarchy residual reported per vintage; jumps > 1% of total listed | reported for 5 parents; 88 jumps listed | **pass** |
