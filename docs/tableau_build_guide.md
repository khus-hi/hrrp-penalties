# Tableau Public dashboard: build guide

The dashboard answers five questions for a hospital quality or finance team:

1. **National map:** where are HRRP penalties heaviest?
2. **Hospital lookup:** how does one hospital compare with peers of the same size and teaching status?
3. **Condition drill-down:** which conditions drive the dollars, and which hospitals drive each condition?
4. **Massachusetts:** what is the penalty and its drivers for every MA hospital?
5. **Parent system:** how much do HRRP penalties matter to HCA, Tenet, CHS and UHS?

Everything is free. You need Tableau Public (desktop app, free account) and the three CSVs below.

---

## 1. Make the export tables

```bash
python -m dashboard.export_tableau
```

This writes three files to `dashboard/tableau_exports/`. Each file has exactly one grain, so nothing is double-counted.

| File | One row per | Key columns |
|---|---|---|
| `hospitals.csv` | HRRP hospital (all ~3,055, including those without a $ estimate) | `ccn`, `hospital_label`, `state`, `zip5`, `county_fips`, `ownership_group`, `parent_system`, `beds`, `bed_size_band`, `teaching_status`, `payment_adjustment_factor`, `is_penalized`, `at_3pct_cap`, `est_annual_base_drg_payments`, `est_penalty_usd`, `estimate_quality`, `penalty_drivers`, `penalty_usd_<condition>` |
| `hospital_conditions.csv` | hospital × condition (6 per hospital) | `ccn`, `condition`, `penalty_indicator`, `err`, `peer_median_err`, `err_minus_peer_median`, `drg_payment_ratio`, `eligible_discharges`, `share_of_penalty`, `condition_penalty_usd` |
| `system_financials.csv` | chain × fiscal year (last 5 10-Ks) | `parent_system`, `fiscal_year`, `revenue`, `operating_income_used`, `operating_income_basis`, `net_income` |

The script checks that `ccn` is unique in `hospitals.csv`, that there is one row per hospital and condition, and that the condition dollars add back to the hospital total.

**Interview line:** "I exported tidy tables at their natural grain and let Tableau relate them, instead of one wide flat file. A flat file would repeat each hospital's penalty six times, once per condition, and any SUM would be six times too big."

---

## 2. Connect the data in Tableau Public

1. Open Tableau Public. Under **Connect**, choose **Text file** and pick `hospitals.csv`.
2. **Fix data types before anything else.** Tableau guesses that `ccn`, `zip5` and `county_fips` are numbers, which drops leading zeros (CCN `010001` becomes `10001`). Click the `#` icon above each of these three columns and choose **String**.
3. Set geographic roles. Click the globe or `Abc` icon:
   - `state` → **Geographic Role → State/Province**
   - `zip5` → **Geographic Role → ZIP Code/Postcode**
4. Drag `hospital_conditions.csv` (from the left panel, under Files) onto the canvas next to `hospitals`. Tableau draws a **relationship** (the "noodle"). Set it to `Ccn = Ccn`. Fix `ccn` to String in this table too.
5. Drag `system_financials.csv` onto the canvas and relate it to `hospitals` on `Parent System = Parent System`.
6. Field names: Tableau usually displays `est_penalty_usd` as **Est Penalty Usd**. The formulas below use those display names. If yours shows the raw names, type those instead.

**Interview line:** "Relationships, not joins. Tableau aggregates each table at its own level of detail before combining them. So chain-level 10-K income and hospital-level penalties can share a view without the financials repeating once per hospital."

---

## 3. Parameter

**Selected Hospital**: right-click in the Data pane → **Create Parameter**.
- Data type: String
- Allowable values: **List**, then **When workbook opens → Hospital Label**. This keeps the list current when you refresh the data.
- Current value: any hospital, e.g. one in Boston.

Right-click the parameter → **Show Parameter**. It becomes a searchable dropdown on the dashboard.

---

## 4. Calculated fields

Create each one with **Analysis → Create Calculated Field**. Names in brackets are what other formulas refer to. The "Why" column is your interview explanation.

### Penalty measures

