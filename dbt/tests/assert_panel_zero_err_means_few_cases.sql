{{ config(severity='warn') }}
-- stg_hrrp_supplemental_history reads an ERR of 0 as "no ERR" (the FY2016-FY2017 files
-- use 0 there). That is only right if those hospitals had too few cases for CMS to score
-- them (fewer than 25). Rows returned: no ERR, yet 25+ cases in a year whose file has
-- case counts. If this returns rows, 0 meant something else and the rule must change.
SELECT ccn, fiscal_year, condition, eligible_discharges
FROM {{ ref('fct_hospital_condition_year') }}
WHERE err IS NULL AND eligible_discharges >= 25 AND fiscal_year < 2019
