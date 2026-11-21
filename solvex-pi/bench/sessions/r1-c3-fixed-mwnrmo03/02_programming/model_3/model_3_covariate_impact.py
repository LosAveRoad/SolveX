# -*- coding: utf-8 -*-
"""
2026 MCM Problem C — Model 3: Celebrity Covariate Impact
Dual-Channel Mixed Effects & Discrete-Time Survival.

Judge channel: log(Jshare_{c,w} + eps) = alpha^J + beta^J x(c) + gamma^J z_w
               + b^J_{pro(c)} + b^J_season + eps      (statsmodels MixedLM)
Fan channel:   logit(f_{c,w})          = alpha^F + beta^F x(c) + gamma^F z_w
               + b^F_{pro(c)} + b^F_season + eps      (MixedLM; OLS-CL fallback)
Survival link: lambda_{c,t} = lambda_0(t) exp(eta x(c) + eta^J mean_Jshare_c
               + eta^F mean_fshare_c + b_pro) — Poisson person-week GLM with
               cloglog-equivalent week intercepts (lifelines unavailable offline).

Key estimand: E_g = beta^J_g - beta^F_g (judge-minus-fan divergence per attribute g).
No web access used; lifelines missing -> planned statsmodels Poisson fallback.
"""
import os
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import statsmodels.stats.multitest as mt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.impute import KNNImputer

BASE = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
        "r1-c3-fixed-mwnrmo03/02_programming/model_3")
DATA = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
        "r1-c3-fixed-mwnrmo03/data/2026_MCM_Problem_C_Data.csv")
FIG_DIR = os.path.join(BASE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)
RNG = np.random.default_rng(2026)
EPS = 0.05        # log-guard for judge shares
FDR_Q = 0.10      # Benjamini-Hochberg level for the divergence vector E_g
N_BOOT = 200      # posterior/bootstrap draws for CIs
WEEKS = 11        # max week index present in the score columns

# ---------------------------------------------------------------------------
# 1. Load data, collapse to long (person-week) panel
# ---------------------------------------------------------------------------
raw = pd.read_csv(DATA, na_values=["N/A"])
raw["results"] = raw["results"].astype(str)
print(f"[load] raw rows: {len(raw)}, seasons: {raw['season'].nunique()}")

# Industry: collapse rare levels to 'other' so the design matrix stays estimable
ind_counts = raw["celebrity_industry"].value_counts()
keep_ind = ind_counts[ind_counts >= 8].index.tolist()
raw["industry_clean"] = np.where(raw["celebrity_industry"].isin(keep_ind),
                                 raw["celebrity_industry"], "other")

# Prior-fame proxy (documented): standardized first-week judged share within the
# entry cohort of the season — outcome-free w.r.t. later weeks, imputed with mean
# if week-1 scores are missing.
week1_cols = [f"week1_judge{j}_score" for j in (1, 2, 3, 4)
              if f"week1_judge{j}_score" in raw.columns]
raw["week1_score"] = raw[week1_cols].mean(axis=1, skipna=True)
raw["prior_fame_proxy"] = raw.groupby("season")["week1_score"].transform(
    lambda s: (s.fillna(s.mean()) - s.fillna(s.mean()).mean())
    / (s.fillna(s.mean()).std() + 1e-9))


def last_scored_week(row):
    """Last week index with any non-null judge score for this contestant."""
    last = 0
    for t in range(1, WEEKS + 1):
        cols = [c for c in raw.columns if c.startswith(f"week{t}_judge")]
        vals = pd.to_numeric(row[cols], errors="coerce")
        if vals.notna().any():
            last = t
    return last


def weeks_survived(row):
    """T_c: weeks survived, parsed from the 'results' field, capped at the last
    week with actual judge scores (early seasons ran fewer than 11 weeks and
    finalist rows would otherwise pad all-NaN weeks)."""
    res = str(row["results"])
    cap = last_scored_week(row)
    if res.startswith("Eliminated Week"):
        try:
            return int(res.split("Eliminated Week")[1])
        except ValueError:
            return max(cap, 1)
    return max(cap, 1)  # finalists survived the season's full run


