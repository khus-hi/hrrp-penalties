-- ZCTA -> county (2020). ZIP codes are not identical to ZCTAs; used only as a fallback.
SELECT geoid_zcta5_20 AS zcta, geoid_county_20 AS county_fips,
       TRY_CAST(arealand_part AS BIGINT) AS land_area_overlap
FROM {{ source('raw', 'zcta_county_rel') }}
WHERE geoid_zcta5_20 <> '' AND geoid_county_20 <> ''
