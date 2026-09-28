# Crosswalk codebook

Status: section 1 approved by Teo, 28 September 2026.

This codebook is the written standard for the three crosswalks. A model or a person labels rows by applying it; the rules decide the hard cases, not the labeller's expertise. Sections 2 and 3 are the model's instructions and are sent with every call; section 1 is for Teo.

Crosswalks covered:

| Crosswalk | File | Rows | How it is labelled |
|---|---|---|---|
| Attribution labels | `crosswalks/attribution_labels.csv` (EFO rows) | 559 | Model, with section 2 |
| Tax and spending heads | `crosswalks/pmd_heads.csv` | 94 | Model, with section 3 |
| Fiscal events | `crosswalks/pmd_events.csv` | 85 | Deterministic date check (section 4); no model |

---

## 1. Rules for Teo to approve

Each rule settles a class of labels that the definitions alone leave open. Approve, or change the choice. Everything else in this codebook follows from the category definitions.

| Rule | Choice | Alternative | Examples it decides |
|---|---|---|---|
| A3 Data beats modelling | A label that mentions outturn or receipts data counts as calibration to outturn, even when it also says "modelling" or "other". The row is flagged `mixed`. | Put mixed labels under modelling and other | "VAT outturn and modelling", "Corporation tax receipts and modelling", "Latest receipts data and modelling changes" |
| A4 Recostings are not policy | A re-estimate of a measure announced at an *earlier* event is modelling and other, even under a policy heading. Only decisions taken at *this* event are policy. | Treat recostings as policy | "Recostings of previous measures", "Revised pension tax relief costing", "CT rate cut recosting" |
| A6 Effective tax rates are modelling | A change in the effective tax rate before policy ("pre-measures ETR") is modelling and other. A change in the tax base itself is an economic determinant. | Treat ETR changes as economic determinants (they partly reflect fiscal drag from earnings growth) | "Pre-measures effective tax rate", "Pre-measures ETR", "Lower SA effective tax rate" versus "Pre-measures tax base", "Key tax bases" |
| A7 One-offs are their own category | Litigation, fines, one-off dividends and one-off compensation payments are classification and one-offs. | Leave them under modelling and other | "Litigation cases", "FCA fines", "RBS dividends", "Re-profiling motor finance compensation" |
| A10 PSNB-neutral items | Rows the OBR calls PSNB-neutral are modelling and other, flagged `psnb_neutral`. They are matched by spending, so they are not forecast errors of the receipts total. | Classification and one-offs | "PSNB-neutral forecast differences" |
| A11 Standard-rated share | The VAT standard-rated share is a modelling judgement (modelling and other) unless the label names an economic cause of the change. Saying what the share is *of* is not a cause. | Economic determinant (it depends on the consumption mix) | "Standard rated share", "SRS of consumer spending" (modelling) versus "Oil price effect on standard rated share" (economic) |
| B3 Broad heads | A PMD head that covers more than one forecast series maps to the dominant series only if all its largest measures fall in that series; otherwise it maps to none. It is always flagged. | Split the head's measures by their descriptions (for example, stamp duty measures naming shares go to the shares series) | "Stamp duty" (property and shares) |

**Why it matters.** The label categories drive the E5 attribution shares ("what share of revisions came from new data, from the economy, from policy") and later the question of whether a revision's cause was visible in the text beforehand. The head mapping decides which tax forecast a policy costing is subtracted from when errors are policy-adjusted; E6 case scores use policy-adjusted errors.

**Decisions (Teo, 28 September 2026).** Every rule takes the choice column: A3 (calibration to outturn, flagged `mixed`), A4, A6, A7, A10, A11 and B3. Teo's notes as written: "A3 put mixed; A4 also the first choice; A6 I agree, also first choice; A7 one-offs are one-offs; rest are also default choices."

**Spot-check and clarification (Teo, 28 September 2026).** A blind check of 20 rows settled by agreement matched 19. The miss, "SRS of household consumption", showed that A11's "ties it to an economy variable" could be read two ways. A11 now says the label must name an economic *cause* of the change; "SRS of household consumption", "SRS of consumer spending" and "Standard rated share of consumer spending" are therefore modelling and other, marked reviewed in the crosswalk.

---

## 2. Attribution labels (model instructions)

### 2.1 Task

The OBR publishes tables that explain why its receipts forecast changed since the previous forecast. Each row of such a table is one cause, in the OBR's own words. You receive one row and must assign exactly one category from 2.3.

### 2.2 What you receive

