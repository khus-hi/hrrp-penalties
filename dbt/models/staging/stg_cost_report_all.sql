-- Medicare cost report (HCRIS) flat file, every report in the file.
-- stg_cost_report keeps one report per hospital.
SELECT
    {{ clean_ccn('provider_ccn') }}                               AS ccn,
    rpt_rec_num,
    TRY_CAST(fiscal_year_begin_date AS DATE)                  AS cr_fy_begin,
    TRY_CAST(fiscal_year_end_date AS DATE)                    AS cr_fy_end,
    type_of_control                                           AS cr_type_of_control,
    {{ to_num('number_of_beds') }}                                AS beds,
    {{ to_num('number_of_interns_and_residents_fte') }}           AS intern_resident_fte,
    {{ to_num('total_discharges_title_xviii') }}                  AS medicare_discharges,
    -- Worksheet E Part A, line 1: Medicare FFS DRG payments excluding outliers.
    -- Our proxy for "base operating DRG payments" (42 CFR 412.152 excludes IME, DSH,
    -- outliers, low-volume). Lines 1.01/1.02 split it around Oct 1 for some hospitals.
    {{ to_num('drg_amounts_other_than_outlier_payments') }}       AS drg_amount_ex_outlier,
    {{ to_num('drg_amounts_before_october_1') }}                  AS drg_amount_before_oct1,
    {{ to_num('drg_amounts_after_october_1') }}                   AS drg_amount_after_oct1,
    {{ to_num('outlier_payments_for_discharges') }}               AS outlier_payments,
    {{ to_num('disproportionate_share_adjustment') }}             AS dsh_payments,
    {{ to_num('total_ime_payment') }}                             AS ime_payments,
    {{ to_num('allowable_dsh_percentage') }}                      AS dsh_pct,           -- Medicare DSH patient percentage
    {{ to_num('net_patient_revenue') }}                           AS net_patient_revenue,
    {{ to_num('total_patient_revenue') }}                         AS total_patient_revenue,
    {{ to_num('net_income') }}                                    AS net_income
FROM {{ source('raw', 'hospital_cost_report') }}
