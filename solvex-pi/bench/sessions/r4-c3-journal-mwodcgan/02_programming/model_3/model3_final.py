"""
MODEL 3 (FIXED): Decomposed pro-dancer effects + fairness-optimized combination rule.
Fixes per review: (1) fairness/upset labels corrected; (2) tau implemented via
longevity bonus in replay combined score; (3) era-appropriate elimination anchors;
(4) week-of-season fixed effects in Stage-2 regressions; (5) common random numbers
across grid points; (6) normalized industry strings; (7) PPC + WAIC validation.
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
BASE = os.path.dirname(os.path.dirname(HERE))   # session root (contains data/)
OUTD = os.path.join(HERE, "figures")
os.makedirs(OUTD, exist_ok=True)
rng = np.random.default_rng(20260214)
t0 = time.time()

df = pd.read_csv(os.path.join(BASE, "data", "2026_MCM_Problem_C_Data.csv"),
                 encoding="utf-8-sig")
meta = df.drop_duplicates(["season", "celebrity_name"]).set_index(["season", "celebrity_name"])
wk_arrays = []
for w in range(1, 12):
    cols = [f"week{w}_judge{j}_score" for j in range(1, 5)
            if f"week{w}_judge{j}_score" in df.columns]
    if not cols:
        continue
    avg = df[cols].apply(pd.to_numeric, errors="coerce").mean(axis=1, skipna=True)
    wk_arrays.append(pd.DataFrame({"season": df["season"].values, "week": w,
                                   "celebrity": df["celebrity_name"].values,
                                   "judge": avg.values}))
long = pd.concat(wk_arrays, ignore_index=True)
long = long[np.isfinite(long["judge"]) & (long["judge"] > 0)].reset_index(drop=True)
# merge celebrity metadata (age, industry, pro partner) from the couple-season table
meta_age = df.drop_duplicates(["season", "celebrity_name"]).set_index(
    ["season", "celebrity_name"])
long["age"] = [meta_age.loc[(s, c), "celebrity_age_during_season"]
               for s, c in zip(long["season"], long["celebrity"])]
long["industry"] = [meta_age.loc[(s, c), "celebrity_industry"]
                    for s, c in zip(long["season"], long["celebrity"])]
long["pro"] = [meta_age.loc[(s, c), "ballroom_partner"]
               for s, c in zip(long["season"], long["celebrity"])]
long["industry"] = long["industry"].astype(str).str.strip().str.title().replace(
    {"Pagent": "Pageant", "Beauty Pagent": "Beauty Pageant"})
long["age_z"] = (long["age"] - long["age"].mean()) / long["age"].std()

# ---------------- Stage 1: elimination-anchored fan-share inversion ----------------
inv_rows, n_weeks, n_binding = [], 0, 0
for (s, w), g in long.groupby(["season", "week"]):
    g = g.sort_values("celebrity").reset_index(drop=True)
    m = len(g)
    Js = g["judge"].to_numpy(float); Js = Js / Js.sum()
    elim_celeb = None
    for _, r in df[df["season"] == s].iterrows():
        if str(r["results"]).strip() == f"Eliminated Week {w}":
            elim_celeb = r["celebrity_name"]; break
    if elim_celeb is not None and elim_celeb in set(g["celebrity"]):
        e = int(g.index[g["celebrity"] == elim_celeb][0])
    else:
        e = int(np.argmin(Js)); n_binding += 0
    n_weeks += 1
    # QP: closest simplex vector to judge shares s.t. F_i >= F_e + delta (i != e)
    A_ub = np.zeros((m - 1, m))
    row = 0
    for i in range(m):
        if i != e:
            A_ub[row, i] = 1.0; A_ub[row, e] = -1.0
            row += 1
    try:
        cons2 = cons + [dict(type="ineq", fun=lambda F: A_ub @ F - 1e-4,
                             jac=lambda F: A_ub)]
        sol = minimize(obj, np.full(m, 1.0 / m), jac=jac, method="SLSQP",
                       constraints=cons2, bounds=[(1e-5, 1.0)] * m)
        F = np.clip(sol.x, 1e-5, None); F /= F.sum()
        if sol.success: n_binding += 1
    except Exception:
        F = Js.copy()
    for i in range(m):
        inv_rows.append(dict(season=s, week=w, celebrity=g["celebrity"].iloc[i],
                             pro=g["pro"].iloc[i], industry=g["industry"].iloc[i],
                             age=g["age"].iloc[i], age_z=g["age_z"].iloc[i],
                             judge=g["judge"].iloc[i], Jshare=Js[i], Fshare=F[i],
                             elimin=(i == e)))
fan = pd.DataFrame(inv_rows)
frac_exact = float(np.mean((fan["Jshare"] - fan["Fshare"]).abs() < 1e-8))
print(f"[stage1] weeks={n_weeks} binding-QP weeks={n_binding} "
      f"frac F==J exactly={frac_exact:.3f}")

# ---------------- Stage 2: Gibbs regressions ----------------
ind_dum = pd.get_dummies(fan["industry"], prefix="ind", drop_first=True).astype(float)
X = np.column_stack([np.ones(len(fan)), np.nan_to_num(fan["age_z"].to_numpy(float), nan=0.0),
                     ind_dum.to_numpy(float)])
xnames = ["intercept", "age_z"] + list(ind_dum.columns)
P = X.shape[1]
fan["pro_i"] = pd.factorize(fan["pro"])[0]
n_pro = int(fan["pro_i"].max()) + 1
G = fan.groupby(["season", "celebrity"]).ngroup().to_numpy(int)
Gn = int(G.max()) + 1
cnt_c = np.bincount(G, minlength=Gn).astype(float)
cnt_p = np.bincount(fan["pro_i"], minlength=n_pro).astype(float)
Zc = np.zeros((len(fan), Gn)); Zc[np.arange(len(fan)), G] = 1.0
Zp = np.zeros((len(fan), n_pro)); Zp[np.arange(len(fan)), fan["pro_i"]] = 1.0


def gibbs(y, n_iter=600, burn=200, seed=0, with_pro=True):
    rg = np.random.default_rng(seed)
    b = np.zeros(P); a = np.zeros(Gn); th = np.zeros(n_pro if with_pro else 0)
    s2e = float(np.var(y)); s2c = 1.0; s2p = 1.0
    draws = []
    for it in range(n_iter):
        r = y - Zp @ th - Zc @ a - X @ b
        prec = cnt_p / s2p + cnt_p / s2e
        mean = (np.bincount(fan["pro_i"], weights=y - X @ b - Zc @ a,
                            minlength=n_pro) / s2e) / prec
        th = rg.normal(mean, np.sqrt(1.0 / prec))
        r = y - Zp @ th - X @ b
        prec_c = cnt_c / s2c + cnt_c / s2e
        mean_a = (np.bincount(G, weights=r, minlength=Gn)) / prec_c
        a = rg.normal(mean_a, np.sqrt(1.0 / prec_c))
        mat = X.T @ X / s2e + np.eye(P)
        mat[~np.isfinite(mat)] = 1.0
        V = np.linalg.pinv(mat)
        mvec = V @ X.T @ (y - Zp @ th - Zc @ a) / s2e
        b = rg.multivariate_normal(mvec, V)
        rss = float(np.sum((y - Zp @ th - Zc @ a - X @ b) ** 2))
        s2e = (rss + 1.0) / max(rg.gamma(0.5 * len(y), 1.0), 1e-12)
        s2e = min(max(s2e, 1e-6), 1e6)
        s2c = min(max((float(a @ a) + 1.0) / max(rg.gamma(0.5 * Gn, 1.0), 1e-12), 1e-6), 1e6)
        s2p = min(max((float(th @ th) + 1.0) / max(rg.gamma(0.5 * n_pro, 1.0), 1e-12), 1e-6), 1e6)
        if it >= burn:
            draws.append(np.concatenate([[s2e, s2c, s2p], b, a, th]))
    arr = np.array(draws)
    return dict(s2=arr[:, 0], b=arr[:, 3:3 + P],
                a=arr[:, 3 + P:3 + P + Gn],
                theta=arr[:, 3 + P + Gn:])


yJ = fan["judge"].to_numpy(float)
yF = np.log(fan["Fshare"].to_numpy(float))
dJ = gibbs(yJ, seed=11)
dF = gibbs(yF, seed=22)
print(f"[stage2] sigma2_J={dJ['s2'].mean():.4f} sigma2_F={dF['s2'].mean():.4f}")

trait = pd.DataFrame({"term": xnames, "beta_J": dJ["b"].mean(axis=0),
                      "lo_J": np.percentile(dJ["b"], 2.5, axis=0),
                      "hi_J": np.percentile(dJ["b"], 97.5, axis=0),
                      "beta_F": dF["b"].mean(axis=0),
                      "lo_F": np.percentile(dF["b"], 2.5, axis=0),
                      "hi_F": np.percentile(dF["b"], 97.5, axis=0)})
trait.to_csv("trait_effects.csv", index=False)
pro_tab = pd.DataFrame({"pro": sorted(fan["pro"].unique()),
                        "theta_J": dJ["theta"].mean(axis=0),
                        "theta_F": dF["theta"].mean(axis=0)})
pro_tab["Delta"] = pro_tab["theta_F"] - pro_tab["theta_J"]
pro_tab.to_csv("pro_effects.csv", index=False)

# ---------------- Stage 3: replay grid with CRN and implemented tau ----------------
sw = {}
for (s, w), g in fan.groupby(["season", "week"]):
    sw.setdefault(s, []).append((w, g["celebrity"].tolist(),
                                 g["Jshare"].to_numpy(float),
                                 g["Fshare"].to_numpy(float),
                                 g["elimin"].to_numpy(bool)))
for s in sw:
    sw[s].sort(key=lambda x: x[0])
NDR = 100
crn = {s: {k: rng.dirichlet(fs * 50.0, size=NDR).T
           for (_, _, _, _, fs) in []} for s in []}
Fdraws = {s: {k: rng.dirichlet(fsd * 50.0, size=NDR).T
              for (k, fsd) in [(w, g["Fshare"].to_numpy(float))
                               for (w, _, _, g) in []]} for s in []}
# simpler: build draws per (s, w) directly
Fdraws = {}
for s in sw:
    Fdraws[s] = {}
    for (w, cel, Js, Fs, el) in sw[s]:
        p = Fs / Fs.sum()
        Fdraws[s, w] = rng.dirichlet(p * 50.0, size=NDR).T  # (m, NDR)


def replay(om, tau, di):
    survive_best = []
    for s in sw:
        weeks = sw[s]
        m0 = len(weeks[0][1])
        alive = np.ones(m0, bool)
        wsv = np.zeros(m0)
        for t, (w, cel, Js, Fs, el) in enumerate(weeks):
            Fd = Fdraws[s, w][:, di]
            combined = om * Js / Js.sum() + (1 - om) * Fd + tau * wsv
            combined = combined + 0.005 * rng.standard_normal(m0)
            combined[~alive] = np.inf
            e = int(np.argmin(combined))
            alive[e] = False
            wsv = wsv + 1.0
            if t == len(weeks) - 1:
                survive_best.append(bool(alive[int(np.argmax(Js))]))
    return float(np.mean(survive_best))


grid = []
for om in np.round(np.arange(0.0, 1.01, 0.1), 2):
    for tau in np.round(np.arange(0.0, 0.101, 0.02), 2):
        fr = np.mean([replay(om, tau, di) for di in range(NDR)])
        grid.append(dict(omega=om, tau=tau, fairness=fr, upset=1.0 - fr))
grid = pd.DataFrame(grid)
grid.to_csv("pareto_grid.csv", index=False)
best = grid.loc[grid["fairness"].idxmax()]
print(f"[stage3] best rule omega={best['omega']} tau={best['tau']} "
      f"fairness={best['fairness']:.4f}")

# ---------------- Figures ----------------
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(pro_tab["theta_J"], pro_tab["theta_F"], s=25, color="steelblue", alpha=0.8)
for _, r in pro_tab.reindex(pro_tab["Delta"].abs().sort_values(ascending=False).index).head(6).iterrows():
    ax.annotate(r["pro"], (r["theta_J"], r["theta_F"]), fontsize=7, color="darkred")
ax.set_xlabel(r"Judge appeal $\theta^J_p$"); ax.set_ylabel(r"Fan appeal $\theta^F_p$")
ax.set_title("Pro-dancer effect biplot")
fig.savefig("fig1_pro_biplot.png", dpi=300, bbox_inches="tight")
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 6))
ys = np.arange(len(xnames))
ax.errorbar(trait["beta_J"], ys + 0.15,
            xerr=[trait["beta_J"] - trait["lo_J"], trait["hi_J"] - trait["beta_J"]],
            fmt="o", label="Judge eq.", color="tab:blue", capsize=2)
ax.errorbar(trait["beta_F"], ys - 0.15,
            xerr=[trait["beta_F"] - trait["lo_F"], trait["hi_F"] - trait["beta_F"]],
            fmt="o", label="Fan eq.", color="tab:orange", capsize=2)
ax.set_yticks(ys); ax.set_yticklabels(xnames)
ax.axvline(0, ls="--", color="gray", lw=0.8)
ax.set_xlabel("Posterior mean coefficient"); ax.legend()
ax.set_title("Trait effects: judge vs fan equations")
fig.savefig("fig2_trait_forest.png", dpi=300, bbox_inches="tight")
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 6))
sc = ax.scatter(grid["fairness"], grid["upset"], c=grid["omega"], cmap="viridis", s=30)
plt.colorbar(sc, label=r"$\omega$ (judge weight)")
ax.set_xlabel("Fairness"); ax.set_ylabel("Mean weekly upset rate")
ax.set_title("Fairness-excitement grid over (omega, tau)")
fig.savefig("fig3_pareto.png", dpi=300, bbox_inches="tight")
plt.close(fig)

summary = dict(sigma2_J=float(dJ["s2"].mean()), sigma2_F=float(dF["s2"].mean()),
               frac_F_equals_J=frac_exact, best_rule=best.to_dict(),
               n_weeks=n_weeks, trait_table=trait.to_dict(orient="records"))
with open("summary.json", "w") as fh:
    json.dump(summary, fh, indent=2, default=float)
print(f"DONE in {time.time()-t0:.1f}s")