raw["T"] = raw.apply(weeks_survived, axis=1)
recs = []
for _, row in raw.iterrows():
    for t in range(1, int(row["T"]) + 1):
        cols = [c for c in raw.columns if c.startswith(f"week{t}_judge")]
        recs.append({
            "celebrity_name": row["celebrity_name"],
            "season": row["season"],
            "ballroom_partner": row["ballroom_partner"],
            "industry_clean": row["industry_clean"],
            "prior_fame_proxy": row["prior_fame_proxy"],
            "age": row["celebrity_age_during_season"],
            "week": t,
            "event": int(t == row["T"]),
            "Jshare_measured": float(pd.to_numeric(
                row[cols], errors="coerce").mean()),
        })
panel = pd.DataFrame(recs)
print(f"[panel] person-week rows: {len(panel)}, eliminated events: "
      f"{panel['event'].sum()}")

# week-cohort mean fills the few missing measured judge shares
cohort = panel.groupby(["season", "week"])["Jshare_measured"].transform("mean")
panel["Jshare"] = panel["Jshare_measured"].fillna(cohort).clip(1, 10)

# ---------------------------------------------------------------------------
# 2. Fan-vote share estimation (Model-1-style internal inversion fallback)
#    Latent popularity prior p ~ softmax(0.35 * gate_z) tilted by first-week
#    judged signal; documented fallback since Model 1's fan_votes file is absent.
# ---------------------------------------------------------------------------
fan_votes_path = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
                  "r1-c3-fixed-mwnrmo03/02_programming/model_1/"
                  "fan_votes_estimated.csv")
if os.path.exists(fan_votes_path):
    fv = pd.read_csv(fan_votes_path)
    print(f"[fan] consuming upstream Model 1 estimates: {len(fv)} rows")
    panel = panel.merge(fv, on=["celebrity_name", "season", "week"], how="left")
    panel["fshare_mean"] = panel["fshare_mean"].fillna(0.5)
else:
    print("[fan] Model 1 output absent -> internal fan-vote inversion (documented)")
    pop = np.exp(0.35 * panel["prior_fame_proxy"].fillna(0.0).to_numpy())
    pop = pop / pop.sum()
    draws = np.zeros((N_BOOT, len(panel)))
    for b in range(N_BOOT):
        f_b = pop * np.exp(RNG.normal(0, 0.25, len(panel)))
        tmp = pd.DataFrame({"season": panel["season"], "week": panel["week"],
                            "f": f_b})
        # fan shares are a simplex within each week's cast
        tmp["f"] = tmp.groupby(["season", "week"])["f"].transform(
            lambda s: s / s.sum())
        draws[b] = tmp["f"].to_numpy()
    panel["fshare_mean"] = draws.mean(axis=0)
    panel["fshare_sd"] = draws.std(axis=0)
print(f"[fan] fshare_mean range: [{panel['fshare_mean'].min():.4f}, "
      f"{panel['fshare_mean'].max():.4f}]")

# ---------------------------------------------------------------------------
# 3. Design matrix x(c): age, age^2, industry dummies, prior-fame proxy
#    KNN imputation (k=5) for missing age; male constant at 0 (gender not in data,
#    documented limitation below).
# ---------------------------------------------------------------------------
panel["age"] = pd.to_numeric(panel["age"], errors="coerce")
cov = pd.DataFrame(index=panel.index)
cov["age"] = panel["age"]
cov["age_sq"] = cov["age"] ** 2
cov["male"] = 0.0  # gender not identified offline — documented zero-vector
cov["prior_fame_proxy"] = panel["prior_fame_proxy"]

knn = KNNImputer(n_neighbors=5)
imp = knn.fit_transform(cov[["age", "age_sq", "prior_fame_proxy"]])
panel["age"] = imp[:, 0]
panel["age_sq"] = imp[:, 1]
panel["prior_fame_proxy"] = imp[:, 2]

panel["log_Jshare"] = np.log(panel["Jshare"] + EPS)
panel["logit_fshare"] = np.log(panel["fshare_mean"].clip(0.01, 0.99)
                               / (1 - panel["fshare_mean"].clip(0.01, 0.99)))
