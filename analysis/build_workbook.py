"""Step 6: Excel workbook. HRRP penalties vs the finances of HCA, Tenet, CHS and UHS.

Run after models.build:   python -m analysis.build_workbook
Writes analysis/output/hrrp_chain_workbook.xlsx. The formula guide is docs/workbook_guide.md.

Design rule: Python only *places data* (CMS hospital inputs, SEC line items). Every
calculation in the workbook is an Excel formula, so anyone can click a cell and see how
it was computed. Yellow cells on the Inputs sheet are the only things meant to be edited.
"""
import duckdb
import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from ingest import config as CFG

OUT = CFG.ROOT / "analysis" / "output" / "hrrp_chain_workbook.xlsx"
CHAINS = list(CFG.SEC_COMPANIES)  # names match seed.system_owner_patterns
YEARS = 5

# XBRL tags tried in order. Companies don't all use the same tag for the same idea,
# so the workbook records which tag each number came from.
TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "HealthCareOrganizationRevenue"],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    # NetIncomeLoss is attributable to the company. Some filers tag only the common-
    # shareholder or consolidated (incl. noncontrolling interests) version.
    "net_income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
}

INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
HEAD_FILL = PatternFill("solid", fgColor="DDEBF7")
BOLD = Font(bold=True)
USD = '"$"#,##0'
USDM = '"$"#,##0.0,,"M"'
PCT = "0.0%"
PCT3 = "0.000%"


# ---------------------------------------------------------------- data from DuckDB
def load(con):
    hosp = con.execute("""
        SELECT parent_system, ccn, facility_name, state, payment_adjustment_factor,
               est_annual_base_drg_payments, estimate_quality
        FROM mart.hospital_penalty_wide WHERE parent_system IS NOT NULL
        ORDER BY parent_system, ccn""").df()
    cond = con.execute("""
        SELECT p.parent_system, s.ccn, p.facility_name, s.condition_label AS condition,
               s.penalty_indicator, s.drg_payment_ratio, s.err, s.peer_median_err,
               s.neutrality_modifier, s.eligible_discharges, m.expected_rate
        FROM mart.hospital_condition_penalty_share s
        JOIN mart.hospital_penalty p USING (ccn)
        LEFT JOIN stg.hrrp_measures m ON m.ccn = s.ccn AND m.condition = s.condition
        WHERE p.parent_system IS NOT NULL
        ORDER BY p.parent_system, s.ccn, s.condition""").df()
    facts = con.execute("""
        SELECT cik, tag, period_end, value_usd, form, filed
        FROM stg.sec_annual""").df()
    return hosp, cond, facts


def pick_sec(facts: pd.DataFrame) -> pd.DataFrame:
    """One row per company x fiscal year: latest-filed 10-K value for each concept."""
    rows = []
    for name, cik in CFG.SEC_COMPANIES.items():
        f = facts[facts.cik == cik].copy()
        f["fy"] = pd.to_datetime(f.period_end).dt.year
        f = f.sort_values("filed").drop_duplicates(["tag", "period_end"], keep="last")
        years = sorted(f.loc[f.tag.isin(TAGS["revenue"]), "fy"].unique())[-YEARS:]
        for fy in years:
            row = {"company": name, "cik": cik, "fy": int(fy)}
            for concept, tags in TAGS.items():
                row[concept], row[concept + "_tag"] = None, None
                for t in tags:
                    hit = f[(f.tag == t) & (f.fy == fy)]
                    if len(hit):
                        r = hit.sort_values("filed").iloc[-1]
                        row[concept], row[concept + "_tag"] = float(r.value_usd), t
                        row["filed"] = str(r.filed)[:10]
                        break
            rows.append(row)
    return pd.DataFrame(rows)


def load_intervals():
    """{chain: (5th, 95th percentile)} from the Monte Carlo output, or None if not run yet."""
    path = CFG.ROOT / "analysis" / "output" / "penalty_interval.csv"
    if not path.exists():
        print(f"No {path.name}: the interval cells stay blank (run python -m analysis.penalty_uncertainty first).")
        return None
    t = pd.read_csv(path)
    t = t[(t.level == "group") & (t.population == "all penalized hospitals")]
    return {r.name: (float(r.p5_usd), float(r.p95_usd)) for r in t.itertuples(index=False)}


