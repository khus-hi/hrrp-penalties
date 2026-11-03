-- For every penalized hospital, the per-condition shares of the penalty add up to 1.
SELECT ccn, sum(share_of_penalty) AS total_share
FROM {{ ref('mart_hospital_condition_penalty_share') }} s
JOIN {{ ref('stg_hrrp_supplemental') }} USING (ccn)
WHERE payment_adjustment_factor < 1
GROUP BY ccn HAVING abs(sum(share_of_penalty) - 1) > 1e-6