- `label`: the row's wording.
- `section`: the heading the row sits under in the table (may be empty).
- `table_title`: the table title, forecast date and table number, e.g. "Non-SA income tax and NICs: changes since October (March 2025, T4.3)".
- `table_rows`: all rows of that table in order, without numbers, with the row to label marked `>>`, and totals, subtotals and group headings tagged. A group heading is a row whose value is the sum of the rows directly beneath it; code finds these from the numbers.
- `group_heading_above`: the group heading the row belongs to, if any (rule A2b).

### 2.3 Categories

Five causes:

1. **policy**: the effect of government decisions announced at this fiscal event. Includes scorecard and non-scorecard measures, direct and indirect effects of decisions, devolved administration decisions, and named measures listed under a government-decisions heading. Does *not* include re-estimates of measures announced at earlier events (rule A4).
2. **economic_determinants**: changes to the OBR's economy forecast that move the tax base. Earnings, wages and salaries, employment, self-employment income, household and government consumption, investment, company profits, property prices and transactions, equity prices, interest rates, exchange rates, oil and gas prices and production, inflation, GDP, population, productivity, hours worked, unemployment. Also generic labels: "economic determinants", "determinants", "market-derived assumptions", "tax base(s)".
3. **calibration_to_outturn**: new data on receipts or the economy that arrived since the previous forecast. "Outturn", "receipts data", "latest receipts", "liabilities data", in-year surpluses or shortfalls ("January and February receipts surplus"), and the receipts of a completed year ("Lower 2016-17 PAYE and NIC1 receipts").
4. **classification_one_offs**: statistical classification or accounting-treatment changes (reclassifications, new items brought into the receipts measure) and identifiable one-off items (rule A7).
5. **modelling_other**: model changes, forecaster judgement, recostings of earlier measures (A4), effective tax rates (A6), error-correction terms, PSNB-neutral items (A10), the standard-rated share (A11), residuals, and anything that is none of the above.

Two structural categories, used when the row is not a cause at all:

6. **underlying_unsplit**: the row is the whole non-policy change in one number ("Underlying forecast differences").
7. **by_tax_head**: the row is one tax in a split of the change *by tax*, not by cause (typically under a "By tax head" section, or a table whose rows are all taxes).

### 2.4 Rules, applied in this order

- **A1 Section first.** Under a government-decisions heading ("Effect of Government decisions", "Changes due to Government decisions", "Direct effect of Government decisions ..."), the row is policy unless A4 applies. Under "(by economic determinant)" or "Economic determinants", it is economic_determinants unless the label clearly names something else. Under "By tax head", it is by_tax_head. Under an "Underlying ..." heading or no heading, the label decides.
- **A2 Group headings.** If the row is a group heading (its value is the sum of the rows directly beneath it), give it the category most of those rows share; if they are evenly mixed, modelling_other.
- **A2b Rows inside a group.** A row that belongs to a group heading (it is one of the rows the heading totals) takes the group heading as its section for A1 and A8. Example: in "SA income tax: changes since March" (November 2025, T4.5), "Changes to SA income tax rates", "Coding out measure" and "Other" sum to "Direct effect of Government decisions", so all three are policy. (Added 28 September 2026 after the pilot; it applies A1 to headings the OBR writes as subtotal rows.)
- **A3 Data beats modelling.** A label mentioning outturn, receipts data, liabilities data or a named past year's receipts is calibration_to_outturn, even when it also says "modelling" or "other". Set `mixed` to true.
- **A4 Recostings.** "Recosting", "re-costing", "revised ... costing", "costing revisions": modelling_other, even under a policy heading.
- **A5 Economy named.** A label naming an economy variable from 2.3 item 2 is economic_determinants. If it combines determinants with modelling or other ("Other determinants and modelling", "Other changes (including determinants)"), it is modelling_other with `mixed` true.
- **A6 Effective tax rates.** "Effective tax rate", "ETR", "pre-measures factors": modelling_other. "Tax base": economic_determinants.
- **A7 One-offs.** Litigation, fines, one-off dividends, one-off compensation or repayment schemes: classification_one_offs (unless A4 applies: a revised costing of a one-off measure is a recosting).
- **A8 "Other".** "Other", "Residual", "Other factors", "Other changes" take the category of their section: policy under a government-decisions heading, economic_determinants under a determinants heading, otherwise modelling_other.
- **A9 A tax named without a cause.** A label that only names a tax or receipts stream ("VAT", "Life insurance", "Self assessment") is by_tax_head when the table or section splits by tax; inside a cause section it is modelling_other.
- **A10 PSNB-neutral.** modelling_other, with `psnb_neutral` true.
- **A11 Standard-rated share.** modelling_other, unless the label names an economic cause of the change ("Oil price effect on standard rated share" is economic_determinants). A label that only says what the share is of ("SRS of consumer spending", "SRS of household consumption") is modelling_other.

