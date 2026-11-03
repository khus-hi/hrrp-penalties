# HRRP panel, FY2016-FY2027: coverage and attrition

_Generated 2026-11-03 20:27 UTC by `python -m analysis.panel_report` from `mart.fct_hospital_condition_year`. Do not edit by hand._

## Years

CMS payment years expected: FY2016-FY2027 (12). Loaded: 12 (FY2016, FY2017, FY2018, FY2019, FY2020, FY2021, FY2022, FY2023, FY2024, FY2025, FY2026, FY2027).

No year is missing.

| fy | status | hospitals | with_any_err | conditions | condition_list | period_start | period_end | period_checked | file_period_start | file_period_end | supplemental_note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 | loaded | 3464 | 3464 | 4 | ami,hf,pn,tha_tka | 2011-07-01 | 2014-06-30 | rule |  |  |  |
| 2017 | loaded | 3448 | 3448 | 4 | ami,cabg,hf,tha_tka | 2012-07-01 | 2015-06-30 | rule |  |  |  |
| 2018 | loaded | 3414 | 3323 | 5 | ami,cabg,hf,pn,tha_tka | 2013-07-01 | 2016-06-30 | rule |  |  |  |
| 2019 | loaded | 3173 | 3173 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2014-07-01 | 2017-06-30 | rule |  |  |  |
| 2020 | loaded | 3130 | 3130 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2015-07-01 | 2018-06-30 | rule |  |  |  |
| 2021 | loaded | 3080 | 3080 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2016-07-01 | 2019-06-30 | cms |  |  |  |
| 2022 | loaded | 3047 | 3047 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2017-07-01 | 2019-12-01 | cms |  |  |  |
| 2023 | loaded | 3044 | 3044 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2018-07-01 | 2021-06-30 | rule |  |  |  |
| 2024 | loaded | 3037 | 3037 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2019-07-01 | 2022-06-30 | rule |  |  |  |
| 2025 | loaded | 2980 | 2980 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2020-07-01 | 2023-06-30 | rule |  |  |  |
| 2026 | loaded | 2945 | 2945 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2021-07-01 | 2024-06-30 | file | 2021-07-01 | 2024-06-30 |  |
| 2027 | loaded | 2912 | 2912 | 6 | ami,cabg,copd,hf,pn,tha_tka | 2023-07-01 | 2025-06-30 | cms |  |  |  |

`period_checked`: `file` = dates printed in CMS's Provider Data Catalog file, `cms` = quoted from a CMS/QualityNet document (link in `ingest/config.py`), `rule` = the standard 3-year window, not yet confirmed (the test `assert_panel_period_matches_file` confirms it once that year's archived Provider Data Catalog file is loaded).

## Hospitals in every year

- Distinct hospitals (CCNs) in any loaded year: **3,661**
- In every one of the 12 loaded years: **2,762**

## Attrition

Year over year: `stayed` = in both years, `left` = in the earlier year only, `joined` = in the later year only. Gaps in the years are shown as they are.

| years | hospitals_before | stayed | left | joined | hospitals_after |
|---|---|---|---|---|---|
| 2016 -> 2017 | 3464 | 3420 | 44 | 28 | 3448 |
| 2017 -> 2018 | 3448 | 3391 | 57 | 23 | 3414 |
| 2018 -> 2019 | 3414 | 3153 | 261 | 20 | 3173 |
| 2019 -> 2020 | 3173 | 3119 | 54 | 11 | 3130 |
| 2020 -> 2021 | 3130 | 3064 | 66 | 16 | 3080 |
| 2021 -> 2022 | 3080 | 3035 | 45 | 12 | 3047 |
| 2022 -> 2023 | 3047 | 3009 | 38 | 35 | 3044 |
| 2023 -> 2024 | 3044 | 3017 | 27 | 20 | 3037 |
| 2024 -> 2025 | 3037 | 2963 | 74 | 17 | 2980 |
| 2025 -> 2026 | 2980 | 2928 | 52 | 17 | 2945 |
| 2026 -> 2027 | 2945 | 2894 | 51 | 18 | 2912 |


Of the hospitals in FY2016, how many are still in each later year:

| fy | still_in | pct_of_fy2016 |
|---|---|---|
| 2016 | 3464 | 100 |
| 2017 | 3420 | 98.7 |
| 2018 | 3363 | 97.1 |
| 2019 | 3118 | 90 |
| 2020 | 3071 | 88.7 |
| 2021 | 3014 | 87 |
| 2022 | 2978 | 86 |
| 2023 | 2944 | 85 |
| 2024 | 2920 | 84.3 |
| 2025 | 2853 | 82.4 |
| 2026 | 2813 | 81.2 |
| 2027 | 2776 | 80.1 |


## Measures by year

`looks_suppressed` = the condition has ERRs but CMS never marked it 'Y' for a penalty.

