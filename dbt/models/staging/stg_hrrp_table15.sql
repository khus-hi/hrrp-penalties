-- Table 15 carries the same factor as the supplemental file; used only as a cross-check.
SELECT {{ clean_ccn('ccn') }} AS ccn, {{ to_num('payment_adjustment_factor') }} AS payment_adjustment_factor
FROM {{ source('raw', 'hrrp_table15') }}
WHERE {{ clean_ccn('ccn') }} IS NOT NULL
