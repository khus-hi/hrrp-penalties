-- The multi-year HRRP panel: one row per hospital (CCN) x condition x payment year.
--
-- Sources, in order of preference:
--   * IPPS final rule supplemental file (CMS's payment inputs) for ERR, peer group,
--     peer median, eligible discharges, penalty indicator and the payment factor;
--   * the Provider Data Catalog HRRP file of that year (if loaded) for rows the
--     supplemental file doesn't have, and for the performance period dates;
--   * ingest/config.py HRRP_YEARS for the period when no file gives the dates.
-- Every derived column says where it came from (*_source).
WITH supp AS (
    SELECT * FROM {{ ref('int_hrrp_condition_year') }}
),
pdc AS (
    SELECT fiscal_year, ccn, condition, err, discharges, period_start, period_end
    FROM {{ ref('stg_hrrp_hospital_history') }}
    WHERE condition IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY fiscal_year, ccn, condition ORDER BY err NULLS LAST) = 1
),
-- Hospital-level values from the supplemental file, so rows that exist only in the
-- PDC file still get the hospital's factor and peer group for that year.
hosp AS (
    SELECT fiscal_year, ccn,
           any_value(payment_adjustment_factor) AS payment_adjustment_factor,
           any_value(dual_proportion)           AS dual_proportion,
           any_value(peer_group)                AS peer_group
    FROM supp GROUP BY 1, 2
),
breaks AS (
    SELECT
        fiscal_year,
        nullif(condition, '')                                       AS condition,
        bool_or(break_type = 'covid_2020_exclusion')                AS covid_2020_excluded,
        bool_or(break_type = 'measure_suppressed')                  AS measure_suppressed,
        string_agg(break_type || ': ' || description, ' | ' ORDER BY break_type) AS notes
    FROM {{ ref('hrrp_known_breaks') }}
    GROUP BY 1, 2
),
joined AS (
    SELECT
        coalesce(s.ccn, p.ccn)                         AS ccn,
        coalesce(s.fiscal_year, p.fiscal_year)         AS fiscal_year,
        coalesce(s.condition, p.condition)             AS condition,
        -- A row in the supplemental file takes its values from it (CMS's payment
        -- inputs); the PDC file only fills rows the supplemental file doesn't have.
        s.err                                          AS err_supplemental,
        CASE WHEN s.ccn IS NULL THEN p.err END         AS err_pdc,
        s.peer_median_err,
        CASE WHEN s.ccn IS NULL THEN p.discharges ELSE s.eligible_discharges END AS eligible_discharges,
        s.drg_payment_ratio,
        s.penalty_indicator,
        p.period_start                                 AS pdc_period_start,
        p.period_end                                   AS pdc_period_end,
        s.ccn IS NOT NULL                              AS in_supplemental,
        p.ccn IS NOT NULL                              AS in_pdc
    FROM supp s
    FULL OUTER JOIN pdc p
      ON p.ccn = s.ccn AND p.fiscal_year = s.fiscal_year AND p.condition = s.condition
)
SELECT
    j.ccn,
    j.fiscal_year,
    j.condition,
    coalesce(j.err_supplemental, j.err_pdc)                     AS err,
    CASE WHEN j.err_supplemental IS NOT NULL THEN 'supplemental'
         WHEN j.err_pdc IS NOT NULL THEN 'pdc' END              AS err_source,
    -- Dual-proportion quintile; CMS only assigns one from FY2019 (stratified method).
    CASE WHEN j.fiscal_year >= 2019 THEN h.peer_group END       AS peer_group,
    j.peer_median_err,
    j.eligible_discharges,
    j.drg_payment_ratio,
    j.penalty_indicator,
    -- Was this condition penalized for this hospital this year?
    --   CMS's own indicator when the file has one; otherwise CMS's rule for that year:
    --   ERR above the peer-group median (FY2019+) or above 1 (FY2016-FY2018).
    --   NULL when there is no ERR (too few cases) or CMS suppressed the measure.
    CASE
        WHEN coalesce(bc.measure_suppressed, FALSE)                    THEN NULL
        WHEN j.penalty_indicator IN ('Y', 'N')                         THEN j.penalty_indicator = 'Y'
        WHEN coalesce(j.err_supplemental, j.err_pdc) IS NULL           THEN NULL
        WHEN j.fiscal_year >= 2019 AND j.peer_median_err IS NOT NULL   THEN coalesce(j.err_supplemental, j.err_pdc) > j.peer_median_err
        WHEN j.fiscal_year < 2019                                      THEN coalesce(j.err_supplemental, j.err_pdc) > 1
    END                                                         AS penalized_condition,
    CASE
        WHEN coalesce(bc.measure_suppressed, FALSE)                    THEN 'suppressed'
        WHEN j.penalty_indicator IN ('Y', 'N')                         THEN 'cms_indicator'
        WHEN coalesce(j.err_supplemental, j.err_pdc) IS NULL           THEN 'no_err'
        WHEN j.fiscal_year >= 2019 AND j.peer_median_err IS NOT NULL   THEN 'err_vs_peer_median'
        WHEN j.fiscal_year < 2019                                      THEN 'err_vs_1'
    END                                                         AS penalized_source,
    h.payment_adjustment_factor,
    h.dual_proportion,
    coalesce(j.pdc_period_start, y.period_start)                AS perf_start,
    coalesce(j.pdc_period_end, y.period_end)                    AS perf_end,
    CASE WHEN j.pdc_period_start IS NOT NULL THEN 'file' ELSE 'config:' || y.period_checked END AS perf_period_source,
    coalesce(by_.covid_2020_excluded, FALSE)                    AS covid_2020_excluded,
    coalesce(bc.measure_suppressed, FALSE)                      AS measure_suppressed,
    nullif(concat_ws(' | ', by_.notes, bc.notes), '')           AS break_notes,
    j.in_supplemental,
    j.in_pdc
FROM joined j
LEFT JOIN hosp h ON h.ccn = j.ccn AND h.fiscal_year = j.fiscal_year
LEFT JOIN {{ ref('stg_hrrp_program_years') }} y ON y.fiscal_year = j.fiscal_year
LEFT JOIN breaks by_ ON by_.fiscal_year = j.fiscal_year AND by_.condition IS NULL
LEFT JOIN breaks bc  ON bc.fiscal_year = j.fiscal_year AND bc.condition = j.condition
