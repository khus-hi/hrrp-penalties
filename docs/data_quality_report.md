# Data-quality report

_Generated 2026-11-03 15:08 UTC by `python -m models.build` (dbt build) from the files in data/raw/ (see data/raw/manifest.json for exact downloads)._

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
| county FIPS found but not in ACS 2024 (e.g. old CT county) | 20 |
| not in Hospital General Information | 20 |
| in IPPS supplemental file but not in HRRP hospital file | 8 |


Full list: `SELECT * FROM qa.unmatched_ccns`.

## Suppressed / missing HRRP values by condition

| condition | rows | err_reported | err_missing | err_na | readmissions_too_few | discharges_missing | footnote_codes_seen |
|---|---|---|---|---|---|---|---|
| ami | 3055 | 1736 | 1319 | 1319 | 496 | 1748 | 1, 29, 5, 7 |
| cabg | 3055 | 878 | 2177 | 2177 | 515 | 2674 | 1, 29, 5, 7 |
| copd | 3055 | 2323 | 732 | 732 | 778 | 1503 | 1, 29, 5, 7 |
| hf | 3055 | 2621 | 434 | 434 | 305 | 731 | 1, 29, 5, 7 |
| pn | 3055 | 2715 | 340 | 340 | 395 | 727 | 1, 29, 5, 7 |
| tha_tka | 3055 | 1447 | 1608 | 1608 | 1194 | 2705 | 1, 29, 5, 7 |


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


## Raw data freshness (`dbt source freshness`)

| source | last_loaded_utc | age_days | result |
|---|---|---|---|
| acs_county | 2026-11-03 15:08 | 0 | pass |
| hospital_all_owners | 2026-11-03 15:08 | 0 | pass |
| hospital_cost_report | 2026-11-03 15:08 | 0 | pass |
| hospital_enrollments | 2026-11-03 15:08 | 0 | pass |
| hospital_general_info | 2026-11-03 15:08 | 0 | pass |
| hrrp_hospital | 2026-11-03 15:08 | 0 | pass |
| hrrp_supplemental | 2026-11-03 15:08 | 0 | pass |
| hrrp_table15 | 2026-11-03 15:08 | 0 | pass |
| sec_facts | 2026-11-03 15:08 | 0 | pass |
| zcta_county_rel | 2026-11-03 15:08 | 0 | pass |


## Assertions: dbt tests (0 failing, 0 warnings, 72 tests)

Generic tests are defined next to each column in `dbt/models/*/_*.yml`; singular tests are `dbt/tests/*.sql`. Each test's dbt name is in `qa.assertions.dbt_test`; its failing rows are kept in the `qa_failures` schema (`cd dbt && dbt test --select <dbt_test>` re-runs one).

