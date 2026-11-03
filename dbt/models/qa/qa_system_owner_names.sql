-- Owner names that matched each system pattern, to check the crosswalk by hand.
SELECT system, owner_org_name, count(DISTINCT ccn) AS ccns
FROM {{ ref('int_owner_matches') }} GROUP BY ALL ORDER BY system, ccns DESC
