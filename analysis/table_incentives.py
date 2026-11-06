#!/usr/bin/env python3
"""Estimate the Verbal Monetary Incentives regression (eq:fixed_eff) and produce
Tables tab:fixed_eff and tab:marg_eff (Appendix "Further results: Verbal
Monetary Incentives").

    Y_{ijt} ~ Binomial(n_{ijt}, p_{ijt}),
    logit(p_{ijt}) = b0 + T'b + u_i + v_j

a binomial GLM with treatment dummies (T0 baseline), model fixed effects, and
task fixed effects. tab:marg_eff is the 10 pairwise treatment contrasts with a
Tukey (studentized-range) correction over k = 5 treatment means.

Writes output/tables/tab_fixed_eff.csv and tab_marg_eff.csv. Run from repo root:
    uv run python analysis/table_incentives.py
"""

import math

import pandas as pd
import statsmodels.api as sm
from scipy.stats import studentized_range

from common import LLM_DB, TAB_DIR, connect_ro

TREAT = {
    "t0-control": "T0",
    "t1-standard-no-incentive": "T1",
    "t2-standard-incentive": "T2",
    "t3-human-no-incentive": "T3",
    "t4-human-incentive": "T4",
}


def tukey_sf(z, k=5):
    """Tukey-HSD-adjusted p-value for a contrast with z-value z (df -> inf)."""
    return float(studentized_range.sf(math.sqrt(2.0) * abs(z), k, 10**7))


def main():
    con = connect_ro(LLM_DB)
    df = pd.read_sql_query(
        "SELECT e.name AS exp, r.model, r.game, r.num_correct, r.num_trials "
        "FROM runs r JOIN experiments e ON e.id=r.experiment_id "
        "WHERE r.status='completed' AND e.name IN "
        "('t0-control','t1-standard-no-incentive','t2-standard-incentive',"
        "'t3-human-no-incentive','t4-human-incentive')",
        con,
    )
    con.close()
    df["treatment"] = df["exp"].map(TREAT)
    print(
        f"data: {len(df)} cells (model x task x treatment), "
        f"{int(df['num_trials'].sum())} trials | "
        f"{df['model'].nunique()} models, {df['game'].nunique()} tasks"
    )

    # design matrix: intercept + treatment dummies (T0 baseline) + model FE + task FE
    X = pd.DataFrame({"Intercept": 1.0}, index=df.index)
    for t in ("T1", "T2", "T3", "T4"):
        X[t] = (df["treatment"] == t).astype(float)
    X = pd.concat(
        [
            X,
            pd.get_dummies(df["model"], prefix="m", drop_first=True, dtype=float),
            pd.get_dummies(df["game"], prefix="g", drop_first=True, dtype=float),
        ],
        axis=1,
    )
    endog = pd.DataFrame(
        {"ok": df["num_correct"], "no": df["num_trials"] - df["num_correct"]}
    )
    res = sm.GLM(endog, X, family=sm.families.Binomial()).fit()
    TAB_DIR.mkdir(parents=True, exist_ok=True)

    # ---- tab:fixed_eff ----
    rows = []
    print("\ntab:fixed_eff")
    print(f"{'':12s}{'coeff':>9s}{'SE':>8s}{'z':>8s}{'Pr(>|z|)':>11s}")
    for lab in ("Intercept", "T1", "T2", "T3", "T4"):
        b, se, z, p = res.params[lab], res.bse[lab], res.tvalues[lab], res.pvalues[lab]
        rows.append({"Term": lab, "Estimate": b, "SE": se, "Stat": z, "P": p})
        ps = "<2e-16" if p < 2e-16 else f"{p:.3f}"
        print(f"{lab:12s}{b:+9.3f}{se:8.3f}{z:+8.2f}{ps:>11s}")
    pd.DataFrame(rows).to_csv(TAB_DIR / "tab_fixed_eff.csv", index=False)

    # ---- tab:marg_eff : 10 Tukey-corrected pairwise treatment contrasts ----
    params, cov = res.params, res.cov_params()
    rows = []
    print("\ntab:marg_eff  (pairwise treatment contrasts, Tukey-corrected, k=5)")
    print(f"{'contrast':12s}{'estimate':>11s}{'SE':>9s}{'z':>9s}{'Pr(>|z|)':>11s}")
    order = ("T0", "T1", "T2", "T3", "T4")
    for i in range(5):
        for j in range(i + 1, 5):
            a, b = order[i], order[j]
            # contrast beta_a - beta_b, with beta_T0 == 0 (reference)
            c = pd.Series(0.0, index=params.index)
            if a != "T0":
                c[a] += 1.0
            if b != "T0":
                c[b] -= 1.0
            est = float(c @ params)
            se = math.sqrt(float(c @ cov @ c))
            z = est / se
            p = tukey_sf(z)
            rows.append({"Contrast": f"{a}-{b}", "Estimate": est, "SE": se, "Stat": z, "P": p})
            print(f"{a + ' - ' + b:12s}{est:+11.3f}{se:9.3f}{z:+9.3f}{p:>11.3f}")
    pd.DataFrame(rows).to_csv(TAB_DIR / "tab_marg_eff.csv", index=False)


if __name__ == "__main__":
    main()
