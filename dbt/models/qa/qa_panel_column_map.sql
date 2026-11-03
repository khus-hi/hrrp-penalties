-- Which raw column fed which panel field, year by year (the audit trail for the
-- harmonising in macros/harmonize.sql). One row per year x raw column that has values.
--   field NULL          -> the column is not used by the panel (fine, but worth a look)
--   competing_columns>1 -> two columns of the same year matched one field: the
--                          COALESCE would pick the first, so the pattern needs fixing
{%- set parts = [] %}
{%- for kind, name in [('supplemental', 'hrrp_supplemental_history'), ('pdc', 'hrrp_hospital_history')] %}
  {%- set rel = source('raw', name) %}
  {%- set cmap = hrrp_column_map(rel, kind) %}
  {%- for col in raw_columns(rel) %}
    {%- set hits = [] %}
    {%- for m in cmap %}{% if m.column == col %}{% do hits.append(m) %}{% endif %}{% endfor %}
    {%- if hits | length == 0 %}{% do hits.append({'field': none, 'condition': none}) %}{% endif %}
    {%- for m in hits %}
      {%- do parts.append(
          "SELECT CAST(fiscal_year AS INT) AS fiscal_year, '" ~ kind ~ "' AS source, '" ~ col ~ "' AS raw_column, "
          ~ ("NULL" if m.field is none else "'" ~ m.field ~ "'") ~ " AS field, "
          ~ ("NULL" if m.condition is none else "'" ~ m.condition ~ "'") ~ " AS condition, "
          ~ "count(" ~ adapter.quote(col) ~ ") AS n_values FROM " ~ rel ~ " GROUP BY 1 HAVING count("
          ~ adapter.quote(col) ~ ") > 0") %}
    {%- endfor %}
  {%- endfor %}
{%- endfor %}
WITH cols AS (
{%- if parts | length == 0 %}
    SELECT NULL::INT AS fiscal_year, NULL AS source, NULL AS raw_column, NULL AS field,
           NULL AS condition, NULL::BIGINT AS n_values WHERE FALSE
{%- else %}
    {{ parts | join('\n    UNION ALL\n    ') }}
{%- endif %}
)
SELECT
    *,
    CASE WHEN field IS NOT NULL
         THEN count(*) OVER (PARTITION BY fiscal_year, source, field, condition) END AS competing_columns
FROM cols
ORDER BY source, fiscal_year, field NULLS LAST, condition, raw_column
