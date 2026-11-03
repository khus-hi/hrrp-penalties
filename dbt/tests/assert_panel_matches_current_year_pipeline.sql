{{ config(severity='error') }}
-- The harmonised panel must reproduce, for the current payment year, exactly what the
-- single-year pipeline (stg_hrrp_supplemental, mapped in ingest/load.py) reads from the
-- same CMS file: ERR, peer median, discharges, penalty indicator and factor. If the
-- regex mapping in macros/harmonize.sql picked a wrong column, this catches it.
-- Compared for the hospitals the panel has that year (the CI fixture keeps a subset);
-- skipped (no rows) if the panel has no rows for the current year.
{%- set conds = hrrp_conditions().keys() | list %}
WITH cur AS (
{%- for c in conds %}
    SELECT ccn, '{{ c }}' AS condition, err_{{ c }} AS err, peer_median_err_{{ c }} AS peer_median_err,
           eligible_discharges_{{ c }} AS eligible_discharges,
           upper(trim(penalty_indicator_{{ c }})) AS penalty_indicator, payment_adjustment_factor
    FROM {{ ref('stg_hrrp_supplemental') }}
    WHERE ccn IN (SELECT ccn FROM {{ ref('fct_hospital_condition_year') }}
                  WHERE fiscal_year = {{ var('program_year', 2026) }} AND in_supplemental)
    {% if not loop.last %}UNION ALL{% endif %}
{%- endfor %}
),
panel AS (
    SELECT * FROM {{ ref('fct_hospital_condition_year') }}
    WHERE fiscal_year = {{ var('program_year', 2026) }} AND in_supplemental
)
SELECT coalesce(c.ccn, p.ccn) AS ccn, coalesce(c.condition, p.condition) AS condition,
       c.err AS err_current, p.err AS err_panel,
       c.payment_adjustment_factor AS paf_current, p.payment_adjustment_factor AS paf_panel
FROM cur c
FULL OUTER JOIN panel p USING (ccn, condition)
WHERE (SELECT count(*) FROM panel) > 0
  AND (c.err IS NOT NULL OR c.peer_median_err IS NOT NULL OR c.eligible_discharges IS NOT NULL
       OR c.penalty_indicator IS NOT NULL OR p.ccn IS NOT NULL)
  AND (c.ccn IS NULL OR p.ccn IS NULL
       OR c.err IS DISTINCT FROM p.err
       OR c.peer_median_err IS DISTINCT FROM p.peer_median_err
       OR c.eligible_discharges IS DISTINCT FROM p.eligible_discharges
       OR c.penalty_indicator IS DISTINCT FROM p.penalty_indicator
       OR c.payment_adjustment_factor IS DISTINCT FROM p.payment_adjustment_factor)
