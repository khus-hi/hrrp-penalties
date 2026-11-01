-- Reusable SQL helpers.
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS int;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS qa;

-- CCN is a 6-character code ("010001"). Spreadsheets often drop the leading zero.
CREATE OR REPLACE MACRO clean_ccn(x) AS
    CASE WHEN regexp_matches(trim(x), '^[0-9A-Za-z]{1,6}$') THEN lpad(upper(trim(x)), 6, '0') END;

-- Numbers arrive as text like "0.9965", "1,234", "12.5%", "N/A". Non-numbers -> NULL.
CREATE OR REPLACE MACRO to_num(x) AS
    TRY_CAST(replace(replace(replace(trim(x), ',', ''), '%', ''), '$', '') AS DOUBLE);

-- County names differ between CMS ("ST. LOUIS") and Census ("St. Louis County").
CREATE OR REPLACE MACRO norm_county(x) AS
    regexp_replace(
        regexp_replace(
            regexp_replace(upper(trim(x)), '\bST\.?\s', 'SAINT ', 'g'),
            '\s(COUNTY|PARISH|BOROUGH|CENSUS AREA|CITY AND BOROUGH|MUNICIPALITY|MUNICIPIO|PLANNING REGION)$', ''),
        '[^A-Z0-9]', '', 'g');
