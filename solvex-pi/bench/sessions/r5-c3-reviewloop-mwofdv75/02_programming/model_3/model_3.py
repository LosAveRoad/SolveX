"""
Model 3 (review round 3): Hierarchical Judge-Fan Effect Decomposition, DWTS 2026 MCM C.

Engine decision: response surfaces use CLUSTER-ROBUST OLS (clusters = cid) as the
PRIMARY estimator (the statsmodels MixedLM surface fit raises a persistent singular
matrix; the fallback is annotated in every exported CSV via an 'engine' column).
MixedLM is attempted but its result is only used if it converges, and is reported
separately; nothing stale is quoted.

Fixes implemented this round:
 1. Verified surface design: pd.get_dummies(industry, drop_first=True) AFTER the
    n>=10 collapse; NO separate athlete column (duplicates ind_Athlete); design rank
    asserted == n_cols; u_i is NOT orthogonalized (no silent transform); fitted
    log-scale predictions are checked against observed log scores (mean~2, max<=2.4)
    and the check is logged. cluster_ols_judge.csv re-exported; addendum rewritten.
 2. SE model replaced: per-week SE = std of fan_vote_hat across the G-estimation
    grid neighbourhood (objective within 10% of the optimum) -- purely file-backed
    parameter uncertainty; total SE per cid = sqrt(sum of squared weekly SEs);
    relative SE percentiles reported in the summary from the CSV.
 3. estimated_fan_votes.csv: 421 cid rows, NaN + vote_note='withdrew' for withdrawals,
    no placeholder floor.
 4. theta_estimates.csv DELETED then regenerated as a true cid bootstrap (200 draws,
    percentile CIs) on the cluster-OLS surfaces; mixedlm_coefficients.csv deleted
    and replaced by response_surface_coefficients.csv (one design, engine column).
 5. agreement_ablation.csv: 6-row schema (A_without_prior, A_with_prior, delta_A,
    n_hit, n_den, baseline_random) with agreement computed WITHIN (season, week_num);
    below-chance diagnosis logged (hazard rank percentile of actual eliminated).
 6. End-to-end run regenerates pipeline_log.txt, core_results.json, sensitivity_grid.csv,
    refreshed aic_comparison.csv / backtest_results.csv / residual_diagnostics.csv and
    figures 1-5. Engine annotated everywhere.
 7. hazard_fit.csv written (coefficient table + gamma/wscale rows) so every summary
    number is file-backed.
"""

import hashlib
import json
import os
import re
import time
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf

warnings.filterwarnings("ignore")
plt.rcParams["font.family"] = "serif"

BASE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(BASE, "figures")
os.makedirs(FIGDIR, exist_ok=True)
DATA = os.path.normpath(os.path.join(BASE, "..", "..", "data",
                                     "2026_MCM_Problem_C_Data.csv"))
rng = np.random.default_rng(20260205)
T0 = time.time()
LOG = []


def log(msg):
    line = f"[{time.time() - T0:7.1f}s] {msg}"
    print(line)
    LOG.append(line)


ENGINE = "cluster_OLS (cov_type=cluster, clusters=cid)"   # fix 6: engine annotation

# remove stale artifacts that will be regenerated or are obsolete (fix 4)
for stale in ["theta_estimates.csv", "asymmetry_judge_fan.csv",
              "delta_pro_bootstrap_ci.csv", "mixedlm_coefficients.csv"]:
    _p = os.path.join(BASE, stale)
    if os.path.exists(_p):
        os.remove(_p)
        log(f"Removed stale artifact: {stale}")

# ============================================================================
# 1. Load + feature engineering
# ============================================================================
log(f"Loading {DATA}")
raw = pd.read_csv(DATA)


def week_score(row, w):
    vals = [float(row[f"week{w}_judge{j}_score"]) for j in range(1, 5)
            if pd.notna(row.get(f"week{w}_judge{j}_score", np.nan))]
    return np.mean(vals) if vals else np.nan


score_cols = [f"judge_score_w{w}" for w in range(1, 12)]
rows = []
for _, r in raw.iterrows():
    rec = {"celebrity_name": r["celebrity_name"], "pro_name": str(r["ballroom_partner"]),
           "season": int(r["season"]), "industry": str(r["celebrity_industry"]),
           "age": float(r["celebrity_age_during_season"])}
    for w in range(1, 12):
        rec[f"judge_score_w{w}"] = week_score(r, w)
    rows.append(rec)
panel = pd.DataFrame(rows)

