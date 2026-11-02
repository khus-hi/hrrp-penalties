-- Summaries of the FY2026 HRRP penalty estimate (mart.hospital_penalty_wide).
-- "estimable" = the hospital has both a CMS factor and a usable cost-report base.
CREATE SCHEMA IF NOT EXISTS analysis;

-- National headline numbers
CREATE OR REPLACE TABLE analysis.national AS
SELECT
    count(*)                                                        AS hospitals_in_hrrp_file,
    count(payment_adjustment_factor)                                AS hospitals_with_cms_factor,
    count(*) FILTER (WHERE is_penalized)                            AS hospitals_penalized,
    round(100.0 * count(*) FILTER (WHERE is_penalized)
          / nullif(count(payment_adjustment_factor), 0), 1)         AS pct_penalized,
    count(*) FILTER (WHERE payment_adjustment_factor = 0.97)        AS hospitals_at_3pct_cap,
    round(avg(payment_adjustment_factor), 4)                        AS mean_factor,
    count(est_penalty_usd)                                          AS hospitals_estimable,
    count(*) FILTER (WHERE is_penalized AND est_penalty_usd IS NULL) AS penalized_but_not_estimable,
    round(sum(est_penalty_usd))                                     AS est_total_penalty_usd,
    round(median(est_penalty_usd) FILTER (WHERE is_penalized))      AS median_penalty_penalized_usd,
    round(max(est_penalty_usd))                                     AS max_penalty_usd,
    round(sum(est_annual_base_drg_payments))                        AS est_total_base_drg_usd
FROM mart.hospital_penalty_wide;

-- Generic group-by used for state / ownership / system
CREATE OR REPLACE MACRO penalty_rollup(grp) AS TABLE
    SELECT
        grp                                                         AS grp,
        count(*)                                                    AS hospitals_in_hrrp_file,
        count(payment_adjustment_factor)                            AS with_cms_factor,
        count(*) FILTER (WHERE is_penalized)                        AS penalized,
        round(100.0 * count(*) FILTER (WHERE is_penalized)
              / nullif(count(payment_adjustment_factor), 0), 1)     AS pct_penalized,
        round(avg(payment_adjustment_factor), 4)                    AS mean_factor,
        count(est_penalty_usd)                                      AS estimable,
        round(sum(est_penalty_usd))                                 AS est_total_penalty_usd,
        round(avg(est_penalty_usd) FILTER (WHERE is_penalized))     AS est_avg_penalty_penalized_usd,
        round(100 * sum(est_penalty_usd) / nullif(sum(est_annual_base_drg_payments)
              FILTER (WHERE est_penalty_usd IS NOT NULL), 0), 3)    AS penalty_pct_of_base_drg
    FROM mart.hospital_penalty_wide
    GROUP BY ALL;

CREATE OR REPLACE TABLE analysis.by_state AS
SELECT grp AS state, * EXCLUDE (grp) FROM penalty_rollup(state) ORDER BY est_total_penalty_usd DESC NULLS LAST;

CREATE OR REPLACE TABLE analysis.by_ownership AS
SELECT coalesce(grp, '(not in General Information)') AS hospital_ownership, * EXCLUDE (grp)
FROM penalty_rollup(hospital_ownership) ORDER BY est_total_penalty_usd DESC NULLS LAST;

CREATE OR REPLACE TABLE analysis.by_system AS
SELECT coalesce(grp, 'Not one of the four chains') AS parent_system, * EXCLUDE (grp)
FROM penalty_rollup(parent_system) ORDER BY parent_system = 'Not one of the four chains', est_total_penalty_usd DESC;

-- Which conditions drive the dollars nationally and for each chain
CREATE OR REPLACE TABLE analysis.by_condition AS
SELECT c.condition_label AS condition,
       count(*) FILTER (WHERE c.share_of_penalty > 0)                  AS hospitals_where_it_contributes,
       round(sum(c.condition_penalty_usd))                             AS est_penalty_usd,
       round(100 * sum(c.condition_penalty_usd)
             / sum(sum(c.condition_penalty_usd)) OVER (), 1)          AS pct_of_total
FROM mart.hospital_condition_penalty c
GROUP BY 1 ORDER BY est_penalty_usd DESC NULLS LAST;

CREATE OR REPLACE TABLE analysis.by_system_condition AS
SELECT coalesce(p.parent_system, 'Not one of the four chains') AS parent_system,
       c.condition_label AS condition,
       round(sum(c.condition_penalty_usd)) AS est_penalty_usd
FROM mart.hospital_condition_penalty c JOIN mart.hospital_penalty p USING (ccn)
GROUP BY ALL ORDER BY 1, 3 DESC NULLS LAST;

-- Massachusetts: every hospital in the HRRP file
CREATE OR REPLACE TABLE analysis.massachusetts AS
SELECT ccn, facility_name, hospital_ownership, parent_system,
       payment_adjustment_factor,
       round(100 * payment_reduction_rate, 2)       AS payment_cut_pct,
       round(est_annual_base_drg_payments)          AS est_base_drg_usd,
       round(est_penalty_usd)                       AS est_penalty_usd,
       penalty_drivers,
       estimate_quality
FROM mart.hospital_penalty_wide
WHERE state = 'MA'
ORDER BY est_penalty_usd DESC NULLS LAST, facility_name;

-- Counts taken straight from CMS's supplemental file, to compare with ours
CREATE OR REPLACE TABLE analysis.cms_file_counts AS
SELECT count(*)                                                 AS hospitals_in_cms_file,
       count(*) FILTER (WHERE payment_adjustment_factor < 1)    AS penalized_in_cms_file,
       count(*) FILTER (WHERE payment_adjustment_factor = 0.97) AS at_cap_in_cms_file,
       round(avg(payment_adjustment_factor), 4)                 AS mean_factor_in_cms_file
FROM stg.hrrp_supplemental;
