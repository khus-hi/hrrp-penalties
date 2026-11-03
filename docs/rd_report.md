# Does a readmission penalty lower that condition's later readmissions?

**Not generated on the real data yet.** This file is written by `python -m analysis.rd_report`
(or `make rd`) from `mart.fct_hospital_condition_year`. It has no numbers until the multi-year
panel (FY2016-FY2027) is loaded from CMS's files, on purpose: every number in it must come from
that run.

To generate it (on your laptop, after the multi-year panel steps):

```bash
make build      # builds mart.fct_hospital_condition_year
make rd         # writes this file, docs/figures/rd/*.png and analysis/output/rd_*.csv
```

What it will contain:

- **Bottom line:** the jump in the same condition's ERR 3 payment years later for hospitals just
  above vs just below their peer-group median, as % of expected readmissions, who it applies to
  (hospitals within the bandwidth of the median), and what it can't rule out.
- **Sharp or fuzzy:** penalized share on each side of the median, with and without CMS's 25-case rule.
- **Timing:** how much the FY t and FY t+h performance periods overlap.
- **Estimates:** pooled (condition x year fixed effects) and per condition, for FY t+3 (main),
  FY t+1 (contaminated by overlap) and FY t+4 (timing check).
- **Validity checks:** density test, covariate balance, placebo cutoffs, donut, half/double bandwidth.
- **Figures:** a binned RD plot per condition, with the fitted lines and their 95% bands.

Method: [pipeline.md](pipeline.md) section 10 and `hrrp/causal/rd.py`.
