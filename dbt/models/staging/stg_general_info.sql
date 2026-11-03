-- Hospital attributes from CMS Hospital General Information.
SELECT
    {{ clean_ccn('facility_id') }}                      AS ccn,
    facility_name,
    citytown                                        AS city,
    state,
    lpad(left(trim(zip_code), 5), 5, '0')           AS zip5,
    countyparish                                    AS county_name,
    hospital_type,
    hospital_ownership,
    emergency_services = 'Yes'                      AS has_emergency_services,
    TRY_CAST(hospital_overall_rating AS INT)        AS star_rating,       -- "Not Available" -> NULL
    hospital_overall_rating                         AS star_rating_raw
FROM {{ source('raw', 'hospital_general_info') }}
