-- Hospital -> county FIPS.
-- 1st choice: state + county name from General Information matched to the ACS county
--             name (exactly one match required).
-- 2nd choice: hospital ZIP -> 2020 ZCTA -> county with the largest land overlap.
-- Known gap: ACS 2022+ uses Connecticut planning regions, so CT hospitals may not match.
CREATE OR REPLACE TABLE int.hospital_county AS
WITH g AS (
    SELECT gi.ccn, gi.state, gi.zip5, gi.county_name, sf.state_fips,
           norm_county(gi.county_name) AS county_key
    FROM stg.general_info gi
    LEFT JOIN seed.state_fips sf ON sf.state_abbr = gi.state
),
name_hits AS (
    SELECT g.ccn, count(a.county_fips) AS n_hits, any_value(a.county_fips) AS county_fips
    FROM g LEFT JOIN stg.acs_county a
      ON a.state_fips = g.state_fips AND a.county_key = g.county_key
    GROUP BY g.ccn
),
zip_hits AS (
    SELECT g.ccn, arg_max(z.county_fips, z.land_area_overlap) AS county_fips,
           count(*) AS n_counties_for_zip
    FROM g JOIN stg.zcta_county z ON z.zcta = g.zip5
    GROUP BY g.ccn
)
SELECT
    g.ccn, g.state, g.county_name, g.zip5,
    CASE WHEN n.n_hits = 1 THEN n.county_fips ELSE zh.county_fips END AS county_fips,
    CASE WHEN n.n_hits = 1 THEN 'county name'
         WHEN zh.county_fips IS NOT NULL THEN 'zip fallback'
    END                                                               AS county_match_method,
    n.n_hits                                                          AS name_match_count,
    zh.n_counties_for_zip
FROM g
LEFT JOIN name_hits n USING (ccn)
LEFT JOIN zip_hits zh USING (ccn);
