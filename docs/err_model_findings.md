# What explains readmission ratios: findings

_Written from the model run in commit 02135ef (2026-11-02): 2,576 hospitals, FY2026 HRRP data. The full output, with every table and check, is in [err_model_report.md](err_model_report.md). If you re-run the pipeline, re-check these numbers against the new report._

## Headline
Hospital and community characteristics explain very little of why one hospital readmits more than another. The full model explains **6.9%** of the variation in composite ERR. Social risk alone (dual-eligible share, county income, county 65+ share) explains **4.8%**, nearly all of it from the dual-eligible share (4.5%). Social risk accounts for about **two-thirds** of what the model explains. Hospital structure (beds, teaching status, ownership) accounts for the other third. **About 93% of the variation is left unexplained.**

## What each factor means (main model, robust standard errors)
| Factor | Association with readmissions vs expected | Holds up? |
|---|---|---|
| Dual-eligible share, +10 points | **+0.79%** (95% CI +0.63% to +0.94%) | Yes: in every version. +1.04% when weighted by case counts, +0.55% per 10 points using DSH % instead |
| For-profit vs nonprofit | **+1.75%** (+1.23% to +2.27%) | Yes, though it halves to +0.84% once star rating is added |
| County income, +$10k | −0.14% (−0.23% to −0.04%) | Fragile: p = 0.097 with errors clustered by state, and it changes sign with star rating added |
| Beds, per doubling | +0.24% (+0.05% to +0.44%) | Fragile: gone when weighted by case counts (+0.02%) |
| Teaching hospital | 0.00% | No association |
| Government vs nonprofit | +0.06% | No association |
| County 65+ share, +5 points | +0.13% | No association |
| "Other" ownership (mostly tribal) | −6.4% | **Ignore.** This rests on a handful of hospitals |

**In one sentence:** hospitals serving more dual-eligible patients, and for-profit hospitals, have somewhat higher readmissions than CMS's clinical risk adjustment expects. Size, teaching status and the age of the county barely matter.

## By condition
The dual-eligible link is strongest for **heart failure (+0.88%)** and **pneumonia (+0.83%)** per 10 points, the two medical conditions that also drive most penalty dollars. It reverses for **elective hip/knee replacement (−0.28%)**, where patients are selected for surgery and social needs matter less.

## Linear vs tree model
The cross-validated R² is 0.058 for the linear model and 0.070 for the gradient-boosted tree. The tree is only slightly better, and the RESET test (p = 0.02) agrees that there is mild curvature, so the linear model is a fair summary. On held-out hospitals, the tree ranks the same top factor first: dual-eligible share, then county income, beds and for-profit status.

## Checks
- **Errors are heteroskedastic** (Breusch-Pagan p ≈ 1e-6), which is why all standard errors are robust (HC3).
- **Residuals have heavy tails** (excess kurtosis 4.6), and 103 hospitals are influential by Cook's distance. With n = 2,576, the conclusions above don't depend on normality.
- **No collinearity problem** (all VIF < 1.5).
- **Star rating** (−1.97% per star) is reported separately and left out of the main model, because star ratings are built partly from readmission measures.

## How this connects to the penalty
CMS already compares each hospital only with hospitals in the same dual-eligible **peer group** (quintile) before setting the penalty. So the dual-eligible link shown here is partly neutralised in the dollars. A hospital is penalized for being worse than similar safety-net hospitals, not worse than all hospitals.

## Where not to read cause
These are associations across hospitals. Specifically:
- The dual-eligible effect mixes patients' social needs, community resources and hospital quality.
- County income describes the county, not the hospital's own patients.
- For-profit status isn't randomly assigned, because chains choose their markets.
- CMS shrinks small hospitals' ERRs toward 1.0, which affects any bed-size result.
- Staffing, post-acute supply and observation-stay use are missing, and likely matter.

[err_model_report.md](err_model_report.md#where-correlation-should-not-be-read-as-cause) has the full list.
