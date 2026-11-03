-- 42 CFR 412.154 caps the HRRP reduction at 3%, so no estimate can exceed 3% of the base.
SELECT ccn, est_penalty_usd, est_annual_base_drg_payments
FROM {{ ref('mart_hospital_penalty') }}
WHERE est_penalty_usd > 0.03 * est_annual_base_drg_payments + 0.01
