-- Pass/fail tests. A failure doesn't stop the build; it's printed in the report.
CREATE OR REPLACE TABLE qa.assertions AS
SELECT 'mart has one row per CCN' AS test,
       (SELECT count(*) - count(DISTINCT ccn) FROM mart.hospital) AS failing_rows
UNION ALL SELECT 'every HRRP measure_name maps to a condition',
       (SELECT count(*) FROM stg.hrrp_measures WHERE condition IS NULL)
UNION ALL SELECT 'every hospital has at most 6 HRRP rows',
       (SELECT count(*) FROM (SELECT ccn FROM stg.hrrp_measures GROUP BY ccn HAVING count(*) > 6))
UNION ALL SELECT 'CCN in HRRP file is 6 characters',
       (SELECT count(*) FROM stg.hrrp_measures WHERE ccn IS NULL)
UNION ALL SELECT 'supplemental file has one row per CCN',
       (SELECT count(*) - count(DISTINCT ccn) FROM stg.hrrp_supplemental)
UNION ALL SELECT 'General Info has one row per CCN',
       (SELECT count(*) - count(DISTINCT ccn) FROM stg.general_info)
UNION ALL SELECT 'payment adjustment factor between 0.97 and 1.0 (42 CFR 412.154 floor)',
       (SELECT count(*) FROM mart.hospital
        WHERE payment_adjustment_factor NOT BETWEEN 0.97 AND 1.0)
UNION ALL SELECT 'supplemental factor equals Table 15 factor',
       (SELECT count(*) FROM mart.hospital
        WHERE abs(payment_adjustment_factor - payment_adjustment_factor_table15) > 1e-6)
UNION ALL SELECT 'ERR values are positive',
       (SELECT count(*) FROM stg.hrrp_measures WHERE err <= 0)
UNION ALL SELECT 'Medicare base DRG payments are not negative',
       (SELECT count(*) FROM mart.hospital WHERE medicare_base_drg_payments < 0)
UNION ALL SELECT 'county FIPS is 5 digits',
       (SELECT count(*) FROM mart.hospital WHERE county_fips IS NOT NULL AND NOT regexp_matches(county_fips, '^[0-9]{5}$'))
UNION ALL SELECT 'ACS median income has no Census sentinel codes left',
       (SELECT count(*) FROM stg.acs_county WHERE median_household_income < 0);

-- For checking the system crosswalk by hand against each company's 10-K hospital count.
CREATE OR REPLACE TABLE qa.system_summary AS
SELECT parent_system, count(*) AS hrrp_hospitals_matched,
       count(*) FILTER (WHERE parent_max_pct_ownership < 100) AS with_stake_under_100pct
FROM mart.hospital WHERE parent_system IS NOT NULL GROUP BY 1 ORDER BY 1;

CREATE OR REPLACE TABLE qa.system_owner_names AS
SELECT system, owner_org_name, count(DISTINCT ccn) AS ccns
FROM int.owner_matches GROUP BY ALL ORDER BY system, ccns DESC;

-- How the cost report years line up with federal FY2026 (Oct 2025 - Sep 2026).
CREATE OR REPLACE TABLE qa.cost_report_years AS
SELECT year(cr_fy_end) AS cost_report_fy_end_year, count(*) AS hospitals
FROM mart.hospital GROUP BY 1 ORDER BY 1;