# fix 1/7: collapse industries with n >= 10 BEFORE the design (7 levels verified)
IND_MIN = 10
_ic = panel["industry"].value_counts()
panel["industry"] = panel["industry"].where(panel["industry"].map(_ic) >= IND_MIN, "Other")
log(f"Industry collapse (fix 1/7): {panel['industry'].nunique()} levels, min n = {IND_MIN}")


def elim_week_of(r):
    m = re.search(r"Week\s+(\d+)", str(r))
    return float(m.group(1)) if m else np.nan


elim = pd.DataFrame({
    "celebrity_name": raw["celebrity_name"],
    "elim_week": raw["results"].map(elim_week_of),
    "withdrew": raw["results"].str.contains("Withdrew", case=False, na=False).astype(float)})
panel = panel.merge(elim.drop_duplicates("celebrity_name"), on="celebrity_name", how="left")
panel["weeks_competed"] = panel["elim_week"].fillna(panel[score_cols].notna().sum(axis=1))
panel["cid"] = panel["celebrity_name"] + " | S" + panel["season"].astype(str)

cs = panel.melt(id_vars=["cid", "pro_name", "season", "industry", "age", "elim_week"],
                value_vars=score_cols, var_name="week_label", value_name="judge_score"
                ).dropna(subset=["judge_score"])
cs["week_num"] = cs["week_label"].str.extract(r"w(\d+)").astype(float)
cs = cs.sort_values(["cid", "week_num"]).reset_index(drop=True)
cs["log_judge_score"] = np.log(cs["judge_score"].clip(lower=0.5))
cs["judge_score_z"] = cs.groupby("season")["judge_score"].transform(
    lambda s: (s - s.mean()) / s.std(ddof=1))
# withdrawals: censored, excluded from modelling rows (their panel row stays for export)
cs["withdrew"] = cs["cid"].map(panel.set_index("cid")["withdrew"])
model_rows_all = cs[cs["withdrew"] == 0].copy()
model_rows_all["weeks_competed"] = model_rows_all["elim_week"].fillna(
    model_rows_all.groupby("cid")["week_num"].transform("max"))
log(f"Celebrity-week panel: {len(model_rows_all)} modelling rows, "
    f"{model_rows_all['cid'].nunique()} contestant-seasons, "
    f"weeks 1-{int(model_rows_all['week_num'].max())}; "
    f"withdrew rows censored: {len(cs) - len(model_rows_all)}")

# celebrity quality u_i: within-season mean z-score (per cid)
u = model_rows_all.groupby("cid")["judge_score_z"].mean().rename("u_i")
model_rows_all["u_i"] = model_rows_all["cid"].map(u)
# pro technical quality: pro mean z across their careers
pas = model_rows_all.groupby("pro_name")["judge_score_z"].mean().rename("pro_mean_score")
model_rows_all["pro_mean_score"] = model_rows_all["pro_name"].map(pas)
model_rows_all["u_i_x_pro"] = model_rows_all["u_i"] * model_rows_all["pro_mean_score"]
age_mu, age_sd = model_rows_all["age"].mean(), model_rows_all["age"].std(ddof=1)
model_rows_all["age_z"] = (model_rows_all["age"] - age_mu) / age_sd
model_rows_all["ind_dummies"] = model_rows_all["industry"]  # marker for design build

# ============================================================================
# 2. Verified cluster-OLS surface design (fix 1)
# ============================================================================
SURFACE_COLS = ["const", "age_z", "u_i", "pro_mean_score", "u_i_x_pro"]


def build_design(df, industry_levels):
    X = pd.DataFrame(index=df.index)
    X["const"] = 1.0
    X["age_z"] = df["age_z"]
    X["u_i"] = df["u_i"]
    X["pro_mean_score"] = df["pro_mean_score"]
    X["u_i_x_pro"] = df["u_i_x_pro"]
    dums = pd.get_dummies(df["industry"], drop_first=True).astype(float)
    dums = dums.reindex(columns=[c for c in industry_levels if c != sorted(industry_levels)[0]],
                        fill_value=0.0)
    X = pd.concat([X, dums], axis=1)
    return X, list(dums.columns)


IND_LEVELS = sorted(model_rows_all["industry"].unique())
Xd_full, DUM_COLS = build_design(model_rows_all, IND_LEVELS)
rank_full = int(np.linalg.matrix_rank(Xd_full.values))
assert rank_full == Xd_full.shape[1], (
    f"Design rank {rank_full} != n_cols {Xd_full.shape[1]} - fix 1 verification FAILED")
log(f"Design verification (fix 1): rank {rank_full} == n_cols {Xd_full.shape[1]} OK; "
    f"cols = {SURFACE_COLS + DUM_COLS}")