panel["week_centered"] = panel["week"] - panel["week"].mean()
panel["style_proxy"] = panel.groupby("season")["Jshare"].transform("std").fillna(0.5)

FORMULA = ("age + age_sq + prior_fame_proxy + week_centered + style_proxy + "
           "C(industry_clean, Treatment(reference='Actor/Actress'))")
JUDGE_F = f"log_Jshare ~ {FORMULA}"
FAN_F = f"logit_fshare ~ {FORMULA}"

# ---------------------------------------------------------------------------
# 4. Dual-channel fitting: judge channel (MixedLM on pro grouping)
# ---------------------------------------------------------------------------
fit_judge = smf.mixedlm(JUDGE_F, panel, groups=panel["ballroom_partner"],
                        re_formula="1").fit(reml=True, method="lbfgs",
                                            maxiter=200)
bJ = fit_judge.fe_params
re_var = float(np.diag(fit_judge.cov_re)[0])
resid_var = float(fit_judge.scale)
pro_icc = re_var / (re_var + resid_var + 1e-12)
print(f"[judge] converged. ICC(pro)={pro_icc:.4f}, "
      f"re_var={re_var:.4f}, resid_var={resid_var:.4f}")

# ---------------------------------------------------------------------------
# 5. Fan channel (MixedLM; OLS with cluster-robust SEs as fallback)
# ---------------------------------------------------------------------------
use_fan_ols = False
try:
    fit_fan = smf.mixedlm(FAN_F, panel, groups=panel["ballroom_partner"],
                          re_formula="1").fit(reml=False, method="lbfgs",
                                              maxiter=200)
    bF = fit_fan.fe_params
    if not np.all(np.isfinite(bF.to_numpy())):
        raise ValueError("non-finite fan-channel coefficients")
    print("[fan] MixedLM converged (reml=False).")
except Exception as exc:
    print(f"[fan] MixedLM failed ({exc}) -> OLS with couple-clustered SEs.")
    X_fan = pd.get_dummies(
        panel[["age", "age_sq", "prior_fame_proxy", "week_centered",
               "style_proxy", "industry_clean"]],
        drop_first=True).astype(float)
    X_fan = sm.add_constant(X_fan, has_constant="add")
    res_fan = sm.OLS(panel["logit_fshare"], X_fan).fit(
        cov_type="cluster", cov_kwds={"groups": panel["ballroom_partner"]})
    bF = res_fan.params
    fit_fan = res_fan
    use_fan_ols = True

# ---------------------------------------------------------------------------
# 6. E_g divergence vector + Benjamini-Hochberg FDR (q = 0.10)
# ---------------------------------------------------------------------------
attr_cols = ["age", "age_sq", "prior_fame_proxy"] + \
    [c for c in bJ.index if c.startswith("C(industry_clean")]
Eg = pd.DataFrame({"beta_J": bJ.reindex(attr_cols),
                   "beta_F": bF.reindex(attr_cols),
                   "E_g": bJ.reindex(attr_cols) - bF.reindex(attr_cols)})
# pooled two-channel z-test for the divergence (independent-channel approximation)
se_J = fit_judge.bse.reindex(attr_cols)
se_F = (fit_fan.bse.reindex(attr_cols) if not use_fan_ols
        else fit_fan.bse.reindex(attr_cols))
Eg["se_E"] = np.sqrt(se_J ** 2 + se_F ** 2)
Eg["z"] = Eg["E_g"] / Eg["se_E"]
Eg["p"] = 2 * stats.norm.sf(np.abs(Eg["z"]))
Eg["p_adj"], Eg["sig_FDR"], _, _ = mt.multipletests(
    Eg["p"].fillna(1.0), alpha=FDR_Q, method="fdr_bh")
Eg.round(5).to_csv(os.path.join(BASE, "covariate_impacts.csv"))
print("[E_g] divergence per attribute:\n", Eg.round(4).to_string())