| fy | condition | hospital_rows | with_err | cms_indicator_y | penalized | median_err | suppressed_per_cms | looks_suppressed |
|---|---|---|---|---|---|---|---|---|
| 2016 | ami | 3464 | 3464 | 0 | 1069 | 0.9438 | False | False |
| 2016 | hf | 3464 | 3464 | 0 | 1481 | 0.9846 | False | False |
| 2016 | pn | 3464 | 3464 | 0 | 1477 | 0.9873 | False | False |
| 2016 | tha_tka | 3464 | 3464 | 0 | 1243 | 0.9385 | False | False |
| 2017 | ami | 3448 | 3448 | 0 | 1063 | 0.9491 | False | False |
| 2017 | cabg | 3448 | 3448 | 0 | 496 | 0 | False | False |
| 2017 | hf | 3448 | 3448 | 0 | 1410 | 0.981 | False | False |
| 2017 | tha_tka | 3448 | 3448 | 0 | 1212 | 0.9379 | False | False |
| 2018 | ami | 3414 | 3027 | 0 | 1412 | 0.9975 | False | False |
| 2018 | cabg | 3414 | 1163 | 0 | 564 | 0.9972 | False | False |
| 2018 | hf | 3414 | 3160 | 0 | 1557 | 0.9992 | False | False |
| 2018 | pn | 3414 | 3199 | 0 | 1524 | 0.9962 | False | False |
| 2018 | tha_tka | 3414 | 2885 | 0 | 1326 | 0.9937 | False | False |
| 2019 | ami | 3173 | 2918 | 1076 | 1076 | 0.9977 | False | False |
| 2019 | cabg | 3173 | 1148 | 496 | 496 | 0.9992 | False | False |
| 2019 | copd | 3173 | 3034 | 1418 | 1418 | 0.9975 | False | False |
| 2019 | hf | 3173 | 3024 | 1414 | 1414 | 0.9981 | False | False |
| 2019 | pn | 3173 | 3053 | 1436 | 1436 | 0.9966 | False | False |
| 2019 | tha_tka | 3173 | 2812 | 1233 | 1233 | 0.9965 | False | False |
| 2020 | ami | 3130 | 2873 | 1054 | 1054 | 0.9978 | False | False |
| 2020 | cabg | 3130 | 1140 | 493 | 493 | 0.9978 | False | False |
| 2020 | copd | 3130 | 3001 | 1400 | 1400 | 0.9979 | False | False |
| 2020 | hf | 3130 | 2985 | 1412 | 1412 | 0.9991 | False | False |
| 2020 | pn | 3130 | 3020 | 1424 | 1424 | 0.9967 | False | False |
| 2020 | tha_tka | 3130 | 2785 | 1218 | 1218 | 0.9957 | False | False |
| 2021 | ami | 3080 | 2822 | 1014 | 1014 | 0.997 | False | False |
| 2021 | cabg | 3080 | 1114 | 486 | 486 | 0.9971 | False | False |
| 2021 | copd | 3080 | 2955 | 1380 | 1380 | 0.9982 | False | False |
| 2021 | hf | 3080 | 2951 | 1392 | 1392 | 1 | False | False |
| 2021 | pn | 3080 | 2977 | 1415 | 1415 | 0.9977 | False | False |
| 2021 | tha_tka | 3080 | 2740 | 1202 | 1202 | 0.9969 | False | False |
| 2022 | ami | 3047 | 2764 | 939 | 939 | 0.9976 | False | False |
| 2022 | cabg | 3047 | 1096 | 445 | 445 | 0.9946 | False | False |
| 2022 | copd | 3047 | 2916 | 1337 | 1337 | 0.9975 | False | False |
| 2022 | hf | 3047 | 2916 | 1364 | 1364 | 1 | False | False |
| 2022 | pn | 3047 | 2943 | 1383 | 1383 | 0.9977 | False | False |
| 2022 | tha_tka | 3047 | 2700 | 1147 | 1147 | 0.9965 | False | False |
| 2023 | ami | 3044 | 2715 | 903 | 903 | 0.9968 | False | False |
| 2023 | cabg | 3044 | 1087 | 432 | 432 | 0.9951 | False | False |
| 2023 | copd | 3044 | 2910 | 1259 | 1259 | 0.9975 | False | False |
| 2023 | hf | 3044 | 2920 | 1336 | 1336 | 0.9995 | False | False |
| 2023 | pn | 3044 | 0 | 0 | 0 |  | True | False |
| 2023 | tha_tka | 3044 | 2675 | 1078 | 1078 | 0.9956 | False | False |
| 2024 | ami | 3037 | 2715 | 866 | 866 | 0.9971 | False | False |
| 2024 | cabg | 3037 | 1067 | 427 | 427 | 0.9984 | False | False |
| 2024 | copd | 3037 | 2901 | 1145 | 1145 | 0.9965 | False | False |
| 2024 | hf | 3037 | 2905 | 1313 | 1313 | 1 | False | False |
| 2024 | pn | 3037 | 2937 | 1340 | 1340 | 0.9978 | False | False |
| 2024 | tha_tka | 3037 | 2627 | 906 | 906 | 0.9934 | False | False |
| 2025 | ami | 2980 | 2671 | 900 | 900 | 0.9969 | False | False |
| 2025 | cabg | 2980 | 1047 | 433 | 433 | 0.9988 | False | False |
| 2025 | copd | 2980 | 2842 | 1150 | 1150 | 0.9964 | False | False |
| 2025 | hf | 2980 | 2849 | 1307 | 1307 | 1.001 | False | False |
| 2025 | pn | 2980 | 2873 | 1340 | 1340 | 0.9976 | False | False |
| 2025 | tha_tka | 2980 | 2561 | 779 | 779 | 0.9924 | False | False |
| 2026 | ami | 3063 | 2665 | 882 | 882 | 0.9972 | False | False |
| 2026 | cabg | 3063 | 1061 | 438 | 438 | 0.9974 | False | False |
| 2026 | copd | 3063 | 2855 | 1142 | 1142 | 0.997 | False | False |
| 2026 | hf | 3063 | 2858 | 1292 | 1292 | 0.9982 | False | False |
| 2026 | pn | 3063 | 2884 | 1322 | 1322 | 0.9963 | False | False |
| 2026 | tha_tka | 3063 | 2554 | 706 | 706 | 0.9922 | False | False |
| 2027 | ami | 2912 | 2603 | 915 | 915 | 0.9977 | False | False |
| 2027 | cabg | 2912 | 1060 | 453 | 453 | 0.9945 | False | False |
| 2027 | copd | 2912 | 2795 | 1263 | 1263 | 0.9967 | False | False |
| 2027 | hf | 2912 | 2795 | 1300 | 1300 | 0.9991 | False | False |
| 2027 | pn | 2912 | 2813 | 1349 | 1349 | 0.9972 | False | False |
| 2027 | tha_tka | 2912 | 2509 | 751 | 751 | 0.9943 | False | False |


