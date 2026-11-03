-- Part of the FY2026 HRRP penalty estimate; method in docs/penalty_method.md.
-- 3. Hospital-level dollars.
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
    FROM {{ ref('mart_hospital') }} h
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
FROM base
