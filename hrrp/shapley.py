"""Exact Shapley decomposition of R-squared across groups of predictors."""
from itertools import combinations
from math import factorial

import pandas as pd
import statsmodels.formula.api as smf


def shapley_r2(data: pd.DataFrame, groups: dict[str, list[str]],
               outcome: str = "err_composite") -> tuple[dict[str, float], float]:
    """Split a model's R-squared fairly across groups of predictors.

    Fits OLS on every subset of groups (2^k fits, fine for a handful of groups). Each
    group's share is its average gain in R-squared when added, over every order the
    groups could be added in. The shares always add up to the full model's R-squared.

    groups maps a label to a list of patsy terms, e.g. {"social risk": ["dual_10pp"]}.
    Returns ({group: share}, full-model R-squared).
    """
    names = list(groups)
    r2 = {}
    for k in range(len(names) + 1):
        for subset in combinations(names, k):
            terms = [t for g in subset for t in groups[g]]
            formula = f"{outcome} ~ " + (" + ".join(terms) if terms else "1")
            r2[frozenset(subset)] = smf.ols(formula, data=data).fit().rsquared
    n = len(names)
    out = {}
    for g in names:
        total = 0.0
        others = [x for x in names if x != g]
        for k in range(n):
            for subset in combinations(others, k):
                w = factorial(k) * factorial(n - k - 1) / factorial(n)
                total += w * (r2[frozenset(subset) | {g}] - r2[frozenset(subset)])
        out[g] = total
    return out, r2[frozenset(names)]
