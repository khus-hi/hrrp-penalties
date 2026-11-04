# FY2026 HRRP penalty estimate

_Generated 2026-11-04 02:24 UTC by `python -m analysis.penalty_report`. Method and assumptions: [penalty_method.md](penalty_method.md). Data-quality assertions failing: 0; warnings: 1 ([data_quality_report.md](data_quality_report.md))._

## National

| hospitals_in_hrrp_file | hospitals_with_cms_factor | hospitals_penalized | pct_penalized | hospitals_at_3pct_cap | mean_factor | hospitals_estimable | penalized_but_not_estimable | est_total_penalty_usd | median_penalty_penalized_usd | max_penalty_usd | est_total_base_drg_usd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3055 | 2937 | 2302 | 78.4 | 15 | 0.9966 | 2900 | 23 | 315,602,534 | 52,443 | 5,846,204 | 85,706,654,970 |


### Uncertainty: 90% interval for the national total

| | Point estimate | 90% interval, same hospitals | Contains point | 90% interval, all penalized hospitals |
|---|---|---|---|---|
| national | $315.6M | $314.6M to $335.7M | yes | $316.1M to $337.3M |

"Same hospitals" covers only hospitals with a usable cost-report base, like the point estimate. "All penalized hospitals" also estimates a base for the penalized hospitals that have none, so it sits higher. Method: [penalty_uncertainty.md](penalty_uncertainty.md).

## Check against CMS

### Counts in CMS's own FY2026 supplemental file

| hospitals_in_cms_file | penalized_in_cms_file | at_cap_in_cms_file | mean_factor_in_cms_file |
|---|---|---|---|
| 2945 | 2304 | 15 | 0.9966 |


### Does the formula reproduce CMS's factor?

| hospitals_compared | mismatches | max_abs_diff | median_abs_diff |
|---|---|---|---|
| 2945 | 0 | 5e-05 | 1.9e-05 |


CMS penalty indicator values by condition:

| condition | penalty_indicator | n | n_err_above_median |
|---|---|---|---|
| ami | N | 2063 | 433 |
| ami | Y | 882 | 882 |
| cabg | N | 2507 | 86 |
| cabg | Y | 438 | 438 |
| copd | N | 1803 | 264 |
| copd | Y | 1142 | 1142 |
| hf | N | 1653 | 115 |
| hf | Y | 1292 | 1292 |
| pn | N | 1623 | 97 |
| pn | Y | 1322 | 1322 |
| tha_tka | N | 2239 | 556 |
| tha_tka | Y | 706 | 706 |


### What the FY2026 final rule says (verbatim text around HRRP mentions that include a $ amount or hospital count)

_Searched 2025-14681.htm: 4,485,518 characters, 117 HRRP mentions, 1 with a $ or hospital count._

> ...dex admissions,'' that are included when calculating each measure. This cohort is the set of hospitalizations that meet all the inclusion and exclusion criteria. For measure cohort details of the most recent versions of the Hospital Readmissions Reduction Program measure set, we refer readers to the measure methodology report and measure risk adjustment statistical model on our website at: https://qualitynet.cms.gov/inpatient/measures/readmission/methodology . Including MA beneficiaries in hospital outcome measures would help ensure that hospital quality would be measured across all Medicare beneficiaries and not just the Fee-For-Service (FFS) population. In 2024, 50 percent of eligible Medicare beneficiaries--or 34.3 million people--were covered by MA plans.\165\ It is projected that nearly two- thirds of all Medicare enrollees will be enrolled in MA plans by 2030.\166\ Consequently, using FFS-only beneficiaries may ex...


## By condition

| condition | hospitals_where_it_contributes | est_penalty_usd | pct_of_total |
|---|---|---|---|
| Pneumonia | 1321 | 103,136,580 | 32.7 |
| Heart failure | 1291 | 72,262,282 | 22.9 |
| AMI | 882 | 46,145,662 | 14.6 |
| CABG | 438 | 40,072,409 | 12.7 |
| Hip/knee | 705 | 38,318,817 | 12.1 |
| COPD | 1142 | 15,666,784 | 5 |