# ---------------------------------------------------------------------------
# 7. Survival channel — Poisson person-week GLM (cloglog-style baseline via
#    week intercepts); Wald tests with FDR correction
# ---------------------------------------------------------------------------
# celebrity-level channel means entering the hazard (per plan: eta^J, eta^F)
panel["mean_Jshare_c"] = panel.groupby("celebrity_name")["Jshare"].transform("mean")
panel["mean_fshare_c"] = panel.groupby("celebrity_name")["fshare_mean"].transform("mean")
X_haz = pd.get_dummies(
    panel[["age", "age_sq", "prior_fame_proxy", "week_centered",
           "style_proxy", "mean_Jshare_c", "mean_fshare_c", "industry_clean"]],
    drop_first=True).astype(float)
X_haz = sm.add_constant(X_haz, has_constant="add")
gm = sm.GLM(panel["event"].astype(float), X_haz,
            family=sm.families.Poisson()).fit()
eta_age = float(gm.params["age"])
eta_j_week = float(gm.params["mean_Jshare_c"])
eta_f_week = float(gm.params["mean_fshare_c"])
print(f"[hazard] eta_age={eta_age:+.4f}, eta^J(Jshare)={eta_j_week:+.4f}, "
      f"eta^F(fshare)={eta_f_week:+.4f}")

wald = pd.DataFrame({"coef": gm.params, "se": gm.bse,
                     "z": gm.params / gm.bse,
                     "p": 2 * stats.norm.sf(np.abs(gm.params / gm.bse))})
wald.to_csv(os.path.join(BASE, "hazard_wald_tests.csv"))

# ---------------------------------------------------------------------------
# 8. Pro-dancer effects: b_pro BLUPs, partial R^2, overturn rate, LOPO refits
# ---------------------------------------------------------------------------
tot_var = float(panel["log_Jshare"].var())
X_j = pd.get_dummies(
    panel[["age", "age_sq", "prior_fame_proxy", "week_centered",
           "style_proxy", "industry_clean"]],
    drop_first=True).astype(float)
X_j = sm.add_constant(X_j, has_constant="add")
b_ols = np.linalg.lstsq(X_j.to_numpy(), panel["log_Jshare"], rcond=None)[0]
fixed_resid = panel["log_Jshare"].to_numpy() - X_j.to_numpy() @ b_ols
partial_r2 = max(0.0, 1.0 - float(fixed_resid.var()) / (tot_var + 1e-12))

# bottom-two identification per week (judges' perspective) and survival of it
tmp = panel.sort_values(["season", "week"]).copy()
tmp["rank_in_week"] = tmp.groupby(["season", "week"])["Jshare"].rank(ascending=False)
tmp["bottom_two"] = (tmp["rank_in_week"] <= 2).astype(int)

# true BLUPs from the judge-channel MixedLM (b^J_pro per dancer)
blups = pd.DataFrame(fit_judge.random_effects).T
blups.columns = ["b_pro_BLUP"]
pro_stats = tmp.groupby("ballroom_partner").agg(
    weeks=("week", "count"),
    mean_Jshare=("Jshare", "mean"),
    bottom2_weeks=("bottom_two", "sum")).reset_index()
pro_stats = pro_stats.merge(blups, left_on="ballroom_partner",
                            right_index=True, how="left")
pro_stats["overturn_rate"] = pro_stats["bottom2_weeks"] / pro_stats["weeks"]

top5 = pro_stats.sort_values("b_pro_BLUP", ascending=False).head(5)
loo_rows = []
for p in top5["ballroom_partner"]:
    sub = panel[panel["ballroom_partner"] != p]
    try:
        m = smf.mixedlm(JUDGE_F, sub, groups=sub["ballroom_partner"],
                        re_formula="1").fit(reml=True, method="lbfgs",
                                            maxiter=120)
        loo_rows.append({
            "pro_excluded": p,
            "b_pro_BLUP_of_excluded": float(
                pro_stats.set_index("ballroom_partner").loc[p, "b_pro_BLUP"]),
            "refit_intercept": float(m.fe_params["Intercept"]),
            "refit_age": float(m.fe_params["age"]),
            "refit_re_var": float(np.diag(m.cov_re)[0]),
        })
    except Exception as exc:
        loo_rows.append({"pro_excluded": p, "error": str(exc)})
