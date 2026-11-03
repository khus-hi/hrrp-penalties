{{ config(severity='error') }}
-- The panel's grain: exactly one row per hospital x condition x payment year.
-- A duplicate would double-count a hospital in every per-year total.
SELECT ccn, condition, fiscal_year, count(*) AS n_rows
FROM {{ ref('fct_hospital_condition_year') }}
GROUP BY ALL
HAVING count(*) > 1