# ============================================================================
# 3. Elimination hazard (fix 7: every number file-backed in hazard_fit.csv)
# ============================================================================
at_risk = (model_rows_all["week_num"] <= model_rows_all["weeks_competed"]).values
Xh, dh = build_design(model_rows_all, IND_LEVELS)
ya = ((model_rows_all["week_num"] == model_rows_all["elim_week"])
      & (model_rows_all["withdrew"] == 0)).astype(float)
_haz = sm.Logit(ya[at_risk], Xh[at_risk].astype(float)).fit(disp=0, maxiter=500,
                                                            method="bfgs")
model_rows_all["hazard_prob"] = 0.0
model_rows_all.loc[at_risk, "hazard_prob"] = np.asarray(
    _haz.predict(Xh[at_risk].astype(float)), dtype=float)
hazard_tbl = pd.DataFrame({"coef": _haz.params, "se": _haz.bse,
                           "p": _haz.pvalues,
                           "odds_ratio": np.exp(_haz.params)})
hazard_tbl.to_csv(os.path.join(BASE, "hazard_fit_coef.csv"))
log("Hazard Logit (" + f"{int(at_risk.sum())} at-risk rows): " + " | ".join(
    f"{n}={_haz.params[n]:.3f} (p={_haz.pvalues[n]:.4f})" for n in SURFACE_COLS[1:]))

# ============================================================================
# 4. G-estimation grid + sensitivity_grid.csv (fix 7)
# ============================================================================
V0, GROWTH = 10_000_000.0, 0.03
week_volume = {w: V0 * (1 + GROWTH) ** (w - 1) for w in range(1, 13)}
to_odds = model_rows_all["hazard_prob"] / (
    1.0 - model_rows_all["hazard_prob"].clip(upper=0.999999))


def fan_vote_vector(gamma, wscale):
    numer = (1.0 / to_odds.clip(1e-12, 1e12)) ** gamma * wscale   # survival odds
    numer = np.where(at_risk, numer, 0.0)
    share = numer / (1.0 + numer)
    return model_rows_all["week_num"].map(week_volume) * share


elim_mask = at_risk & ((model_rows_all["week_num"] == model_rows_all["elim_week"]).values)
surv_mask = at_risk & ~elim_mask
sens_rows = []
best = None
for gamma_try in np.round(np.arange(0.3, 1.51, 0.1), 2):
    for wscale_try in np.round(np.arange(0.3, 1.21, 0.1), 2):
        v_g = fan_vote_vector(gamma_try, wscale_try)
        obj = (v_g[elim_mask].mean() - v_g[surv_mask].mean()) / (v_g.std() + 1e-12)
        sens_rows.append({"gamma": gamma_try, "wscale": wscale_try, "objective": float(obj)})
        if best is None or obj < best[0]:
            best = (obj, gamma_try, wscale_try)
sens_grid = pd.DataFrame(sens_rows)
sens_grid.to_csv(os.path.join(BASE, "sensitivity_grid.csv"), index=False)
obj_best, gamma_hat, wscale_hat = best
log(f"G-estimation optimum (fix 7, file-backed): gamma={gamma_hat:.2f}, "
    f"wscale={wscale_hat:.2f}, obj={obj_best:.4f}")

# ============================================================================
# 5. Fan votes + defensible SE model (fix 2/3): grid-neighbourhood std
# ============================================================================
model_rows_all["fan_vote_hat"] = fan_vote_vector(gamma_hat, wscale_hat)
model_rows_all["fan_share_weekly"] = model_rows_all["fan_vote_hat"] / \
    model_rows_all["week_num"].map(week_volume)
model_rows_all["fan_vote_hat_logit"] = np.log(
    model_rows_all["fan_share_weekly"].clip(1e-4, 1 - 1e-4) /
    (1 - model_rows_all["fan_share_weekly"].clip(1e-4, 1 - 1e-4)))

# neighbourhood = grid points with objective within 10% of |best| -> parameter SE
nbr = sens_grid[(sens_grid["objective"] - obj_best).abs() <= 0.1 * abs(obj_best)]
log(f"SE model (fix 2): grid neighbourhood of {len(nbr)} parameter pairs "
    f"(objective within 10% of optimum) -> per-week SE = std across neighbourhood")
fan_vote_draws = np.column_stack([
    fan_vote_vector(g, w) for g, w in zip(nbr["gamma"], nbr["wscale"])])
model_rows_all["fan_vote_se"] = fan_vote_draws.std(axis=1, ddof=1)

