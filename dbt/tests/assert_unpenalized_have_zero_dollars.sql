-- A hospital with factor 1.0 (no penalty) must have an estimate of $0.
SELECT ccn, est_penalty_usd
FROM {{ ref('mart_hospital_penalty') }}
WHERE payment_adjustment_factor = 1 AND est_penalty_usd <> 0
