-- Why ERR / readmission values are missing, by condition. CMS suppresses small counts
-- ("Too Few to Report") and marks non-participation with N/A plus a footnote code.
SELECT
    coalesce(condition, 'UNMAPPED: ' || measure_name)        AS condition,
    count(*)                                                 AS rows,
    count(err)                                               AS err_reported,
    count(*) - count(err)                                    AS err_missing,
    count(*) FILTER (WHERE err IS NULL AND err_raw ILIKE 'N/A')               AS err_na,
    count(*) FILTER (WHERE readmissions_raw ILIKE 'Too Few to Report')        AS readmissions_too_few,
    count(*) FILTER (WHERE discharges IS NULL)                                AS discharges_missing,
    string_agg(DISTINCT footnote, ', ' ORDER BY footnote)                                     AS footnote_codes_seen
FROM {{ ref('stg_hrrp_measures') }}
GROUP BY ALL ORDER BY 1