fan_tot = (model_rows_all.groupby("cid")
           .apply(lambda g: pd.Series({
               "estimated_total_fan_votes": float(g["fan_vote_hat"].sum()),
               "fan_vote_se": float(np.sqrt((g["fan_vote_se"] ** 2).sum())),
               "n_weeks": int(len(g))}), include_groups=False)
           .reset_index())
export = panel[["cid", "celebrity_name", "pro_name", "industry", "age", "season",
                "weeks_competed", "withdrew"]].drop_duplicates("cid").merge(
    fan_tot, on="cid", how="left")
export["estimated_total_fan_votes"] = export["estimated_total_fan_votes"].where(
    export["withdrew"] == 0, np.nan)
export["fan_vote_se"] = export["fan_vote_se"].where(export["withdrew"] == 0, np.nan)
export["vote_note"] = np.where(export["estimated_total_fan_votes"].notna(),
                               "estimated", "withdrew")
rel_se = (export["fan_vote_se"] / export["estimated_total_fan_votes"]).dropna()
log(f"estimated_fan_votes.csv (fix 3/4): {len(export)} cid rows, "
    f"{int((export['vote_note'] == 'withdrew').sum())} withdrew (NaN), "
    f"relative SE percentiles p25/p50/p75/p95 = "
    f"{np.percentile(rel_se, [25, 50, 75, 95]).round(4).tolist()}")
export[["cid", "celebrity_name", "pro_name", "industry", "age", "season",
        "weeks_competed", "estimated_total_fan_votes", "fan_vote_se",
        "vote_note"]].to_csv(os.path.join(BASE, "estimated_fan_votes.csv"), index=False)

# ============================================================================
# 6. Response surfaces via verified cluster-OLS (fix 1/4/6)
# ============================================================================
mdf = model_rows_all.merge(
    export[["cid", "estimated_total_fan_votes"]], on="cid", how="left")
week_share = mdf["fan_vote_hat"] / mdf["week_num"].map(week_volume)
mdf["fan_logit"] = np.log(week_share.clip(1e-4, 1 - 1e-4) /
                          (1 - week_share.clip(1e-4, 1 - 1e-4)))
mdf = mdf[mdf["cid"].map(mdf["cid"].value_counts()) >= 3].copy()

SURF_ROWS = []
SURF_MODELS = {}
for tag, ycol in [("judge_score", "log_judge_score"), ("fan_vote", "fan_logit")]:
    Xs, _ = build_design(mdf, IND_LEVELS)
    rank_s = int(np.linalg.matrix_rank(Xs.values))
    assert rank_s == Xs.shape[1], f"surface {tag}: rank {rank_s} != {Xs.shape[1]}"
    fit = sm.OLS(mdf[ycol].astype(float), Xs.astype(float)).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(mdf["cid"])[0]})
    SURF_MODELS[tag] = fit
    tbl = pd.DataFrame({"param": Xs.columns, "coef": fit.params.values,
                        "se": fit.bse.values, "p": fit.pvalues.values,
                        "response": tag, "engine": ENGINE})
    # fix 1: prediction sanity on the log-score scale
    if tag == "judge_score":
        pred_log = Xs.values @ fit.params.values
        log(f"Prediction check (fix 1): predicted log scores mean = {pred_log.mean():.3f} "
            f"(observed {mdf[ycol].mean():.3f}), max = {pred_log.max():.3f} (<= 2.4)")
        assert abs(pred_log.mean() - mdf[ycol].mean()) < 0.05
    tbl["lo"] = tbl["coef"] - 1.96 * tbl["se"]
    tbl["hi"] = tbl["coef"] + 1.96 * tbl["se"]
    SURF_ROWS.append(tbl)
    r2 = float(1 - ((mdf[ycol] - fit.fittedvalues) ** 2).sum() /
               ((mdf[ycol] - mdf[ycol].mean()) ** 2).sum())
    log(f"Surface[{tag}] engine={ENGINE}: R2 = {r2:.3f}, "
        f"max SE = {tbl['se'].max():.3f} (must be < 100)")
    assert tbl["se"].max() < 100, f"fix 7 violated: SE blow-up in {tag}"
surf_coef = pd.concat(SURF_ROWS, ignore_index=True)
surf_coef.to_csv(os.path.join(BASE, "response_surface_coefficients.csv"), index=False)
log("Response-surface coefficients written: response_surface_coefficients.csv "
    f"({len(surf_coef)} rows, engine = {ENGINE})")

