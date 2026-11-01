-- One row per hospital x HRRP condition, from the CMS FY2026 HRRP hospital file.
-- Performance period on the file: 07/01/2021 - 06/30/2024.
CREATE OR REPLACE TABLE stg.hrrp_measures AS
SELECT
    clean_ccn(facility_id)                         AS ccn,
    facility_name,
    state,
    measure_name,
    CASE
        WHEN measure_name ILIKE '%-AMI-%'      THEN 'ami'
        WHEN measure_name ILIKE '%-HF-%'       THEN 'hf'
        WHEN measure_name ILIKE '%-PN-%'       THEN 'pn'
        WHEN measure_name ILIKE '%-COPD-%'     THEN 'copd'
        WHEN measure_name ILIKE '%-CABG-%'     THEN 'cabg'
        WHEN measure_name ILIKE '%-HIP-KNEE-%' THEN 'tha_tka'
    END                                            AS condition,
    to_num(excess_readmission_ratio)               AS err,
    excess_readmission_ratio                       AS err_raw,      -- kept to count suppression reasons
    to_num(number_of_discharges)                   AS discharges,
    number_of_discharges                           AS discharges_raw,
    to_num(number_of_readmissions)                 AS readmissions,
    number_of_readmissions                         AS readmissions_raw,
    to_num(predicted_readmission_rate)             AS predicted_rate,
    to_num(expected_readmission_rate)              AS expected_rate,
    nullif(trim(footnote), '')                     AS footnote,
    TRY_STRPTIME(start_date, '%m/%d/%Y')::DATE     AS period_start,
    TRY_STRPTIME(end_date,   '%m/%d/%Y')::DATE     AS period_end
FROM raw.hrrp_hospital;
