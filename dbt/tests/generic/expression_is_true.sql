{#-
  Generic test: every row must satisfy a SQL condition on the column.
  Rows where the condition is NULL are not counted, the same as the old
  checks/04_assertions.sql (e.g. a NULL factor is not "outside 0.97-1.0").
  Usage in a .yml file:
      data_tests:
        - expression_is_true:
            arguments:
              expression: "between 0.97 and 1.0"
-#}
{% test expression_is_true(model, column_name, expression) %}
select *
from {{ model }}
where not ({{ column_name }} {{ expression }})
{% endtest %}