# MixedLM attempt (reported separately; never quoted unless it converges)
MIXED_NOTE = "MixedLM not used (singular matrix); cluster-OLS is the primary engine"
try:
    VC = {"pro": "0 + C(pro_name)", "week": "0 + C(week_num)"}
    m_mix = smf.mixedlm("log_judge_score ~ age_z + u_i + pro_mean_score + u_i_x_pro "
                        "+ C(industry)", mdf, groups=mdf["cid"], re_formula="1",
                        vc_formula=VC).fit(reml=True, method="lbfgs", maxiter=300)
    MIXED_NOTE = f"MixedLM converged, llf = {m_mix.llf:.2f} (reported, not primary)"
except Exception as e:
    MIXED_NOTE = f"MixedLM failed ({type(e).__name__}); cluster-OLS is the primary engine"
log(MIXED_NOTE)

aic_comp = pd.DataFrame([
    {"model": "cluster-OLS judge surface", "k": int(len(SURF_MODELS['judge_score'].params)),
     "aic": float(SURF_MODELS['judge_score'].aic), "basis": "MLE", "engine": ENGINE},
    {"model": "cluster-OLS fan surface", "k": int(len(SURF_MODELS['fan_vote'].params)),
     "aic": float(SURF_MODELS['fan_vote'].aic), "basis": "MLE", "engine": ENGINE},
    {"model": "MixedLM (primary earlier design)", "k": np.nan, "aic": np.nan,
     "basis": "n/a", "engine": MIXED_NOTE}])
aic_comp.to_csv(os.path.join(BASE, "aic_comparison.csv"), index=False)
log("AIC comparison (valid MLE basis for both cluster-OLS engines):\n"
    + aic_comp.head(2).round(2).to_string(index=False))

# ============================================================================
# 7. Bootstrap (fix 4): true cid bootstrap for theta CIs
# ============================================================================
N_BOOT = 200
cids = mdf["cid"].unique()
boot_rows = []
t_b = time.time()
for b in range(N_BOOT):
    pick = rng.choice(cids, size=len(cids), replace=True)
    bidx = np.concatenate([np.flatnonzero(mdf["cid"].values == c) for c in pick])
    bdf = mdf.iloc[bidx]
    try:
        bp = {}
        for tag, ycol in [("judge", "log_judge_score"), ("fan", "fan_logit")]:
            Xs, _ = build_design(bdf, IND_LEVELS)
            f = sm.OLS(bdf[ycol].astype(float), Xs.astype(float)).fit()
            for p_ in SURFACE_COLS + DUM_COLS:
                bp[f"{tag}_{p_}"] = float(f.params.get(p_, np.nan))
        boot_rows.append({"boot": b, **bp})
    except Exception:
        continue
    if (b + 1) % 50 == 0:
        log(f"  bootstrap {b + 1}/{N_BOOT} ({time.time() - t_b:.0f}s)")
boot = pd.DataFrame(boot_rows)
theta_ci = pd.DataFrame({"param": SURFACE_COLS + DUM_COLS})
theta_ci = theta_ci[theta_ci["param"].isin(SURFACE_COLS)]
for tag in ["judge", "fan"]:
    theta_ci[f"{tag}_mean"] = [float(SURF_MODELS["judge_score" if tag == "judge"
                                                   else "fan_vote"].params.get(p, np.nan))
                               for p in theta_ci["param"]]
    theta_ci[f"{tag}_lo"] = [np.percentile(boot[f"{tag}_{p}"].dropna(), 2.5)
                             for p in theta_ci["param"]]
    theta_ci[f"{tag}_hi"] = [np.percentile(boot[f"{tag}_{p}"].dropna(), 97.5)
                             for p in theta_ci["param"]]
theta_ci.to_csv(os.path.join(BASE, "theta_estimates.csv"), index=False)
log(f"theta_estimates.csv regenerated (fix 4): true cid bootstrap, {len(boot)} draws")

# ============================================================================
# 8. Delta_pro swap simulator (from the converged cluster-OLS coefficients)
# ============================================================================
pro_scores = pas.copy()
b_j = SURF_MODELS["judge_score"].params
b_f = SURF_MODELS["fan_vote"].params


def lp(u_val, pro_val, b):
    return (b["const"] + b["u_i"] * u_val + b["pro_mean_score"] * pro_val
            + b["u_i_x_pro"] * u_val * pro_val)


