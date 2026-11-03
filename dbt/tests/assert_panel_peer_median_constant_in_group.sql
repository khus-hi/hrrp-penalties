-- CMS publishes one median ERR per year x condition x peer group, repeated on every
-- hospital's row. More than one distinct value in a group means a column was mapped
-- wrongly (or the peer group was). Works on the CI fixture too.
SELECT fiscal_year, condition, peer_group,
       count(DISTINCT peer_median_err) AS distinct_medians,
       min(peer_median_err) AS min_median, max(peer_median_err) AS max_median
FROM {{ ref('fct_hospital_condition_year') }}
WHERE peer_median_err IS NOT NULL
GROUP BY ALL
HAVING count(DISTINCT peer_median_err) > 1