| Name | Formula | Why |
|---|---|---|
| **Has $ Estimate** | `NOT ISNULL([Est Penalty Usd])` | Some hospitals have a CMS factor but no usable cost report. They stay on the map but out of dollar ratios. |
| **Payment Reduction %** | `1 - [Payment Adjustment Factor]` | CMS's factor 0.9950 means a 0.50% cut to every Medicare base DRG payment. Row level, for one hospital. |
| **Penalty % of Base (weighted)** | `SUM(IF [Has $ Estimate] THEN [Est Penalty Usd] END) / SUM(IF [Has $ Estimate] THEN [Est Annual Base Drg Payments] END)` | The dollar-weighted rate for a group (a state, a chain). Averaging hospital percentages would let a 25-bed hospital count as much as a 900-bed one. |
| **Hospitals in HRRP Payment File** | `COUNTD(IF NOT ISNULL([Payment Adjustment Factor]) THEN [Ccn] END)` | Denominator. Excludes Maryland (waiver) and others with no factor. |
| **Penalized Hospitals** | `COUNTD(IF [Is Penalized] THEN [Ccn] END)` | Hospitals with factor < 1. |
| **% Penalized** | `[Penalized Hospitals] / [Hospitals in HRRP Payment File]` | |
| **Penalty per Hospital** | `SUM([Est Penalty Usd]) / COUNTD(IF [Has $ Estimate] THEN [Ccn] END)` | Mean dollars among hospitals with an estimate. |
| **Estimate Status** | `IF ISNULL([Payment Adjustment Factor]) THEN "No CMS factor" ELSEIF NOT [Has $ Estimate] THEN "Factor, no $ base" ELSEIF [Is Penalized] THEN "Penalized" ELSE "Not penalized" END` | One color legend that explains missing values instead of hiding them. |

### Peer comparison (same size band and teaching status)

| Name | Formula | Why |
|---|---|---|
| **Peer Group** | `[Bed Size Band] + " | " + [Teaching Status]` | 4 size bands × teaching/non-teaching. The bands are a presentation choice, not a CMS definition. CMS's own peer groups are dual-eligible quintiles, which are in `Cms Dual Peer Group` if you want a second comparison. |
| **Is Selected Hospital** | `[Hospital Label] = [Selected Hospital]` | TRUE for the one hospital picked in the parameter. |
| **Selected Peer Group** | `{ FIXED : MAX(IF [Is Selected Hospital] THEN [Peer Group] END) }` | A FIXED LOD with no dimension returns one value for the whole table: the selected hospital's group, copied to every row. That lets you filter everyone else to that group. |
| **In Selected Peer Group** | `[Peer Group] = [Selected Peer Group]` | Filter = TRUE. |
| **Peer Median Reduction %** | `{ FIXED [Peer Group] : MEDIAN(IF NOT ISNULL([Payment Adjustment Factor]) THEN [Payment Reduction %] END) }` | Median, not mean, because most hospitals sit near 0% and a few near 3%. |
| **Peer Median Penalty $** | `{ FIXED [Peer Group] : MEDIAN([Est Penalty Usd]) }` | |
| **Peer Hospitals** | `{ FIXED [Peer Group] : COUNTD([Ccn]) }` | Show it, so a viewer knows how big the comparison group is. |
| **Gap vs Peer Median (pp)** | `(AVG([Payment Reduction %]) - AVG([Peer Median Reduction %])) * 100` | Percentage points above or below the peer median. |
| **Percentile in Peer Group** | `RANK_PERCENTILE(AVG([Payment Reduction %]), 'asc')` | Table calculation. Set **Compute Using → Ccn** on the sheet where it is used. 0.90 means a larger cut than 90% of peers. |

### Condition drill-down (fields from `hospital_conditions`)

| Name | Formula | Why |
|---|---|---|
| **Counts Toward Penalty** | `[Penalty Indicator] = "Y"` | CMS only counts a condition when it flags it Y (enough cases, ERR above the peer median). |
| **ERR Above Peer Median** | `[Err] > [Peer Median Err]` | |
| **Condition Share of National $** | `SUM([Condition Penalty Usd]) / TOTAL(SUM([Condition Penalty Usd]))` | Table calc: each condition's slice of all dollars. |
| **ERR Gap** | `AVG([Err Minus Peer Median])` | How far above the peer median a hospital sits. That gap times the DRG payment ratio is that condition's term in CMS's formula. |

### Parent system (uses `system_financials`)

| Name | Formula | Why |
|---|---|---|
| **Latest Fiscal Year** | `{ FIXED [Parent System (System Financials)] : MAX([Fiscal Year]) }` | Latest 10-K per chain. |
| **Latest Operating Income** | `SUM(IF [Fiscal Year] = [Latest Fiscal Year] THEN [Operating Income Used] END)` | HCA's figure is EBIT because HCA does not tag operating income. `Operating Income Basis` says which. |
| **Latest Revenue** | `SUM(IF [Fiscal Year] = [Latest Fiscal Year] THEN [Revenue] END)` | |
| **Penalty % of Operating Income** | `SUM([Est Penalty Usd]) / [Latest Operating Income]` | Mixes two related tables. Tableau sums penalties over the chain's hospitals and takes the chain's one income figure, so neither is repeated. |
| **Is Public Chain** | `[Parent System] <> "Not one of the four chains"` | Filter for the system view. |

