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
    COLUMNS('^(err|peer_median_err|eligible_discharges|drg_payment_ratio)_') ,
    COLUMNS('^penalty_indicator_')
FROM raw.hrrp_supplemental
WHERE clean_ccn(ccn) IS NOT NULL;

-- Table 15 carries the same factor; used only as a cross-check.
CREATE OR REPLACE TABLE stg.hrrp_table15 AS
SELECT clean_ccn(ccn) AS ccn, to_num(payment_adjustment_factor) AS payment_adjustment_factor
FROM raw.hrrp_table15
WHERE clean_ccn(ccn) IS NOT NULL;
