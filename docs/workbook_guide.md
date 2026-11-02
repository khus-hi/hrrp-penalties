# Workbook guide: `analysis/output/hrrp_chain_workbook.xlsx`

Build it with `python -m analysis.build_workbook`. Python only places the data. Every calculation is an Excel formula you can click and trace. **Yellow cells on `Inputs` are the only ones meant to be edited.** The cost inputs start blank on purpose, so no number in the workbook is invented.

## Flow
```
Inputs ──► Condition_Data (one row per hospital × condition)
             └─► Hospital_Data (one row per chain hospital)
                    ├─► Chain_Summary ◄── SEC_Financials (10-K line items)
                    ├─► Scenarios
                    └─► ROI
```

## Inputs
| Cell | What it is | Why it's an input |
|---|---|---|
| B3:B5 | Scenario cuts in excess readmissions (10/20/30%) | Your scenarios |
| B6 | Years in the CMS performance period (3) | FY2026 HRRP uses 07/2021 to 06/2024 discharges. This turns 3-year counts into a yearly figure |
| B9 | Chain for the ROI case | Dropdown |
| B10 | Cut the program achieves | Defaults to scenario 2 (`=B4`) |
| B11:B14 | Enrolment share, cost per patient, fixed cost, margin per avoided readmission | Your assumptions. Left blank deliberately |

## Condition_Data: the CMS formula, one condition at a time
Columns A–K are CMS data: penalty indicator, DRG payment ratio, ERR, peer-group median ERR, neutrality modifier, eligible discharges and expected readmission rate.

**Penalty term, baseline (column L)**
```
=IF(AND(E="Y", ISNUMBER(G), ISNUMBER(F)), F * MAX(G - H, 0), 0)
```
*How to say it in an interview:* "This is one piece of CMS's formula in 42 CFR 412.152. A condition adds to the penalty only if CMS flags it ('Y'). Its contribution is the share of the hospital's Medicare base DRG payments that come from that condition, times how far the hospital's ERR sits above its peer group's median. Below the median it contributes zero."

**Penalty term, scenario k (columns M–P)**
```
=IF(AND(E="Y", ...), F * MAX( IF(G>1, G - pct*(G-1), G) - H, 0), 0)
```
"'Excess readmissions' means readmissions above what CMS expects, which is the part of ERR above 1.0. A 20% cut shrinks that part by 20%: an ERR of 1.10 becomes 1.08. Then the same CMS term is re-applied. Hospitals already at or below expected (ERR ≤ 1) are unchanged."

**Avoided readmissions per year (column Q)**
```
= J / years * K/100 * MAX(G - 1, 0) * pct
```
"Discharges per year × expected readmission rate gives expected readmissions. Multiplying by (ERR − 1) gives the excess readmissions, and the cut % gives how many are avoided."

## Hospital_Data: from terms to dollars
| Column | Formula | Plain English |
|---|---|---|
| I: Est. penalty $ | `(1 − E) × F` | CMS's own factor × base DRG payments. This is the headline estimate |
| J: Recomputed factor | `MAX(0.97, 1 − NM × SUMIFS(terms for this CCN))` | Rebuilds CMS's factor from the per-condition terms, with the 3% floor (42 CFR 412.154) |
| K: Check | `E − J` | Should be about 0. The pipeline confirmed a match within 0.00005 for every hospital |
| L–O: Scenario factors | same as J with scenario terms | The factor if excess readmissions fall by the scenario % |
| P–T: Penalty $ | `(1 − factor) × F` | Dollars for the baseline and each scenario |

Scenarios use the **recomputed** baseline (P), so savings compare like with like.

## SEC_Financials
Values come straight from SEC companyfacts: the latest-filed 10-K value for each fiscal year, with the XBRL tag recorded next to each number.
- **Operating income used (L):** `=IF(ISNUMBER(F), F, IF(AND(ISNUMBER(H), ISNUMBER(J)), H + J, ""))`
  "If the company reports operating income, use it. If not, use EBIT: pre-tax income plus interest expense. EBIT is the standard stand-in for operating income, and column M says which basis was used."
- **Net income** uses `NetIncomeLoss` (attributable to the company, excluding noncontrolling interests) where the company tags it. Otherwise it uses the common-shareholder version, and failing that `ProfitLoss`, which **includes** noncontrolling interests. Column O shows which was used. The difference matters for HCA and Tenet, which have large joint-venture partners.
- **Read one-off years carefully:** a year with large gains on hospital or business sales (Tenet's 2024 operating income stands out in the history) makes the penalty look smaller relative to income than it usually is. Check the 10-K before quoting that year.

## Chain_Summary
| Column | Formula | Meaning |
|---|---|---|
| B | `COUNTIFS(system = chain)` | Chain hospitals in the HRRP file |
| D | `SUMIFS(est. penalty, system = chain)` | Total estimated FY2026 penalty |
| E | `MAXIFS(fiscal year, company = chain)` | Latest 10-K year available |
| F–H | `INDEX/MATCH` on company **and** year | Revenue, operating income and net income for that year |
| I–K | `penalty / F,G,H` | Penalty as a share of each measure |

The history block repeats the lookup for every year, plus operating margin (`operating income / revenue`), and compares the FY2026 penalty with each year's operating income.

## Scenarios
`Savings = baseline penalty − scenario penalty`, by chain, and `savings / latest operating income`.

What's held fixed, which is worth saying up front in an interview:
- **Peer medians and the neutrality modifier stay at FY2026 values.** In reality, if every hospital improved, medians would fall too, so a single chain's savings would be smaller.
- **Penalty base stays the same.** Payments are not inflated.
- **Timing lag.** HRRP looks back 2–3 years, so savings arrive with a delay.

## ROI
| Row | Formula | Meaning |
|---|---|---|
| Eligible discharges / yr | `SUMIFS(discharges, chain) / years` | Patients in the 6 HRRP conditions |
| Enrolled | `× enrolment share` | Who the program serves |
| Program cost | `fixed + enrolled × cost per patient` | Annual cost |
| Avoided readmissions | `SUMIFS(column Q, chain)` | From Condition_Data |
| HRRP penalty avoided | `baseline − ROI-case penalty` | From Hospital_Data P and T |
| Margin effect | `avoided × margin per readmission` | Usually **negative** under fee-for-service, because a readmission is also paid revenue |
| Net benefit | `penalty avoided + margin effect − cost` | |
| ROI | `net benefit / cost` | |
| Break-even cost per patient | `(penalty avoided + margin − fixed) / enrolled` | Highest per-patient cost that still breaks even |

**The honest interview point:** for a fee-for-service hospital, avoiding a readmission removes the penalty but also removes the payment for that readmission. A care-transitions program that pays off from the HRRP penalty alone can look worse once the margin effect is entered. That's why the margin input exists.
