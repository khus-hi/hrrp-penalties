-- Hospital (CCN) -> parent system.
-- Path: CCN -> enrollment(s) -> every owner on the enrollment -> owner name matched to
-- seed.system_owner_patterns. A hospital with no matching owner is "not one of the four
-- chains", not an error.
CREATE OR REPLACE TABLE int.owner_matches AS
SELECT DISTINCT
    e.ccn,
    o.enrollment_id,
    o.owner_org_name,
    o.role_code_owner,
    o.pct_ownership,
    p.system,
    TRY_CAST(p.cik AS BIGINT) AS cik
FROM stg.enrollment_ccn e
JOIN stg.owners o USING (enrollment_id)
JOIN seed.system_owner_patterns p
  ON o.owner_org_name ILIKE p.owner_name_pattern;

CREATE OR REPLACE TABLE int.hospital_system AS
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
FROM int.owner_matches
GROUP BY ccn;