90% intervals by condition:

| | Point estimate | 90% interval, same hospitals | Contains point | 90% interval, all penalized hospitals |
|---|---|---|---|---|
| AMI | $46.1M | $45.9M to $49.4M | yes | $46.1M to $49.6M |
| Heart failure | $72.3M | $72.0M to $76.4M | yes | $72.5M to $76.9M |
| Pneumonia | $103.1M | $102.7M to $109.3M | yes | $103.1M to $109.7M |
| COPD | $15.7M | $15.6M to $16.7M | yes | $15.7M to $16.7M |
| CABG | $40.1M | $39.8M to $43.4M | yes | $40.0M to $43.6M |
| Hip/knee | $38.3M | $38.1M to $41.0M | yes | $38.4M to $41.3M |

"Same hospitals" covers only hospitals with a usable cost-report base, like the point estimate. "All penalized hospitals" also estimates a base for the penalized hospitals that have none, so it sits higher. Method: [penalty_uncertainty.md](penalty_uncertainty.md).

## By parent system

| parent_system | hospitals_in_hrrp_file | with_cms_factor | penalized | pct_penalized | mean_factor | estimable | est_total_penalty_usd | est_avg_penalty_penalized_usd | penalty_pct_of_base_drg |
|---|---|---|---|---|---|---|---|---|---|
| HCA Healthcare | 145 | 144 | 137 | 95.1 | 0.9945 | 144 | 26,138,176 | 190,790 | 0.569 |
| Tenet Healthcare | 61 | 59 | 46 | 78 | 0.9942 | 59 | 4,870,438 | 105,879 | 0.47 |
| Community Health Systems | 50 | 49 | 44 | 89.8 | 0.9953 | 49 | 4,396,223 | 99,914 | 0.55 |
| Universal Health Services | 25 | 22 | 21 | 95.5 | 0.9962 | 22 | 3,005,030 | 143,097 | 0.469 |
| Not one of the four chains | 2774 | 2663 | 2054 | 77.1 | 0.9967 | 2626 | 277,192,667 | 136,481 | 0.369 |


90% intervals by chain:

| | Point estimate | 90% interval, same hospitals | Contains point | 90% interval, all penalized hospitals |
|---|---|---|---|---|
| HCA Healthcare | $26.1M | $25.9M to $29.1M | yes | $25.9M to $29.1M |
| Tenet Healthcare | $4.9M | $4.8M to $5.8M | yes | $4.8M to $5.8M |
| Community Health Systems | $4.4M | $4.3M to $4.9M | yes | $4.3M to $4.9M |
| Universal Health Services | $3.0M | $2.9M to $3.2M | yes | $2.9M to $3.2M |

"Same hospitals" covers only hospitals with a usable cost-report base, like the point estimate. "All penalized hospitals" also estimates a base for the penalized hospitals that have none, so it sits higher. Method: [penalty_uncertainty.md](penalty_uncertainty.md).

| parent_system | condition | est_penalty_usd |
|---|---|---|
| Community Health Systems | CABG | 1,194,269 |
| Community Health Systems | Pneumonia | 973,903 |
| Community Health Systems | AMI | 900,765 |
| Community Health Systems | Heart failure | 674,987 |
| Community Health Systems | Hip/knee | 466,878 |
| Community Health Systems | COPD | 185,420 |
| HCA Healthcare | Pneumonia | 8,334,795 |
| HCA Healthcare | Heart failure | 4,998,554 |
| HCA Healthcare | AMI | 4,840,951 |
| HCA Healthcare | Hip/knee | 3,764,888 |
| HCA Healthcare | CABG | 3,398,511 |
| HCA Healthcare | COPD | 800,476 |
| Tenet Healthcare | Pneumonia | 1,554,925 |
| Tenet Healthcare | Hip/knee | 1,188,223 |
| Tenet Healthcare | AMI | 728,532 |
| Tenet Healthcare | Heart failure | 653,736 |
| Tenet Healthcare | CABG | 638,109 |
| Tenet Healthcare | COPD | 106,913 |
| Universal Health Services | Pneumonia | 1,687,116 |
| Universal Health Services | Heart failure | 655,875 |
| Universal Health Services | CABG | 250,665 |
| Universal Health Services | Hip/knee | 200,523 |
| Universal Health Services | AMI | 137,060 |
| Universal Health Services | COPD | 73,791 |


