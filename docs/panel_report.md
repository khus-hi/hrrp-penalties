# HRRP panel, FY2016-FY2027: coverage and attrition

**Not generated on the real data yet.** This file is written by `python -m analysis.panel_report`
(or `make panel`) from `mart.fct_hospital_condition_year` after the multi-year ingest. It has no
numbers until then, on purpose: every number in it must come from CMS's files.

To generate it (on your laptop, with the full data):

```bash
python -m ingest.download --history-only   # FY2016-FY2027 HRRP supplemental files
python -m ingest.load
make build
make panel                                  # writes this file
```

What it will contain:

- **Years:** every payment year FY2016-FY2027, loaded or missing (with the reason), hospitals,
  conditions, and the performance period (from config and, where loaded, from CMS's file).
- **Hospitals in every year:** distinct CCNs in any year and in every loaded year.
- **Attrition:** year-over-year stayed / left / joined, and how many of the first year's
  hospitals are still in each later year.
- **Measures by year** and the **known breaks** (COVID-19 2020 exclusion in FY2022-FY2024,
  FY2023 pneumonia suppression, FY2019 peer groups, FY2027 2-year period).
