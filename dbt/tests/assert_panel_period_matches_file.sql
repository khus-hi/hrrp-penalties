-- The performance period in ingest/config.py must agree with the Start/End Date that
-- CMS printed in that year's Provider Data Catalog file, for every year where we have
-- the file. This is how the dates marked period_checked = 'rule' get checked.
SELECT fiscal_year, period_checked,
       config_period_start, file_period_start, config_period_end, file_period_end
FROM {{ ref('qa_panel_year_coverage') }}
WHERE file_period_start IS NOT NULL
  AND (file_period_start <> config_period_start OR file_period_end <> config_period_end)
