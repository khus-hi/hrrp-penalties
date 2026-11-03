{{ config(severity='error') }}
-- Does our reading of the CMS formula (42 CFR 412.152/412.154) reproduce CMS's own
-- payment adjustment factor?  factor = max(0.97, 1 - NM x sum of DRG ratio x excess ERR).
-- CMS publishes the factor to 4 decimals, so the tolerance is 0.0001.
-- Fails for any hospital with a published factor whose recomputed factor is off by
-- more than that, or missing. Returns the offending hospitals.
SELECT s.ccn,
       s.payment_adjustment_factor                   AS paf_published,
       r.paf_recomputed,
       s.payment_adjustment_factor - r.paf_recomputed AS diff
FROM {{ ref('stg_hrrp_supplemental') }} s
LEFT JOIN {{ ref('mart_hospital_paf_recomputed') }} r USING (ccn)
WHERE s.payment_adjustment_factor IS NOT NULL
  AND (r.paf_recomputed IS NULL
       OR abs(s.payment_adjustment_factor - r.paf_recomputed) > 0.0001)
