-- Diagnostics shown in the penalty report
SELECT count(*)                                  AS hospitals_compared,
       count(*) FILTER (WHERE abs(s.payment_adjustment_factor - r.paf_recomputed) > 0.0001) AS mismatches,
       round(max(abs(s.payment_adjustment_factor - r.paf_recomputed)), 5)                    AS max_abs_diff,
       round(median(abs(s.payment_adjustment_factor - r.paf_recomputed)), 6)                 AS median_abs_diff
FROM {{ ref('stg_hrrp_supplemental') }} s JOIN {{ ref('mart_hospital_paf_recomputed') }} r USING (ccn)
