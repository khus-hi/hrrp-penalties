-- PECOS enrollment -> CCN bridge. One enrollment can list several CCNs joined by "|".
CREATE OR REPLACE TABLE stg.enrollment_ccn AS
SELECT DISTINCT enrollment_id, clean_ccn(c) AS ccn, organization_name, doing_business_as_name
FROM raw.hospital_enrollments,
     unnest(string_split(ccn, '|')) AS t(c)
WHERE clean_ccn(c) IS NOT NULL;

-- Every owner of every enrollment (direct = role 34, indirect 5%+ = role 35).
CREATE OR REPLACE TABLE stg.owners AS
SELECT
    enrollment_id,
    associate_id_owner,
    upper(trim(organization_name_owner))                       AS owner_org_name,
    nullif(trim(last_name_owner), '') IS NOT NULL              AS owner_is_individual,
    role_code_owner,
    role_text_owner,
    to_num(percentage_ownership)                               AS pct_ownership,
    for_profit_owner = 'Y'                                     AS owner_for_profit,
    chain_home_office_owner = 'Y'                              AS owner_chain_home_office
FROM raw.hospital_all_owners;
