-- Provider Data Catalog HRRP hospital files of every loaded year, one row per
-- hospital x condition x year. The current file is always here; archived years only
-- if their ZIPs were saved in data/raw/pdc_archive/. When a year appears in several
-- monthly snapshots, the latest snapshot is kept ('current' beats any archive).
{%- set rel = source('raw', 'hrrp_hospital_history') %}
WITH mapped AS (
    SELECT
        CAST(fiscal_year AS INT)                                AS fiscal_year,
        snapshot,
        {{ clean_ccn(harmonized(rel, 'pdc', 'ccn')) }}          AS ccn,
        {{ harmonized(rel, 'pdc', 'measure_name') }}            AS measure_name,
        {{ harmonized(rel, 'pdc', 'err') }}                     AS err_raw,
        {{ harmonized(rel, 'pdc', 'discharges') }}              AS discharges_raw,
        {{ harmonized(rel, 'pdc', 'readmissions') }}            AS readmissions_raw,
        {{ harmonized(rel, 'pdc', 'predicted_rate') }}          AS predicted_rate_raw,
        {{ harmonized(rel, 'pdc', 'expected_rate') }}           AS expected_rate_raw,
        nullif(trim({{ harmonized(rel, 'pdc', 'footnote') }}), '') AS footnote,
        {{ harmonized(rel, 'pdc', 'start_date') }}              AS start_raw,
        {{ harmonized(rel, 'pdc', 'end_date') }}                AS end_raw
    FROM {{ rel }}
)
SELECT
    fiscal_year,
    snapshot,
    ccn,
    measure_name,
    CASE
        WHEN measure_name ILIKE '%-AMI-%'      OR measure_name ILIKE '%MYOCARDIAL%'    THEN 'ami'
        WHEN measure_name ILIKE '%-HF-%'       OR measure_name ILIKE '%HEART FAILURE%' THEN 'hf'
        WHEN measure_name ILIKE '%-PN-%'       OR measure_name ILIKE '%PNEUMONIA%'     THEN 'pn'
        WHEN measure_name ILIKE '%-COPD-%'     OR measure_name ILIKE '%PULMONARY%'     THEN 'copd'
        WHEN measure_name ILIKE '%-CABG-%'     OR measure_name ILIKE '%BYPASS%'        THEN 'cabg'
        WHEN measure_name ILIKE '%-HIP-KNEE-%' OR measure_name ILIKE '%ARTHROPLASTY%'  THEN 'tha_tka'
    END                                                            AS condition,
    {{ to_num('err_raw') }}                                        AS err,
    err_raw,
    {{ to_num('discharges_raw') }}                                 AS discharges,
    {{ to_num('readmissions_raw') }}                               AS readmissions,
    {{ to_num('predicted_rate_raw') }}                             AS predicted_rate,
    {{ to_num('expected_rate_raw') }}                              AS expected_rate,
    footnote,
    COALESCE(TRY_STRPTIME(start_raw, '%m/%d/%Y'), TRY_STRPTIME(start_raw, '%Y-%m-%d'))::DATE AS period_start,
    COALESCE(TRY_STRPTIME(end_raw,   '%m/%d/%Y'), TRY_STRPTIME(end_raw,   '%Y-%m-%d'))::DATE AS period_end
FROM mapped
WHERE ccn IS NOT NULL
QUALIFY dense_rank() OVER (
    PARTITION BY fiscal_year ORDER BY (snapshot = 'current') DESC, snapshot DESC) = 1
