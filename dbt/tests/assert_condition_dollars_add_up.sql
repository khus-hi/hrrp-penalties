-- The by-condition dollars add back up to the hospital's estimated penalty (to the cent).
SELECT c.ccn, sum(c.condition_penalty_usd) AS sum_condition_usd, any_value(p.est_penalty_usd) AS hospital_usd
FROM {{ ref('mart_hospital_condition_penalty') }} c
JOIN {{ ref('mart_hospital_penalty') }} p USING (ccn)
WHERE p.est_penalty_usd > 0
GROUP BY c.ccn HAVING abs(sum(c.condition_penalty_usd) - any_value(p.est_penalty_usd)) > 0.01
