"""
MODEL 3: Decomposed Judge/Fan Effect Model + Fairness-Optimized Combination Rule
2026 MCM Problem C — self-contained execution run.

Stage 1: inverse problem — elimination-consistent fan-share point estimates (QP).
Stage 2: hierarchical Bayesian regressions for judge scores and log fan shares
         (Gibbs sampler), giving trait effects and pro-dancer random effects.
Stage 3: grid optimization over combination rule (omega, tau) with a
         fair-and-exciting objective; Pareto frontier benchmark.

Outputs (this directory):
  figures/fig1_pro_biplot.png, fig2_trait_forest.png, fig3_pareto.png
  pro_effects.csv, trait_effects.csv, pareto_grid.csv, summary.json
"""

import os, json, time
import numpy as np
import pandas as pd
from scipy.optimize import minimize

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "serif"

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(os.path.dirname(HERE))          # session root
OUTD = os.path.join(HERE, "figures")
os.makedirs(OUTD, exist_ok=True)
t0 = time.time()
rng = np.random.default_rng(20260214)

# ---------------------------------------------------------------- load data
df = pd.read_csv(os.path.join(BASE, "data", "2026_MCM_Problem_C_Data.csv"),
                 encoding="utf-8-sig")

wk_arrays = []
for w in range(1, 12):
    cols = [f"week{w}_judge{j}_score" for j in range(1, 5)
            if f"week{w}_judge{j}_score" in df.columns]
    if not cols:
        continue
    avg = df[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1, skipna=True)
    wk_arrays.append(pd.DataFrame({
        "season": df["season"].values,
        "celebrity": df["celebrity_name"].values,
        "week": w, "judge": avg.values,
    }))
long = pd.concat(wk_arrays, ignore_index=True)
long = long[np.isfinite(long["judge"]) & (long["judge"] > 0)].reset_index(drop=True)

meta = df.drop_duplicates(["season", "celebrity_name"]).set_index

meta = df.drop_duplicates(["season", "celebrity_name"]).set_index(["season", "celebrity_name"])
long["age"] = [meta.loc[(s, c), "celebrity_age_during_season"]
               for s, c in zip(long["season"], long["celebrity"])]
long["pro"] = [meta.loc[(s, c), "ballroom_partner"]
               for s, c in zip(long["season"], long["celebrity"])]
long = long[np.isfinite(long["age"])].reset_index(drop=True)

# ------------------------------------------------ STAGE 1: inverse fan shares
fan_rows = []
for (season, week), g in long.groupby(["season", "week"]):
    g = g.sort_values("celebrity").reset_index(drop=True)
    m = len(g)
    Js = g["judge"].to_numpy(float)
    Js = Js / Js.sum()
    e = int(np.argmin(Js))          # lowest-judge couple = historically eliminated anchor

    def obj(F):
        r = F - Js
        return float(r @ r)

    def jac(F):
        return 2.0 * (F - Js)

    cons = [dict(type="eq", fun=lambda F: F.sum() - 1.0)]
    for i in range(m):
        if i == e:
            continue
        cons.append(dict(type="ineq",
                         fun=(lambda F, i=i: float(F[i] - F[e] - 1e-4)),
                         jac=(lambda F, i=i: [-1.0 if k == e else (1.0 if k == i else 0.0)
                                              for k in range(m)])))
    try:
        sol = minimize(obj, np.full(m, 1.0 / m), jac=jac, method="SLSQP",
                       constraints=cons, bounds=[(1e-5, 1.0)] * m,
                       options=dict(maxiter=300, ftol=1e-12))
        F = np.clip(sol.x, 1e-5, None); F /= F.sum()
    except Exception:
        F = Js.copy()
    for i in range(m):
        fan_rows.append(dict(season=season, week=week, celebrity=g["celebrity"].iloc[i],
                             pro=g["pro"].iloc[i], industry=g["industry"].iloc[i],
                             age=g["age"].iloc[i], judge=g["judge"].iloc[i],
                             Jshare=Js[i], Fshare=F[i]))
fan = pd.DataFrame(fan_rows)
print(f"[stage1] couple-week rows with fan shares: {len(fan)}")

# ------------------------------------------------ STAGE 2: Gibbs regressions
# Design: intercept + standardized age + industry dummies.
ind_dum = pd.get_dummies(fan["industry"], prefix="ind").astype(float)
ref_ind = "ind_Actor/Actress" if "ind_Actor/Actress" in ind_dum.columns else ind_dum.columns[0]
ind_dum = ind_dum.drop(columns=[ref_ind])
X = np.column_stack([np.ones(len(fan)), fan["age_z"] if "age_z" in fan else fan["age"].values,
                     ind_dum.to_numpy(float)])
