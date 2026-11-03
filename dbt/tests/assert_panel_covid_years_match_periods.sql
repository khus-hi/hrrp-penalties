-- The years flagged covid_2020_exclusion in seeds/hrrp_known_breaks.csv must be
-- exactly the years whose performance period reaches into the excluded
-- December 2019 - June 2020 window (FY2022 stops at December 1, 2019 because of it).
WITH flagged AS (
    SELECT DISTINCT fiscal_year FROM {{ ref('hrrp_known_breaks') }} WHERE break_type = 'covid_2020_exclusion'
),
by_period AS (
    SELECT fiscal_year FROM {{ ref('stg_hrrp_program_years') }}
    WHERE period_end >= DATE '2019-12-01' AND period_start <= DATE '2020-06-30'
)
SELECT coalesce(f.fiscal_year, p.fiscal_year) AS fiscal_year,
       f.fiscal_year IS NOT NULL AS flagged_in_seed,
       p.fiscal_year IS NOT NULL AS period_overlaps_2020_window
FROM flagged f
FULL OUTER JOIN by_period p USING (fiscal_year)
WHERE f.fiscal_year IS NULL OR p.fiscal_year IS NULL
