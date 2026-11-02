-- Checks on the penalty estimate. Appended to qa.assertions (created in 04).

-- Does our reading of the CMS formula reproduce CMS's published factor?
-- CMS publishes the factor to 4 decimals, so allow a rounding tolerance.
CREATE OR REPLACE TABLE qa.paf_recompute_mismatches AS
SELECT s.ccn, s.payment_adjustment_factor AS paf_published, r.paf_recomputed,
       s.payment_adjustment_factor - r.paf_recomputed AS diff
FROM stg.hrrp_supplemental s
JOIN mart.hospital_paf_recomputed r USING (ccn)
WHERE abs(s.payment_adjustment_factor - r.paf_recomputed) > 0.0001;

-- Diagnostics shown in the penalty report
CREATE OR REPLACE TABLE qa.paf_recompute_summary AS
SELECT count(*)                                  AS hospitals_compared,
       count(*) FILTER (WHERE abs(s.payment_adjustment_factor - r.paf_recomputed) > 0.0001) AS mismatches,
       round(max(abs(s.payment_adjustment_factor - r.paf_recomputed)), 5)                    AS max_abs_diff,
       round(median(abs(s.payment_adjustment_factor - r.paf_recomputed)), 6)                 AS median_abs_diff
FROM stg.hrrp_supplemental s JOIN mart.hospital_paf_recomputed r USING (ccn);

CREATE OR REPLACE TABLE qa.penalty_indicator_values AS
SELECT condition, penalty_indicator, count(*) AS n,
       count(*) FILTER (WHERE err > peer_median_err) AS n_err_above_median
FROM mart.hospital_condition_penalty_share GROUP BY ALL ORDER BY 1, 2;

INSERT INTO qa.assertions
SELECT 'recomputed factor (1 - NM x sum of ratio x excess ERR, floor 0.97) matches CMS',
       (SELECT count(*) FROM qa.paf_recompute_mismatches)
UNION ALL SELECT 'condition shares sum to 1 for every penalized hospital',
       (SELECT count(*) FROM (
            SELECT ccn FROM mart.hospital_condition_penalty_share s
            JOIN stg.hrrp_supplemental USING (ccn)
            WHERE payment_adjustment_factor < 1
            GROUP BY ccn HAVING abs(sum(share_of_penalty) - 1) > 1e-6))
UNION ALL SELECT 'condition dollars add up to hospital dollars',
       (SELECT count(*) FROM (
            SELECT c.ccn FROM mart.hospital_condition_penalty c
            JOIN mart.hospital_penalty p USING (ccn)
            WHERE p.est_penalty_usd > 0
            GROUP BY c.ccn HAVING abs(sum(c.condition_penalty_usd) - any_value(p.est_penalty_usd)) > 0.01))
UNION ALL SELECT 'no penalty above 3% of the base',
       (SELECT count(*) FROM mart.hospital_penalty WHERE est_penalty_usd > 0.03 * est_annual_base_drg_payments + 0.01)
UNION ALL SELECT 'unpenalized hospitals (factor = 1) have $0',
       (SELECT count(*) FROM mart.hospital_penalty WHERE payment_adjustment_factor = 1 AND est_penalty_usd <> 0);
