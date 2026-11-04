# How the FY2026 HRRP penalty is estimated

```
estimated penalty $ = (1 − CMS payment adjustment factor) × annualised Medicare base DRG payments
```

The factor comes straight from CMS. The dollar base is an estimate built from the cost report. Each row of `mart.hospital_penalty` has an `estimate_quality` flag saying which case applies to it.

## What is exact (from CMS)
1. **Payment adjustment factor.** This is CMS's FY2026 number from the IPPS final rule supplemental file, cross-checked against Table 15. It can't be lower than 0.97 (42 CFR 412.154(c)(2)).
2. **Which conditions drive it.** The regulation (42 CFR 412.152) defines the penalty as the sum over conditions of *DRG payment ratio × (ERR − peer-group median ERR, if positive)*, times a neutrality modifier. CMS publishes every one of those inputs. A condition counts only when CMS's per-condition penalty indicator is "Y". We split each hospital's dollars across conditions by those exact terms, and the dbt test `assert_factor_recompute_matches_cms` re-derives CMS's factor from them. If that test passes, the split is CMS's own arithmetic, not an assumption.

## Assumptions in the dollar base (each one is a source of error)
| # | Assumption | Direction of error |
|---|---|---|
| A1 | The base is HCRIS Worksheet E Part A line 1, "DRG amounts other than outlier payments," which is the closest public match to the regulation's "base operating DRG payment." The regulation also excludes IME, DSH, outlier and low-volume payments, and HCRIS reports those on separate lines. | Close in scope |
| A2 | We use each hospital's **latest cost report** (mostly fiscal years ending 2024 or 2025), not actual FY2026 (Oct 2025 to Sep 2026) payments, which aren't public yet. No inflation or volume adjustment is applied. | Likely **understates** FY2026 dollars, since payment rates rise each year |
| A3 | Reports covering 180 to 400 days are scaled to 365 days. Shorter or longer reports get no estimate. | Small. Short reports are noisy |
| A4 | If the HCRIS DRG amount is already net of that year's HRRP or VBP adjustments, the base is a bit low. At most that understates a penalty by a factor of 1/(1 − 0.03), about 3%. | Small **understatement** |
| A5 | Fee-for-service Medicare only. Medicare Advantage payments are not penalized under HRRP, and HCRIS line 1 is FFS. | Matches the program |
| A6 | The parent system reflects ownership **today** (CMS All Owners), not during FY2026. | Hospitals sold mid-year are counted under the current owner |
| A7 | Hospitals in CMS's payment file but not in the HRRP hospital file (8) are left out. | Small undercount |

## How to read "penalized but not estimable"
These hospitals have a CMS factor below 1 but no usable cost-report base, so they count toward CMS's number of penalized hospitals but add $0 to our total. The report lists how many there are.

## How big is the error? (90% interval)
`python -m analysis.penalty_uncertainty` puts a number on assumptions A1-A4. It rebuilds every hospital's base a second way, from CMS's FY2026 IPPS Impact File (transfer-adjusted cases x case-mix index x FY2026 wage-adjusted standardized amounts), reports how far the two bases are apart, and runs a Monte Carlo that resamples those observed gaps, the observed drift in CMS's DRG payment ratios, and bases for penalized hospitals that have none. Results and every distribution are in [penalty_uncertainty.md](penalty_uncertainty.md).
