"""Monte Carlo interval for the FY2026 HRRP penalty estimate.

The point estimate is

    penalty_i = (1 - CMS payment adjustment factor_i) x base_i

The factor is CMS's exact number, so all uncertainty sits in the dollar base and in how
a hospital's dollars are split across conditions. Three inputs are drawn here, and every
distribution is resampled from observed data (no assumed shapes):

1. Payment base: cost report (HCRIS, 2024-25 actual payments) vs the FY2026 IPPS Impact
   File (CMS's FY2026 rates applied to FY2024 claim volume). Each draw first picks which
   source's *level* is right, 50/50, because the two differ systematically (different
   years and rates) and that choice moves every hospital together. Within the chosen
   source each hospital gets an idiosyncratic error resampled from the observed
   hospital-level gaps ln(Impact / cost report), centred on their median and scaled by
   1/sqrt(2) (if both sources are equally noisy, each carries half the variance of
   their difference).
2. DRG payment ratios: CMS measures them over the performance period, years before the
   payment year. Each hospital-condition ratio is multiplied by a drift resampled from
   the observed change in that condition's ratio between two CMS files three years apart.
   The factor is fixed (CMS's), so this only moves dollars between conditions.
3. Penalized hospitals with a missing or blank base: CMS penalized them, so their cut is
   known, but the cost report has no usable base. They get the other source's base
   (scaled by a resampled gap ratio) or, with neither source, the base of a randomly
   drawn hospital of similar size.

Everything here is pure numpy/pandas so it can be unit-tested without the database.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CONDITIONS = ["ami", "hf", "pn", "copd", "cabg", "tha_tka"]
LEVELS = (5, 50, 95)  # 90% interval + median


# ---------------------------------------------------------------- Impact File base
@dataclass
class StandardizedAmounts:
    """FY2026 national operating standardized amounts (full-update hospitals)."""
    high_labor: float      # Table 1A: wage index > 1
    high_nonlabor: float
    high_labor_share: float
    low_labor: float       # Table 1B: wage index <= 1
    low_nonlabor: float
    low_labor_share: float
    snippets: dict = field(default_factory=dict)


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def _parse_table(text: str, table: str) -> tuple[float, float, float, str]:
    """(labor $, nonlabor $, labor share, snippet) from Table 1A or 1B of the final rule.

    The table heading states the labor share ("66.0 Percent Labor Share"); the first two
    dollar amounts after it are labor and nonlabor for hospitals that submitted quality
    data and are meaningful EHR users (the first column). The two amounts must split in
    the stated share, which guards against reading the wrong numbers.
    """
    pat = re.compile(rf"Table {table}\W{{1,6}}National Adjusted Operating Standardized Amounts", re.I)
    for m in pat.finditer(text):
        chunk = text[m.start(): m.start() + 2500]
        share = re.search(r"\(\s*([\d.]+)\s*Percent Labor Share", chunk, re.I)
        dollars = re.findall(r"\$\s?([\d,]+\.\d{2})", chunk)
        if not share or len(dollars) < 2:
            continue
        labor, nonlabor = (float(d.replace(",", "")) for d in dollars[:2])
        s = float(share.group(1)) / 100
        if abs(labor / (labor + nonlabor) - s) < 0.005:
            return labor, nonlabor, s, chunk[:700]
    raise ValueError(f"Table {table} (national operating standardized amounts) not found in the rule text, "
                     "or its amounts don't match its stated labor share")


def parse_standardized_amounts(raw_rule_text: str) -> StandardizedAmounts:
    text = _strip_html(raw_rule_text)
    hl, hn, hs, s1 = _parse_table(text, "1A")
    ll, ln, ls, s2 = _parse_table(text, "1B")
    return StandardizedAmounts(hl, hn, hs, ll, ln, ls, {"1A": s1, "1B": s2})


def impact_base(cases, cmi, wage_index, cola, sa: StandardizedAmounts) -> np.ndarray:
    """Base operating DRG payments implied by the Impact File.

    cases x case-mix index x (labor amount x wage index + nonlabor amount x COLA), using
    Table 1A amounts where the wage index is above 1 and Table 1B otherwise (the
    statutory 62% labor share floor). Outlier, IME, DSH and low-volume payments are not
    in it, matching the HRRP definition of the base (42 CFR 412.152).
    """
    cases, cmi, wi = (np.asarray(x, dtype=float) for x in (cases, cmi, wage_index))
    cola = np.where(np.isnan(np.asarray(cola, dtype=float)), 1.0, np.asarray(cola, dtype=float))
    labor = np.where(wi > 1, sa.high_labor, sa.low_labor)
    nonlabor = np.where(wi > 1, sa.high_nonlabor, sa.low_nonlabor)
    return cases * cmi * (labor * wi + nonlabor * cola)


# ---------------------------------------------------------------- gap distribution
def trimmed(x, lo=1, hi=99) -> tuple[np.ndarray, float, float]:
    """Finite values of x inside its [lo, hi] percentiles (and the cut points)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return x, np.nan, np.nan
    a, b = np.percentile(x, [lo, hi])
    return x[(x >= a) & (x <= b)], float(a), float(b)


