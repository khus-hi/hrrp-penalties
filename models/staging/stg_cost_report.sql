-- Medicare cost report (HCRIS) flat file. A hospital can have more than one report
-- in the file (e.g. a short period after a change of ownership), so we keep the
-- report with the latest fiscal-year end and record how many there were.
CREATE OR REPLACE TABLE stg.cost_report_all AS
SELECT
    clean_ccn(provider_ccn)                                   AS ccn,
    rpt_rec_num,
    TRY_CAST(fiscal_year_begin_date AS DATE)                  AS cr_fy_begin,
    TRY_CAST(fiscal_year_end_date AS DATE)                    AS cr_fy_end,
    type_of_control                                           AS cr_type_of_control,
    to_num(number_of_beds)                                    AS beds,
    to_num(number_of_interns_and_residents_fte)               AS intern_resident_fte,
    to_num(total_discharges_title_xviii)                      AS medicare_discharges,
    -- Worksheet E Part A, line 1: Medicare FFS DRG payments excluding outliers.
    -- Our proxy for "base operating DRG payments" (42 CFR 412.152 excludes IME, DSH,
    -- outliers, low-volume). Lines 1.01/1.02 split it around Oct 1 for some hospitals.
    to_num(drg_amounts_other_than_outlier_payments)           AS drg_amount_ex_outlier,
    to_num(drg_amounts_before_october_1)                      AS drg_amount_before_oct1,
    to_num(drg_amounts_after_october_1)                       AS drg_amount_after_oct1,
    to_num(outlier_payments_for_discharges)                   AS outlier_payments,
    to_num(disproportionate_share_adjustment)                 AS dsh_payments,
    to_num(total_ime_payment)                                 AS ime_payments,
    to_num(net_patient_revenue)                               AS net_patient_revenue,
    to_num(total_patient_revenue)                             AS total_patient_revenue,
    to_num(net_income)                                        AS net_income
FROM raw.hospital_cost_report;

CREATE OR REPLACE TABLE stg.cost_report AS
SELECT * EXCLUDE (rn),
    -- Use line 1; if blank, fall back to the sum of the before/after-Oct-1 lines.
    coalesce(drg_amount_ex_outlier,
             CASE WHEN drg_amount_before_oct1 IS NOT NULL OR drg_amount_after_oct1 IS NOT NULL
                  THEN coalesce(drg_amount_before_oct1, 0) + coalesce(drg_amount_after_oct1, 0) END)
        AS medicare_base_drg_payments,
    CASE WHEN drg_amount_ex_outlier IS NOT NULL THEN 'line 1'
         WHEN drg_amount_before_oct1 IS NOT NULL OR drg_amount_after_oct1 IS NOT NULL THEN 'lines 1.01+1.02'
    END AS medicare_base_drg_source
FROM (
    SELECT *,
        count(*) OVER (PARTITION BY ccn) AS n_reports_in_file,
        row_number() OVER (PARTITION BY ccn ORDER BY cr_fy_end DESC NULLS LAST, rpt_rec_num DESC) AS rn
    FROM stg.cost_report_all
    WHERE ccn IS NOT NULL
)
WHERE rn = 1;
