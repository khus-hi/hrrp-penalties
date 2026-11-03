-- ACS 2020-2024 5-year estimates by county.
-- Census uses large negative codes (e.g. -666666666) for "no estimate"; they become NULL.
WITH x AS (
    SELECT
        state || county                                         AS county_fips,
        state                                                   AS state_fips,
        "name"                                                  AS acs_name,
        split_part("name", ',', 1)                              AS acs_county_name,
        {{ to_num('total_population') }}                        AS total_population,
        {{ to_num('median_age') }}                              AS median_age,
        {{ to_num('median_household_income') }}                 AS median_household_income,
        {{ to_num('pop_m_020') }} + {{ to_num('pop_m_021') }} + {{ to_num('pop_m_022') }} + {{ to_num('pop_m_023') }}
          + {{ to_num('pop_m_024') }} + {{ to_num('pop_m_025') }}
          + {{ to_num('pop_f_044') }} + {{ to_num('pop_f_045') }} + {{ to_num('pop_f_046') }} + {{ to_num('pop_f_047') }}
          + {{ to_num('pop_f_048') }} + {{ to_num('pop_f_049') }}  AS pop_65_plus
    FROM {{ source('raw', 'acs_county') }}
)
SELECT
    county_fips, state_fips, acs_name, acs_county_name,
    {{ norm_county('acs_county_name') }}                        AS county_key,
    CASE WHEN total_population >= 0 THEN total_population END   AS total_population,
    CASE WHEN median_age >= 0 THEN median_age END               AS median_age,
    CASE WHEN median_household_income >= 0 THEN median_household_income END AS median_household_income,
    CASE WHEN pop_65_plus >= 0 AND total_population > 0
         THEN pop_65_plus / total_population END                AS share_age_65_plus
FROM x
