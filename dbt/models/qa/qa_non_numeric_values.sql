-- Other text values that were turned into NULL during casting.
SELECT 'hrrp err' AS field, err_raw AS raw_value, count(*) AS n
FROM {{ ref('stg_hrrp_measures') }} WHERE err IS NULL GROUP BY ALL
UNION ALL
SELECT 'star rating', star_rating_raw, count(*) FROM {{ ref('stg_general_info') }} WHERE star_rating IS NULL GROUP BY ALL
ORDER BY field, n DESC