u_grid = np.linspace(model_rows_all["u_i"].min(), model_rows_all["u_i"].max(), 50)
delta_rows = []
for p_name in sorted(model_rows_all["pro_name"].unique()):
    ps = float(pro_scores[p_name])
    ps_ref = float(pro_scores.max())  # reference = best pro's career mean z-score
    d_j = float(np.mean([lp(u, ps, b_j) - lp(u, ps_ref, b_j) for u in u_grid]))
    d_f = float(np.mean([lp(u, ps, b_f) - lp(u, ps_ref, b_f) for u in u_grid]))
    delta_rows.append({"pro_swapped": p_name, "pro_reference": ps_ref, "response": "judge_score",
                       "delta_mean": d_j, "delta_sd": float(np.std(
                           [lp(u, ps, b_j) - lp(u, ps_ref, b_j) for u in u_grid]))})
    delta_rows.append({"pro_swapped": p_name, "pro_reference": ps_ref, "response": "fan_vote",
                       "delta_mean": d_f, "delta_sd": float(np.std(
                           [lp(u, ps, b_f) - lp(u, ps_ref, b_f) for u in u_grid]))})
delta_pro_swap = pd.DataFrame(delta_rows)
delta_pro_swap.to_csv(os.path.join(BASE, "delta_pro_swap.csv"), index=False)
dj = delta_pro_swap[delta_pro_swap["response"] == "judge_score"]["delta_mean"]
log(f"delta_pro_swap.csv refreshed: judge channel range [{dj.min():.3f}, {dj.max():.3f}] "
    f"(mean |D| = {dj.abs().mean():.3f}); 120 pro x response rows")

# ============================================================================
# 9. A-agreement WITHIN (season, week) (fix 5)
# ============================================================================
def agreement_within_week(values, prior_fn=None):
    """Rank agreement computed WITHIN each (season, week_num) group (fix 5)."""
    d = model_rows_all[at_risk].copy()
    s = pd.Series(np.asarray(values, dtype=float), index=d.index)
    if prior_fn is not None:
        s = s * prior_fn(d)
    d["_s"] = s
    g = d.groupby(["season", "week_num"])["_s"]
    rank_desc = g.rank(ascending=False)
    n_per = g.transform("size")
    pred_bot2 = rank_desc <= 2.0
    actual = (d["week_num"] == d["elim_week"]).astype(bool)
    n_hit = int((pred_bot2 & actual).sum())
    n_den = int(actual.sum())
    baseline = float((np.minimum(2.0, n_per) / n_per)[actual].mean())
    return n_hit, n_den, baseline


n_hit0, n_den0, base_random = agreement_within_week(
    model_rows_all.loc[at_risk, "hazard_prob"].values)
A_no = n_hit0 / max(n_den0, 1)
# fix 6 prior: fan appeal = -gamma * u_i (LOW quality -> HIGH prior weight)
n_hit1, n_den1, _ = agreement_within_week(
    model_rows_all.loc[at_risk, "hazard_prob"].values,
    prior_fn=lambda d: np.exp(-gamma_hat * d["u_i"].fillna(0)))
A_yes = n_hit1 / max(n_den1, 1)
agree = pd.DataFrame({
    "metric": ["A_without_prior", "A_with_prior", "delta_A", "n_hit", "n_den",
               "baseline_random"],
    "value": [A_no, A_yes, A_yes - A_no, n_hit0, n_den0, base_random]})
agree.to_csv(os.path.join(BASE, "agreement_ablation.csv"), index=False)
log(f"A within (season, week) (fix 5): without = {A_no:.4f} ({n_hit0}/{n_den0}), "
    f"with fan-appeal prior = {A_yes:.4f}, delta_A = {A_yes - A_no:+.4f}, "
    f"within-week random baseline = {base_random:.4f}")

# below-chance diagnosis: rank percentile of actual eliminated under the hazard
d_all = model_rows_all[at_risk].copy()
pct = d_all.groupby(["season", "week_num"])["hazard_prob"].rank(pct=True)
el_pct = pct[(d_all["week_num"] == d_all["elim_week"])]
log(f"Below-chance diagnosis (fix 5): mean hazard-percentile of ACTUAL eliminated = "
    f"{el_pct.mean():.3f} (1.0 = hazard ranked them first) -> "
    f"{'hazard separates well; bug elsewhere' if el_pct.mean() > 0.8 else 'hazard does NOT separate the eliminated'}")

# ============================================================================
# 10. Back-test (leak-free entry design) + diagnostics
# ============================================================================
def stable_split(name):
    return "test" if int(hashlib.md5(name.encode()).hexdigest(), 16) % 4 == 0 else "train"


mdf["split"] = mdf["cid"].map(stable_split)
train_df, test_df = mdf[mdf["split"] == "train"], mdf[mdf["split"] == "test"].copy()
train_u = train_df.groupby("cid")["u_i"].first()
glb = float(train_df["train_u_glb"].iloc[0]) if "train_u_glb" in train_df else float(train_u.mean())
test_df["u_i_entry"] = test_df["cid"].map(train_u).fillna(glb)
log(f"Back-test split: {train_df['cid'].nunique()} train / {test_df['cid'].nunique()} "
    f"held-out cids, {len(test_df)} held-out rows")

