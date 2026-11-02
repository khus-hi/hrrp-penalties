-- FY2026 payment adjustment factors from the IPPS final rule supplemental file.
-- Columns were matched by pattern in ingest/load.py; unmatched ones are NULL
-- (see raw.column_mapping_log). Nothing here is estimated.
CREATE OR REPLACE TABLE stg.hrrp_supplemental AS
SELECT
    clean_ccn(ccn)                         AS ccn,
    to_num(payment_adjustment_factor)      AS payment_adjustment_factor,
    to_num(payment_reduction_pct)          AS payment_reduction_pct,
    to_num(dual_proportion)                AS dual_proportion,
    TRY_CAST(to_num(peer_group) AS INT)    AS peer_group,
    to_num(neutrality_modifier)            AS neutrality_modifier,
    -- Per-condition inputs CMS used to compute the factor
    to_num(err_ami)                    AS err_ami,
    to_num(peer_median_err_ami)        AS peer_median_err_ami,
    to_num(eligible_discharges_ami)    AS eligible_discharges_ami,
    to_num(drg_payment_ratio_ami)      AS drg_payment_ratio_ami,
    penalty_indicator_ami,
    to_num(err_hf)                    AS err_hf,
    to_num(peer_median_err_hf)        AS peer_median_err_hf,
    to_num(eligible_discharges_hf)    AS eligible_discharges_hf,
    to_num(drg_payment_ratio_hf)      AS drg_payment_ratio_hf,
    penalty_indicator_hf,
    to_num(err_pn)                    AS err_pn,
    to_num(peer_median_err_pn)        AS peer_median_err_pn,
    to_num(eligible_discharges_pn)    AS eligible_discharges_pn,
    to_num(drg_payment_ratio_pn)      AS drg_payment_ratio_pn,
    penalty_indicator_pn,
    to_num(err_copd)                    AS err_copd,
    to_num(peer_median_err_copd)        AS peer_median_err_copd,
    to_num(eligible_discharges_copd)    AS eligible_discharges_copd,
    to_num(drg_payment_ratio_copd)      AS drg_payment_ratio_copd,
    penalty_indicator_copd,
    to_num(err_cabg)                    AS err_cabg,
    to_num(peer_median_err_cabg)        AS peer_median_err_cabg,
    to_num(eligible_discharges_cabg)    AS eligible_discharges_cabg,
    to_num(drg_payment_ratio_cabg)      AS drg_payment_ratio_cabg,
    penalty_indicator_cabg,
    to_num(err_tha_tka)                    AS err_tha_tka,
    to_num(peer_median_err_tha_tka)        AS peer_median_err_tha_tka,
    to_num(eligible_discharges_tha_tka)    AS eligible_discharges_tha_tka,
    to_num(drg_payment_ratio_tha_tka)      AS drg_payment_ratio_tha_tka,
    penalty_indicator_tha_tka
FROM raw.hrrp_supplemental
WHERE clean_ccn(ccn) IS NOT NULL;

-- Table 15 carries the same factor; used only as a cross-check.
CREATE OR REPLACE TABLE stg.hrrp_table15 AS
SELECT clean_ccn(ccn) AS ccn, to_num(payment_adjustment_factor) AS payment_adjustment_factor
FROM raw.hrrp_table15
WHERE clean_ccn(ccn) IS NOT NULL;