def gap_summary(ratio) -> dict:
    """Distribution of Impact-File base / cost-report base across hospitals."""
    r = np.asarray(ratio, dtype=float)
    r = r[np.isfinite(r) & (r > 0)]
    if len(r) == 0:
        return {"hospitals": 0}
    q = np.percentile(r, [5, 10, 25, 50, 75, 90, 95])
    return {
        "hospitals": int(len(r)),
        **{f"p{p}": float(v) for p, v in zip([5, 10, 25, 50, 75, 90, 95], q, strict=True)},
        "mean": float(r.mean()),
        "share_within_10pct": float(np.mean(np.abs(r - 1) <= 0.10 + 1e-12)),
        "share_within_25pct": float(np.mean(np.abs(r - 1) <= 0.25 + 1e-12)),
        "share_impact_higher": float(np.mean(r > 1)),
    }


# ---------------------------------------------------------------- Monte Carlo
@dataclass
class MCInputs:
    """One row per hospital with a CMS factor, plus the pools resampled from.

    rate        1 - CMS factor (0 if not penalized)
    cr_base     annualised cost-report base (NaN if not estimable)
    if_base     Impact File base (NaN if not in the Impact File)
    size_band   integer bed band, for hospitals with neither base (-1 = unknown)
    group       label rolled up separately (parent system)
    excess      (n, 6) CMS excess terms max(ERR - peer median, 0), 0 where the penalty
                indicator is N; columns follow CONDITIONS
    drg_ratio   (n, 6) CMS DRG payment ratios (NaN where missing)
    log_gap     pool of observed ln(if/cr), trimmed
    drift       dict condition -> pool of observed ln(ratio_now / ratio_3y_earlier), trimmed
    """
    rate: np.ndarray
    cr_base: np.ndarray
    if_base: np.ndarray
    size_band: np.ndarray
    group: np.ndarray
    excess: np.ndarray
    drg_ratio: np.ndarray
    log_gap: np.ndarray
    drift: dict


def point_estimate(inp: MCInputs) -> dict:
    """The published point estimate: cost-report base only, shares at CMS's own ratios."""
    pen = np.where(np.isnan(inp.cr_base), 0.0, inp.rate * np.nan_to_num(inp.cr_base))
    shares = condition_shares(inp.excess, inp.drg_ratio, None)
    return _rollup(pen[None, :], shares[None, :, :], inp.group)