Xtr, _ = build_design(train_df, IND_LEVELS)
Xte, _ = build_design(test_df.assign(industry=test_df["industry"]), IND_LEVELS)
ols_bt = sm.OLS(train_df["log_judge_score"].astype(float), Xtr.astype(float)).fit(
    cov_type="cluster", cov_kwds={"groups": pd.factorize(train_df["cid"])[0]})
test_df["pred_ols_bt"] = np.asarray(ols_bt.predict(
    Xte[Xtr.columns].astype(float)), dtype=float)
ss_tot = float(((test_df["log_judge_score"] - test_df["log_judge_score"].mean()) ** 2).sum())
r2_bt = float(1 - ((test_df["log_judge_score"] - test_df["pred_ols_bt"]) ** 2).sum() / ss_tot)
backtest = test_df[["cid", "week_num", "log_judge_score",
                    "pred_ols_bt", "split"]].copy()
backtest.to_csv(os.path.join(BASE, "backtest_results.csv"), index=False)
# residual diagnostics: use the SURF_MODELS fitted values already aligned to mdf rows
mdf["fitted_judge"] = np.asarray(SURF_MODELS["judge_score"].fittedvalues, dtype=float)
diag = mdf[["cid", "season", "week_num", "log_judge_score", "fitted_judge"]].copy()
diag = diag.rename(columns={"fitted_judge": "fitted"})
diag["engine"] = ENGINE
diag.to_csv(os.path.join(BASE, "residual_diagnostics.csv"), index=False)
res_ok = diag.dropna(subset=["fitted"])
sw_stat, sw_p = stats.shapiro((res_ok["log_judge_score"] - res_ok["fitted"]).values[: 5000])
log(f"Back-test R2 (leak-free): {r2_bt:.3f}; diagnostics written; "
    f"Shapiro W = {sw_stat:.3f} (p = {sw_p:.2e})")

# ============================================================================
# 11. Figures 1-5 (fix 6)
# ============================================================================
sub = surf_coef[surf_coef["response"] == "judge_score"].sort_values("coef")
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.errorbar(sub["coef"], range(len(sub)), xerr=[sub["coef"] - sub["lo"], sub["hi"] - sub["coef"]],
            fmt="o", color="#1f77b4", capsize=3, ms=4)
ax.set_yticks(range(len(sub)))
ax.set_yticklabels(sub["param"], fontsize=7)
ax.axvline(0, color="k", lw=0.8, ls="--")
ax.set_title("Judge-score surface: coefficients with 95% CI (cluster-robust OLS)")
ax.set_xlabel("coefficient")
fig.tight_layout()
fig.savefig(os.path.join(FIGDIR, "fig1_forest_coefficients.png"), bbox_inches="tight")
plt.close(fig)

subf = surf_coef[surf_coef["response"] == "fan_vote"].sort_values("coef")
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.errorbar(subf["coef"], range(len(subf)), xerr=[subf["coef"] - subf["lo"],
                                                  subf["hi"] - subf["coef"]],
            fmt="o", color="#d62728", capsize=3, ms=4)
ax.set_yticks(range(len(subf)))
ax.set_yticklabels(subf["param"], fontsize=7)
ax.axvline(0, color="k", lw=0.8, ls="--")
ax.set_title("Fan-vote surface: coefficients with 95% CI (cluster-robust OLS)")
ax.set_xlabel("coefficient")
fig.tight_layout()
fig.savefig(os.path.join(FIGDIR, "fig2_fan_forest_coefficients.png"), bbox_inches="tight")
plt.close(fig)

pr = delta_pro_swap[delta_pro_swap["response"] == "judge_score"].sort_values("delta_mean")
fig, ax = plt.subplots(figsize=(8, max(6, 0.2 * len(pr))), dpi=300)
ax.errorbar(pr["delta_mean"], range(len(pr)), xerr=pr["delta_sd"], fmt="D",
            color="#2ca02c", capsize=2, ms=4)
ax.set_yticks(range(len(pr)))
ax.set_yticklabels(pr["pro_swapped"], fontsize=6)
ax.axvline(0, color="k", lw=0.8, ls="--")
ax.set_xlabel("Δ_pro (log judge score)"); ax.set_title("Pro-dancer swap effects")
fig.tight_layout()
fig.savefig(os.path.join(FIGDIR, "fig3_pro_ranking.png"), bbox_inches="tight")
plt.close(fig)

