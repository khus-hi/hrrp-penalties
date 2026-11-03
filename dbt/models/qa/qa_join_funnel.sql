-- How many hospitals survive each join, applied cumulatively in a sensible order.
-- (mart_hospital itself LEFT JOINs everything, so this is a report, not a filter.)
WITH h AS (SELECT * FROM {{ ref('mart_hospital') }}),
steps AS (
    SELECT 1 AS step_order, 'In CMS FY2026 HRRP hospital file' AS step,
           count(*) AS hospitals_remaining FROM h
    UNION ALL SELECT 2, '+ at least one non-suppressed ERR',
           count(*) FILTER (WHERE n_conditions_with_err > 0) FROM h
    UNION ALL SELECT 3, '+ payment adjustment factor (IPPS supplemental file)',
           count(*) FILTER (WHERE n_conditions_with_err > 0 AND payment_adjustment_factor IS NOT NULL) FROM h
    UNION ALL SELECT 4, '+ in Hospital General Information',
           count(*) FILTER (WHERE n_conditions_with_err > 0 AND payment_adjustment_factor IS NOT NULL
                            AND hospital_type IS NOT NULL) FROM h
    UNION ALL SELECT 5, '+ cost report with Medicare base DRG payments',
           count(*) FILTER (WHERE n_conditions_with_err > 0 AND payment_adjustment_factor IS NOT NULL
                            AND hospital_type IS NOT NULL AND medicare_base_drg_payments IS NOT NULL) FROM h
    UNION ALL SELECT 6, '+ county FIPS found',
           count(*) FILTER (WHERE n_conditions_with_err > 0 AND payment_adjustment_factor IS NOT NULL
                            AND hospital_type IS NOT NULL AND medicare_base_drg_payments IS NOT NULL
                            AND county_fips IS NOT NULL) FROM h
    UNION ALL SELECT 7, '+ ACS income and age for that county',
           count(*) FILTER (WHERE n_conditions_with_err > 0 AND payment_adjustment_factor IS NOT NULL
                            AND hospital_type IS NOT NULL AND medicare_base_drg_payments IS NOT NULL
                            AND county_fips IS NOT NULL AND county_median_household_income IS NOT NULL
                            AND county_median_age IS NOT NULL) FROM h
)
SELECT step_order, step, hospitals_remaining,
       lag(hospitals_remaining) OVER (ORDER BY step_order) - hospitals_remaining AS dropped_here
FROM steps ORDER BY step_order
