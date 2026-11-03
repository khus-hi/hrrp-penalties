"""Pure, unit-tested logic behind the HRRP penalty pipeline.

The scripts in ingest/, models/, analysis/ and dashboard/ read data and write reports.
The calculations they rely on live here as plain functions that take DataFrames and
return DataFrames, so they can be tested without downloading anything:

- hrrp.penalty: CMS's payment adjustment factor, re-derived from its published inputs.
- hrrp.err: the discharge-weighted composite ERR and the 0-1 vs 0-100 percent fix.
- hrrp.shapley: an exact Shapley split of R-squared across groups of predictors.
- hrrp.causal.rd: the regression discontinuity at the peer-group median (does a penalty
  lower the condition's later readmissions?).
"""
