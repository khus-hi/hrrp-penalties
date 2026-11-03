-- For checking the system crosswalk by hand against each company's 10-K hospital count.
SELECT parent_system, count(*) AS hrrp_hospitals_matched,
       count(*) FILTER (WHERE parent_max_pct_ownership < 100) AS with_stake_under_100pct
FROM {{ ref('mart_hospital') }} WHERE parent_system IS NOT NULL GROUP BY 1 ORDER BY 1
