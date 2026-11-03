{#-
  Harmonise column names across HRRP years.

  CMS renamed the HRRP columns several times (e.g. "Provider Number" -> "Hospital CCN",
  "Excess Readmission Ratio (AMI)" -> "ERR for AMI"). ingest/load.py stacks every year
  with its OWN column names (union by name, so a column one year lacks is NULL that
  year). These macros read the stacked raw table's columns when the model compiles and
  map each one to a canonical field by regex. Nothing is guessed: a field with no
  matching column is NULL, and qa.panel_column_map shows, for every year, which raw
  column fed which field (and flags a year where two columns compete for one field).

  The patterns are matched against snake_case names (ingest.load.norm), so
  "ERR for THA/TKA" is err_for_thatka.
-#}

{#- Per-condition columns of the supplemental file: field -> [include, exclude] -#}
{% macro hrrp_condition_fields() -%}
  {{ return({
      'err':                 ['(^|_)err(_|$)|excess_readmission_ratio', 'median|peer'],
      'peer_median_err':     ['median', none],
      'eligible_discharges': ['discharge|number_of_(eligible|cases)', 'readmission'],
      'penalty_indicator':   ['penalty_indicator|penalized', none],
      'drg_payment_ratio':   ['payment_ratio|drg_payment|ratio_of_(base|drg)', 'excess_readmission'],
  }) }}
{%- endmacro %}

{#- The six HRRP conditions, as they appear inside column names -#}
{% macro hrrp_conditions() -%}
  {{ return({
      'ami':     '(^|_)ami(_|$)|myocardial',
      'hf':      '(^|_)hf(_|$)|heart_failure',
      'pn':      '(^|_)pn(_|$)|pneumonia',
      'copd':    'copd',
      'cabg':    'cabg|bypass',
      'tha_tka': '(^|_)(tha|tka|thatka|tha_tka|hip|knee|hipknee)(_|$)',
  }) }}
{%- endmacro %}

{#- Hospital-level columns (only columns that name no condition are considered) -#}
{% macro hrrp_hospital_fields() -%}
  {{ return({
      'payment_adjustment_factor': ['adjustment_factor', 'neutral|peer'],
      'payment_reduction_pct':     ['reduction_(percent|pct|percentage)|percent_reduction', none],
      'dual_proportion':           ['dual_(proportion|eligible)', none],
      'peer_group':                ['peer_group', 'median'],
      'neutrality_modifier':       ['neutrality', none],
  }) }}
{%- endmacro %}

{#- Provider Data Catalog HRRP hospital file (one row per hospital x measure) -#}
{% macro hrrp_pdc_fields() -%}
  {{ return({
      'ccn':            ['^(facility_id|provider_number|provider_id|ccn|hospital_ccn)$', none],
      'facility_name':  ['^(facility_name|hospital_name)$', none],
      'state':          ['^state$', none],
      'measure_name':   ['^(measure_name|measure_id|measure)$', none],
      'err':            ['excess_readmission_ratio', none],
      'discharges':     ['^number_of_discharges$', none],
      'readmissions':   ['^number_of_readmissions$', none],
      'predicted_rate': ['predicted_readmission_rate', none],
      'expected_rate':  ['expected_readmission_rate', none],
      'footnote':       ['^footnote', none],
      'start_date':     ['^start_date$', none],
      'end_date':       ['^end_date$', none],
  }) }}
{%- endmacro %}

{#- The raw table's column names, in order, minus the loader's helper columns (empty while dbt only parses the project) -#}
{% macro raw_columns(relation) -%}
  {% if not execute %}{{ return([]) }}{% endif %}
  {% set rel = load_relation(relation) %}
  {% if rel is none %}{{ return([]) }}{% endif %}
  {% set cols = [] %}
  {% for c in adapter.get_columns_in_relation(rel) %}
    {% if c.name not in ['fiscal_year', 'source_file', 'source_ccn', 'snapshot', '_loaded_at'] %}
      {% do cols.append(c.name) %}
    {% endif %}
  {% endfor %}
  {{ return(cols) }}
{%- endmacro %}

{% macro _matches(col, include, exclude) -%}
  {{ return(modules.re.search(include, col) is not none
            and (exclude is none or modules.re.search(exclude, col) is none)) }}
{%- endmacro %}

{#-
  The column map: a list of {column, field, condition} for a stacked raw table.
  kind = 'supplemental' (hospital + per-condition fields) or 'pdc'.
-#}
{% macro hrrp_column_map(relation, kind) -%}
  {% set out = [] %}
  {% for col in raw_columns(relation) %}
    {% if kind == 'pdc' %}
      {% for field, pat in hrrp_pdc_fields().items() %}
        {% if _matches(col, pat[0], pat[1]) %}{% do out.append({'column': col, 'field': field, 'condition': none}) %}{% endif %}
      {% endfor %}
    {% else %}
      {% set conds = [] %}
      {% for cond, cpat in hrrp_conditions().items() %}
        {% if modules.re.search(cpat, col) is not none %}{% do conds.append(cond) %}{% endif %}
      {% endfor %}
      {% if conds | length == 1 %}
        {% for field, pat in hrrp_condition_fields().items() %}
          {% if _matches(col, pat[0], pat[1]) %}{% do out.append({'column': col, 'field': field, 'condition': conds[0]}) %}{% endif %}
        {% endfor %}
      {% elif conds | length == 0 %}
        {% for field, pat in hrrp_hospital_fields().items() %}
          {% if _matches(col, pat[0], pat[1]) %}{% do out.append({'column': col, 'field': field, 'condition': none}) %}{% endif %}
        {% endfor %}
      {% endif %}
    {% endif %}
  {% endfor %}
  {{ return(out) }}
{%- endmacro %}

{#-
  SQL for one canonical field: COALESCE over every raw column mapped to it (in a given
  year only one of them has values; qa.panel_column_map checks that), or NULL.
-#}
{% macro harmonized(relation, kind, field, condition=none) -%}
  {% set cols = [] %}
  {% for m in hrrp_column_map(relation, kind) %}
    {% if m.field == field and m.condition == condition %}{% do cols.append(adapter.quote(m.column)) %}{% endif %}
  {% endfor %}
  {%- if cols | length == 0 -%} CAST(NULL AS VARCHAR)
  {%- elif cols | length == 1 -%} {{ cols[0] }}
  {%- else -%} COALESCE({{ cols | join(', ') }})
  {%- endif -%}
{%- endmacro %}