## By ownership type

| hospital_ownership | hospitals_in_hrrp_file | with_cms_factor | penalized | pct_penalized | mean_factor | estimable | est_total_penalty_usd | est_avg_penalty_penalized_usd | penalty_pct_of_base_drg |
|---|---|---|---|---|---|---|---|---|---|
| Voluntary non-profit - Private | 1474 | 1422 | 1156 | 81.3 | 0.9967 | 1402 | 186,206,496 | 163,196 | 0.385 |
| Proprietary | 619 | 587 | 456 | 77.7 | 0.9957 | 577 | 57,480,749 | 127,170 | 0.538 |
| Voluntary non-profit - Church | 199 | 194 | 151 | 77.8 | 0.9969 | 192 | 22,555,907 | 151,382 | 0.358 |
| Voluntary non-profit - Other | 241 | 229 | 192 | 83.8 | 0.9966 | 228 | 20,139,445 | 105,442 | 0.317 |
| Government - Hospital District or Authority | 220 | 217 | 159 | 73.3 | 0.9972 | 216 | 14,796,756 | 93,650 | 0.287 |
| Government - Local | 135 | 135 | 109 | 80.7 | 0.9968 | 135 | 6,101,411 | 55,976 | 0.277 |
| Government - State | 45 | 41 | 32 | 78 | 0.9981 | 40 | 4,779,271 | 149,352 | 0.216 |
| (not in General Information) | 20 | 18 | 13 | 72.2 | 0.9953 | 16 | 1,208,853 | 92,989 | 0.833 |
| Physician | 70 | 64 | 20 | 31.3 | 0.9965 | 64 | 1,199,769 | 59,988 | 0.218 |
| Government - Federal | 23 | 22 | 12 | 54.5 | 0.998 | 22 | 1,127,059 | 93,922 | 0.386 |
| Tribal | 9 | 8 | 2 | 25 | 0.9998 | 8 | 6,818 | 3,409 | 0.048 |


## By state

