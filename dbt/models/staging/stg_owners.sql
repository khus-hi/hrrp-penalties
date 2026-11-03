-- Every owner of every enrollment (direct = role 34, indirect 5%+ = role 35).
SELECT
    enrollment_id,
    associate_id_owner,
    upper(trim(organization_name_owner))                       AS owner_org_name,
    nullif(trim(last_name_owner), '') IS NOT NULL              AS owner_is_individual,
    role_code_owner,
    role_text_owner,
    {{ to_num('percentage_ownership') }}                           AS pct_ownership,
    for_profit_owner = 'Y'                                     AS owner_for_profit,
    chain_home_office_owner = 'Y'                              AS owner_chain_home_office
FROM {{ source('raw', 'hospital_all_owners') }}