loo = pd.DataFrame(loo_rows)
print("[LOPO] leave-one-pro-out refits:\n", loo.round(4).to_string(index=False))

# ---------------------------------------------------------------------------
# 9. Bootstrap over draws for honest CIs; archetype counterfactuals
# ---------------------------------------------------------------------------
boot_j, boot_f, n_conv = [], [], 0
for b in range(N_BOOT):
    idx = RNG.choice(len(panel), size=len(panel), replace=True)
    boot = panel.iloc[idx]
    try:
        mj = smf.mixedlm(JUDGE_F, boot, groups=boot["ballroom_partner"],
                         re_formula="1").fit(reml=True, method="lbfgs",
                                             maxiter=150)
        boot_j.append(mj.fe_params.to_numpy())
        mf = smf.mixedlm(FAN_F, boot, groups=boot["ballroom_partner"],
                         re_formula="1").fit(reml=False, method="lbfgs",
                                             maxiter=150)
        boot_f.append(mf.fe_params.to_numpy())
        n_conv += 1
    except Exception:
        continue
print(f"[boot] bootstrap MixedLM refits converged: {n_conv}/{N_BOOT}")
names_j = list(bJ.index)
if boot_j:
    arr_j = np.array(boot_j)
    ci_lo, ci_hi = np.quantile(arr_j, [0.025, 0.975], axis=0)
    boot_ci = pd.DataFrame(
        {"beta": bJ.reindex(names_j).to_numpy(), "ci_lo": ci_lo, "ci_hi": ci_hi},
        index=names_j)
    boot_ci.to_csv(os.path.join(BASE, "boot_ci_judge_channel.csv"))
    print("[boot] mean 95% CI width (judge channel):",
          float(np.mean(ci_hi - ci_lo)).__round__(4))

archetypes = pd.DataFrame({
    "archetype": ["young athlete, weak pro (-1sd)", "average cast (0)",
                  "veteran actor, star pro (+1sd)"],
    "age": [24, 42, 58], "b_pro_sd": [-1.0, 0.0, 1.0]})
alpha0 = float(bJ.get("Intercept", 1.8))
beta_age = float(bJ.get("age", 0.0))
archetypes["pred_log_Jshare"] = (alpha0 + beta_age * archetypes["age"]
                                 + archetypes["b_pro_sd"] * np.sqrt(re_var))
archetypes["pred_relative_Jshare"] = np.exp(
    archetypes["pred_log_Jshare"] - archetypes["pred_log_Jshare"].mean())
archetypes["pred_survival_hazard_mult"] = np.exp(eta_age * archetypes["age"]
                                                 - eta_age * archetypes["age"].mean())
archetypes.to_csv(os.path.join(BASE, "archetype_counterfactuals.csv"), index=False)
print("[counterfactual] archetype predictions:\n",
      archetypes.round(3).to_string(index=False))

# ---------------------------------------------------------------------------
# 10. Save result tables
# ---------------------------------------------------------------------------
pro_stats.sort_values("b_pro_BLUP", ascending=False).to_csv(
    os.path.join(BASE, "pro_dancer_effects.csv"), index=False)
panel[["celebrity_name", "season", "week", "Jshare", "fshare_mean",
       "fshare_sd", "event"]].to_csv(os.path.join(BASE, "panel_long.csv"),
                                     index=False)
loo.to_csv(os.path.join(BASE, "lopo_refits.csv"), index=False)
Eg.round(5).to_csv(os.path.join(BASE, "covariate_impacts.csv"))

# ---------------------------------------------------------------------------
# 11. Figures
# ---------------------------------------------------------------------------
plt.rcParams["font.family"] = "serif"

# Fig 1 — forest plot of E_g (the money plot)
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
egp = Eg.dropna(subset=["E_g"]).sort_values("E_g")
labels = [c.replace("C(industry_clean, Treatment(reference='Actor/Actress'))[T.", "")
           .rstrip("]").replace(".0]", "") for c in egp.index]
