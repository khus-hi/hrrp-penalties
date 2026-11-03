-- One row per HRRP payment year FY2016-FY2027 from ingest/config.py HRRP_YEARS: the
-- performance period and where its dates came from, plus whether ingest.load found
-- that year's supplemental file.
SELECT
    CAST(y.fiscal_year AS INT)          AS fiscal_year,
    CAST(y.period_start AS DATE)        AS period_start,
    CAST(y.period_end AS DATE)          AS period_end,
    y.period_checked,
    y.period_source,
    y.landing_page,
    y.note,
    f.status                            AS supplemental_status,
    f.source_file                       AS supplemental_file,
    CAST(f."rows" AS INT)               AS supplemental_rows,
    f.note                              AS supplemental_note
FROM {{ source('raw', 'hrrp_program_years') }} y
LEFT JOIN {{ source('raw', 'hrrp_history_files') }} f USING (fiscal_year)
