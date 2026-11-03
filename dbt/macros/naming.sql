{#-
  Keep the table names the pipeline had before dbt.

  dbt's default would put models in "main_stg", "main_mart" and so on, and name the
  tables after the files (mart.mart_hospital). These two overrides use the folder's
  schema as-is (stg, int, mart, qa, seed) and drop the layer prefix from the table
  name, so models/marts/mart_hospital.sql builds mart.hospital. The file names keep
  the prefix because dbt model names must be unique across the whole project.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}

{% macro generate_alias_name(custom_alias_name=none, node=none) -%}
    {%- if custom_alias_name -%}
        {{ custom_alias_name | trim }}
    {%- elif node.resource_type == 'model' -%}
        {{ modules.re.sub('^(stg|int|mart|qa)_', '', node.name) }}
    {%- else -%}
        {{ node.name }}
    {%- endif -%}
{%- endmacro %}
