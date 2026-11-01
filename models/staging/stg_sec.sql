-- Annual (10-K, full-year) consolidated facts for the four public hospital companies.
-- companyfacts has no segment/payer breakdowns, so Medicare revenue isn't available here.
CREATE OR REPLACE TABLE stg.sec_annual AS
SELECT
    TRY_CAST(cik AS BIGINT)            AS cik,
    entity_name,
    tag,
    label,
    TRY_CAST(start_date AS DATE)          AS period_start,
    TRY_CAST(end_date AS DATE)            AS period_end,
    TRY_CAST(val AS DOUBLE)            AS value_usd,
    TRY_CAST(fy AS INT)                AS fy_filed,
    form,
    TRY_CAST(filed AS DATE)            AS filed
FROM raw.sec_facts
WHERE taxonomy = 'us-gaap' AND unit = 'USD' AND form IN ('10-K', '10-K/A')
  AND date_diff('day', TRY_CAST(start_date AS DATE), TRY_CAST(end_date AS DATE)) BETWEEN 350 AND 380;