### 2.5 Worked examples

| Label | Section | Category | Rule |
|---|---|---|---|
| Average earnings | (by economic determinant) | economic_determinants | A1 |
| Scorecard measures | Effect of Government decisions | policy | A1 |
| Indirect effects of Government decisions | (none) | policy | 2.3 item 1 |
| Recostings of previous measures | (by other category) | modelling_other | A4 |
| Income and expenditure | Underlying OBR forecast changes, value = sum of Average earnings ... Other beneath it | economic_determinants | A2 |
| Other assumptions | Underlying OBR forecast changes, group heading over "IT and NICs receipts and modelling" ... "Other judgements and modelling" | calibration_to_outturn | A2, A3 (most rows beneath mention receipts or outturn) |
| Outturn PAYE receipts | (by other category) | calibration_to_outturn | A3 |
| Latest receipts | (none) | calibration_to_outturn | A3 |
| CGT outturn and modelling | Underlying OBR forecast changes | calibration_to_outturn, mixed | A3 |
| Pre-measures effective tax rate | (none), in a table with "Forecast changes to earnings and employment" | modelling_other | A6 |
| Key tax bases | Underlying forecast changes since March 2020 | economic_determinants | A5, A6 |
| Exchange rates | Underlying OBR forecast changes | economic_determinants | A5 |
| Error correction | (none) | modelling_other | 2.3 item 5 |
| Litigation cases | (none) | classification_one_offs | A7 |
| Underlying forecast differences | By policy and forecast differences | underlying_unsplit | 2.3 item 6 |
| Value added tax | By tax head | by_tax_head | A1 |
| Other | Effect of Government decisions | policy | A8 |
| Other | Underlying OBR forecast changes | modelling_other | A8 |

### 2.6 Answer format

Return JSON only:

```json
{"category": "<one of the 7>", "second": "<next most likely, or null>",
 "p_first": 0.0, "p_second": 0.0, "mixed": false, "psnb_neutral": false,
 "rule": "<rule id or definition used, e.g. A3>", "reason": "<one sentence>"}
```

`p_first` and `p_second` are your probabilities for the two categories. Use a low `p_first` when the label is unclear even with the context; do not guess confidently.

Jev does not write text: it receives section 2.3 as a Choice question and returns a probability for every category, plus yes/no answers to narrow tests (rules A3–A11) from which code applies the rule order (`src/fvd/jev_label.py`). This JSON format is for generative models.

---

## 3. Tax and spending heads (model instructions)

### 3.1 Task

The OBR Policy Measures Database gives each costed policy measure a head (e.g. "Fuel duty", "Stamp duty", "Tax credits"). The dataset subtracts each measure's costing from one forecast series when it policy-adjusts errors. You receive one head and must choose the forecast series it belongs to, or none.

### 3.2 What you receive

- `head`: the head as the database writes it, and whether it is a tax or spending head.
- `measures`: the number of measures and the largest few, by value.
- `options`: the list of forecast series (code and name) of the same type, plus `(none)`.

### 3.3 Rules

- **B1 Same thing.** If a series covers exactly what the head covers, choose it.
- **B2 Narrower head.** If the head is part of what one series covers (a surcharge, a sub-levy, a component the OBR forecasts inside that series), choose that series. Example: a surcharge on bank profits is part of onshore corporation tax.
- **B3 Broader head.** If the head covers more than one series, choose the dominant series only if all its largest measures fall in it, and set `flag` to true; otherwise `(none)`, flagged.
- **B4 No series.** If no series covers the head, `(none)`. The measure then enters only the aggregate policy adjustment.
- **B5 Spending.** Spending heads follow the same rules against the spending series. Benefits and tax credits belong to welfare spending unless a finer series fits.

### 3.4 Answer format

```json
{"series": "<code or (none)>", "second": "<code, (none) or null>",
 "p_first": 0.0, "p_second": 0.0, "flag": false,
 "rule": "<B1-B5>", "reason": "<one sentence>"}
```

---

## 4. Fiscal events (deterministic, no model)

A PMD event maps to the OBR forecast published at that fiscal event. The check: the event's type and year (Budget, Autumn Statement, Spring Statement, Spring Forecast; year) must match a forecast in the vintage calendar published at that event, per the dates in `inventory/vintage_calendar`. Rows that match are settled; any that do not go to Teo with the candidate forecasts listed. Events before June 2010 are not checked, because the component forecasts start then.