---

## 5. Build the sheets

Make each sheet with **Worksheet → New Worksheet** and rename its tab.

### Sheet `Map – States`
1. Double-click **State**. Tableau draws a map. On the Marks card, change the mark type to **Map** (filled).
2. Drag **Penalty % of Base (weighted)** to Color. Edit colors → sequential (e.g. *Orange* or *Blue*). Under **Advanced**, start the range at 0.
3. Drag **SUM(Est Penalty Usd)**, **Penalized Hospitals**, **% Penalized** and **Hospitals in HRRP Payment File** to Tooltip. Format dollars as Currency (custom), Millions, 1 decimal.
4. Maryland shows as missing. Add a caption: "Maryland hospitals are exempt from HRRP under the state's all-payer waiver."

### Sheet `Map – Hospitals`
1. Double-click **Zip5**, which has the ZIP Code role. Mark type **Circle**.
2. **Est Penalty Usd** → Size. **Estimate Status** → Color, with Penalized in a strong color, Not penalized grey, and the two "no" statuses light grey.
3. **Hospital Label** → Detail. Add **Penalty Drivers** and **Payment Reduction %** to Tooltip.
4. Note in the caption that points sit at the ZIP's centre. CMS General Information has no street-level coordinates.

### Sheet `Top Hospitals`
Rows: **Hospital Label**. Columns: **SUM(Est Penalty Usd)**. Sort descending. Add **Penalty Drivers** to Label or Tooltip. Filter **Has $ Estimate** = True. Use **Top N** (Filter on Hospital Label → Top → by field → Top 15 by SUM(Est Penalty Usd)).

### Sheet `Lookup – Card` (selected hospital)
1. Filter **Is Selected Hospital** = True.
2. Use Measure Names / Measure Values as Text: **Payment Adjustment Factor**, **Payment Reduction %**, **SUM(Est Penalty Usd)**, **Peer Median Reduction %**, **Gap vs Peer Median (pp)**, **Peer Hospitals**.
3. Put **Hospital Label**, **Peer Group**, **Parent System** and **Ownership Group** on Rows, or in the title as `<Hospital Label>`.

### Sheet `Lookup – Peer Strip`
1. Filter **In Selected Peer Group** = True and **Has $ Estimate** = True.
2. Columns: **AVG(Payment Reduction %)**. Detail: **Ccn**, **Hospital Label**. Mark type **Circle**. Add jitter by putting `INDEX() % 20` on Rows (set Compute Using → Ccn), or simply leave as a strip.
3. **Is Selected Hospital** → Color (True = bold color, False = light grey) and → Size (True larger).
4. Add a reference line: Analytics pane → **Reference Line**, Per Table, **Median** of AVG(Payment Reduction %), labelled "Peer median".
5. Tooltip: **Percentile in Peer Group** (Compute Using → Ccn).

### Sheet `Lookup – Conditions` (selected hospital vs CMS peer median)
1. Filter **Is Selected Hospital** = True. This field comes from `hospitals`, and the relationship filters `hospital_conditions` too.
2. Rows: **Condition**. Columns: **AVG(Err)** as Circle. Add **AVG(Peer Median Err)** as a second measure on a synchronized **dual axis**, shown as a vertical line mark (Gantt Bar works).
3. **Counts Toward Penalty** → Color. Tooltip: **Eligible Discharges**, **Drg Payment Ratio**, **SUM(Condition Penalty Usd)**.
4. Caption: "CMS compares each condition with the median of hospitals with a similar share of dual-eligible patients (its peer group), not with the size/teaching peers above."

### Sheet `Conditions – National`
Rows: **Condition**. Columns: **SUM(Condition Penalty Usd)**. Sort descending. Label: **Condition Share of National $**.

### Sheet `Conditions – Hospitals`
Rows: **Hospital Label**. Columns: **SUM(Condition Penalty Usd)**, Top 20. Color: **AVG(Err Minus Peer Median)**. This sheet will be filtered by a click on `Conditions – National`.

### Sheet `Conditions – ERR Scatter`
Columns: **AVG(Drg Payment Ratio)**. Rows: **AVG(Err Minus Peer Median)**. Detail: **Ccn**. Size: **SUM(Condition Penalty Usd)**. Filter **Counts Toward Penalty** = True. This shows the formula in a picture: dollars grow with both how far above the median a hospital is (y) and how much of its Medicare payment comes from that condition (x).

