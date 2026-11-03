-- Hospital (CCN) -> parent system. A hospital with no matching owner is "not one of
-- the four chains", not an error.
SELECT
    ccn,
    CASE WHEN count(DISTINCT system) = 1 THEN any_value(system) END        AS parent_system,
    CASE WHEN count(DISTINCT system) = 1 THEN any_value(cik) END           AS parent_cik,
    count(DISTINCT system) > 1                                              AS system_conflict,
    string_agg(DISTINCT system, ' | ')                                      AS systems_matched,
    -- Largest stated stake held by a matching owner (direct or indirect). Joint
    -- ventures show < 100; percentages are self-reported to CMS.
    max(pct_ownership)                                                      AS parent_max_pct_ownership,
    string_agg(DISTINCT owner_org_name, ' | ')                              AS matched_owner_names
FROM {{ ref('int_owner_matches') }}
GROUP BY ccn
