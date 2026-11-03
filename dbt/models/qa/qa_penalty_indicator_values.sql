-- CMS penalty indicator values by condition (shown in docs/penalty_report.md).
SELECT condition, penalty_indicator, count(*) AS n,
       count(*) FILTER (WHERE err > peer_median_err) AS n_err_above_median
FROM {{ ref('mart_hospital_condition_penalty_share') }} GROUP BY ALL ORDER BY 1, 2
