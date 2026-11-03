-- Does our reading of the CMS formula reproduce CMS's published factor?
-- CMS publishes the factor to 4 decimals, so allow a rounding tolerance.
SELECT s.ccn, s.payment_adjustment_factor AS paf_published, r.paf_recomputed,
       s.payment_adjustment_factor - r.paf_recomputed AS diff
FROM {{ ref('stg_hrrp_supplemental') }} s
JOIN {{ ref('mart_hospital_paf_recomputed') }} r USING (ccn)
WHERE abs(s.payment_adjustment_factor - r.paf_recomputed) > 0.0001
