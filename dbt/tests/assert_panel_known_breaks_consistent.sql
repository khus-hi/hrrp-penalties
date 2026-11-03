-- The breaks CMS announced (seeds/hrrp_known_breaks.csv) and what the data shows
-- must agree:
--   * a measure CMS says it suppressed must not carry a CMS penalty indicator of 'Y';
--   * a measure that looks suppressed in the data (ERRs but never a 'Y') must be in
--     the seed, so a break we didn't know about gets noticed instead of read as
--     "nobody was penalized".
SELECT fiscal_year, condition, with_err, cms_indicator_y, suppressed_per_cms, looks_suppressed,
       CASE WHEN suppressed_per_cms THEN 'suppressed per CMS but has penalty indicators = Y'
            ELSE 'looks suppressed but not in seeds/hrrp_known_breaks.csv' END AS problem
FROM {{ ref('qa_panel_measure_coverage') }}
WHERE (suppressed_per_cms AND cms_indicator_y > 0)
   OR (looks_suppressed AND NOT suppressed_per_cms)
