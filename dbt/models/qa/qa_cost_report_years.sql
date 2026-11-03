-- How the cost report years line up with federal FY2026 (Oct 2025 - Sep 2026).
SELECT year(cr_fy_end) AS cost_report_fy_end_year, count(*) AS hospitals
FROM {{ ref('mart_hospital') }} GROUP BY 1 ORDER BY 1