# ---------------------------------------------------------------- sheet helpers
def header(ws, row, cols, widths=None):
    for j, c in enumerate(cols, 1):
        cell = ws.cell(row, j, c)
        cell.font, cell.fill = BOLD, HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    if widths:
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w


def put(ws, ref, value, fmt=None, note=None, fill=None, bold=False):
    c = ws[ref]
    c.value = value
    if fmt:
        c.number_format = fmt
    if note:
        c.comment = Comment(note, "pipeline")
    if fill:
        c.fill = fill
    if bold:
        c.font = BOLD
    return c


def blank(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


# ---------------------------------------------------------------- build
def build(hosp, cond, sec, intervals=None):
    wb = Workbook()

    # README -------------------------------------------------------------------------
    ws = wb.active
    ws.title = "README"
    lines = [
        "HRRP penalties vs hospital-chain finances (HCA, Tenet, CHS, UHS)",
        "",
        "Sheets: Inputs (yellow = editable) -> Condition_Data -> Hospital_Data -> Chain_Summary, Scenarios, ROI. SEC_Financials holds the 10-K numbers.",
        "Every calculated cell is an Excel formula. Click any cell to see it. docs/workbook_guide.md explains each one.",
        "Sources: CMS FY2026 HRRP supplemental file (factors, ERRs, peer medians, DRG payment ratios), CMS HRRP hospital file (expected rates),",
        "Medicare cost reports (base DRG payments, latest report, annualised), CMS All Owners (parent system), SEC EDGAR companyfacts (10-K).",
        "Key caveats: penalty dollars use 2024-25 cost-report payments, not FY2026 actuals; chain mapping is today's ownership;",
        "SEC figures are company-wide (all hospitals, all payers); scenarios hold peer-group medians and the neutrality modifier fixed.",
        "Uncertainty: Inputs rows 25-33 and Chain_Summary columns L-O give each chain's 90% Monte Carlo interval (docs/penalty_uncertainty.md).",
        "ROI cost inputs come from the Care Transitions Intervention trial (AHRQ); labelled CHOICE cells are assumptions to overwrite.",
    ]
    for i, t in enumerate(lines, 1):
        ws.cell(i, 1, t).font = BOLD if i == 1 else Font()
    ws.column_dimensions["A"].width = 150

    # Inputs -------------------------------------------------------------------------
    inp = wb.create_sheet("Inputs")
    inp.column_dimensions["A"].width = 58
    inp.column_dimensions["B"].width = 22
    inp.column_dimensions["C"].width = 80
    put(inp, "A1", "Scenario inputs", bold=True)
    put(inp, "A3", "Scenario 1: cut in excess readmissions"); put(inp, "B3", 0.10, PCT, fill=INPUT_FILL)
    put(inp, "A4", "Scenario 2: cut in excess readmissions"); put(inp, "B4", 0.20, PCT, fill=INPUT_FILL)
    put(inp, "A5", "Scenario 3: cut in excess readmissions"); put(inp, "B5", 0.30, PCT, fill=INPUT_FILL)
    put(inp, "C3", "Excess = readmissions above CMS's expected level (the part of ERR above 1.0).")
    put(inp, "A6", "Years in the CMS performance period"); put(inp, "B6", 3, "0", fill=INPUT_FILL)
    put(inp, "C6", "FY2026 HRRP period is 07/01/2021-06/30/2024 (3 years). Used to turn eligible discharges into a yearly figure.")
    put(inp, "A8", "ROI case", bold=True)
    put(inp, "A9", "Chain"); put(inp, "B9", CHAINS[0], fill=INPUT_FILL)
    dv = DataValidation(type="list", formula1='"' + ",".join(CHAINS) + '"', allow_blank=False)
    inp.add_data_validation(dv); dv.add("B9")
    put(inp, "A10", "Cut in excess readmissions the program achieves"); put(inp, "B10", "=B4", PCT, fill=INPUT_FILL)
    put(inp, "C10", "Defaults to Scenario 2. Overwrite with your own assumption.")
    # ROI cost inputs, filled from published sources (rows 17-22). Each yellow cell either points at a
    # sourced number or is a labelled choice. Overwrite any of them with your hospital's own figures.
    put(inp, "A11", "Share of eligible HRRP discharges enrolled"); put(inp, "B11", 1.0, PCT, fill=INPUT_FILL)
    put(inp, "C11", "CHOICE, not data: enrol every HRRP-eligible discharge (the most expensive case). Lower it to target high-risk patients.")
    put(inp, "A12", "Program cost per enrolled patient ($)"); put(inp, "B12", "=B19/B20", USD, fill=INPUT_FILL)
    put(inp, "C12", "Annual cost of one transitions coach / patients one coach serves per year (rows 19-20).")
    put(inp, "A13", "Fixed annual program cost ($): staff, software"); put(inp, "B13", 0, USD, fill=INPUT_FILL)
    put(inp, "C13", "CHOICE: 0, because the published coach cost already includes salary, benefits and other expenses. "
                    "Add your own IT or management overhead here.")
    put(inp, "A14", "Margin per avoided readmission ($, can be negative)"); put(inp, "B14", 0, USD, fill=INPUT_FILL)
    put(inp, "C14", "CHOICE: 0 = HRRP-penalty-only view. Under fee-for-service an avoided readmission is also lost revenue: "
                    "enter the contribution margin the hospital would have earned as a negative number. No public source gives "
                    "this margin, so it is not pre-filled. Row 22 shows the average cost of a readmission for scale.")

    put(inp, "A17", "Published sources for the ROI inputs", bold=True)
    put(inp, "A18", "Source item"); put(inp, "B18", "Value"); put(inp, "C18", "Where it comes from")
    for ref in ("A18", "B18", "C18"):
        inp[ref].font, inp[ref].fill = BOLD, HEAD_FILL
    put(inp, "A19", "Annual cost of one transitions coach ($)"); put(inp, "B19", 74310, USD)
    put(inp, "C19", "Care Transitions Intervention RCT (Coleman et al., Arch Intern Med 2006;166:1822-8), as reported by AHRQ: "
                    "https://psnet.ahrq.gov/innovation/transition-coachesr-reduce-readmissions-medicare-patients-complex-postdischarge-needs "
                    "(salary, benefits, other expenses; study-era dollars, not inflated)")
    put(inp, "A20", "Patients one coach serves per year"); put(inp, "B20", 300, "#,##0")
    put(inp, "C20", "Same AHRQ page: 24-28 patients at a time, approximately 300 per year.")
    put(inp, "A21", "Trial 30-day readmission rate: control vs intervention"); put(inp, "B21", "11.9% vs 8.3%")
    put(inp, "C21", "Coleman 2006 RCT (n = 750): a 30% relative drop in all readmissions among enrolled patients. "
                    "Our default cut (B10 = 20% of EXCESS readmissions) is smaller than that, so it is conservative.")
    put(inp, "A22", "Average cost of a readmission, 2020, all payers ($)"); put(inp, "B22", 16300, USD)
    put(inp, "C22", "AHRQ HCUP Statistical Brief #304 (Nationwide Readmissions Database 2020; cost, not charges): "
                    "https://hcup-us.ahrq.gov/reports/statbriefs/sb304-readmissions-2016-2020.pdf . Reference only, not used in a formula.")

    # Uncertainty: 90% Monte Carlo interval per chain (rows 25-33), from
    # analysis/output/penalty_interval.csv (python -m analysis.penalty_uncertainty).
    put(inp, "A25", "Uncertainty in the penalty $: 90% Monte Carlo interval", bold=True)
    put(inp, "C25", "From docs/penalty_uncertainty.md, all penalized hospitals: payment base (cost report vs CMS Impact "
                    "File), DRG payment ratio drift and a base for penalized hospitals with none, 10,000 draws. "
                    "Data, not inputs to edit.")
    interval_rows = {}
    for k, chain in enumerate(CHAINS):
        r_lo, r_hi = 26 + 2 * k, 27 + 2 * k
        lo, hi = (intervals or {}).get(chain, (None, None))
        put(inp, f"A{r_lo}", f"{chain}: low (5th percentile)"); put(inp, f"B{r_lo}", lo, USD)
        put(inp, f"A{r_hi}", f"{chain}: high (95th percentile)"); put(inp, f"B{r_hi}", hi, USD)
        if lo is None:
            put(inp, f"C{r_lo}", "Not available: run python -m analysis.penalty_uncertainty, then rebuild the workbook.")
        interval_rows[chain] = (r_lo, r_hi)

    S1, S2, S3, SR = "Inputs!$B$3", "Inputs!$B$4", "Inputs!$B$5", "Inputs!$B$10"

    # Condition_Data -----------------------------------------------------------------
    cd = wb.create_sheet("Condition_Data")
    cols = ["Parent system", "CCN", "Hospital", "Condition", "CMS penalty indicator", "DRG payment ratio",
            "ERR", "Peer-group median ERR", "Neutrality modifier", "Eligible discharges (3 yrs)",
            "Expected readmission rate (%)",
            "Penalty term: baseline", "Penalty term: scenario 1", "Penalty term: scenario 2",
            "Penalty term: scenario 3", "Penalty term: ROI case", "Avoided readmissions / yr (ROI case)"]
    header(cd, 1, cols, [24, 8, 34, 13, 10, 10, 9, 10, 10, 11, 11, 12, 12, 12, 12, 12, 13])
    for i, r in enumerate(cond.itertuples(index=False), start=2):
        vals = [r.parent_system, r.ccn, r.facility_name, r.condition, blank(r.penalty_indicator),
                blank(r.drg_payment_ratio), blank(r.err), blank(r.peer_median_err),
                blank(r.neutrality_modifier), blank(r.eligible_discharges), blank(r.expected_rate)]
        for j, v in enumerate(vals, 1):
            cd.cell(i, j, v)

        def term(pct):
            # new ERR = ERR minus pct of its excess over 1.0; term = ratio x excess over peer median
            new_err = f"IF($G{i}>1,$G{i}-{pct}*($G{i}-1),$G{i})" if pct else f"$G{i}"
            return f'=IF(AND($E{i}="Y",ISNUMBER($G{i}),ISNUMBER($F{i})),$F{i}*MAX({new_err}-$H{i},0),0)'
        cd.cell(i, 12, term(None))
        cd.cell(i, 13, term(S1)); cd.cell(i, 14, term(S2)); cd.cell(i, 15, term(S3)); cd.cell(i, 16, term(SR))
        cd.cell(i, 17, f"=IF(AND(ISNUMBER($G{i}),ISNUMBER($J{i}),ISNUMBER($K{i})),"
                       f"$J{i}/Inputs!$B$6*$K{i}/100*MAX($G{i}-1,0)*{SR},0)")
    n_cd = len(cond) + 1
    cd.freeze_panes = "E2"

    # Hospital_Data ------------------------------------------------------------------
    hd = wb.create_sheet("Hospital_Data")
    cols = ["Parent system", "CCN", "Hospital", "State", "CMS payment adjustment factor",
            "Base DRG payments / yr (cost report, annualised)", "Estimate quality", "Neutrality modifier",
            "Est. penalty $ (CMS factor)", "Recomputed factor: baseline", "Check: CMS - recomputed",
            "Factor: scenario 1", "Factor: scenario 2", "Factor: scenario 3", "Factor: ROI case",
            "Penalty $: baseline (recomputed)", "Penalty $: scenario 1", "Penalty $: scenario 2",
            "Penalty $: scenario 3", "Penalty $: ROI case"]
    header(hd, 1, cols, [24, 8, 34, 6, 11, 16, 28, 10, 14, 11, 10, 10, 10, 10, 10, 14, 14, 14, 14, 14])
    nm = cond.groupby("ccn")["neutrality_modifier"].first()
    rng = lambda col: f"Condition_Data!${col}$2:${col}${n_cd}"
    for i, r in enumerate(hosp.itertuples(index=False), start=2):
        for j, v in enumerate([r.parent_system, r.ccn, r.facility_name, r.state,
                               blank(r.payment_adjustment_factor), blank(r.est_annual_base_drg_payments),
                               r.estimate_quality, blank(nm.get(r.ccn))], 1):
            hd.cell(i, j, v)
        hd.cell(i, 9, f'=IF(AND(ISNUMBER(E{i}),ISNUMBER(F{i})),(1-E{i})*F{i},"")').number_format = USD

        def factor(term_col):
            return (f'=IF(ISNUMBER(H{i}),MAX(0.97,1-H{i}*SUMIFS({rng(term_col)},{rng("B")},B{i})),"")')
        hd.cell(i, 10, factor("L")).number_format = "0.0000"
        hd.cell(i, 11, f'=IF(AND(ISNUMBER(E{i}),ISNUMBER(J{i})),E{i}-J{i},"")').number_format = "0.00000"
        for j, col in zip(range(12, 16), ["M", "N", "O", "P"]):
            hd.cell(i, j, factor(col)).number_format = "0.0000"
        for j, fcol in zip(range(16, 21), ["J", "L", "M", "N", "O"]):
            hd.cell(i, j, f'=IF(AND(ISNUMBER({fcol}{i}),ISNUMBER(F{i})),(1-{fcol}{i})*F{i},"")').number_format = USD
        hd.cell(i, 5).number_format = "0.0000"
        hd.cell(i, 6).number_format = USD
    n_hd = len(hosp) + 1
    hd.freeze_panes = "E2"
    H = lambda col: f"Hospital_Data!${col}$2:${col}${n_hd}"

    # SEC_Financials -----------------------------------------------------------------
    sf = wb.create_sheet("SEC_Financials")
    cols = ["Company", "CIK", "Fiscal year", "Revenue", "Revenue tag", "Operating income (reported)",
            "Operating income tag", "Pre-tax income", "Pre-tax tag", "Interest expense", "Interest tag",
            "Operating income used", "Basis", "Net income", "Net income tag (ProfitLoss = includes noncontrolling interests)", "Last 10-K filed"]
    header(sf, 1, cols, [26, 9, 8, 16, 34, 16, 22, 16, 30, 14, 22, 16, 30, 16, 16, 12])
    for i, r in enumerate(sec.itertuples(index=False), start=2):
        vals = [r.company, r.cik, r.fy, blank(r.revenue), r.revenue_tag, blank(r.operating_income),
                r.operating_income_tag, blank(r.pretax_income), r.pretax_income_tag,
                blank(r.interest_expense), r.interest_expense_tag]
        for j, v in enumerate(vals, 1):
            sf.cell(i, j, v)
        # Reported operating income if the company tags it; otherwise EBIT = pre-tax + interest.
        sf.cell(i, 12, f'=IF(ISNUMBER(F{i}),F{i},IF(AND(ISNUMBER(H{i}),ISNUMBER(J{i})),H{i}+J{i},""))')
        sf.cell(i, 13, f'=IF(ISNUMBER(F{i}),"reported operating income",IF(ISNUMBER(L{i}),'
                       f'"EBIT proxy: pre-tax income + interest expense","not available"))')
        sf.cell(i, 14, blank(r.net_income)); sf.cell(i, 15, r.net_income_tag); sf.cell(i, 16, r.filed)
        for j in (4, 6, 8, 10, 12, 14):
            sf.cell(i, j).number_format = USDM
    n_sf = max(len(sec) + 1, 2)
    F = lambda col: f"SEC_Financials!${col}$2:${col}${n_sf}"

    # Chain_Summary ------------------------------------------------------------------
    cs = wb.create_sheet("Chain_Summary")
    cols = ["Chain", "HRRP hospitals mapped", "Penalized (factor < 1)", "Est. FY2026 HRRP penalty $",
            "Latest fiscal year in SEC data", "Revenue (latest FY)", "Operating income (latest FY)",
            "Net income (latest FY)", "Penalty as % of operating income", "Penalty as % of revenue",
            "Penalty as % of net income"]
    header(cs, 1, cols, [26, 10, 10, 16, 10, 16, 16, 16, 12, 12, 12])
    for i, chain in enumerate(CHAINS, start=2):
        put(cs, f"A{i}", chain)
        put(cs, f"B{i}", f"=COUNTIFS({H('A')},A{i})")
        put(cs, f"C{i}", f'=COUNTIFS({H("A")},A{i},{H("E")},"<1")')
        put(cs, f"D{i}", f"=SUMIFS({H('I')},{H('A')},A{i})", USD)
        put(cs, f"E{i}", f'=IF(COUNTIFS({F("A")},A{i})=0,"",_xlfn.MAXIFS({F("C")},{F("A")},A{i}))', "0")
        for col, src in zip("FGH", "DLN"):
            look = f'INDEX({F(src)},MATCH(1,INDEX(({F("A")}=A{i})*({F("C")}=E{i}),0),0))'
            put(cs, f"{col}{i}", f'=IFERROR(IF({look}="","",{look}),"")', USDM)
        put(cs, f"I{i}", f'=IF(ISNUMBER(G{i}),D{i}/G{i},"")', PCT3)
        put(cs, f"J{i}", f'=IF(ISNUMBER(F{i}),D{i}/F{i},"")', PCT3)
        put(cs, f"K{i}", f'=IF(ISNUMBER(H{i}),D{i}/H{i},"")', PCT3)
    # 90% interval columns (appended so the columns above keep their letters)
    for col, title in zip("LMNO", ["Penalty $: 90% interval low", "Penalty $: 90% interval high",
                                    "Low as % of operating income", "High as % of operating income"]):
        cell = cs.cell(1, " ABCDEFGHIJKLMNO".index(col), title)
        cell.font, cell.fill = BOLD, HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cs.column_dimensions[col].width = 14 if col in "LM" else 12
    for i, chain in enumerate(CHAINS, start=2):
        r_lo, r_hi = interval_rows[chain]
        put(cs, f"L{i}", f'=IF(ISNUMBER(Inputs!$B${r_lo}),Inputs!$B${r_lo},"")', USD)
        put(cs, f"M{i}", f'=IF(ISNUMBER(Inputs!$B${r_hi}),Inputs!$B${r_hi},"")', USD)
        put(cs, f"N{i}", f'=IF(AND(ISNUMBER(L{i}),ISNUMBER(G{i})),L{i}/G{i},"")', PCT3)
        put(cs, f"O{i}", f'=IF(AND(ISNUMBER(M{i}),ISNUMBER(G{i})),M{i}/G{i},"")', PCT3)
    t = len(CHAINS) + 2
    put(cs, f"A{t}", "All four chains", bold=True)
    for col in "BCD":
        put(cs, f"{col}{t}", f"=SUM({col}2:{col}{t-1})", USD if col == "D" else None, bold=True)
    put(cs, f"L{t+1}", "Chain intervals don't add: each chain's 5th/95th percentile comes from its own draws.")

    # 5-year history block
    top = t + 3
    put(cs, f"A{top}", "Five-year history (SEC 10-K, $ millions shown). The penalty is FY2026, compared with each year's operating income.", bold=True)
    hdr = ["Chain", "Fiscal year", "Revenue", "Operating income used", "Net income", "Operating margin",
           "FY2026 penalty as % of that year's operating income"]
    for j, c in enumerate(hdr, 1):
        cell = cs.cell(top + 1, j, c); cell.font, cell.fill = BOLD, HEAD_FILL
    r0 = top + 2
    for k, rr in enumerate(sec.sort_values(["company", "fy"]).itertuples(index=False)):
        i = r0 + k
        put(cs, f"A{i}", rr.company); put(cs, f"B{i}", rr.fy, "0")
        for col, src in zip("CDE", "DLN"):
            look = f'INDEX({F(src)},MATCH(1,INDEX(({F("A")}=A{i})*({F("C")}=B{i}),0),0))'
            put(cs, f"{col}{i}", f'=IFERROR(IF({look}="","",{look}),"")', USDM)
        put(cs, f"F{i}", f'=IF(AND(ISNUMBER(C{i}),ISNUMBER(D{i})),D{i}/C{i},"")', PCT)
        put(cs, f"G{i}", f'=IF(ISNUMBER(D{i}),SUMIFS({H("I")},{H("A")},A{i})/D{i},"")', PCT3)

    # Scenarios ----------------------------------------------------------------------
    sc = wb.create_sheet("Scenarios")
    cols = ["Chain", "Baseline penalty $ (recomputed)",
            "Scenario 1 penalty $", "Scenario 2 penalty $", "Scenario 3 penalty $",
            "Savings: scenario 1", "Savings: scenario 2", "Savings: scenario 3",
            "Savings 1 as % of op. income", "Savings 2 as % of op. income", "Savings 3 as % of op. income"]
    header(sc, 1, cols, [26, 16, 16, 16, 16, 15, 15, 15, 12, 12, 12])
    put(sc, "A2", "Cut in excess readmissions:"); put(sc, "C2", f"={S1}", PCT); put(sc, "D2", f"={S2}", PCT); put(sc, "E2", f"={S3}", PCT)
    for k, chain in enumerate(CHAINS):
        i = k + 3
        put(sc, f"A{i}", chain)
        for col, src in zip("BCDE", "PQRS"):
            put(sc, f"{col}{i}", f"=SUMIFS({H(src)},{H('A')},$A{i})", USD)
        for col, s in zip("FGH", "CDE"):
            put(sc, f"{col}{i}", f"=$B{i}-{s}{i}", USD)
        for col, s in zip("IJK", "FGH"):
            put(sc, f"{col}{i}", f'=IFERROR({s}{i}/INDEX(Chain_Summary!$G$2:$G${len(CHAINS)+1},'
                                 f'MATCH($A{i},Chain_Summary!$A$2:$A${len(CHAINS)+1},0)),"")', PCT3)
    t = len(CHAINS) + 3
    put(sc, f"A{t}", "All four chains", bold=True)
    for col in "BCDEFGH":
        put(sc, f"{col}{t}", f"=SUM({col}3:{col}{t-1})", USD, bold=True)
    put(sc, f"A{t+2}", "Method: each condition's ERR is moved toward 1.0 by the scenario %, only where ERR > 1. The CMS formula is then "
                      "re-applied with peer medians and the neutrality modifier held fixed, and the 0.97 floor kept. See docs/workbook_guide.md.")

    # ROI ----------------------------------------------------------------------------
    ro = wb.create_sheet("ROI")
    ro.column_dimensions["A"].width = 62; ro.column_dimensions["B"].width = 20; ro.column_dimensions["C"].width = 90
    rows = [
        ("Chain", "=Inputs!B9", None, "Picked on the Inputs sheet."),
        ("Cut in excess readmissions", "=Inputs!B10", PCT, ""),
        ("Eligible HRRP discharges per year", f"=SUMIFS(Condition_Data!$J$2:$J${n_cd},Condition_Data!$A$2:$A${n_cd},B3)/Inputs!B6",
         "#,##0", "CMS eligible discharges for the 6 conditions, divided by the years in the performance period."),
        ("Patients enrolled per year", "=B5*Inputs!B11", "#,##0", "Eligible discharges x enrolment share."),
        ("Program cost per year", "=Inputs!B13+B6*Inputs!B12", USD, "Fixed cost + enrolled patients x cost per patient."),
        ("Avoided readmissions per year", f"=SUMIFS(Condition_Data!$Q$2:$Q${n_cd},Condition_Data!$A$2:$A${n_cd},B3)", "#,##0",
         "Sum over hospital-conditions: discharges/yr x expected rate x (ERR - 1) x cut %. That's excess readmissions times the cut."),
        ("HRRP penalty avoided per year", f"=SUMIFS({H('P')},{H('A')},B3)-SUMIFS({H('T')},{H('A')},B3)", USD,
         "Baseline penalty minus the penalty with the ROI-case cut (Hospital_Data columns P and T)."),
        ("Margin effect of avoided readmissions", "=B8*Inputs!B14", USD,
         "Avoided readmissions x margin per readmission (negative = revenue the hospital no longer earns)."),
        ("Net annual benefit", "=B9+B10-B7", USD, "Penalty avoided + margin effect - program cost."),
        ("ROI", '=IF(B7>0,B11/B7,"enter costs on Inputs")', PCT, "Net benefit / program cost."),
        ("Break-even cost per enrolled patient", '=IF(B6>0,(B9+B10-Inputs!B13)/B6,"enter enrolment share")', USD,
         "Highest per-patient cost at which the program still pays for itself."),
        ("Benefit-cost ratio", '=IF(B7>0,(B9+B10)/B7,"")', "0.00", "Above 1 means benefits exceed costs."),
    ]
    put(ro, "A1", "Care-transitions program: simple annual ROI", bold=True)
    for k, (label, f, fmt, note) in enumerate(rows, start=3):
        put(ro, f"A{k}", label); put(ro, f"B{k}", f, fmt); put(ro, f"C{k}", note)
    put(ro, "A17", "Timing caveat: HRRP looks back 2-3 years, so lower readmissions cut penalties with a lag, not in the same year.")
    put(ro, "A18", "Scope caveat: this counts only the HRRP penalty and the chosen margin effect. Quality, length-of-stay and value-based contract effects are excluded.")

    for wsx in (cs, sc):
        wsx.freeze_panes = "B2"
    return wb


def main():
    con = duckdb.connect(str(CFG.DB_PATH), read_only=True)
    hosp, cond, facts = load(con)
    con.close()
    sec = pick_sec(facts)
    wb = build(hosp, cond, sec, load_intervals())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"{len(hosp)} chain hospitals, {len(cond)} hospital-condition rows, {len(sec)} company-years")
    cov = sec.assign(op=sec.operating_income.notna(), ebit=sec.pretax_income.notna() & sec.interest_expense.notna())
    print(cov.groupby("company")[["fy"]].agg(["min", "max", "count"]).to_string())
    print(sec[["company", "fy", "revenue_tag", "operating_income_tag", "pretax_income_tag",
               "interest_expense_tag", "net_income_tag"]].to_string(index=False))
    print(f"Workbook: {OUT}  (open in Excel; formulas calculate on open)")


if __name__ == "__main__":
    main()