### Sheet `MA – Table`
1. Filter **State** = MA (right-click the filter → **Show Filter** if you'd like to reuse this as "any state" later).
2. Rows: **Hospital Label**, **Parent System**, **Teaching Status**. Measure Values: **Payment Adjustment Factor**, **SUM(Est Penalty Usd)**, **Penalty Drivers** (as a Row dimension if you want text). Sort by penalty descending.

### Sheet `MA – Condition Mix`
Filter **State** = MA. Rows: **Hospital Label** (Top 15 by penalty). Columns: **SUM(Condition Penalty Usd)**. Color: **Condition**. Stacked bars show each hospital's driver mix at a glance.

### Sheet `MA – Map`
Duplicate `Map – Hospitals` and filter **State** = MA.

### Sheet `System – Summary`
1. Filter **Is Public Chain** = True.
2. Rows: **Parent System**. Text table with **Hospitals in HRRP Payment File**, **% Penalized**, **SUM(Est Penalty Usd)**, **Penalty per Hospital**, **Penalty % of Base (weighted)**, **Latest Operating Income**, **Penalty % of Operating Income**, **Operating Income Basis** (from `system_financials`; put it on Rows or Detail).

### Sheet `System – vs National`
Duplicate `System – Summary` and remove the Is Public Chain filter. The "Not one of the four chains" row is the benchmark for everyone else. Show a bar of **Penalty % of Base (weighted)** and **% Penalized** for all five rows.

### Sheet `System – Conditions`
Filter **Is Public Chain** = True. Columns: **Parent System**. Rows: **Condition**. Color/Label: percent of total of **SUM(Condition Penalty Usd)** (Quick Table Calculation → Percent of Total → Compute Using Table Down). This shows each chain's driver mix.

### Sheet `System – Financial History`
From `system_financials`: Columns **Fiscal Year** (discrete), Rows **Operating Income Used** and **Revenue**, Color **Parent System**. Tooltip: **Operating Income Basis**. Caption: one-off gains (Tenet 2024) inflate some years.

---

## 6. Assemble the dashboards

**Dashboard → New Dashboard.** Set Size → **Fixed, 1200 × 900** (Tableau Public renders fixed sizes most reliably). Build five dashboards:

| Dashboard | Sheets | Interactivity |
|---|---|---|
| **1 National** | `Map – States` (top), `Map – Hospitals`, `Top Hospitals` | Dashboard → Actions → **Add Action → Filter**: source `Map – States`, target `Map – Hospitals` and `Top Hospitals`, run on **Select**, clearing shows all values. |
| **2 Hospital Lookup** | `Lookup – Card`, `Lookup – Peer Strip`, `Lookup – Conditions` | Show the **Selected Hospital** parameter (dropdown with search). Optional: **Change Parameter** action from `Top Hospitals` so clicking a hospital on dashboard 1 updates the lookup. |
| **3 Conditions** | `Conditions – National`, `Conditions – Hospitals`, `Conditions – ERR Scatter` | Filter action: source `Conditions – National`, targets the other two, on Select. |
| **4 Massachusetts** | `MA – Map`, `MA – Table`, `MA – Condition Mix` | Highlight action on Hospital Label across the three. |
| **5 Parent Systems** | `System – Summary`, `System – vs National`, `System – Conditions`, `System – Financial History` | Filter action on Parent System. |

Add navigation: drag **Navigation** objects (Objects pane → Navigation) onto each dashboard, one button per dashboard, so a viewer can move between them. Put a short text box at the top of each dashboard with the one-sentence takeaway, and a footer: "Source: CMS FY2026 HRRP, CMS cost reports, SEC EDGAR. Dollar figures are estimates; see github.com/khus-hi/hrrp-penalties."

Optional: **Story → New Story** with the five dashboards as story points, if you prefer a guided walk-through.

---

## 7. Publish

1. **File → Save to Tableau Public As…** and sign in to your free account. Tableau Public saves the data as an extract inside the workbook automatically.
2. Anything published to Tableau Public is public. That's fine here: every input is public government or SEC data.
3. On your Tableau Public profile, open the viz → **Settings** (gear) → turn on "Allow others to download" if you want recruiters to see the calculated fields.
4. When the data changes, rerun `python -m dashboard.export_tableau`, open the workbook in Tableau Public, **Data → Refresh**, and save again.

---

## 8. Caveats to state on the dashboard (and in interviews)

- **Dollars are estimates.** CMS's factor × each hospital's latest cost-report base DRG payments (2024-25 reports), not FY2026 actual claims. See `docs/penalty_method.md`.
- **Maryland is exempt** (all-payer waiver), so it is blank on the map, not zero.
- **Size/teaching peers are my grouping**, for a like-for-like comparison. CMS's penalty compares hospitals within dual-eligible quintiles, which is why the condition view uses CMS's peer median.
- **Chain mapping** reflects today's CMS ownership records, matched by owner name.
- **10-K income is company-wide** (all payers, all facilities). The penalty is Medicare inpatient only, so the ratio shows scale, not a share of Medicare profit.