| state | hospitals_in_hrrp_file | with_cms_factor | penalized | pct_penalized | mean_factor | estimable | est_total_penalty_usd | est_avg_penalty_penalized_usd | penalty_pct_of_base_drg |
|---|---|---|---|---|---|---|---|---|---|
| CA | 277 | 273 | 217 | 79.5 | 0.9968 | 272 | 37,527,266 | 173,737 | 0.34 |
| FL | 169 | 167 | 155 | 92.8 | 0.995 | 165 | 34,818,144 | 226,092 | 0.55 |
| MA | 55 | 53 | 47 | 88.7 | 0.9916 | 53 | 22,419,561 | 477,012 | 0.75 |
| NY | 129 | 125 | 104 | 83.2 | 0.9963 | 123 | 21,347,028 | 207,253 | 0.356 |
| NJ | 61 | 61 | 56 | 91.8 | 0.9937 | 61 | 19,331,532 | 345,206 | 0.639 |
| TX | 284 | 272 | 192 | 70.6 | 0.9968 | 269 | 19,302,029 | 100,531 | 0.344 |
| PA | 133 | 128 | 114 | 89.1 | 0.9962 | 118 | 17,279,571 | 163,015 | 0.481 |
| IL | 114 | 114 | 100 | 87.7 | 0.9958 | 114 | 17,136,023 | 171,360 | 0.491 |
| OH | 118 | 116 | 97 | 83.6 | 0.9962 | 114 | 10,415,105 | 109,633 | 0.392 |
| MI | 90 | 85 | 72 | 84.7 | 0.9964 | 85 | 8,305,880 | 115,359 | 0.398 |
| GA | 94 | 92 | 77 | 83.7 | 0.9968 | 92 | 7,590,428 | 98,577 | 0.359 |
| TN | 78 | 76 | 60 | 78.9 | 0.9959 | 74 | 7,394,240 | 127,487 | 0.427 |
| VA | 71 | 71 | 56 | 78.9 | 0.9966 | 65 | 6,904,895 | 132,786 | 0.333 |
| AZ | 64 | 63 | 51 | 81 | 0.9968 | 61 | 6,624,060 | 132,481 | 0.371 |
| IN | 82 | 79 | 64 | 81 | 0.9968 | 78 | 6,586,104 | 104,541 | 0.368 |
| MO | 63 | 63 | 54 | 85.7 | 0.9966 | 63 | 5,852,245 | 108,375 | 0.351 |
| SC | 51 | 51 | 43 | 84.3 | 0.9967 | 49 | 5,715,320 | 136,079 | 0.442 |
| AL | 77 | 73 | 60 | 82.2 | 0.9964 | 73 | 5,417,310 | 90,288 | 0.525 |
| KY | 59 | 59 | 53 | 89.8 | 0.9951 | 58 | 5,166,426 | 99,354 | 0.499 |
| LA | 82 | 79 | 51 | 64.6 | 0.9968 | 79 | 4,335,283 | 85,006 | 0.45 |
| NC | 80 | 78 | 64 | 82.1 | 0.9968 | 78 | 4,328,247 | 67,629 | 0.207 |
| CT | 27 | 26 | 23 | 88.5 | 0.996 | 25 | 4,223,981 | 183,651 | 0.402 |
| MS | 59 | 54 | 46 | 85.2 | 0.9965 | 53 | 4,204,868 | 91,410 | 0.529 |
| NV | 22 | 20 | 18 | 90 | 0.9957 | 20 | 3,573,487 | 198,527 | 0.448 |
| OK | 76 | 71 | 47 | 66.2 | 0.9968 | 70 | 3,436,181 | 73,110 | 0.305 |
| AR | 43 | 42 | 33 | 78.6 | 0.9966 | 42 | 3,342,267 | 101,281 | 0.395 |
| WV | 25 | 24 | 19 | 79.2 | 0.996 | 24 | 2,964,812 | 156,043 | 0.569 |
| WI | 65 | 65 | 43 | 66.2 | 0.9977 | 65 | 2,459,984 | 57,209 | 0.203 |
| MN | 46 | 46 | 30 | 65.2 | 0.9985 | 46 | 2,063,061 | 68,769 | 0.154 |
| IA | 30 | 30 | 20 | 66.7 | 0.9973 | 30 | 1,846,039 | 92,302 | 0.256 |
| KS | 44 | 44 | 26 | 59.1 | 0.9975 | 44 | 1,810,929 | 69,651 | 0.209 |
| WA | 46 | 46 | 29 | 63 | 0.999 | 46 | 1,756,735 | 60,577 | 0.105 |
| CO | 51 | 51 | 23 | 45.1 | 0.999 | 51 | 1,374,990 | 59,782 | 0.133 |
| NH | 13 | 13 | 12 | 92.3 | 0.9971 | 13 | 1,302,480 | 108,540 | 0.286 |
| NE | 25 | 23 | 15 | 65.2 | 0.9983 | 23 | 827,615 | 55,174 | 0.145 |
| AK | 8 | 8 | 6 | 75 | 0.9965 | 8 | 816,854 | 136,142 | 0.336 |
| RI | 10 | 10 | 6 | 60 | 0.9965 | 10 | 732,363 | 122,061 | 0.307 |
| SD | 17 | 16 | 13 | 81.3 | 0.9971 | 16 | 691,026 | 53,156 | 0.187 |
| DE | 6 | 6 | 4 | 66.7 | 0.9984 | 6 | 575,545 | 143,886 | 0.252 |
| UT | 32 | 31 | 17 | 54.8 | 0.9979 | 31 | 566,943 | 33,350 | 0.117 |
| HI | 11 | 11 | 10 | 90.9 | 0.9981 | 11 | 558,765 | 55,877 | 0.193 |
| NM | 26 | 25 | 15 | 60 | 0.9982 | 25 | 557,976 | 37,198 | 0.163 |
| OR | 32 | 32 | 17 | 53.1 | 0.9993 | 32 | 500,709 | 29,453 | 0.06 |
| DC | 6 | 6 | 5 | 83.3 | 0.9987 | 6 | 332,054 | 66,411 | 0.083 |
| MT | 11 | 11 | 7 | 63.6 | 0.999 | 11 | 286,004 | 40,858 | 0.089 |
| VT | 6 | 6 | 5 | 83.3 | 0.9979 | 6 | 226,842 | 45,368 | 0.16 |
| WY | 8 | 8 | 7 | 87.5 | 0.9985 | 8 | 226,345 | 32,335 | 0.211 |
| ME | 13 | 13 | 7 | 53.8 | 0.9977 | 13 | 223,125 | 31,875 | 0.095 |
| ND | 7 | 7 | 6 | 85.7 | 0.9991 | 7 | 175,227 | 29,205 | 0.061 |
| ID | 16 | 14 | 6 | 42.9 | 0.9995 | 14 | 148,630 | 24,772 | 0.044 |
| MD | 43 | 0 | 0 |  |  | 0 |  |  |  |


