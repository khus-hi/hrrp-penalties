-- Same joins measured independently (not cumulative), so one weak source is easy to spot.
SELECT 'payment adjustment factor (supplemental)' AS source, count(payment_adjustment_factor) AS matched, count(*) AS total FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'payment adjustment factor (Table 15)', count(payment_adjustment_factor_table15), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'General Information', count(hospital_type), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'cost report: any report', count(cr_fy_end), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'cost report: Medicare base DRG payments', count(medicare_base_drg_payments), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'star rating', count(star_rating), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'county FIPS', count(county_fips), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'ACS county income', count(county_median_household_income), count(*) FROM {{ ref('mart_hospital') }}
UNION ALL SELECT 'one of the four public chains', count(parent_system), count(*) FROM {{ ref('mart_hospital') }}
