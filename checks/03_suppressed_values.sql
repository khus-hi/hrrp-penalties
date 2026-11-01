-- Why ERR / readmission values are missing, by condition. CMS suppresses small counts
-- ("Too Few to Report") and marks non-participation with N/A plus a footnote code.
CREATE OR REPLACE TABLE qa.suppressed_values AS
SELECT
    coalesce(condition, 'UNMAPPED: ' || measure_name)        AS condition,
    count(*)                                                 AS rows,
    count(err)                                               AS err_reported,
    count(*) - count(err)                                    AS err_missing,
    count(*) FILTER (WHERE err IS NULL AND err_raw ILIKE 'N/A')               AS err_na,
    count(*) FILTER (WHERE readmissions_raw ILIKE 'Too Few to Report')        AS readmissions_too_few,
    count(*) FILTER (WHERE discharges IS NULL)                                AS discharges_missing,
    string_agg(DISTINCT footnote, ', ')                                       AS footnote_codes_seen
FROM stg.hrrp_measures
GROUP BY ALL ORDER BY 1;

-- Other text values that were turned into NULL during casting.
CREATE OR REPLACE TABLE qa.non_numeric_values AS
SELECT 'hrrp err' AS field, err_raw AS raw_value, count(*) AS n
FROM stg.hrrp_measures WHERE err IS NULL GROUP BY ALL
UNION ALL
SELECT 'star rating', star_rating_raw, count(*) FROM stg.general_info WHERE star_rating IS NULL GROUP BY ALL
ORDER BY field, n DESC;

-- IPPS spreadsheet columns that could not be matched (left NULL on purpose).
CREATE OR REPLACE TABLE qa.column_mapping_misses AS
SELECT source, field FROM raw.column_mapping_log WHERE matched_column IS NULL;
