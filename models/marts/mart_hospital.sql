-- ONE ROW PER HOSPITAL in the CMS FY2026 HRRP file.
-- Everything is LEFT JOINed onto that spine so no hospital silently disappears;
-- the join funnel in checks/ reports how many have each piece.
CREATE OR REPLACE TABLE mart.hospital AS
WITH spine AS (
    SELECT ccn, any_value(facility_name) AS hrrp_facility_name, any_value(state) AS hrrp_state,
           min(period_start) AS hrrp_period_start, max(period_end) AS hrrp_period_end
    FROM stg.hrrp_measures WHERE ccn IS NOT NULL GROUP BY ccn
),
err AS (
    -- Long -> wide: one ERR and discharge count column per condition.
    SELECT ccn,
        max(err) FILTER (WHERE condition = 'ami')            AS err_ami,
        max(err) FILTER (WHERE condition = 'hf')             AS err_hf,
        max(err) FILTER (WHERE condition = 'pn')             AS err_pn,
        max(err) FILTER (WHERE condition = 'copd')           AS err_copd,
        max(err) FILTER (WHERE condition = 'cabg')           AS err_cabg,
        max(err) FILTER (WHERE condition = 'tha_tka')        AS err_tha_tka,
        max(discharges) FILTER (WHERE condition = 'ami')     AS discharges_ami,
        max(discharges) FILTER (WHERE condition = 'hf')      AS discharges_hf,
        max(discharges) FILTER (WHERE condition = 'pn')      AS discharges_pn,
        max(discharges) FILTER (WHERE condition = 'copd')    AS discharges_copd,
        max(discharges) FILTER (WHERE condition = 'cabg')    AS discharges_cabg,
        max(discharges) FILTER (WHERE condition = 'tha_tka') AS discharges_tha_tka
    FROM stg.hrrp_measures GROUP BY ccn
),
n_err AS (
    SELECT ccn, count(err) AS n_conditions_with_err FROM stg.hrrp_measures GROUP BY ccn
)
SELECT
    s.ccn,
    coalesce(gi.facility_name, s.hrrp_facility_name)        AS facility_name,
    s.hrrp_state                                            AS state,
    s.hrrp_period_start, s.hrrp_period_end,

    -- Excess readmission ratio by condition (NULL = suppressed / not reported)
    e.err_ami, e.err_hf, e.err_pn, e.err_copd, e.err_cabg, e.err_tha_tka,
    e.discharges_ami, e.discharges_hf, e.discharges_pn,
    e.discharges_copd, e.discharges_cabg, e.discharges_tha_tka,
    ne.n_conditions_with_err,

    -- FY2026 payment adjustment (IPPS final rule). 1.0 = no penalty, 0.97 = max 3% cut.
    sup.payment_adjustment_factor,
    t15.payment_adjustment_factor                           AS payment_adjustment_factor_table15,
    sup.dual_proportion,
    sup.peer_group,

    -- Medicare FFS base DRG payments (cost report proxy; see docs/data_sources.md)
    cr.medicare_base_drg_payments,
    cr.medicare_base_drg_source,
    cr.cr_fy_begin, cr.cr_fy_end,
    cr.medicare_discharges,
    cr.net_patient_revenue,
    cr.dsh_pct,

    -- Attributes
    gi.hospital_type,
    gi.hospital_ownership,
    cr.cr_type_of_control,
    cr.beds,
    cr.intern_resident_fte,
    -- HCRIS leaves the resident FTE line blank when a hospital has no residents, so a
    -- blank means 0 (non-teaching). NULL only when there is no cost report at all.
    CASE WHEN cr.cr_fy_end IS NULL THEN NULL
         ELSE coalesce(cr.intern_resident_fte, 0) > 0 END   AS is_teaching,
    gi.star_rating,
    gi.has_emergency_services,

    -- County context (ACS 2020-2024 5-year)
    hc.county_fips,
    hc.county_match_method,
    acs.acs_name                                            AS county_acs_name,
    acs.median_household_income                             AS county_median_household_income,
    acs.median_age                                          AS county_median_age,
    acs.share_age_65_plus                                   AS county_share_age_65_plus,

    -- Parent system (only the four public chains are mapped)
    hs.parent_system,
    hs.parent_cik,
    hs.parent_max_pct_ownership,
    coalesce(hs.system_conflict, false)                     AS parent_system_conflict
FROM spine s
LEFT JOIN err   e  USING (ccn)
LEFT JOIN n_err ne USING (ccn)
LEFT JOIN stg.hrrp_supplemental sup USING (ccn)
LEFT JOIN stg.hrrp_table15      t15 USING (ccn)
LEFT JOIN stg.general_info      gi  USING (ccn)
LEFT JOIN stg.cost_report       cr  USING (ccn)
LEFT JOIN int.hospital_county   hc  USING (ccn)
LEFT JOIN stg.acs_county        acs ON acs.county_fips = hc.county_fips
LEFT JOIN int.hospital_system   hs  USING (ccn);
