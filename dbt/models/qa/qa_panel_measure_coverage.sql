-- One row per year x condition: how many hospitals had an ERR, a CMS penalty indicator,
-- and a penalty. `looks_suppressed` flags a condition that has ERRs but was never used
-- for a penalty (no 'Y' at all), which is what a measure CMS suppressed looks like.
-- assert_panel_known_breaks_consistent compares this with seeds/hrrp_known_breaks.csv.
SELECT
    fiscal_year,
    condition,
    count(*)                                                AS hospital_rows,
    count(err)                                              AS with_err,
    count(penalty_indicator)                                AS with_cms_indicator,
    count(*) FILTER (WHERE penalty_indicator = 'Y')         AS cms_indicator_y,
    count(*) FILTER (WHERE penalized_condition)             AS penalized,
    round(median(err), 4)                                   AS median_err,
    bool_or(measure_suppressed)                             AS suppressed_per_cms,
    count(err) > 0 AND count(penalty_indicator) > 0
        AND count(*) FILTER (WHERE penalty_indicator = 'Y') = 0 AS looks_suppressed
FROM {{ ref('fct_hospital_condition_year') }}
GROUP BY ALL
ORDER BY fiscal_year, condition