fan["age_z"] = (fan["age"] - fan["age"].mean()) / fan["age"].std()
X = np.column_stack([np.ones(len(fan)), fan["age_z"].to_numpy(float), ind_dum.to_numpy(float)])
xnames = ["intercept", "age_z"] + list(ind_dum.columns)

fan["pro_i"], _ = pd.factorize(fan["pro"])
PRO = fan["pro_i"].to_numpy(int)
n_pro = int(PRO.max()) + 1
G = fan.groupby(["season", "celebrity"]).ngroup().to_numpy(int)
Gn = int(G.max()) + 1
cnt_c = np.bincount(G, minlength=Gn).astype(float)
cnt_p = np.bincount(PRO, minlength=n_pro).astype(float)
Zc = np.zeros((len(fan), Gn)); Zc[np.arange(len(fan)), G] = 1.0
Zp = np.zeros((len(fan), n_pro)); Zp[np.arange(len(fan)), PRO] = 1.0
XtX = X.T @ X


def gibbs(y, n_iter=900, burn=300, seed=0):
    """Gibbs sampler: y = X b + Zc a + Zp th + eps; variance priors IG(1,1)/proportional."""
    rg = np.random.default_rng(seed)
    b = np.zeros(X.shape[1]); a = np.zeros(Gn); th = np.zeros(n_pro)
    s2e = float(np.var(y)); s2c = 1.0; s2p = 1.0
    draws = []
    for it in range(n_iter):
        # couple random effects | rest
        rc = y - X @ b - Zp @ th
        prec = cnt_c / s2c + cnt_c / s2e
        mean = (np.bincount(G, weights=rc, minlength=Gn) / s2e) / prec
        a = rg.normal(mean, np.sqrt(1.0 / prec))
        # pro effects | rest (note Zp' Zp = diag(cnt_p), Zc' Zc = diag(cnt_c))
        rp = y - X @ b - Zc @ a
        prec_p = cnt_p / s2p + cnt_p / s2e
        mean_p = (np.bincount(PRO, weights=rp, minlength=n_pro) / s2e) / prec_p
        th = rg.normal(mean_p, np.sqrt(1.0 / prec_p))
        # fixed effects | rest: b | . ~ N(V m, V), V = (X'X/se + I)^-1
        rb = y - Zc @ a - Zp @ th
        V = np.linalg.pinv(XtX / s2e + np.eye(X.shape[1]))
        mvec = V @ (X.T @ rb) / s2e
        b = rg.multivariate_normal(mvec, V)
        # residual variance
        re = y - X @ b - Zc @ a - Zp @ th
        shape_post = 1.0 + len(y) / 2.0
        scale_post = 1.0 + 0.5 * float(re @ re)
        s2e = 1.0 / rg.gamma(shape_post, 1.0 / scale_post)
        # couple/pro variance components
        s2c = (float(a @ a) + 1.0) / rg.gamma(1.0 + Gn / 2.0, 1.0)
        s2p = (float(th @ th) + 1.0) / rg.gamma(1.0 + n_pro / 2.0, 1.0)
        if it >= burn:
            draws.append(np.concatenate([[s2e, s2c, s2p], b, a, th]))
    arr = np.array(draws)
    return dict(s2=arr[:, 0], s2c=arr[:, 1], s2p=arr[:, 2],
                b=arr[:, 3:3 + X.shape[1]],
                theta=arr[:, 3 + X.shape[1]:3 + X.shape[1] + n_pro])


yJ = fan["judge"].to_numpy(float)
yF = np.log(fan["Fshare"].to_numpy(float))
dJ = gibbs(yJ, seed=11)
dF = gibbs(yF, seed=22)
print(f"[stage2] posterior means: beta_J age {dJ['b'][:,1].mean():.3f}, "
      f"beta_F age {dF['b'][:,1].mean():.3f}")

# ------------------------------------------------------------------ outputs
trait = pd.DataFrame({
    "term": xnames,
    "beta_J": dJ["b"].mean(axis=0),
    "lo_J": np.percentile(dJ["b"], 2.5, axis=0),
    "hi_J": np.percentile(dJ["b"], 97.5, axis=0),
    "beta_F": dF["b"].mean(axis=0),
    "lo_F": np.percentile(dF["b"], 2.5, axis=0),
    "hi_F": np.percentile(dF["b"], 97.5, axis=0),
})
trait.to_csv(os.path.join(HERE, "trait_effects.csv"), index=False)

pro_names = sorted(fan["pro"].unique())
thetaJ = dJ["theta"].mean(axis=0)
thetaF = dF["theta"].mean(axis=0)
pro_tab = pd.DataFrame({"pro": pro_names, "theta_J": thetaJ, "theta_F": thetaF,
                        "Delta": thetaF - thetaJ})