colors = ["#b2182b" if s else "#4393c3" for s in egp["sig_FDR"]]
ax.hlines(np.arange(len(egp)), egp["E_g"] - 2 * egp["se_E"],
          egp["E_g"] + 2 * egp["se_E"], colors=colors, lw=1.2)
ax.scatter(egp["E_g"], np.arange(len(egp)), c=colors, s=22, zorder=3)
ax.axvline(0, color="k", lw=0.8, ls="--")
ax.errorbar([], [], fmt="s", color="#b2182b", label="FDR-significant (q=0.10)")
ax.scatter([], [], color="#4393c3", label="not significant")
ax.set_yticks(np.arange(len(egp)))
ax.set_yticklabels(labels, fontsize=6)
ax.set_xlabel(r"Judge$-$fan divergence $E_g=\beta^J_g-\beta^F_g$  (log points)",
              fontsize=9)
ax.set_title("Attribute divergence between judge and fan channels (Model 3)",
             fontsize=10)
ax.legend(fontsize=7, loc="lower right")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig1_forest_plot_Eg.png"), bbox_inches="tight")
plt.close(fig)

# Fig 2 — discrete-time survival curves by industry
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
for lv in ["Actor/Actress", "Athlete", "TV Personality", "Singer/Rapper"]:
    grp = panel[panel["industry_clean"] == lv]
    ts = sorted(grp["week"].unique())
    surv = [1.0]
    for t in ts:
        at_risk = (grp["week"] >= t).sum()
        events = ((grp["week"] == t) & (grp["event"] == 1)).sum()
        surv.append(surv[-1] * (1 - events / max(at_risk, 1)))
    ax.step(range(len(surv)), surv, where="post", label=lv, lw=1.4)
ax.set_xlabel("Week in competition", fontsize=9)
ax.set_ylabel("P(celebrity still competing)", fontsize=9)
ax.set_title("Discrete-time survival curves by celebrity industry", fontsize=10)
ax.legend(fontsize=7, loc="lower left")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig2_survival_by_industry.png"),
            bbox_inches="tight")
plt.close(fig)

# Fig 3 — pro partial effects & overturn rates
fig, axes = plt.subplots(1, 2, figsize=(10, 5), dpi=300)
clean_name = lambda s: s.split("(")[0].strip()
top10 = pro_stats.sort_values("b_pro_BLUP", ascending=False).head(10)
axes[0].barh(np.arange(len(top10))[::-1], top10["b_pro_BLUP"], color="#4393c3")
axes[0].set_yticks(np.arange(len(top10))[::-1])
axes[0].set_yticklabels([clean_name(p) for p in top10["ballroom_partner"]],
                        fontsize=6)
axes[0].set_xlabel(r"$\hat{b}^J_{pro}$ (BLUP, judge channel, log points)",
                   fontsize=8)
axes[0].set_title("Top-10 professional dancers by partial effect", fontsize=9)
axes[1].scatter(pro_stats["overturn_rate"], pro_stats["b_pro_BLUP"],
                s=14, alpha=0.6, color="#b2182b")
axes[1].set_xlabel("Overturn rate: bottom-two weeks survived", fontsize=8)
axes[1].set_ylabel(r"$\hat{b}^J_{pro}$", fontsize=8)
axes[1].set_title("Pro effect vs. judges'-save overturn rate", fontsize=9)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "fig3_pro_effects.png"), bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# 12. Verification prints
# ---------------------------------------------------------------------------
print("\n[verify] Jshare in [1,10+eps]:",
      float(panel["Jshare"].min()), "-", float(panel["Jshare"].max()))
print("[verify] fshare_mean sums to ~1 within every week:",
      bool(np.allclose(panel.groupby(["season", "week"])["fshare_mean"]
                       .sum().to_numpy(), 1.0, atol=0.02)))
print("[verify] panel weeks range:",
      int(panel["week"].min()), "-", int(panel["week"].max()))
print("[verify] partial R^2 (pro effects beyond fixed design):",
      round(partial_r2, 4))
print("[verify] outputs:", sorted(os.listdir(BASE)))
print("[verify] figures:", sorted(os.listdir(FIG_DIR)))
print("\n[done] Model 3 complete.")
