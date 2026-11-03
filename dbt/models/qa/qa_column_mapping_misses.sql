-- IPPS spreadsheet columns that could not be matched (left NULL on purpose).
SELECT source, field FROM {{ source('raw', 'column_mapping_log') }} WHERE matched_column IS NULL
