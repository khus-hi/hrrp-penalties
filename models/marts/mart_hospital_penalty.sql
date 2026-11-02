-- FY2026 HRRP PENALTY ESTIMATE, one row per hospital, plus a by-condition table.
--
--   penalty $ = (1 - payment adjustment factor) x annualised Medicare base DRG payments
--
-- The factor is CMS's exact number. The dollar base is our estimate; every assumption
-- is listed in docs/penalty_method.md and flagged per row in `estimate_quality`.

-- 1. What each condition contributed to the factor, using CMS's own inputs.
--    42 CFR 412.152: excess payments = sum over conditions of
--    (DRG payment ratio) x (ERR - peer-group median ERR, if positive), times the
--    neutrality modifier. The factor is 1 minus that, floored at 0.97.
CREATE OR REPLACE TABLE mart.hospital_condition_penalty_share AS
WITH long AS (
    SELECT ccn, 'ami' AS condition, 'AMI' AS condition_label, drg_payment_ratio_ami AS drg_payment_ratio,
           err_ami AS err, peer_median_err_ami AS peer_median_err, eligible_discharges_ami AS eligible_discharges
    FROM stg.hrrp_supplemental
    UNION ALL
    SELECT ccn, 'hf' AS condition, 'Heart failure' AS condition_label, drg_payment_ratio_hf AS drg_payment_ratio,
           err_hf AS err, peer_median_err_hf AS peer_median_err, eligible_discharges_hf AS eligible_discharges
    FROM stg.hrrp_supplemental
    UNION ALL
    SELECT ccn, 'pn' AS condition, 'Pneumonia' AS condition_label, drg_payment_ratio_pn AS drg_payment_ratio,
           err_pn AS err, peer_median_err_pn AS peer_median_err, eligible_discharges_pn AS eligible_discharges
    FROM stg.hrrp_supplemental
    UNION ALL
    SELECT ccn, 'copd' AS condition, 'COPD' AS condition_label, drg_payment_ratio_copd AS drg_payment_ratio,
           err_copd AS err, peer_median_err_copd AS peer_median_err, eligible_discharges_copd AS eligible_discharges
    FROM stg.hrrp_supplemental
    UNION ALL
    SELECT ccn, 'cabg' AS condition, 'CABG' AS condition_label, drg_payment_ratio_cabg AS drg_payment_ratio,
           err_cabg AS err, peer_median_err_cabg AS peer_median_err, eligible_discharges_cabg AS eligible_discharges
    FROM stg.hrrp_supplemental
    UNION ALL
    SELECT ccn, 'tha_tka' AS condition, 'Hip/knee' AS condition_label, drg_payment_ratio_tha_tka AS drg_payment_ratio,
           err_tha_tka AS err, peer_median_err_tha_tka AS peer_median_err, eligible_discharges_tha_tka AS eligible_discharges
    FROM stg.hrrp_supplemental
)
SELECT
    l.*,
    s.neutrality_modifier,
    coalesce(greatest(l.err - l.peer_median_err, 0), 0) * coalesce(l.drg_payment_ratio, 0) AS excess_term,
    excess_term / nullif(sum(excess_term) OVER (PARTITION BY l.ccn), 0)                   AS share_of_penalty
FROM long l
JOIN stg.hrrp_supplemental s USING (ccn);

-- 2. Re-derive CMS's factor from those inputs. If our reading of the formula is right,
--    this matches the published factor (checked in checks/05_penalty_checks.sql).
CREATE OR REPLACE TABLE mart.hospital_paf_recomputed AS
SELECT ccn,
       any_value(neutrality_modifier)                                              AS neutrality_modifier,
       sum(excess_term)                                                            AS sum_excess_terms,
       greatest(0.97, 1 - any_value(neutrality_modifier) * sum(excess_term))       AS paf_recomputed
FROM mart.hospital_condition_penalty_share
GROUP BY ccn;

-- 3. Hospital-level dollars.
CREATE OR REPLACE TABLE mart.hospital_penalty AS
WITH base AS (
    SELECT
        h.ccn, h.facility_name, h.state, h.hospital_type, h.hospital_ownership,
        h.parent_system, h.is_teaching, h.beds, h.star_rating,
        h.payment_adjustment_factor,
        h.payment_adjustment_factor < 1                                    AS is_penalized,
        1 - h.payment_adjustment_factor                                    AS payment_reduction_rate,
        h.medicare_base_drg_payments                                       AS cost_report_base_drg_payments,
        h.cr_fy_begin, h.cr_fy_end,
        date_diff('day', h.cr_fy_begin, h.cr_fy_end) + 1                   AS cr_days,
        h.net_patient_revenue
    FROM mart.hospital h
)
SELECT
    *,
    -- Assumption A: scale the cost-report year to 365 days (most are already 12 months).
    CASE WHEN cr_days BETWEEN 180 AND 400
         THEN cost_report_base_drg_payments * 365.0 / cr_days END         AS est_annual_base_drg_payments,
    CASE
        WHEN payment_adjustment_factor IS NULL       THEN 'no factor: not in FY2026 HRRP payment file'
        WHEN cost_report_base_drg_payments IS NULL   THEN 'no base: cost report missing or blank DRG line'
        WHEN cr_days NOT BETWEEN 180 AND 400         THEN 'no base: cost report period under 180 or over 400 days'
        WHEN cr_days BETWEEN 360 AND 370             THEN 'ok: full-year cost report'
        ELSE 'ok but annualised: partial-year cost report'
    END                                                                    AS estimate_quality,
    payment_reduction_rate * est_annual_base_drg_payments                  AS est_penalty_usd,
    est_penalty_usd / nullif(net_patient_revenue * 365.0 / cr_days, 0)    AS est_penalty_share_of_net_patient_revenue
FROM base;

-- 4. Split each hospital's dollars across conditions by CMS's own contribution shares.
CREATE OR REPLACE TABLE mart.hospital_condition_penalty AS
SELECT s.ccn, s.condition, s.condition_label, s.err, s.peer_median_err, s.drg_payment_ratio,
       s.share_of_penalty,
       p.est_penalty_usd * s.share_of_penalty AS condition_penalty_usd
FROM mart.hospital_condition_penalty_share s
JOIN mart.hospital_penalty p USING (ccn);

-- Wide version for dashboards: one $ column per condition, plus the top drivers in words.
CREATE OR REPLACE TABLE mart.hospital_penalty_wide AS
SELECT p.*,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'ami') AS penalty_usd_ami,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'hf') AS penalty_usd_hf,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'pn') AS penalty_usd_pn,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'copd') AS penalty_usd_copd,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'cabg') AS penalty_usd_cabg,
    sum(condition_penalty_usd) FILTER (WHERE condition = 'tha_tka') AS penalty_usd_tha_tka,
    string_agg(condition_label || ' ' || round(100 * share_of_penalty)::INT || '%', ', '
               ORDER BY share_of_penalty DESC) FILTER (WHERE share_of_penalty > 0) AS penalty_drivers
FROM mart.hospital_penalty p
LEFT JOIN mart.hospital_condition_penalty c USING (ccn)
GROUP BY ALL;