| test | models | failing_rows | result |
|---|---|---|---|
| accepted_values: int_hospital_county.county_match_method in 2 listed values | int_hospital_county | 0 | pass |
| accepted_values: mart_hospital.hospital_ownership in 10 listed values | mart_hospital | 0 | pass |
| accepted_values: mart_hospital_condition_penalty_share.condition in 6 listed values | mart_hospital_condition_penalty_share | 0 | pass |
| accepted_values: mart_hospital_penalty.estimate_quality in 5 listed values | mart_hospital_penalty | 0 | pass |
| accepted_values: stg_cost_report.medicare_base_drg_source in 2 listed values | stg_cost_report | 0 | pass |
| accepted_values: stg_hrrp_measures.condition in 6 listed values | stg_hrrp_measures | 0 | pass |
| accepted_values: system_owner_patterns.system in 4 listed values | system_owner_patterns | 0 | pass |
| condition dollars add up to hospital dollars | mart_hospital_condition_penalty, mart_hospital_penalty | 0 | pass |
| condition shares sum to 1 for every penalized hospital | mart_hospital_condition_penalty_share, stg_hrrp_supplemental | 0 | pass |
| every hospital has at most 6 HRRP rows | stg_hrrp_measures | 0 | pass |
| int_hospital_county.county_fips similar to '[0-9]{5}' | int_hospital_county | 0 | pass |
| join funnel has 7 steps, starts at every HRRP hospital, never grows, ends at the complete rows of mart.hospital | mart_hospital, qa_join_funnel, stg_hrrp_measures | 0 | pass |
| mart_hospital.county_fips similar to '[0-9]{5}' | mart_hospital | 0 | pass |
| mart_hospital.medicare_base_drg_payments >= 0 | mart_hospital | 0 | pass |
| mart_hospital.payment_adjustment_factor between 0.97 and 1.0 | mart_hospital | 0 | pass |
| no penalty above 3% of the base | mart_hospital_penalty | 0 | pass |
| not_null: int_hospital_county.ccn | int_hospital_county | 0 | pass |
| not_null: int_hospital_system.ccn | int_hospital_system | 0 | pass |
| not_null: mart_hospital.ccn | mart_hospital | 0 | pass |
| not_null: mart_hospital.parent_system_conflict | mart_hospital | 0 | pass |
| not_null: mart_hospital_condition_penalty.ccn | mart_hospital_condition_penalty | 0 | pass |
| not_null: mart_hospital_condition_penalty_share.ccn | mart_hospital_condition_penalty_share | 0 | pass |
| not_null: mart_hospital_paf_recomputed.ccn | mart_hospital_paf_recomputed | 0 | pass |
| not_null: mart_hospital_penalty.ccn | mart_hospital_penalty | 0 | pass |
| not_null: mart_hospital_penalty.estimate_quality | mart_hospital_penalty | 0 | pass |
| not_null: mart_hospital_penalty_wide.ccn | mart_hospital_penalty_wide | 0 | pass |
| not_null: qa_join_funnel.step_order | qa_join_funnel | 0 | pass |
| not_null: state_fips.state_abbr | state_fips | 0 | pass |
| not_null: state_fips.state_fips | state_fips | 0 | pass |
| not_null: stg_acs_county.county_fips | stg_acs_county | 0 | pass |
| not_null: stg_cost_report.ccn | stg_cost_report | 0 | pass |
| not_null: stg_enrollment_ccn.ccn | stg_enrollment_ccn | 0 | pass |
| not_null: stg_enrollment_ccn.enrollment_id | stg_enrollment_ccn | 0 | pass |
| not_null: stg_general_info.ccn | stg_general_info | 0 | pass |
| not_null: stg_hrrp_measures.ccn | stg_hrrp_measures | 0 | pass |
| not_null: stg_hrrp_measures.condition | stg_hrrp_measures | 0 | pass |
| not_null: stg_hrrp_supplemental.ccn | stg_hrrp_supplemental | 0 | pass |
| not_null: stg_hrrp_table15.ccn | stg_hrrp_table15 | 0 | pass |
| not_null: system_owner_patterns.owner_name_pattern | system_owner_patterns | 0 | pass |
| not_null: system_owner_patterns.system | system_owner_patterns | 0 | pass |
| recomputed factor (1 - NM x sum of ratio x excess ERR, floor 0.97) matches CMS within 0.0001 for every hospital | mart_hospital_paf_recomputed, stg_hrrp_supplemental | 0 | pass |
| relationships: int_hospital_county.ccn -> stg_general_info.ccn | int_hospital_county, stg_general_info | 0 | pass |
| relationships: int_hospital_system.ccn -> stg_enrollment_ccn.ccn | int_hospital_system, stg_enrollment_ccn | 0 | pass |
| relationships: int_hospital_system.parent_system -> system_owner_patterns.system | int_hospital_system, system_owner_patterns | 0 | pass |
| relationships: int_owner_matches.ccn -> stg_enrollment_ccn.ccn | int_owner_matches, stg_enrollment_ccn | 0 | pass |
| relationships: mart_hospital.ccn -> stg_hrrp_measures.ccn | mart_hospital, stg_hrrp_measures | 0 | pass |
| relationships: mart_hospital.county_fips -> stg_acs_county.county_fips | mart_hospital, stg_acs_county | 0 | pass |
| relationships: mart_hospital.parent_system -> system_owner_patterns.system | mart_hospital, system_owner_patterns | 0 | pass |
| relationships: mart_hospital_condition_penalty.ccn -> mart_hospital_penalty.ccn | mart_hospital_condition_penalty, mart_hospital_penalty | 0 | pass |
| relationships: mart_hospital_condition_penalty_share.ccn -> stg_hrrp_supplemental.ccn | mart_hospital_condition_penalty_share, stg_hrrp_supplemental | 0 | pass |
| relationships: mart_hospital_paf_recomputed.ccn -> stg_hrrp_supplemental.ccn | mart_hospital_paf_recomputed, stg_hrrp_supplemental | 0 | pass |
| relationships: mart_hospital_penalty.ccn -> mart_hospital.ccn | mart_hospital, mart_hospital_penalty | 0 | pass |
| relationships: mart_hospital_penalty_wide.ccn -> mart_hospital_penalty.ccn | mart_hospital_penalty, mart_hospital_penalty_wide | 0 | pass |
| stg_acs_county.median_household_income >= 0 | stg_acs_county | 0 | pass |
| stg_hrrp_measures.err > 0 | stg_hrrp_measures | 0 | pass |
| supplemental factor equals Table 15 factor | mart_hospital | 0 | pass |
| unique: int_hospital_county.ccn | int_hospital_county | 0 | pass |
| unique: int_hospital_system.ccn | int_hospital_system | 0 | pass |
| unique: mart_hospital.ccn | mart_hospital | 0 | pass |
| unique: mart_hospital_paf_recomputed.ccn | mart_hospital_paf_recomputed | 0 | pass |
| unique: mart_hospital_penalty.ccn | mart_hospital_penalty | 0 | pass |
| unique: mart_hospital_penalty_wide.ccn | mart_hospital_penalty_wide | 0 | pass |
| unique: qa_join_funnel.step_order | qa_join_funnel | 0 | pass |
| unique: state_fips.state_abbr | state_fips | 0 | pass |
| unique: state_fips.state_fips | state_fips | 0 | pass |
| unique: stg_acs_county.county_fips | stg_acs_county | 0 | pass |
| unique: stg_cost_report.ccn | stg_cost_report | 0 | pass |
| unique: stg_general_info.ccn | stg_general_info | 0 | pass |
| unique: stg_hrrp_supplemental.ccn | stg_hrrp_supplemental | 0 | pass |
| unique: stg_hrrp_table15.ccn | stg_hrrp_table15 | 0 | pass |
| unique: system_owner_patterns.owner_name_pattern | system_owner_patterns | 0 | pass |
| unpenalized hospitals (factor = 1) have $0 | mart_hospital_penalty | 0 | pass |
