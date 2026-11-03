-- FY2026 HRRP PENALTY ESTIMATE, one row per hospital, plus a by-condition table.
--
--   penalty $ = (1 - payment adjustment factor) x annualised Medicare base DRG payments
--
-- The factor is CMS's exact number. The dollar base is our estimate; every assumption
-- is listed in docs/penalty_method.md and flagged per row in `estimate_quality`.

-- 1. What each condition contributed to the factor, using CMS's own inputs.
--    42 CFR 412.152: excess payments = sum over conditions of
--    (DRG payment ratio) x (ERR - peer-group median ERR, if positive), times the
--    neutrality modifier. The factor is 1 minus that, floored at 0.97.
--    A condition only counts when CMS's penalty indicator for it is "Y" (CMS sets it
--    to "N" when, e.g., the hospital has too few eligible cases for that condition).
WITH long AS (
    SELECT ccn, 'ami' AS condition, 'AMI' AS condition_label, drg_payment_ratio_ami AS drg_payment_ratio,
           err_ami AS err, peer_median_err_ami AS peer_median_err, eligible_discharges_ami AS eligible_discharges,
           penalty_indicator_ami AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental') }}
    UNION ALL
    SELECT ccn, 'hf' AS condition, 'Heart failure' AS condition_label, drg_payment_ratio_hf AS drg_payment_ratio,
           err_hf AS err, peer_median_err_hf AS peer_median_err, eligible_discharges_hf AS eligible_discharges,
           penalty_indicator_hf AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental') }}
    UNION ALL
    SELECT ccn, 'pn' AS condition, 'Pneumonia' AS condition_label, drg_payment_ratio_pn AS drg_payment_ratio,
           err_pn AS err, peer_median_err_pn AS peer_median_err, eligible_discharges_pn AS eligible_discharges,
           penalty_indicator_pn AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental') }}
    UNION ALL
    SELECT ccn, 'copd' AS condition, 'COPD' AS condition_label, drg_payment_ratio_copd AS drg_payment_ratio,
           err_copd AS err, peer_median_err_copd AS peer_median_err, eligible_discharges_copd AS eligible_discharges,
           penalty_indicator_copd AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental') }}
    UNION ALL
    SELECT ccn, 'cabg' AS condition, 'CABG' AS condition_label, drg_payment_ratio_cabg AS drg_payment_ratio,
           err_cabg AS err, peer_median_err_cabg AS peer_median_err, eligible_discharges_cabg AS eligible_discharges,
           penalty_indicator_cabg AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental') }}
    UNION ALL
    SELECT ccn, 'tha_tka' AS condition, 'Hip/knee' AS condition_label, drg_payment_ratio_tha_tka AS drg_payment_ratio,
           err_tha_tka AS err, peer_median_err_tha_tka AS peer_median_err, eligible_discharges_tha_tka AS eligible_discharges,
           penalty_indicator_tha_tka AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental') }}
)
SELECT
    l.*,
    s.neutrality_modifier,
    CASE WHEN upper(trim(l.penalty_indicator)) IN ('N', 'NO', '0', 'FALSE') THEN false
         WHEN upper(trim(l.penalty_indicator)) IN ('Y', 'YES', '1', 'TRUE') THEN true
         ELSE NULL END                                                                      AS counts_for_penalty,
    CASE WHEN counts_for_penalty IS false THEN 0
         ELSE coalesce(greatest(l.err - l.peer_median_err, 0), 0) * coalesce(l.drg_payment_ratio, 0)
    END                                                                                     AS excess_term,
    excess_term / nullif(sum(excess_term) OVER (PARTITION BY l.ccn), 0)                   AS share_of_penalty
FROM long l
JOIN {{ ref('stg_hrrp_supplemental') }} s USING (ccn)
