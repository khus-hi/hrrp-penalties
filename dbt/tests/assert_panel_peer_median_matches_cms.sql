-- Recompute each peer group's median ERR from the panel and compare it with the
-- median CMS published in the supplemental file (FY2019+, stratified method).
-- CMS's median is over every hospital in the peer group with an ERR for that
-- condition, so this only means something on the FULL data: groups with fewer than
-- var('panel_peer_median_min_hospitals') hospitals (e.g. the 50-hospital CI fixture)
-- are skipped. Tolerance 1e-6: the file carries ERRs and medians to ~16 digits.
WITH grp AS (
    SELECT fiscal_year, condition, peer_group,
           count(err)                    AS hospitals_with_err,
           median(err)                   AS recomputed_median,
           min(peer_median_err)          AS published_median
    FROM {{ ref('fct_hospital_condition_year') }}
    WHERE fiscal_year >= 2019 AND err_source = 'supplemental' AND peer_group IS NOT NULL
      AND NOT measure_suppressed
    GROUP BY ALL
)
SELECT *, recomputed_median - published_median AS diff
FROM grp
WHERE hospitals_with_err >= {{ var('panel_peer_median_min_hospitals', 100) }}
  AND published_median IS NOT NULL
  AND abs(recomputed_median - published_median) > 1e-6
