-- Hospital (CCN) -> every owner whose name matches a parent-system pattern.
-- Path: CCN -> enrollment(s) -> every owner on the enrollment -> owner name matched to
-- seeds/system_owner_patterns.csv.
SELECT DISTINCT
    e.ccn,
    o.enrollment_id,
    o.owner_org_name,
    o.role_code_owner,
    o.pct_ownership,
    p.system,
    TRY_CAST(p.cik AS BIGINT) AS cik
FROM {{ ref('stg_enrollment_ccn') }} e
JOIN {{ ref('stg_owners') }} o USING (enrollment_id)
JOIN {{ ref('system_owner_patterns') }} p
  ON o.owner_org_name ILIKE p.owner_name_pattern
