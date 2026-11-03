-- Part of the FY2026 HRRP penalty estimate; method in docs/penalty_method.md.
-- 4. Split each hospital's dollars across conditions by CMS's own contribution shares.
SELECT s.ccn, s.condition, s.condition_label, s.err, s.peer_median_err, s.drg_payment_ratio,
       s.share_of_penalty,
       s.counts_for_penalty,
       p.est_penalty_usd * s.share_of_penalty AS condition_penalty_usd
FROM {{ ref('mart_hospital_condition_penalty_share') }} s
JOIN {{ ref('mart_hospital_penalty') }} p USING (ccn)