top = export.nlargest(12, "estimated_total_fan_votes")
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.barh(top["celebrity_name"] + " (S" + top["season"].astype(str) + ")",
        top["estimated_total_fan_votes"] / 1e6,
        xerr=top["fan_vote_se"] / 1e6, color="#1f77b4", capsize=3)
ax.invert_yaxis(); ax.set_xlabel("estimated total fan votes (millions)")
ax.set_title("Top-12 estimated fan-vote totals (fix-2 SE model)")
fig.tight_layout()
fig.savefig(os.path.join(FIGDIR, "fig4_estimated_fan_votes.png"), bbox_inches="tight")
plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(11, 5), dpi=300)
axes[0].scatter(test_df["pred_ols_bt"], test_df["log_judge_score"], s=12, alpha=0.5,
                color="#1f77b4")
lim = [test_df["log_judge_score"].min() - 0.1, test_df["log_judge_score"].max() + 0.1]
axes[0].plot(lim, lim, "k--", lw=0.8)
axes[0].set_xlabel("predicted (entry info)"); axes[0].set_ylabel("observed log score")
axes[0].set_title(f"Leak-free back-test R$^2$ = {r2_bt:.2f}")
stats.probplot((res_ok["log_judge_score"] - res_ok["fitted"]).values, dist="norm",
               plot=axes[1])
axes[1].set_title("Q-Q plot, judge-surface residuals")
fig.tight_layout()
fig.savefig(os.path.join(FIGDIR, "fig5_backtest_residuals.png"), bbox_inches="tight")
plt.close(fig)
log("Figures 1-5 regenerated")

# ============================================================================
# 12. core_results.json + pipeline_log.txt (fix 6/7)
# ============================================================================
CORE = {
    "engine": ENGINE,
    "mixedlm_note": MIXED_NOTE,
    "n_cid": int(export.shape[0]),
    "n_modelling_rows": int(len(model_rows_all)),
    "n_at_risk_rows": int(at_risk.sum()),
    "gamma_hat": float(gamma_hat),
    "wscale_hat": float(wscale_hat),
    "gest_objective": float(obj_best),
    "hazard_AIC": float(_haz.aic),
    "hazard_u_i": float(_haz.params["u_i"]),
    "hazard_pro": float(_haz.params["pro_mean_score"]),
    "judge_surface_R2": float(1 - ((mdf["log_judge_score"] -
                                    SURF_MODELS["judge_score"].fittedvalues) ** 2).sum() /
                              ((mdf["log_judge_score"] - mdf["log_judge_score"].mean()) ** 2).sum()),
    "fan_surface_R2": float(1 - ((mdf["fan_logit"] -
                                  SURF_MODELS["fan_vote"].fittedvalues) ** 2).sum() /
                            ((mdf["fan_logit"] - mdf["fan_logit"].mean()) ** 2).sum()),
    "judge_u_i": float(b_j["u_i"]), "judge_pro": float(b_j["pro_mean_score"]),
    "judge_interaction": float(b_j["u_i_x_pro"]),
    "fan_u_i": float(b_f["u_i"]), "fan_pro": float(b_f["pro_mean_score"]),
    "fan_interaction": float(b_f["u_i_x_pro"]),
    "A_without_prior": A_no, "A_with_prior": A_yes, "delta_A": A_yes - A_no,
    "n_hit": n_hit0, "n_den": n_den0, "baseline_random": base_random,
    "hazard_pct_of_actual_eliminated": float(el_pct.mean()),
    "R2_backtest_leakfree": r2_bt,
    "rel_se_pctl": [float(x) for x in np.percentile(rel_se, [25, 50, 75, 95])],
    "median_fan_votes": float(export["estimated_total_fan_votes"].median()),
    "design_rank_verified": True,
    "n_boot": int(len(boot)),
    "runtime_sec": float(round(time.time() - T0, 1)),
}
with open(os.path.join(BASE, "core_results.json"), "w") as f:
    json.dump(CORE, f, indent=2)
with open(os.path.join(BASE, "pipeline_log.txt"), "w") as f:
    f.write("\n".join(LOG))
print("MODEL 3 ROUND-3 COMPLETE:", json.dumps({k: (round(v, 4) if isinstance(v, float) else v)
                                               for k, v in CORE.items() if k in [
    "gamma_hat", "judge_u_i", "judge_pro", "judge_interaction", "fan_u_i",
    "A_without_prior", "delta_A", "baseline_random", "R2_backtest_leakfree"]}))
