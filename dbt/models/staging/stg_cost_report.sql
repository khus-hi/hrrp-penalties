-- One cost report per hospital. A hospital can have more than one report in the
-- file (e.g. a short period after a change of ownership), so we keep the report
-- with the latest fiscal-year end and record how many there were.
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
    FROM {{ ref('stg_cost_report_all') }}
    WHERE ccn IS NOT NULL
)
WHERE rn = 1
