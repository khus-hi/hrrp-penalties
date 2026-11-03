{#-
  Reusable cleaning expressions (ported from models/staging/00_macros.sql, which
  created DuckDB SQL macros). As dbt macros they expand inline when a model compiles,
  so the compiled SQL in target/compiled/ shows exactly what ran.
-#}

{#- CCN is a 6-character code ("010001"). Spreadsheets often drop the leading zero. -#}
{% macro clean_ccn(x) -%}
    CASE WHEN regexp_matches(trim({{ x }}), '^[0-9A-Za-z]{1,6}$') THEN lpad(upper(trim({{ x }})), 6, '0') END
{%- endmacro %}

{#- Numbers arrive as text like "0.9965", "1,234", "12.5%", "N/A". Non-numbers -> NULL. -#}
{% macro to_num(x) -%}
    TRY_CAST(replace(replace(replace(trim({{ x }}), ',', ''), '%', ''), '$', '') AS DOUBLE)
{%- endmacro %}

{#- County names differ between CMS ("ST. LOUIS") and Census ("St. Louis County"). -#}
{% macro norm_county(x) -%}
    regexp_replace(
        regexp_replace(
            regexp_replace(upper(trim({{ x }})), '\bST\.?\s', 'SAINT ', 'g'),
            '\s(COUNTY|PARISH|BOROUGH|CENSUS AREA|CITY AND BOROUGH|MUNICIPALITY|MUNICIPIO|PLANNING REGION)$', ''),
        '[^A-Z0-9]', '', 'g')
{%- endmacro %}
