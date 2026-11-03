-- The join funnel (qa.join_funnel) must behave like a funnel:
--   * 7 steps, numbered 1-7
--   * step 1 = every hospital in the CMS HRRP file (distinct CCNs in stg_hrrp_measures)
--   * no step has more hospitals than the step before it
--   * the last step = hospitals in mart_hospital that have every piece
-- Returns one row per broken rule.
WITH f AS (SELECT * FROM {{ ref('qa_join_funnel') }}),
hrrp AS (SELECT count(DISTINCT ccn) AS n FROM {{ ref('stg_hrrp_measures') }} WHERE ccn IS NOT NULL),
complete AS (
    SELECT count(*) AS n FROM {{ ref('mart_hospital') }}
    WHERE n_conditions_with_err > 0 AND payment_adjustment_factor IS NOT NULL
      AND hospital_type IS NOT NULL AND medicare_base_drg_payments IS NOT NULL
      AND county_fips IS NOT NULL AND county_median_household_income IS NOT NULL
      AND county_median_age IS NOT NULL
)
SELECT 'funnel does not have steps 1-7' AS problem
FROM f HAVING count(*) <> 7 OR min(step_order) <> 1 OR max(step_order) <> 7
UNION ALL
SELECT 'step 1 is not every hospital in the HRRP file'
FROM f, hrrp WHERE f.step_order = 1 AND f.hospitals_remaining <> hrrp.n
UNION ALL
SELECT 'step ' || step_order || ' has more hospitals than the step before'
FROM f WHERE dropped_here < 0
UNION ALL
SELECT 'last step does not equal the complete hospitals in mart_hospital'
FROM f, complete WHERE f.step_order = 7 AND f.hospitals_remaining <> complete.n
