-- The factor in the IPPS supplemental file must equal the one in Table 15.
SELECT ccn, payment_adjustment_factor, payment_adjustment_factor_table15
FROM {{ ref('mart_hospital') }}
WHERE abs(payment_adjustment_factor - payment_adjustment_factor_table15) > 1e-6
