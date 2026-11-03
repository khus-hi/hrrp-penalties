-- HRRP has six conditions, so no hospital can have more than six rows in the file.
SELECT ccn, count(*) AS n_rows
FROM {{ ref('stg_hrrp_measures') }}
GROUP BY ccn HAVING count(*) > 6
