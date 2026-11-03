-- Part of the FY2026 HRRP penalty estimate; method in docs/penalty_method.md.
-- Wide version for dashboards: one $ column per condition, plus the top drivers in words.
SELECT p.*,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'ami') AS penalty_usd_ami,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'hf') AS penalty_usd_hf,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'pn') AS penalty_usd_pn,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'copd') AS penalty_usd_copd,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'cabg') AS penalty_usd_cabg,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'tha_tka') AS penalty_usd_tha_tka,
    string_agg(condition_label || ' ' || round(100 * share_of_penalty)::INT || '%', ', '
               ORDER BY share_of_penalty DESC)
        FILTER (WHERE p.is_penalized AND share_of_penalty >= 0.005)          AS penalty_drivers
FROM {{ ref('mart_hospital_penalty') }} p
LEFT JOIN {{ ref('mart_hospital_condition_penalty') }} c USING (ccn)
GROUP BY ALL
