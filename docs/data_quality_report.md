# Data-quality report

_Generated 2026-11-02 18:00 UTC by `python -m models.build` from the files in data/raw/ (see data/raw/manifest.json for exact downloads)._

## Join funnel (cumulative)

| step_order | step | hospitals_remaining | dropped_here |
|---|---|---|---|
| 1 | In CMS FY2026 HRRP hospital file | 3055 |  |
| 2 | + at least one non-suppressed ERR | 2833 | 222 |
| 3 | + payment adjustment factor (IPPS supplemental file) | 2791 | 42 |
| 4 | + in Hospital General Information | 2776 | 15 |
| 5 | + cost report with Medicare base DRG payments | 2759 | 17 |
| 6 | + county FIPS found | 2752 | 7 |
| 7 | + ACS income and age for that county | 2733 | 19 |


## Coverage by source (independent)

| source | matched | total | pct |
|---|---|---|---|
| payment adjustment factor (supplemental) | 2937 | 3055 | 96.1 |
| payment adjustment factor (Table 15) | 2937 | 3055 | 96.1 |
| General Information | 3035 | 3055 | 99.3 |
| cost report: any report | 3034 | 3055 | 99.3 |
| cost report: Medicare base DRG payments | 3002 | 3055 | 98.3 |
| star rating | 2654 | 3055 | 86.9 |
| county FIPS | 3028 | 3055 | 99.1 |
| ACS county income | 3008 | 3055 | 98.5 |
| one of the four public chains | 281 | 3055 | 9.2 |


## Unmatched CCNs by reason

| reason | ccns |
|---|---|
| not in IPPS supplemental file (no adjustment factor) | 118 |
| cost report has no Medicare base DRG amount | 32 |
| no county FIPS (name and ZIP both failed) | 27 |
| no cost report in HCRIS file | 21 |
| not in Hospital General Information | 20 |
| county FIPS found but not in ACS 2024 (e.g. old CT county) | 20 |
| in IPPS supplemental file but not in HRRP hospital file | 8 |


Full list: `SELECT * FROM qa.unmatched_ccns`.

## Suppressed / missing HRRP values by condition

| condition | rows | err_reported | err_missing | err_na | readmissions_too_few | discharges_missing | footnote_codes_seen |
|---|---|---|---|---|---|---|---|
| ami | 3055 | 1736 | 1319 | 1319 | 496 | 1748 | 1, 7, 5, 29 |
| cabg | 3055 | 878 | 2177 | 2177 | 515 | 2674 | 1, 7, 29, 5 |
| copd | 3055 | 2323 | 732 | 732 | 778 | 1503 | 5, 29, 7, 1 |
| hf | 3055 | 2621 | 434 | 434 | 305 | 731 | 29, 1, 7, 5 |
| pn | 3055 | 2715 | 340 | 340 | 395 | 727 | 5, 1, 7, 29 |
| tha_tka | 3055 | 1447 | 1608 | 1608 | 1194 | 2705 | 1, 7, 5, 29 |


## Text values turned into NULL

| field | raw_value | n |
|---|---|---|
| hrrp err | N/A | 6610 |
| star rating | Not Available | 2245 |


## IPPS spreadsheet columns not found (left NULL)

| source | field |
|---|---|
| hrrp_table15 | payment_reduction_pct |
| hrrp_table15 | dual_proportion |
| hrrp_table15 | peer_group |
| hrrp_table15 | neutrality_modifier |


## Parent-system crosswalk (check against each 10-K)

| parent_system | hrrp_hospitals_matched | with_stake_under_100pct |
|---|---|---|
| Community Health Systems | 50 | 0 |
| HCA Healthcare | 145 | 3 |
| Tenet Healthcare | 61 | 7 |
| Universal Health Services | 25 | 0 |


| system | owner_org_name | ccns |
|---|---|---|
| Community Health Systems | COMMUNITY HEALTH SYSTEMS INC | 87 |
| HCA Healthcare | HCA HEALTHCARE INC | 264 |
| HCA Healthcare | HCA INC | 262 |
| HCA Healthcare | HCA HEALTHCARE, INC | 3 |
| Tenet Healthcare | TENET HEALTHCARE CORPORATION | 86 |
| Tenet Healthcare | TENET HEALTHSYSTEM MEDICAL, INC. | 11 |
| Universal Health Services | UNIVERSAL HEALTH SERVICES INC | 169 |
| Universal Health Services | UNIVERSAL HEALTH SERVICES | 1 |


## Cost report fiscal-year ends (federal FY2026 = Oct 2025 to Sep 2026)

| cost_report_fy_end_year | hospitals |
|---|---|
| 2024 | 1825 |
| 2025 | 1209 |
|  | 21 |


## Assertions (0 failing)

| test | failing_rows | result |
|---|---|---|
| mart has one row per CCN | 0 | pass |
| every HRRP measure_name maps to a condition | 0 | pass |
| every hospital has at most 6 HRRP rows | 0 | pass |
| CCN in HRRP file is 6 characters | 0 | pass |
| supplemental file has one row per CCN | 0 | pass |
| General Info has one row per CCN | 0 | pass |
| payment adjustment factor between 0.97 and 1.0 (42 CFR 412.154 floor) | 0 | pass |
| supplemental factor equals Table 15 factor | 0 | pass |
| ERR values are positive | 0 | pass |
| Medicare base DRG payments are not negative | 0 | pass |
| county FIPS is 5 digits | 0 | pass |
| ACS median income has no Census sentinel codes left | 0 | pass |
| recomputed factor (1 - NM x sum of ratio x excess ERR, floor 0.97) matches CMS | 0 | pass |
| condition shares sum to 1 for every penalized hospital | 0 | pass |
| condition dollars add up to hospital dollars | 0 | pass |
| no penalty above 3% of the base | 0 | pass |
| unpenalized hospitals (factor = 1) have $0 | 0 | pass |
