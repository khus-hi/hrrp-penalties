-- Every CCN that failed a join, with the reason, so each one can be looked up.
CREATE OR REPLACE TABLE qa.unmatched_ccns AS
SELECT ccn, facility_name, state, 'not in IPPS supplemental file (no adjustment factor)' AS reason
FROM mart.hospital WHERE payment_adjustment_factor IS NULL
UNION ALL
SELECT ccn, facility_name, state, 'not in Hospital General Information'
FROM mart.hospital WHERE hospital_type IS NULL
UNION ALL
SELECT ccn, facility_name, state, 'no cost report in HCRIS file'
FROM mart.hospital WHERE cr_fy_end IS NULL
UNION ALL
SELECT ccn, facility_name, state, 'cost report has no Medicare base DRG amount'
FROM mart.hospital WHERE cr_fy_end IS NOT NULL AND medicare_base_drg_payments IS NULL
UNION ALL
SELECT ccn, facility_name, state, 'no county FIPS (name and ZIP both failed)'
FROM mart.hospital WHERE county_fips IS NULL
UNION ALL
SELECT ccn, facility_name, state, 'county FIPS found but not in ACS 2024 (e.g. old CT county)'
FROM mart.hospital WHERE county_fips IS NOT NULL AND county_acs_name IS NULL
UNION ALL
SELECT ccn, facility_name, state, 'owners match more than one system pattern'
FROM mart.hospital WHERE parent_system_conflict
UNION ALL
-- Reverse direction: hospitals CMS gave a factor to that aren't in the HRRP hospital file.
SELECT s.ccn, NULL, NULL, 'in IPPS supplemental file but not in HRRP hospital file'
FROM stg.hrrp_supplemental s ANTI JOIN mart.hospital h USING (ccn);