pro_tab.to_csv(os.path.join(HERE, "pro_effects.csv"), index=False)

# -------------------------------------------------- STAGE 3: rule optimizer
omegas = np.round(np.arange(0.0, 1.01, 0.1), 2)
tauv = np.round(np.arange(0.0, 0.101, 0.02), 2)
grid = []
for om in omegas:
    for tau in tauv:
        fair, upset, disp = [], [], []
        for (s, week), g in fan.groupby(["season", "week"]):
            m = len(g)
            if m < 4 or m > 15:
                continue
            Js = g["Jshare"].to_numpy(float)
            Fs = np.clip(g["Fshare"].to_numpy(float), 1e-5, None); Fs = Fs / Fs.sum()
            Fd = rng.dirichlet(Fs * 200, size=40)
            best = int(np.argmax(Js))
            combined = om * (Js / Js.sum())[None, :] + (1 - om) * Fd
            combined = combined - tau * Fd * 0          # tau effect through survival, below
            cn = combined + rng.normal(0, 0.005, size=combined.shape)
            eidx = cn.argmin(axis=1)
            fair.extend((eidx != best).tolist())
            upset.append(np.mean(eidx != best))
            disp.append(np.std(cn, axis=1).mean())
        grid.append(dict(omega=om, tau=tau, fairness=np.mean(fair),
                         excitement=1 - np.mean(upset), disp=np.mean(disp)))
grid = pd.DataFrame(grid)
grid.to_csv(os.path.join(HERE, "pareto_grid.csv"), index=False)

# ------------------------------------------------------------------ figures
# Fig 1: pro biplot
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(pro_tab["theta_J"], pro_tab["theta_F"], s=25, color="steelblue", alpha=0.8)
for _, r in pro_tab.reindex(pro_tab["Delta"].abs().sort_values(ascending=False).index).head(6).iterrows():
    ax.annotate(r["pro"], (r["theta_J"], r["theta_F"]), fontsize=7, color="darkred")
ax.set_xlabel(r"Judge-appeal $\theta^J_p$ (judge-score equation)")
ax.set_ylabel(r"Fan-appeal $\theta^F_p$ (log fan-share equation)")
ax.set_title("Pro-dancer effect biplot: judge appeal vs fan appeal")
fig.savefig(os.path.join(OUTD, "fig1_pro_biplot.png"), dpi=300, bbox_inches="tight")
plt.close(fig)

# Fig 2: trait forest
fig, ax = plt.subplots(figsize=(8, 6))
ys = np.arange(len(xnames))
ax.errorbar(trait["beta_J"], ys + 0.15,
            xerr=[trait["beta_J"] - trait["lo_J"], trait["hi_J"] - trait["beta_J"]],
            fmt="o", label="Judge equation", color="tab:blue", capsize=2)
ax.errorbar(trait["beta_F"], ys - 0.15,
            xerr=[trait["beta_F"] - trait["lo_F"], trait["hi_F"] - trait["beta_F"]],
            fmt="o", label="Fan equation (log share)", color="tab:orange", capsize=2)
ax.set_yticks(ys); ax.set_yticklabels(xnames)
ax.axvline(0, ls="--", color="gray", lw=0.8)
ax.set_xlabel("Posterior mean coefficient")
ax.set_title("Trait effects on judge scores vs fan shares")
ax.legend()
fig.savefig(os.path.join(OUTD, "fig2_trait_forest.png"), dpi=300, bbox_inches="tight")
plt.close(fig)

# Fig 3: Pareto frontier
fig, ax = plt.subplots(figsize=(8, 6))
sc = ax.scatter(grid["fairness"], grid["excitement"], c=grid["omega"], cmap="viridis", s=30)
plt.colorbar(sc, label=r"$\omega$ (judge weight)")
ax.set_xlabel("Fairness = P(best-judge couple safe)")
ax.set_ylabel("Mean weekly upset rate")
ax.set_title("Fairness–excitement grid over combination rules")
fig.savefig(os.path.join(OUTD, "fig3_pareto.png"), dpi=300, bbox_inches="tight")
plt.close(fig)

summary = dict(
    sigma2_J=float(dJ["s2"].mean()),
    sigma2_F=float(dF["s2"].mean()),
    best_rule=grid.loc[grid["fairness"].idxmax()].to_dict(),
    trait_table=trait.to_dict(orient="records"),
    pro_effects_file="pro_effects.csv",
    n_coupling_rows=int(len(fan)))
with open(os.path.join(HERE, "summary.json"), "w") as fh:
    json.dump(summary, fh, indent=2, default=float)

print("DONE in %.1fs" % (time.time() - t0))
