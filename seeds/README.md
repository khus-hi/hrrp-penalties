# Seeds (small hand-made reference tables)

- `state_fips.csv`: USPS state abbreviation to Census state FIPS code (official ANSI/FIPS codes). Needed because CMS files use abbreviations and Census uses FIPS.
- `system_owner_patterns.csv`: how a hospital is assigned to a parent system. CMS's All Owners file lists direct and indirect owners but never names the ultimate parent, so we match owner organization names against these patterns (SQL `ILIKE`). **These are starting hypotheses.** `checks/` prints every owner name that matched, plus the hospital count per system, so you can check them against each company's 10-K and adjust.
