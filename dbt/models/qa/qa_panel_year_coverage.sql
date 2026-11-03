-- One row per HRRP payment year FY2016-FY2027: did we get CMS's file, how many
-- hospitals and conditions it has, and its performance period. A year CMS no longer
-- publishes (or that failed to download) shows status 'missing' with the reason.
SELECT
    y.fiscal_year,
    y.supplemental_status,
    y.supplemental_file,
    y.supplemental_note,
    count(DISTINCT f.ccn)                                   AS hospitals,
    count(DISTINCT f.ccn) FILTER (WHERE f.err IS NOT NULL)  AS hospitals_with_any_err,
    count(DISTINCT f.condition)                             AS conditions,
    string_agg(DISTINCT f.condition, ',' ORDER BY f.condition) AS condition_list,
    count(*) FILTER (WHERE f.in_pdc)                        AS rows_with_pdc_file,
    y.period_start                                          AS config_period_start,
    y.period_end                                            AS config_period_end,
    y.period_checked,
    min(f.perf_start) FILTER (WHERE f.perf_period_source = 'file') AS file_period_start,
    max(f.perf_end)   FILTER (WHERE f.perf_period_source = 'file') AS file_period_end
FROM {{ ref('stg_hrrp_program_years') }} y
LEFT JOIN {{ ref('fct_hospital_condition_year') }} f USING (fiscal_year)
GROUP BY ALL
ORDER BY y.fiscal_year
