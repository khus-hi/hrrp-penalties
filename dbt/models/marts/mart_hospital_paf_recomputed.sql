-- Part of the FY2026 HRRP penalty estimate; method in docs/penalty_method.md.
-- 2. Re-derive CMS's factor from those inputs. If our reading of the formula is right,
--    this matches the published factor (checked by tests/assert_factor_recompute_matches_cms.sql).
SELECT ccn,
       any_value(neutrality_modifier)                                              AS neutrality_modifier,
       sum(excess_term)                                                            AS sum_excess_terms,
       greatest(0.97, 1 - any_value(neutrality_modifier) * sum(excess_term))       AS paf_recomputed
FROM {{ ref('mart_hospital_condition_penalty_share') }}
GROUP BY ccn
