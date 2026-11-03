-- PECOS enrollment -> CCN bridge. One enrollment can list several CCNs joined by "|".
SELECT DISTINCT enrollment_id, {{ clean_ccn('c') }} AS ccn, organization_name, doing_business_as_name
FROM {{ source('raw', 'hospital_enrollments') }},
     unnest(string_split(ccn, '|')) AS t(c)
WHERE {{ clean_ccn('c') }} IS NOT NULL
