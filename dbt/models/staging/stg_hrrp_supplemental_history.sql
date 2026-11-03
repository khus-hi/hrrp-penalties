-- Every year's IPPS final rule HRRP supplemental file, one row per hospital x year,
-- with CMS's changing column names mapped to one set of names (macros/harmonize.sql).
-- Values are CMS's; only the names and types change here.
{%- set rel = source('raw', 'hrrp_supplemental_history') %}
{%- set conds = hrrp_conditions().keys() | list %}
SELECT
    CAST(fiscal_year AS INT)                                              AS fiscal_year,
    {{ clean_ccn('source_ccn') }}                                         AS ccn,
    source_file,
    {{ to_num(harmonized(rel, 'supplemental', 'payment_adjustment_factor')) }} AS payment_adjustment_factor,
    {{ to_num(harmonized(rel, 'supplemental', 'payment_reduction_pct')) }}     AS payment_reduction_pct,
    {{ to_num(harmonized(rel, 'supplemental', 'dual_proportion')) }}           AS dual_proportion,
    TRY_CAST({{ to_num(harmonized(rel, 'supplemental', 'peer_group')) }} AS INT) AS peer_group,
    {{ to_num(harmonized(rel, 'supplemental', 'neutrality_modifier')) }}       AS neutrality_modifier
{%- for c in conds %},
    {{ to_num(harmonized(rel, 'supplemental', 'err', c)) }}                 AS err_{{ c }},
    {{ to_num(harmonized(rel, 'supplemental', 'peer_median_err', c)) }}     AS peer_median_err_{{ c }},
    {{ to_num(harmonized(rel, 'supplemental', 'eligible_discharges', c)) }} AS eligible_discharges_{{ c }},
    {{ to_num(harmonized(rel, 'supplemental', 'drg_payment_ratio', c)) }}   AS drg_payment_ratio_{{ c }},
    upper(trim({{ harmonized(rel, 'supplemental', 'penalty_indicator', c) }})) AS penalty_indicator_{{ c }}
{%- endfor %}
FROM {{ rel }}
WHERE {{ clean_ccn('source_ccn') }} IS NOT NULL