def condition_shares(excess, drg_ratio, drift_mult):
    """Each hospital's split across conditions: excess x ratio (x drift), normalised."""
    w = excess * np.nan_to_num(drg_ratio)
    if drift_mult is not None:
        w = w * drift_mult
    tot = w.sum(axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(tot > 0, w / tot, 0.0)


def _rollup(pen, shares, group) -> dict:
    """pen (draws, n), shares (draws, n, 6) -> totals per draw."""
    out = {"national": pen.sum(axis=1)}
    cond = np.einsum("dn,dnc->dc", pen, shares)
    for k, c in enumerate(CONDITIONS):
        out[f"condition:{c}"] = cond[:, k]
    for g in pd.unique(group):
        if isinstance(g, str) and g:
            out[f"group:{g}"] = pen[:, group == g].sum(axis=1)
    return out


def draw_bases(inp: MCInputs, rng, n_draws, vary_base=True, impute_missing=True) -> np.ndarray:
    """(draws, n) simulated base payments."""
    n = len(inp.rate)
    cr, ifb = inp.cr_base, inp.if_base
    has_cr, has_if = ~np.isnan(cr), ~np.isnan(ifb)
    gap = inp.log_gap if len(inp.log_gap) else np.zeros(1)
    noise_pool = (gap - np.median(gap)) / np.sqrt(2)

    if not vary_base:
        base = np.tile(np.where(has_cr, cr, np.nan), (n_draws, 1))
        world_if = np.zeros(n_draws, dtype=bool)
    else:
        world_if = rng.random(n_draws) < 0.5
        own = np.where(world_if[:, None], np.where(has_if, ifb, np.nan), np.where(has_cr, cr, np.nan))
        # Hospitals missing the chosen source take the other one, converted by a resampled gap.
        g = rng.choice(gap, size=(n_draws, n))
        other = np.where(world_if[:, None], cr * np.exp(g), ifb * np.exp(-g))
        noise = np.exp(rng.choice(noise_pool, size=(n_draws, n)))
        base = np.where(np.isnan(own), other, own * noise)
        # Without imputation, keep the point estimate's population: CR-estimable hospitals only.
        if not impute_missing:
            base = np.where(has_cr[None, :], base, np.nan)

    if impute_missing:
        # Penalized hospitals with neither source: base of a random hospital in the same bed band
        # (from the source of that draw's world).
        need = np.isnan(base) & (inp.rate > 0)[None, :]
        if need.any():
            for w in (False, True):
                pool_vals = ifb if w else cr
                rows = np.where(world_if == w)[0]
                if len(rows) == 0:
                    continue
                for band in np.unique(inp.size_band):
                    cand = pool_vals[(inp.size_band == band) & ~np.isnan(pool_vals)]
                    if len(cand) == 0:
                        cand = pool_vals[~np.isnan(pool_vals)]
                    if len(cand) == 0:
                        continue
                    cols = np.where(inp.size_band == band)[0]
                    sub = need[np.ix_(rows, cols)]
                    if sub.any():
                        block = base[np.ix_(rows, cols)]
                        block[sub] = rng.choice(cand, size=int(sub.sum()))
                        base[np.ix_(rows, cols)] = block
    return np.nan_to_num(base, nan=0.0)


def simulate(inp: MCInputs, n_draws=10_000, seed=2026, chunk=500,
             vary_base=True, vary_ratios=True, impute_missing=True) -> dict:
    """Totals per draw for national, each condition and each group. Seeded, so reruns match."""
    rng = np.random.default_rng(seed)
    parts: dict[str, list] = {}
    done = 0
    while done < n_draws:
        k = min(chunk, n_draws - done)
        base = draw_bases(inp, rng, k, vary_base, impute_missing)
        pen = inp.rate[None, :] * base
        if vary_ratios:
            mult = np.ones((k, len(inp.rate), len(CONDITIONS)))
            for j, c in enumerate(CONDITIONS):
                pool = inp.drift.get(c)
                if pool is not None and len(pool):
                    mult[:, :, j] = np.exp(rng.choice(pool, size=(k, len(inp.rate))))
            shares = condition_shares(inp.excess[None], inp.drg_ratio[None], mult)
        else:
            shares = np.broadcast_to(condition_shares(inp.excess, inp.drg_ratio, None), (k, *inp.excess.shape))
        for key, v in _rollup(pen, shares, inp.group).items():
            parts.setdefault(key, []).append(v)
        done += k
    return {key: np.concatenate(v) for key, v in parts.items()}


def interval_table(draws: dict, point: dict) -> pd.DataFrame:
    """One row per total: point estimate, mean, 5th / 50th / 95th percentile, contains flag."""
    rows = []
    for key, v in draws.items():
        kind, _, name = key.partition(":")
        p = float(point.get(key, np.zeros(1))[0])
        lo, med, hi = np.percentile(v, LEVELS)
        rows.append({"level": kind, "name": name or "national", "point_estimate_usd": p,
                     "mc_mean_usd": float(v.mean()), "p5_usd": float(lo), "p50_usd": float(med),
                     "p95_usd": float(hi), "interval_contains_point": bool(lo <= p <= hi)})
    return pd.DataFrame(rows)