## Known breaks in the series

From `seeds/hrrp_known_breaks.csv`; each row links the CMS page that announced it. Rows they touch carry `covid_2020_excluded`, `measure_suppressed` and `break_notes` in the panel.

| fy | condition | break_type | description | source_url |
|---|---|---|---|---|
| 2016 | cabg | not_in_program | CABG surgery joined HRRP in FY2017, so FY2016 has five conditions | https://www.cms.gov/medicare/medicare-fee-for-service-payment/acuteinpatientpps/hrrp-archives |
| 2019 | all | methodology_change | Stratified methodology starts: each hospital is compared with the median ERR of its dual-proportion peer group (quintile 1-5); before FY2019 a condition was penalized when ERR > 1 | https://www.qualityreportingcenter.com/globalassets/iqr2020events/hrrp080720/hrrp_fy2021_hsrrelease_webinar_slides_vfinal508.pdf |
| 2022 | all | covid_2020_exclusion | Performance period ends December 1, 2019 instead of June 30, 2020; claims for January 1 - June 30, 2020 are not used (COVID-19 exception) | https://www.qualityreportingcenter.com/globalassets/iqr2021events/vbp81921/vbp_transcript081921_vfinal508.pdf |
| 2023 | all | covid_2020_exclusion | January - June 2020 is excluded from the performance period (COVID-19) | https://www.cms.gov/medicare/medicare-fee-for-service-payment/acuteinpatientpps/hrrp-archives |
| 2023 | pn | measure_suppressed | Pneumonia readmission measure suppressed from FY2023 payment reduction calculations because of COVID-19 | https://www.cms.gov/medicare/medicare-fee-for-service-payment/acuteinpatientpps/hrrp-archives |
| 2024 | all | covid_2020_exclusion | January - June 2020 is excluded from the performance period (COVID-19) | https://www.cms.gov/medicare/medicare-fee-for-service-payment/acuteinpatientpps/hrrp-archives |
| 2027 | all | period_length_change | Performance period shortened from 3 years to 2 years (July 1, 2023 - June 30, 2025) | https://www.cms.gov/files/document/fy-2027-hrrp-fact-sheet-pdf.pdf |


## How to read the panel

- Before FY2019 a condition was penalized when ERR > 1; from FY2019 when ERR > the median of the hospital's dual-proportion peer group. `penalized_source` says which rule each row used.
- FY2022-FY2024 leave out January-June 2020, and FY2022's period stops at December 1, 2019. Trends across FY2021-FY2025 mix periods with and without that half-year.
- FY2023 pneumonia ERRs are kept but did not count toward payment (`measure_suppressed`).
- FY2027 measures 2 years of discharges instead of 3, so its ERRs rest on fewer cases.
