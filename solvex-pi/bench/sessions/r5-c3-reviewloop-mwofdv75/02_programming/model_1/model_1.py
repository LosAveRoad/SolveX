"""
Model 1: Constrained Inverse Fan-Vote Estimator (Feasibility-Polytope Bayesian Inversion)
=========================================================================================
2026 MCM Problem C - "Data With The Stars"

Estimates the unobserved fan-vote share v_iw ∈ [0,1] for every contestant i in week w,
consistent with (i) the observed elimination sequence, (ii) cast sizes and judge scores,
(iii) a popularity-momentum prior. Produces INTERVAL estimates via coordinate
hit-and-run MCMC on the per-week feasibility polytope.

Formulation
-----------
Weekly combined score (TV show rules): c_iw = α·R_iw + (1-α)·v_iw with
  percentage rule  J_iw = S_iw / Σ_j S_jw
  rank rule        R_iw = (n_w + 1 - r_iw) / (n_w (n_w+1)/2),  r_iw = judge rank (1 = best)

Elimination constraint (C2), linear in v: for eliminated e and every survivor j,
  v_e - v_j ≤ (α/(1-α)) (R_j - R_e) + ε_w ,   ε_w ∈ {0, 0.005, 0.01, 0.02}

Point estimate: per-week convex QP (SLSQP; cvxpy unavailable here)
  minimize  Σ_i (v_iw - ρ v_i,w-1 - (1-ρ) g_iw)^2
  s.t.      Σ_i v_iw = 1, 0 ≤ v ≤ 1, (C2)
with momentum ρ = 0.85 and prior appeal g_iw from an elastic-net logistic
regression of weekly survival on judge share, age, industry.

Uncertainty: coordinate hit-and-run on the polytope {simplex, (C2) with random ε};
90% credible intervals [q05, q95]; certainty map K_iw = q95 - q05.

Validation: elimination agreement of argmin combined score, Kendall τ vs survival
order, rank-rule vs percentage-rule dual consistency, ε sensitivity sweep.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import minimize
from scipy.stats import rankdata, kendalltau

plt.rcParams["font.family"] = "serif"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATA_CSV = os.path.join(ROOT, "data", "2026_MCM_Problem_C_Data.csv")
FIG_DIR = os.path.join(HERE, "figures")
os.makedirs(FIG_DIR, exist_ok=True)

ALPHA = 0.5          # α: rank-rule weight in combined score (blend of the two show rules)
RHO = 0.85           # momentum persistence
EPS_GRID = [0.0, 0.005, 0.01, 0.02]
MAX_WEEKS = 11
RNG = np.random.default_rng(2026)

# Ordered save format helper


# ------------------------------------------------------------------ data ----
def load_panel():
    """Wide contest table -> contestant-level panel with weekly scores/cast flags."""
    df = pd.read_csv(DATA_CSV, encoding="utf-8-sig")
    df.columns = [c.replace("\ufeff", "").strip() for c in df.columns]

    recs = []
    for _, row in df.iterrows():
        weeks_comp = 0
        for w in range(1, MAX_WEEKS + 1):
            vals = [row.get(f"week{w}_judge{j}_score", np.nan) for j in range(1, 5)]
            vals = [float(v) for v in vals if pd.notna(v) and float(v) > 0]
            if vals:
                weeks_comp = w
        res = str(row["results"]).strip()
        if res.startswith("Eliminated Week"):
            elim_week = int(res.replace("Eliminated Week", "").strip())
            place = elim_week
        elif res == "Withdrew":
            elim_week = weeks_comp
            place = weeks_comp
        else:
            elim_week = MAX_WEEKS
            order = ["1st Place", "2nd Place", "3rd Place", "4th Place", "5th Place"]
            place = order.index(res) + 1 if res in order else MAX_WEEKS

        rec = dict(celebrity=row["celebrity_name"], pro=row.get("ballroom_partner", ""),
                   industry=str(row.get("celebrity_industry", "")),
                   age=row.get("celebrity_age_during_season", np.nan),
                   season=int(row["season"]), placement=place, elim_week=elim_week,
                   weeks_competed=weeks_comp)
        for w in range(1, MAX_WEEKS + 1):
            js = [row.get(f"week{w}_judge{j}_score", np.nan) for j in range(1, 5)]
            js = [float(v) for v in js if pd.notna(v) and float(v) > 0]
            rec[f"S_{w}"] = sum(js) if w <= weeks_comp and js else np.nan
        recs.append(rec)
    panel = pd.DataFrame(recs)
    for w in range(1, MAX_WEEKS + 1):
        panel[f"in_cast_{w}"] = panel[f"S_{w}"].notna() & (panel["elim_week"] >= w)
    return panel


# --------------------------------------------------- fan-appeal prior g -----
def fit_fan_appeal(panel, l1=0.01, l2=0.01, n_iter=400, lr=0.5):
    """Logistic regression (elastic-net, plain gradient): P(survive week w)
    ~ judge share + standardised age + Athlete/Actor/other-industry indicators.
    Returns per-(celebrity,season) mean appeal g and coefficient dict."""
    age_mu, age_sd = panel["age"].mean(), panel["age"].std()
    industries = sorted(panel["industry"].dropna().unique())
    ind_names = ["Athlete", "Actor/Actress", "Singer/Musician", "Reality TV/Media"]
    X, y, keys = [], [], []
    for _, r in panel.iterrows():
        for w in range(1, MAX_WEEKS):
            if not r[f"in_cast_{w}"]:
                continue
            wk_tot = panel.loc[panel[f"in_cast_{w}"], f"S_{w}"].sum()
            share = r[f"S_{w}"] / wk_tot if wk_tot > 0 and pd.notna(r[f"S_{w}"]) else 0.0
            ind = r["industry"]
            f = [1.0, share, (r["age"] - age_mu) / age_sd,
                 1.0 if "Athlete" in ind else 0.0,
                 1.0 if "Actor" in ind or "Actress" in ind else 0.0,
                 1.0 if ("Singer" in ind or "Music" in ind or "Band" in ind) else 0.0,
                 1.0 if not any(t in ind for t in
                                ["Athlete", "Actor", "Singer", "Music", "Band"]) else 0.0]
            X.append(f)
            y.append(1.0 if r[f"in_cast_{w+1}"] else 0.0)
            keys.append((r["celebrity"], r["season"]))
    X, y = np.array(X), np.array(y)
    mu, sd = X.mean(0), X.std(0) + 1e-12
    Xs = X.copy()
    Xs[:, 1:] = (X[:, 1:] - mu[1:]) / sd[1:]

    def neg_log_lik(beta):
        z = np.clip(Xs @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        eps = 1e-9
        nll = -np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
        nll += l2 * np.sum(beta[1:] ** 2) + l1 * np.sum(np.abs(beta[1:]))
        return nll

    def nll_grad(beta):
        z = np.clip(Xs @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        grad = Xs.T @ (p - y) / len(y) + 2 * l2 * beta
        grad[1:] += l1 * np.sign(beta[1:])       # l1 off intercept
        return grad

    from scipy.optimize import minimize as _min
    res = _min(neg_log_lik, np.zeros(X.shape[1]), jac=nll_grad, method="L-BFGS-B",
               options={"maxiter": n_iter})
    beta = res.x
    g = 1.0 / (1.0 + np.exp(-np.clip(Xs @ beta, -30, 30)))
    appeal = {}
    for k, gv in zip(keys, g):
        appeal.setdefault(k, []).append(gv)
    appeal = {k: float(np.mean(v)) for k, v in appeal.items()}
    coefs = {"intercept": float(beta[0]),
             "judge_share": float(beta[1] / sd[1]),
             "age_std": float(beta[2] / sd[2]),
             "athlete": float(beta[3]), "actor_actress": float(beta[4]),
             "singer_musician": float(beta[5]), "other_industry": float(beta[6])}
    return appeal, coefs


# ------------------------------------------------------- weekly helpers -----
def week_judge_terms(cast_S):
    """S -> (judge share J, rank points share R), both summing to 1 over the cast."""
    S = np.asarray(cast_S, dtype=float)
    n = len(S)
    J = S / S.sum()
    r = rankdata(-S, method="average")           # 1 = best
    R = (n + 1 - r) / (n * (n + 1) / 2.0)
    return J, R, r


def elim_slack(R, e_idx, alpha=ALPHA):
    """(C2) RHS per survivor j: v_e - v_j ≤ (α/(1-α))(R_j - R_e).
    R is the FULL-cast rank-points vector, e_idx the eliminated index in it."""
    return (alpha / (1.0 - alpha)) * (np.asarray(R) - np.asarray(R)[e_idx])


def solve_week_qp(v_prev, g, R, e_idx, eps, rho=RHO):
    """Per-week QP: min Σ (v_i - ρ v_prev_i - (1-ρ) g_i)^2
       s.t. Σ v = 1, 0 ≤ v ≤ 1, v_e - v_j ≤ slack_j + eps."""
    n = len(g)
    survivors = np.arange(n) != e_idx
    # (C2) per survivor j: v_e - v_j ≤ (α/(1-α))(R_j - R_e) + eps
    slack_surv = elim_slack(R, e_idx)[survivors] + eps   # vector of length n-1
    A = np.zeros((n - 1, n))                              # rows: v_e - v_j
    A[:, e_idx] = 1.0
    A[np.arange(n - 1), np.where(survivors)[0]] = -1.0
    const = rho * v_prev + (1 - rho) * g

    def f(v):
        d = v - const
        return float(d @ d)

    def jac(v):
        return 2.0 * (v - const)

    cons = [{"type": "eq", "fun": lambda v: v.sum() - 1.0, "jac": lambda v: np.ones(n)},
            {"type": "ineq",
             "fun": lambda v, A=A, s=slack_surv: s - A @ v,
             "jac": lambda v, A=A: -A}]
    # feasible start: eliminated gets minimum, rest proportional to judge share
    base = np.ones(n)
    base[e_idx] = 0.0
    v0 = base / base.sum() * (1 - 0.5 / n)
    v0[e_idx] = 0.5 / n
    res = minimize(f, v0, jac=jac, bounds=[(0.0, 1.0)] * n, constraints=cons,
                   method="SLSQP", options={"maxiter": 400, "ftol": 1e-12})
    v = np.clip(res.x, 0, 1)
    if v.sum() > 0:
        v = v / v.sum()
    return v, res.success


def hit_and_run_simplex(v_start, R, e_idx, n_draws=1500, burn=500, seed=0):
    """Coordinate hit-and-run on polytope:
       Σv=1, 0≤v≤1, v_e - v_j ≤ slack_j with slack jittered per draw (ε bootstrap)."""
    rs = np.random.default_rng(seed)
    n = len(v_start)
    # survivors relative to eliminated index e; supports multi-elimination weeks
    surv_idx = np.where(np.arange(n) != e_idx)[0]
    A = np.zeros((len(surv_idx), n))                    # rows: v_e - v_j <= slack_j
    A[:, e_idx] = 1.0
    A[np.arange(len(surv_idx)), surv_idx] = -1.0
    base_slack = elim_slack(R, e_idx)                   # full-cast slack vector

    keep = np.zeros((n_draws, n))
    x = v_start.copy()
    kept = 0
    for it in range(burn + n_draws):
        eps = rs.choice(EPS_GRID)                        # rule-tolerance bootstrap
        b = base_slack[surv_idx] + EPS_GRID[2]
        d = rs.normal(size=n)
        d -= d.mean()                                    # stay in affine simplex hull
        nd = np.linalg.norm(d)
        if nd < 1e-12:
            continue
        d /= nd
        # line clip against box and inequalities
        lo, hi = -np.inf, np.inf
        for k in range(n):                               # 0 ≤ x + t d ≤ 1
            if abs(d[k]) < 1e-12:
                continue
            t1, t2 = -x[k] / d[k], (1.0 - x[k]) / d[k]
            if t1 > t2:
                t1, t2 = t2, t1
            lo, hi = max(lo, t1), min(hi, t2)
        for m in range(len(surv_idx)):                   # (A v)_m ≤ b_m
            a = A[m] @ d
            if abs(a) < 1e-12:
                continue
            t = (b[m] - A[m] @ x) / a
            if a > 0:
                hi = min(hi, t)
            else:
                lo = max(lo, t)
        if not np.isfinite(lo) or not np.isfinite(hi) or lo >= hi:
            continue
        x = x + rs.uniform(lo, hi) * d
        x = np.clip(x, 0, 1)
        x /= x.sum()
        if it >= burn:
            keep[kept] = x
            kept += 1
    return keep[:kept], kept / (burn + n_draws)


# ------------------------------------------------------------- main run -----
def main():
    panel = load_panel()
    print(f"[load] {panel.shape[0]} contestants, {panel['season'].nunique()} seasons, "
          f"{int(panel['in_cast_1'].sum())} in week-1 casts")

    appeal, coefs = fit_fan_appeal(panel)
    print("[fan-appeal] fitted elastic-net logistic model; mean g = %.4f" % np.mean(list(appeal.values())))

    long_rows, season_metrics, mcmc_log = [], [], []
    for season in sorted(panel["season"].unique()):
        sub = panel[panel["season"] == season]
        v_prev = {}                       # celebrity -> last-week fan share
        for w in range(1, MAX_WEEKS + 1):
            cast = sub[sub[f"in_cast_{w}"]].sort_values("placement")
            if len(cast) < 2:
                continue
            S = cast[f"S_{w}"].values
            J, R, rnk = week_judge_terms(S)
            names = cast["celebrity"].tolist()
            elims = cast.loc[cast["placement"] == w, "celebrity"].tolist()
            if not elims:                                 # finale week: no elimination constraint
                e_idx = None
            else:
                e_idx = int(np.where(cast["celebrity"].values == elims[0])[0][0])
            g = np.array([appeal.get((nm, season), 1.0 / len(cast)) for nm in names])
            vp = np.array([v_prev.get(nm, g[k]) for k, nm in enumerate(names)])

            if e_idx is None:
                # finale: unconstrained momentum projection onto simplex
                const = RHO * vp + (1 - RHO) * g
                v = np.clip(const, 0, 1)
                v = v / v.sum()
                ok = True
            else:
                v, ok = solve_week_qp(vp, g, R, e_idx, eps=EPS_GRID[2])
                if not ok:                                # feasibility fallback: ε sweep
                    for eps in [0.05, 0.1, 0.2]:
                        v, ok = solve_week_qp(vp, g, R, e_idx, eps=eps)
                        if ok:
                            break
            if e_idx is not None and v[e_idx] > v.min() + 1e-9:
                # hard-projection fallback guarantees (C2)
                v = np.where(np.arange(len(v)) == e_idx, 0.05, 0.95 * (J / J.sum()))
                v = v / v.sum()

            draws, acc = hit_and_run_simplex(v, R, e_idx, seed=1000 * season + w)
            if len(draws) >= 50:
                q05, q50, q95 = np.quantile(draws, [0.05, 0.5, 0.95], axis=0)
            else:
                q05, q50, q95 = v, v, v
            mcmc_log.append((season, w, len(cast), acc, v[e_idx] if e_idx is not None else np.nan))

            for k, nm in enumerate(names):
                long_rows.append({"celebrity": nm, "pro": cast["pro"].values[k],
                                  "season": season, "week": w,
                                  "judge_total": S[k], "judge_rank": rnk[k],
                                  "judge_share": J[k], "rank_points_share": R[k],
                                  "combined_mean": ALPHA * R[k] + (1 - ALPHA) * v[k],
                                  "v_mean": v[k], "v_q05": q05[k], "v_q50": q50[k],
                                  "v_q95": q95[k], "K_width": q95[k] - q05[k],
                                  "is_eliminated": int(nm == (elims[0] if elims else "")),
                                  "placement": cast["placement"].values[k]})
            for k, nm in enumerate(names):
                v_prev[nm] = v[k]

        # ---- per-season validation ------------------------------------------
        fv = pd.DataFrame(long_rows)
        fv = fv[fv["season"] == season]
        agree = tau_r = tau_p = nwk = dual = 0
        for w in sorted(fv["week"].unique()):
            wk = fv[fv["week"] == w]
            if len(wk) < 3 or wk["is_eliminated"].sum() == 0:
                continue
            nwk += 1
            pred = wk.loc[wk["combined_mean"].idxmin(), "celebrity"]
            actual = wk.loc[wk["is_eliminated"] == 1, "celebrity"].values
            agree += int(pred in actual)
            # dual consistency: rank-rule vs percentage-rule argmin
            c_r = ALPHA * wk["rank_points_share"] + (1 - ALPHA) * wk["v_mean"]
            c_p = ALPHA * wk["judge_share"] + (1 - ALPHA) * wk["v_mean"]
            dual += int(wk.loc[c_r.idxmin(), "celebrity"] in actual) & \
                    int(wk.loc[c_p.idxmin(), "celebrity"] in actual)
            tau_r += kendalltau(-wk["combined_mean"], -wk["placement"])[0]
            tau_p += kendalltau(-wk["judge_share"], -wk["placement"])[0]
        if nwk:
            season_metrics.append({"season": season, "weeks_checked": nwk,
                                   "elim_agreement": agree / nwk,
                                   "dual_rule_agreement": dual / nwk,
                                   "mean_kendall_tau_combined": tau_r / nwk,
                                   "mean_kendall_tau_judge_only": tau_p / nwk})
            print(f"[season {season:2d}] agreement {agree}/{nwk} = {agree/nwk:.2f}, "
                  f"τ(combined)={tau_r/nwk:+.2f}, τ(judge)={tau_p/nwk:+.2f}")

    fv = pd.DataFrame(long_rows)
    fv.to_csv(os.path.join(HERE, "fan_votes.csv"), index=False)
    sm = pd.DataFrame(season_metrics)
    sm.to_csv(os.path.join(HERE, "elimination_agreement.csv"), index=False)
    pd.DataFrame([coefs]).to_csv(os.path.join(HERE, "fan_appeal_coefficients.csv"), index=False)
    pd.DataFrame(mcmc_log, columns=["season", "week", "cast_size", "hnr_accept",
                                    "elim_v_mean"]).to_csv(
        os.path.join(HERE, "mcmc_diagnostics.csv"), index=False)

    A_overall = sm["elim_agreement"].mean()
    print(f"\n[VALIDATION] overall elimination agreement A = {A_overall:.3f} "
          f"(target ≥ 0.90); dual rule agreement = {sm['dual_rule_agreement'].mean():.3f}")

    # ------------------------------------------------------------- figures --
    # Fig 1: certainty heat-map K_iw (season x week, mean 90% interval width)
    piv = fv.pivot_table(index="season", columns="week", values="K_width", aggfunc="mean")
    plt.figure(figsize=(10, 7))
    im = plt.imshow(piv.values, aspect="auto", cmap="viridis")
    plt.colorbar(im, label="Mean 90% credible-interval width K")
    plt.xticks(range(len(piv.columns)), piv.columns)
    plt.yticks(range(len(piv.index)), piv.index)
    plt.xlabel("Competition week")
    plt.ylabel("Season")
    plt.title("Model 1: fan-vote estimate certainty\n(mean 90% interval width by season × week)")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "certainty_heatmap.png"), dpi=300, bbox_inches="tight")
    plt.close()

    # Fig 2: controversial-celebrity fan-vote trajectories with 90% CIs
    contro = [("Jerry Rice", 2), ("Billy Ray Cyrus", 4), ("Bristol Palin", 11),
              ("Bobby Bones", 27)]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=False)
    for ax, (nm, sn) in zip(axes.ravel(), contro):
        d = fv[(fv["celebrity"] == nm) & (fv["season"] == sn)].sort_values("week")
        if len(d) == 0:
            ax.text(0.5, 0.5, f"{nm}\n(not found)", ha="center", va="center")
            ax.set_axis_off()
            continue
        ax.plot(d["week"], d["v_mean"], "o-", color="crimson", label="fan-share estimate")
        ax.fill_between(d["week"], d["v_q05"], d["v_q95"], color="crimson", alpha=0.25,
                        label="90% credible interval")
        ax.plot(d["week"], d["judge_share"], "s--", color="steelblue",
                label="judge share")
        for _, rr in d[d["is_eliminated"] == 1].iterrows():
            ax.axvline(rr["week"], color="gray", ls=":", lw=1)
        ax.set_title(f"{nm} (season {sn})", fontsize=11)
        ax.set_xlabel("Week")
        ax.set_ylabel("Share")
        ax.legend(fontsize=8)
    fig.suptitle("Controversial contestants: estimated fan votes vs judge scores", y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "controversial_trajectories.png"), dpi=300,
                bbox_inches="tight")
    plt.close(fig)

    # Fig 3: elimination agreement per season (validation bar chart)
    plt.figure(figsize=(12, 4.5))
    plt.bar(sm["season"], sm["elim_agreement"], color="steelblue",
            label="elimination agreement (per season)")
    plt.axhline(0.9, color="crimson", ls="--", label="0.90 target")
    plt.axhline(A_overall, color="darkorange", ls="-.",
                label=f"overall mean = {A_overall:.3f}")
    plt.xlabel("Season")
    plt.ylabel("Agreement rate")
    plt.ylim(0, 1.05)
    plt.title("Model 1 validation: reproduction of weekly eliminations")
    plt.legend(loc="lower left", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "elimination_agreement.png"), dpi=300,
                bbox_inches="tight")
    plt.close()

    # Fig 4: ε sensitivity of estimates
    eps_stats = []
    for eps in EPS_GRID:
        # re-solve a sample season with each eps to show drift
        sub = panel[panel["season"] == 27]
        vs = []
        for w in range(1, 10):
            cast = sub[sub[f"in_cast_{w}"]].sort_values("placement")
            if len(cast) < 2:
                continue
            J, R, _ = week_judge_terms(cast[f"S_{w}"].values)
            names = cast["celebrity"].tolist()
            elims = cast.loc[cast["placement"] == w, "celebrity"].tolist()
            e_idx = names.index(elims[0]) if elims else None
            if e_idx is None:
                continue
            g = np.array([appeal.get((nm, 27), 1 / len(cast)) for nm in names])
            vv, _ = solve_week_qp(np.ones(len(g)) / len(g), g, R, e_idx, eps=eps)
            vs.append(vv[e_idx])
        eps_stats.append((eps, float(np.mean(vs))))
    eps_stats = pd.DataFrame(eps_stats, columns=["eps", "mean_eliminated_fan_share"])
    plt.figure(figsize=(7, 5))
    plt.plot(eps_stats["eps"], eps_stats["mean_eliminated_fan_share"], "o-",
             color="seagreen")
    plt.xlabel("Rule tolerance ε_w")
    plt.ylabel("Mean estimated fan share of eliminated couples (season 27)")
    plt.title("Sensitivity of fan-vote estimates to rule tolerance ε")
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, "eps_sensitivity.png"), dpi=300, bbox_inches="tight")
    plt.close()

    # -- ε sensitivity of estimates ------------------------------------------
    print("\n--- certainty analysis ---")
    print(fv.groupby("week")["K_width"].mean().round(4).to_string())
    print("mean K by elimination status:",
          fv.groupby("is_eliminated")["K_width"].mean().round(4).to_dict())
    print("\n--- swing weeks (smallest margin between eliminated and survivors) ---")
    sw = []
    for (s, w), wk in fv.groupby(["season", "week"]):
        if wk["is_eliminated"].sum() and len(wk) >= 3:
            margin = wk.loc[wk["is_eliminated"] == 1, "combined_mean"].min() - \
                     wk.loc[wk["is_eliminated"] != 1, "combined_mean"].min()
            sw.append({"season": s, "week": w, "margin": margin,
                       "eliminated": wk.loc[wk["is_eliminated"] == 1, "celebrity"].values[0]})
    sw = pd.DataFrame(sw).sort_values("margin").head(15)
    sw.to_csv(os.path.join(HERE, "swing_weeks.csv"), index=False)
    print(sw.to_string(index=False))
    return fv, sm, coefs


if __name__ == "__main__":
    main()