## Massachusetts: every hospital

| ccn | facility_name | hospital_ownership | parent_system | payment_adjustment_factor | payment_cut_pct | est_base_drg_usd | est_penalty_usd | penalty_drivers | estimate_quality |
|---|---|---|---|---|---|---|---|---|---|
| 220077 | BAYSTATE MEDICAL CENTER | Voluntary non-profit - Private |  | 0.9811 | 1.89 | 167,038,922 | 3,157,036 | AMI 38%, CABG 33%, Pneumonia 19%, Heart failure 7%, COPD 3% | ok: full-year cost report |
| 220100 | SOUTH SHORE HOSPITAL | Voluntary non-profit - Private |  | 0.9848 | 1.52 | 138,691,862 | 2,108,116 | Pneumonia 63%, AMI 17%, Heart failure 15%, COPD 5% | ok: full-year cost report |
| 220012 | CAPE COD HOSPITAL | Voluntary non-profit - Private |  | 0.9844 | 1.56 | 118,370,280 | 1,846,576 | Pneumonia 39%, Heart failure 28%, AMI 20%, Hip/knee 8%, COPD 3%, CABG 2% | ok: full-year cost report |
| 220105 | WINCHESTER HOSPITAL | Voluntary non-profit - Private |  | 0.97 | 3 | 44,566,328 | 1,336,990 | Pneumonia 35%, Heart failure 32%, Hip/knee 27%, COPD 6% | ok: full-year cost report |
| 220110 | BRIGHAM AND WOMEN'S HOSPITAL | Voluntary non-profit - Private |  | 0.9948 | 0.52 | 242,315,472 | 1,260,040 | AMI 91%, Pneumonia 9% | ok: full-year cost report |
| 220090 | MILFORD REGIONAL MEDICAL CENTER | Voluntary non-profit - Other |  | 0.9703 | 2.97 | 39,859,273 | 1,183,820 | Pneumonia 46%, Heart failure 41%, COPD 13% | ok: full-year cost report |
| 220073 | BROWN UNIVERSITY HEALTH MORTON HOSPITAL | Proprietary |  | 0.97 | 3 | 29,657,767 | 889,733 | Hip/knee 62%, Pneumonia 22%, Heart failure 11%, COPD 5% | ok but annualised: partial-year cost report |
| 220008 | STURDY MEMORIAL HOSPITAL | Voluntary non-profit - Other |  | 0.9748 | 2.52 | 35,253,301 | 888,383 | Pneumonia 43%, Hip/knee 31%, Heart failure 19%, COPD 8% | ok: full-year cost report |
| 220086 | BETH ISRAEL DEACONESS MEDICAL CENTER | Voluntary non-profit - Private |  | 0.9954 | 0.46 | 177,290,161 | 815,535 | AMI 62%, CABG 32%, Pneumonia 6% | ok: full-year cost report |
| 220036 | BOSTON MEDICAL CENTER-BRIGHTON | Proprietary |  | 0.9802 | 1.98 | 40,083,701 | 793,657 | AMI 69%, CABG 17%, Heart failure 13%, COPD 1% | ok but annualised: partial-year cost report |
| 220116 | TUFTS MEDICAL CENTER | Voluntary non-profit - Private |  | 0.9901 | 0.99 | 74,450,167 | 737,057 | AMI 45%, CABG 33%, Hip/knee 16%, Heart failure 3%, COPD 2%, Pneumonia 1% | ok: full-year cost report |
| 220063 | LOWELL GENERAL HOSPITAL | Voluntary non-profit - Private |  | 0.9899 | 1.01 | 60,318,860 | 609,220 | Pneumonia 39%, Heart failure 27%, AMI 20%, COPD 15% | ok: full-year cost report |
| 220070 | MELROSEWAKEFIELD HEALTHCARE | Voluntary non-profit - Private |  | 0.9808 | 1.92 | 30,332,077 | 582,376 | Pneumonia 47%, Hip/knee 20%, Heart failure 17%, COPD 13%, AMI 4% | ok: full-year cost report |
| 220171 | LAHEY HOSPITAL & MEDICAL CENTER, BURLINGTON | Voluntary non-profit - Private |  | 0.996 | 0.4 | 143,548,607 | 574,194 | Hip/knee 39%, CABG 30%, Heart failure 23%, COPD 4%, AMI 4% | ok: full-year cost report |
| 220029 | ANNA JAQUES HOSPITAL | Voluntary non-profit - Private |  | 0.9777 | 2.23 | 21,888,490 | 488,113 | Hip/knee 41%, Pneumonia 34%, COPD 14%, Heart failure 11% | ok: full-year cost report |
| 220111 | GOOD SAMARITAN MEDICAL CENTER | Proprietary |  | 0.9895 | 1.05 | 45,031,320 | 472,829 | Pneumonia 42%, Heart failure 39%, Hip/knee 12%, COPD 6% | ok but annualised: partial-year cost report |
| 220083 | BETH ISRAEL DEACONESS HOSPITAL - NEEDHAM | Voluntary non-profit - Private |  | 0.9841 | 1.59 | 26,963,030 | 428,712 | Pneumonia 72%, Heart failure 28% | ok: full-year cost report |
| 220080 | HOLY FAMILY HOSPITAL | Proprietary |  | 0.9859 | 1.41 | 27,342,664 | 385,532 | Hip/knee 62%, Pneumonia 16%, Heart failure 15%, COPD 5%, AMI 1% | ok but annualised: partial-year cost report |
| 220175 | METROWEST MEDICAL CENTER | Voluntary non-profit - Private | Tenet Healthcare | 0.9864 | 1.36 | 24,521,443 | 333,492 | Pneumonia 57%, Heart failure 37%, AMI 7% | ok: full-year cost report |
| 220035 | NORTH SHORE MEDICAL CENTER - | Voluntary non-profit - Private |  | 0.9957 | 0.43 | 75,497,790 | 324,640 | Pneumonia 97%, COPD 3% | ok: full-year cost report |
| 220101 | NEWTON-WELLESLEY HOSPITAL | Voluntary non-profit - Private |  | 0.9958 | 0.42 | 75,083,441 | 315,350 | Hip/knee 86%, Pneumonia 14%, AMI 1% | ok: full-year cost report |
| 220135 | FALMOUTH HOSPITAL | Voluntary non-profit - Private |  | 0.9913 | 0.87 | 36,172,972 | 314,705 | Pneumonia 69%, Heart failure 26%, COPD 5% | ok: full-year cost report |
| 220163 | UMASS MEMORIAL MEDICAL CENTER/UNIVERSITY CAMPUS | Voluntary non-profit - Private |  | 0.9981 | 0.19 | 154,600,145 | 293,740 | CABG 71%, AMI 28%, Hip/knee 1%, COPD 1% | ok: full-year cost report |
| 220015 | COOLEY DICKINSON HOSPITAL INC,THE | Voluntary non-profit - Private |  | 0.9907 | 0.93 | 24,348,621 | 226,442 | Heart failure 78%, Hip/knee 12%, COPD 11% | ok: full-year cost report |
| 220001 | UMASS MEMORIAL HEALTHALLIANCE HOSPITALS | Voluntary non-profit - Other |  | 0.9921 | 0.79 | 26,301,675 | 207,783 | Pneumonia 71%, Heart failure 18%, COPD 6%, AMI 4% | ok: full-year cost report |
| 220033 | NORTHEAST HOSPITAL CORPORATION | Voluntary non-profit - Private |  | 0.9972 | 0.28 | 70,482,666 | 197,351 | Heart failure 68%, COPD 22%, AMI 10% | ok: full-year cost report |
| 220049 | MARLBOROUGH HOSPITAL | Voluntary non-profit - Private |  | 0.986 | 1.4 | 13,582,366 | 190,153 | Pneumonia 64%, Heart failure 21%, COPD 15% | ok: full-year cost report |
| 220019 | UMASS MEMORIAL HEALTH - HARRINGTON HOSPITAL | Voluntary non-profit - Private |  | 0.9876 | 1.24 | 14,066,062 | 174,419 | Pneumonia 51%, Heart failure 40%, COPD 8% | ok: full-year cost report |
| 220176 | ST VINCENT HOSPITAL | Proprietary | Tenet Healthcare | 0.9955 | 0.45 | 38,444,805 | 173,002 | AMI 24%, Hip/knee 23%, CABG 22%, Pneumonia 18%, Heart failure 13% | ok: full-year cost report |
| 220002 | MOUNT AUBURN HOSPITAL | Voluntary non-profit - Private |  | 0.9955 | 0.45 | 36,366,666 | 163,650 | Pneumonia 100% | ok: full-year cost report |
| 220066 | MERCY MEDICAL CTR | Voluntary non-profit - Private |  | 0.9931 | 0.69 | 23,187,093 | 159,991 | Pneumonia 55%, COPD 26%, Heart failure 19% | ok: full-year cost report |
| 220024 | HOLYOKE MEDICAL CENTER | Voluntary non-profit - Private |  | 0.9925 | 0.75 | 19,359,779 | 145,198 | Pneumonia 58%, Heart failure 27%, COPD 9%, Hip/knee 6% | ok: full-year cost report |
| 220108 | BETH ISRAEL DEACONESS HOSPITAL - MILTON | Government - Federal |  | 0.9958 | 0.42 | 33,816,394 | 142,029 | Pneumonia 81%, COPD 19% | ok: full-year cost report |
| 220030 | BAYSTATE WING HOSPITAL | Voluntary non-profit - Other |  | 0.9936 | 0.64 | 14,044,512 | 89,885 | Heart failure 46%, COPD 29%, Pneumonia 26% | ok: full-year cost report |
| 220095 | HEYWOOD HOSPITAL - | Voluntary non-profit - Private |  | 0.9948 | 0.52 | 12,399,431 | 64,477 | COPD 40%, Pneumonia 35%, Heart failure 26% | ok: full-year cost report |
| 220020 | SAINT ANNE'S HOSPITAL | Proprietary |  | 0.9981 | 0.19 | 32,452,519 | 61,660 | Heart failure 51%, AMI 25%, COPD 24% | ok but annualised: partial-year cost report |
| 220084 | EMERSON HOSPITAL - | Voluntary non-profit - Private |  | 0.9978 | 0.22 | 24,771,713 | 54,498 | Pneumonia 67%, COPD 33% | ok: full-year cost report |
| 220010 | MERRIMACK HEALTH LAWRENCE HOSPITAL | Voluntary non-profit - Private |  | 0.9985 | 0.15 | 35,631,910 | 53,448 | AMI 72%, Heart failure 28% | ok: full-year cost report |
| 220046 | BERKSHIRE MEDICAL CENTER | Voluntary non-profit - Other |  | 0.9993 | 0.07 | 60,920,870 | 42,645 | Heart failure 100% | ok: full-year cost report |
| 220065 | BAYSTATE NOBLE HOSPITAL | Voluntary non-profit - Private |  | 0.9958 | 0.42 | 9,890,059 | 41,538 | Heart failure 74%, Pneumonia 26% | ok: full-year cost report |
| 220016 | BAYSTATE FRANKLIN MEDICAL CENTER | Voluntary non-profit - Private |  | 0.9979 | 0.21 | 14,084,327 | 29,577 | COPD 64%, Heart failure 36% | ok: full-year cost report |
| 220031 | BOSTON MEDICAL CENTER | Voluntary non-profit - Private |  | 0.9995 | 0.05 | 48,226,924 | 24,113 | COPD 100% | ok: full-year cost report |
| 220177 | NANTUCKET COTTAGE HOSPITAL | Voluntary non-profit - Private |  | 0.9915 | 0.85 | 2,131,339 | 18,116 | Pneumonia 55%, Heart failure 45% | ok: full-year cost report |
| 220098 | NASHOBA VALLEY MEDICAL CENTER | Proprietary |  | 0.9982 | 0.18 | 5,105,941 | 9,191 | Pneumonia 67%, COPD 26%, Heart failure 7% | ok but annualised: partial-year cost report |
| 220060 | BETH ISRAEL DEACONESS HOSPITAL PLYMOUTH | Voluntary non-profit - Private |  | 0.9999 | 0.01 | 68,204,425 | 6,820 | AMI 100% | ok: full-year cost report |
| 220052 | SIGNATURE HEALTHCARE BROCKTON HOSPITAL | Voluntary non-profit - Other |  | 0.9984 | 0.16 | 2,109,595 | 3,375 | COPD 100% | ok: full-year cost report |
| 220017 | CARNEY HOSPITAL | Proprietary |  | 0.9999 | 0.01 | 3,504,967 | 350 | Pneumonia 100% | ok but annualised: partial-year cost report |
| 220119 | BRIGHAM AND WOMEN FAULKNER HOSPITAL | Voluntary non-profit - Private |  | 1 | 0 | 37,644,239 | 0 |  | ok: full-year cost report |
| 220011 | CAMBRIDGE HEALTH ALLIANCE | Government - Local |  | 1 | 0 | 13,555,161 | 0 |  | ok: full-year cost report |
| 220075 | MASSACHUSETTS EYE AND EAR INFIRMARY - | Voluntary non-profit - Private |  | 1 | 0 | 5,410,251 | 0 |  | ok: full-year cost report |
| 220071 | MASSACHUSETTS GENERAL HOSPITAL | Voluntary non-profit - Private |  | 1 | 0 | 291,933,878 | 0 |  | ok: full-year cost report |
| 220088 | NEW ENGLAND BAPTIST HOSPITAL | Voluntary non-profit - Private |  | 1 | 0 | 38,205,323 | 0 |  | ok: full-year cost report |
| 220074 | SOUTHCOAST HOSPITALS GROUP | Voluntary non-profit - Private |  | 1 | 0 | 139,712,861 | 0 |  | ok: full-year cost report |
| 220062 | ADCARE HOSPITAL OF WORCESTER INC | Proprietary |  |  |  | 12,283,900 |  |  | no factor: not in FY2026 HRRP payment file |
| 220126 | NORWOOD HOSPITAL | Proprietary |  |  |  |  |  |  | no factor: not in FY2026 HRRP payment file |
