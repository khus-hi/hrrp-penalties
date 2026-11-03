-- Supplemental file, unpivoted: one row per hospital x condition x year.
-- A condition is kept for a year only if that year's file has any value for it (CABG
-- before FY2017 has no columns, so no rows), or if CMS says it was suppressed that
-- year (seed hrrp_known_breaks), so a suppressed measure stays visible in the panel.
{%- set conds = hrrp_conditions().keys() | list %}
WITH long AS (
{%- for c in conds %}
    SELECT
        fiscal_year, ccn, source_file, payment_adjustment_factor, dual_proportion, peer_group,
        '{{ c }}'                       AS condition,
        err_{{ c }}                     AS err,
        peer_median_err_{{ c }}         AS peer_median_err,
        eligible_discharges_{{ c }}     AS eligible_discharges,
        drg_payment_ratio_{{ c }}       AS drg_payment_ratio,
        penalty_indicator_{{ c }}       AS penalty_indicator
    FROM {{ ref('stg_hrrp_supplemental_history') }}
    {% if not loop.last %}UNION ALL{% endif %}
{%- endfor %}
),
condition_years AS (
    SELECT fiscal_year, condition
    FROM long
    GROUP BY 1, 2
    HAVING count(coalesce(CAST(err AS VARCHAR), CAST(peer_median_err AS VARCHAR),
                          CAST(eligible_discharges AS VARCHAR), penalty_indicator)) > 0
    UNION
    SELECT fiscal_year, condition FROM {{ ref('hrrp_known_breaks') }} WHERE break_type = 'measure_suppressed'
)
SELECT long.*
FROM long
JOIN condition_years USING (fiscal_year, condition)
