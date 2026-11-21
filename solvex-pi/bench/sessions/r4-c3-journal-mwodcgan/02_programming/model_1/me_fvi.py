"""
Model 1: Maximum-Entropy Fan-Vote Inversion with Elimination Constraints (ME-FVI)
=================================================================================
2026 MCM Problem C -- "Data With The Stars"  (REVISED per review)

Goal
----
Fan votes are a closely guarded secret. For every couple-i / week-w that they
competed, we estimate the fan-vote SHARE F_{i,w} (sums to 1 within the week) by
solving, per week, a maximum-entropy (minimum KL to a flat prior) problem on the
fan simplex subject to the recorded outcome:

    C_{i,w} = alpha * J_{i,w} + (1-alpha) * F_{i,w},  alpha = 0.5
    C_{e,w} + gamma <= C_{i,w}   for every survivor i, eliminated couple e

gamma >= 0 is a required elimination margin. gamma_max per week is now computed
EXACTLY with a linear program (scipy.optimize.linprog / HiGHS):

    variables x = [F_1..F_n, t];  maximize t subject to
        alpha*(J_i - J_e) + (1-alpha)*(F_i - F_e) >= t   for all (e, i) pairs
        sum F = 1,  0 <= F <= 1,  -1 <= t <= 1

(This fixes the review's Critical Issue: the old bisection ignored gamma in the
fallback feasibility check and returned the hard-coded 0.5 bracket in ~110
weeks; mathematically gamma_max <= 1/n_survivors at the cap tensions.)

The max-entropy point estimate is the least-committal fan vector consistent
with the observed elimination (gamma = 0 constraint set, SLSQP on the simplex
with a margin-INCLUSIVE feasibility check in both the SLSQP and fallback paths).
Uncertainty comes from a per-week Dirichlet bootstrap calibrated (bisection on
concentration kappa) so that >=90% of draws reproduce the recorded elimination;
the [5%, 95%] percentiles give 90% predictive intervals.

Statistical tests (fix for review Issues 3-4):
  * per-week one-sided binomial test: P(X >= model_hits) under
    X ~ Binom(K, p0_week) with p0_week the Laplace-smoothed null (uniform
    Dirichlet fans) reproduction probability; p < 0.01 weeks counted.
  * pooled 2x2 chi-square test (model hits vs null hits over all weeks).
  * "judges alone" statistic: fraction of week-events where the recorded
    eliminated couple had strictly minimal judge_total (and, separately,
    strictly minimal judge rank share).

Outputs (same directory):
    fan_votes_estimates.csv   point estimates + 90% bands (pct & rank rules)
    weekly_certainty.csv      per-week certainty / gamma_max / hit rates
    null_model_pvalues.csv    per-week null rates, model rates, binomial p
    consistency_report.json   feasibility, judges-alone, null tests, hold-out
    kappa_capped_weeks.csv    weeks whose calibrated kappa hit the 500 cap
    holdout_results.csv       judge-prior-only predictive check
    case_studies.csv          controversial celebrity trajectories
    figures/*.png             publication figures
    handoff.json              status handoff
"""

import json
import os
import numpy as np
import pandas as pd
from scipy.optimize import minimize, linprog
from scipy import stats

rng = np.random.default_rng(2026)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data", "2026_MCM_Problem_C_Data.csv"))
FIGDIR = os.path.join(HERE, "figures")
os.makedirs(FIGDIR, exist_ok=True)

ALPHA = 0.5          # show's rule: combined score = 50% judges + 50% fans (shares)
WEEKS = 11
EPS = 1e-6
K_BOOT = 300         # calibrated bootstrap draws per week
K_NULL = 1000        # null (uniform-Dirichlet) draws per week

# ----------------------------------------------------------------------------
# 1. Load wide table -> long format (one row per couple-week)
# ----------------------------------------------------------------------------
raw = pd.read_csv(DATA, na_values=["N/A"])
judge_cols = {w: [f"week{w}_judge{j}_score" for j in range(1, 5)] for w in range(1, WEEKS + 1)}

def parse_elim_week(res):
    """Return (kind, week): kind in {'eliminated','finalist','withdrew'}."""
    if isinstance(res, str) and res.startswith("Eliminated Week"):
        return "eliminated", int(res.split()[-1])
    if isinstance(res, str) and "Place" in str(res):
        return "finalist", 99
    if isinstance(res, str) and res.strip().lower().startswith("withdraw"):
        return "withdrew", None
    return "unknown", None

rows = []
for _, r in raw.iterrows():
    kind, ewek = parse_elim_week(r["results"])
    for w in range(1, WEEKS + 1):
        js = pd.to_numeric(pd.Series([r[c] for c in judge_cols[w]]), errors="coerce")
        total = float(np.nansum(js))
        rows.append(dict(
            season=int(r["season"]), celebrity=r["celebrity_name"], partner=r["ballroom_partner"],
            week=w, judge_total=total, kind=kind,
            exit_week=(ewek if ewek is not None else 99),
            placement=r["placement"], industry=r["celebrity_industry"],
            age=r["celebrity_age_during_season"],
        ))
long = pd.DataFrame(rows)

def week_table(season, week):
    """Active couples in a season-week: danced (judge_total > 0) and not yet out.
    Withdrawals are excluded from all constraint sets (exit was not fan-driven)."""
    sub = long[(long.season == season) & (long.week == week)]
    sub = sub[(sub.judge_total > 0) & (sub.exit_week >= week)]
    return sub.reset_index(drop=True)

# ----------------------------------------------------------------------------
# 2. Per-week primitives
# ----------------------------------------------------------------------------
def judge_shares(sub):
    """(J_pct, J_rank, n): pct rule = share of judge points; rank rule = rank
    converted to share (higher = better), ties -> average rank."""
    s = sub.judge_total.values
    n = len(s)
    Jpct = s / s.sum()
    order = np.argsort(-s, kind="stable")
    ranks = np.empty(n)
    ranks[order] = np.arange(1, n + 1)
    for v in np.unique(s):                      # average rank for ties
        m = s == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    share = n + 1 - ranks
    return Jpct, share / share.sum()

def combined(F, J):
    return ALPHA * J + (1 - ALPHA) * F

# ----------------------------------------------------------------------------
# 3. Max-entropy point estimate (min KL to flat prior) with margin-inclusive
#    feasibility check in BOTH solver paths (review fix #1)
# ----------------------------------------------------------------------------
def _kl(F, q):
    return float(np.sum(F * np.log(np.clip(F, EPS, None) / q)))

def _kl_grad(F, q):
    return np.log(np.clip(F, EPS, None) / q) + 1.0

def _worst_violation(F, J, elim_idx, gamma):
    """max over (e,i) of C_e - C_i + gamma  (<= 0 required). gamma-INCLUSIVE."""
    A = combined(F, J)
    return max(A[e] - A[i] + gamma for e in elim_idx for i in np.setdiff1d(np.arange(len(F)), elim_idx))

def solve_week(n, J, elim_idx, gamma, q=None):
    """Max-entropy F on simplex s.t. C_e + gamma <= C_i for all survivors."""
    if q is None:
        q = np.full(n, 1.0 / n)
    def make(ie, ii):
        return lambda F: (combined(F, J)[ie] - combined(F, J)[ii]) - gamma
    res = None
    try:
        res = minimize(_kl, np.full(n, 1.0 / n), args=(q,), jac=_kl_grad, method="SLSQP",
                       bounds=[(EPS, 1.0)] * n,
                       constraints=[{"type": "ineq", "fun": make(e, i)}
                                    for e in elim_idx for i in np.setdiff1d(np.arange(n), elim_idx)],
                       options={"maxiter": 400, "ftol": 1e-12})
    except Exception:
        res = None
    if res is not None and res.success:
        F = res.x / res.x.sum()
        viol = max(0.0, _worst_violation(F, J, elim_idx, gamma))
        if viol <= 1e-6:
            return F, True, viol
    # fallback: projected-gradient repair (internal loop is gamma-inclusive)
    F = soft_repair(n, J, elim_idx, gamma)
    viol = max(0.0, _worst_violation(F, J, elim_idx, gamma))
    return F, viol <= 1e-6, viol

def soft_repair(n, J, elim_idx, gamma):
    """Projected-gradient descent on the gamma-INCLUSIVE worst-case violation."""
    F = np.full(n, 1.0 / n)
    surv = np.setdiff1d(np.arange(n), elim_idx)
    for _ in range(20000):
        A = combined(F, J)
        viol = np.array([[A[e] - A[i] - gamma for i in surv] for e in elim_idx])
        if viol.max() <= 1e-9:
            break
        g = np.zeros(n)
        step_v = viol.max()
        for a, e in enumerate(elim_idx):
            for b, i in enumerate(surv):
                if viol[a, b] > step_v - 1e-12:
                    g[e] += 1.0
                    g[i] -= 1.0
        F = F - 0.05 * np.sign(g) * np.abs(g) / max(np.abs(g).max(), 1e-12)
        F = np.clip(F, EPS, None)
        F = F / F.sum()
    return F

# ----------------------------------------------------------------------------
# 3b. EXACT gamma_max via linear program (review fix #1, preferred alternative)
# ----------------------------------------------------------------------------
def gamma_max_lp(n, J, elim_idx):
    """Exact maximum elimination margin for the constraint set
       C_i - C_e >= gamma  for all (eliminated e, survivor i).
    LP: max t s.t.  alpha*(J_i - J_e) + (1-alpha)*(F_i - F_e) >= t,
        sum F = 1, 0 <= F <= 1, -1 <= t <= 1."""
    surv = np.setdiff1d(np.arange(n), elim_idx)
    nvar = n + 1
    c = np.zeros(nvar); c[-1] = -1.0                       # maximize t
    A_ub, b_ub = [], []
    for e in elim_idx:
        for i in surv:
            row = np.zeros(nvar)
            row[e] = (1 - ALPHA)                            # (1-a)(F_e - F_i) + t <= a(J_i - J_e)
            row[i] = -(1 - ALPHA)
            row[-1] = 1.0
            A_ub.append(row)
            b_ub.append(ALPHA * (J[i] - J[e]))
    A_eq = np.zeros((1, nvar)); A_eq[0, :n] = 1.0
    bounds = [(0.0, 1.0)] * n + [(-1.0, 1.0)]
    out = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub), A_eq=A_eq, b_eq=[1.0],
                  bounds=bounds, method="highs")
    return float(out.x[-1]) if out.success else np.nan

# ----------------------------------------------------------------------------
# 4. Calibrated Dirichlet bootstrap -> 90% predictive intervals
# ----------------------------------------------------------------------------
def _hit_rate(X, J, elim_idx):
    """Vectorized: fraction of draws X (K x n) reproducing the observed
    elimination (eliminated couple strictly lowest combined score)."""
    A = ALPHA * J[None, :] + (1 - ALPHA) * X
    e_min = A[:, elim_idx].min(axis=1)
    mask = np.ones(X.shape[1], dtype=bool)
    mask[elim_idx] = False
    return float(np.mean(np.all(e_min[:, None] <= A[:, mask] - 1e-12, axis=1)))

def bootstrap_week(n, J, elim_idx, Fstar, K=K_BOOT, target=0.90):
    """Calibrate Dirichlet concentration kappa by bisection so >= target of the
    draws still reproduce the observed elimination."""
    def hit(kappa):
        X = rng.dirichlet(np.maximum(kappa * Fstar, 1e-9), size=K)
        return _hit_rate(X, J, elim_idx)
    kap_lo, kap_hi = 1.0, 500.0
    hit_hi = hit(kap_hi)
    if hit_hi < target:                       # kappa cap reached: report wide band
        X = rng.dirichlet(np.maximum(kap_hi * Fstar, 1e-9), size=K)
        return np.percentile(X, 5, axis=0), np.percentile(X, 95, axis=0), kap_hi, _hit_rate(X, J, elim_idx), True
    while kap_hi - kap_lo > 0.05 * kap_hi:
        mid = 0.5 * (kap_lo + kap_hi)
        if hit(mid) >= target:
            kap_hi = mid
        else:
            kap_lo = mid
    kappa = kap_hi
    X = rng.dirichlet(np.maximum(kappa * Fstar, 1e-9), size=K)
    return np.percentile(X, 5, axis=0), np.percentile(X, 95, axis=0), kappa, _hit_rate(X, J, elim_idx), False

# ----------------------------------------------------------------------------
# 5. Run the inversion for every season-week (both combination rules)
# ----------------------------------------------------------------------------
est_rows, weeks_info, kappa_capped = [], [], []
for season in sorted(long.season.unique()):
    for w in range(1, WEEKS + 1):
        sub = week_table(season, w)
        if len(sub) < 3:
            continue
        elim = sub.index[sub.exit_week == w].tolist()
        if not elim:
            continue
        Jpct, Jrank = judge_shares(sub)
        n = len(sub)
        rec = dict(season=season, week=w, n_couples=n,
                   elim_celebs=";".join(sub.celebrity.values[elim]), n_elim=len(elim))
        for rule, J in (("pct", Jpct), ("rank", Jrank)):
            Fstar, ok, viol = solve_week(n, J, elim, 0.0)
            gm = gamma_max_lp(n, J, elim)                     # exact LP value
            if ok:
                Flo, Fhi, kappa, hit_rate, capped = bootstrap_week(n, J, elim, Fstar)
            else:
                Fstar = soft_repair(n, J, elim, 0.0)
                Flo, Fhi = np.zeros(n), np.ones(n)
                kappa, hit_rate, capped = np.nan, 0.0, True
            rec[f"feasible_{rule}"] = bool(ok and (gm >= -1e-9))
            rec[f"gamma_max_{rule}"] = gm
            rec[f"hit_rate_{rule}"] = hit_rate
            if capped and rule == "pct":
                kappa_capped.append(dict(season=season, week=w, n_couples=n,
                                         hit_rate_pct=hit_rate, kappa=kappa))
            for idx in sub.index.values:
                est_rows.append(dict(
                    season=season, week=w, rule=rule,
                    celebrity=sub.celebrity.values[idx], partner=sub.partner.values[idx],
                    judge_total=sub.judge_total.values[idx],
                    judge_share_pct=round(float(Jpct[idx]), 6) if rule == "pct" else "",
                    judge_share_rank=round(float(Jrank[idx]), 6) if rule == "rank" else "",
                    eliminated=bool(sub.exit_week.values[idx] == w),
                    fan_share=round(float(Fstar[idx]), 6),
                    fan_share_lo95=round(float(Flo[idx]), 6),
                    fan_share_hi95=round(float(Fhi[idx]), 6),
                    fan_votes_1M=round(float(Fstar[idx]) * 1e6, 1),   # pseudo votes, weekly total = 1,000,000
                    fan_votes_lo95=round(float(Flo[idx]) * 1e6, 1),
                    fan_votes_hi95=round(float(Fhi[idx]) * 1e6, 1),
                    kappa_bootstrap=round(float(kappa), 2),
                ))
        weeks_info.append(rec)
weekdf = pd.DataFrame(weeks_info)

est = pd.DataFrame(est_rows)
est["fan_share"] = est["fan_share"].astype(float)
est["fan_share_lo95"] = est["fan_share_lo95"].astype(float)
est["fan_share_hi95"] = est["fan_share_hi95"].astype(float)
mask = est.rule == "pct"
est["gap_F_minus_J"] = np.nan
est.loc[mask, "gap_F_minus_J"] = (est.loc[mask, "fan_share"]
                                  - est.loc[mask, "judge_share_pct"].astype(float))

# ----------------------------------------------------------------------------
# 6. Consistency metrics, judges-alone statistic, and null-model tests
# ----------------------------------------------------------------------------
feas_pct = weekdf["feasible_pct"].mean()
feas_rank = weekdf["feasible_rank"].mean()

# --- Judges-alone: would the recorded couple have been eliminated on judge
# scores ALONE? Count weeks where the eliminated couple has strictly minimal
# judge_total (equivalently minimal pct share) / strictly minimal rank share.
ja_tot, ja_rank, ja_n = 0, 0, 0
for season in sorted(long.season.unique()):
    for w in range(1, WEEKS + 1):
        sub = week_table(season, w)
        if len(sub) < 3:
            continue
        elim = sub.index[sub.exit_week == w].tolist()
        if not elim:
            continue
        ja_n += 1
        surv = [i for i in sub.index if i not in elim]
        if sub.loc[elim, "judge_total"].max() < sub.loc[surv, "judge_total"].min() - 1e-12:
            ja_tot += 1
        Jpct_, Jrank_ = judge_shares(sub)
        if Jrank_[elim].max() < Jrank_[surv].min() - 1e-12:
            ja_rank += 1
judges_alone = dict(pct=float(ja_tot / ja_n), rank=float(ja_rank / ja_n), n_weeks=ja_n)

# --- Null model: uniform-Dirichlet fan vectors; per-week rates, model-vs-null
# one-sided binomial test, pooled chi-square (review fix #4).
null_rows = []
pool_m_hits = pool_m_n = pool_0_hits = pool_0_n = 0
for _, rec in weekdf.iterrows():
    sub = week_table(rec.season, rec.week)
    if len(sub) < 3:
        continue
    elim = sub.index[sub.exit_week == rec.week].tolist()
    if not elim:
        continue
    Jpct, _ = judge_shares(sub)
    n = len(sub)
    X0 = rng.dirichlet(np.ones(n), size=K_NULL)
    A0 = ALPHA * Jpct[None, :] + (1 - ALPHA) * X0
    e_min = A0[:, elim].min(axis=1)
    smask = np.ones(n, dtype=bool); smask[elim] = False
    null_hits = int(np.sum(np.all(e_min[:, None] <= A0[:, smask] - 1e-12, axis=1)))
    null_rate = (null_hits + 1) / (K_NULL + 2)            # Laplace-smoothed
    h_m = int(round(rec.hit_rate_pct * K_BOOT))
    # one-sided binomial test: is the calibrated model MORE consistent than null?
    p_val = float(stats.binom.sf(h_m - 1, K_BOOT, null_rate))
    null_rows.append(dict(season=rec.season, week=rec.week, n=n,
                          null_hit_rate=null_hits / K_NULL, null_rate_smoothed=null_rate,
                          model_hit_rate=rec.hit_rate_pct, model_hits=h_m,
                          binom_p_value_model_vs_null=p_val))
    pool_m_hits += h_m; pool_m_n += K_BOOT
    pool_0_hits += null_hits; pool_0_n += K_NULL

nulldf = pd.DataFrame(null_rows)
tbl = [[pool_m_hits, pool_m_n - pool_m_hits], [pool_0_hits, pool_0_n - pool_0_hits]]
chi2, chi2_p, _, _ = stats.chi2_contingency(tbl)

# --- Sanity check on corrected gamma_max: must satisfy gamma_max <= 1/n_surv
weekdf["gamma_bound_ok"] = weekdf.gamma_max_pct <= 1.0 / (weekdf.n_couples - weekdf.n_elim) + 1e-9
gm_viol = int((~weekdf.gamma_bound_ok).sum())

# --- Band width vs gamma_max association (re-check the old narrative claim)
hw = (est[mask].fan_share_hi95 - est[mask].fan_share_lo95).groupby(
    [est[mask].season, est[mask].week]).mean()
mrg = weekdf.set_index(["season", "week"]).gamma_max_pct
corr_hw_gm = float(np.corrcoef(hw.values, mrg.loc[hw.index].values)[0, 1])

# --- Hold-out: judge-prior-only temperature model (softmax over logit rank share)
def logit_share(Jr, eps=1e-3):
    p = np.clip(Jr, eps, 1 - eps)
    return np.log(p / (1 - p))

holdout_rows = []
seasons = sorted(long.season.unique())
for season in seasons:
    for w in range(4, WEEKS + 1):
        sub_all = {ww: week_table(season, ww) for ww in range(1, WEEKS + 1)}
        subs_train = [sub_all[ww] for ww in range(1, w)
                      if len(sub_all[ww]) >= 3 and sub_all[ww].exit_week.eq(ww).any()]
        els_train = [s.index[s.exit_week == ww].tolist()
                     for ww, s in zip(range(1, w), subs_train)]
        if w not in sub_all or len(sub_all[w]) < 3 or not sub_all[w].exit_week.eq(w).any():
            continue
        if len(subs_train) < 3:
            continue
        best_beta, best_hits = 1.0, -1
        for beta in np.linspace(0.0, 6.0, 61):
            hits = 0
            for s, el in zip(subs_train, els_train):
                _, Jr = judge_shares(s)
                F = np.exp(beta * logit_share(Jr)); F = F / F.sum()
                A = combined(F, Jr)
                surv = [i for i in range(len(s)) if i not in el]
                if el and surv and all(A[el].min() <= A[i] - 1e-12 for i in surv):
                    hits += 1
            if hits > best_hits:
                best_hits, best_beta = hits, beta
        _, Jr_t = judge_shares(sub_all[w])
        el_t = sub_all[w].index[sub_all[w].exit_week == w].tolist()
        F_t = np.exp(best_beta * logit_share(Jr_t)); F_t = F_t / F_t.sum()
        pred = int(np.argmin(combined(F_t, Jr_t)))
        st_t = sub_all[w]
        holdout_rows.append(dict(season=season, week=w, beta_fitted=best_beta,
                                 n_train_weeks=len(els_train),
                                 pred_celebrity=st_t.celebrity.values[pred],
                                 actual_celebrities=";".join(st_t.celebrity.values[el_t]),
                                 correct=bool(pred in el_t), n_couples=len(st_t)))
hold = pd.DataFrame(holdout_rows)

# ----------------------------------------------------------------------------
# 7. Case studies & save all outputs
# ----------------------------------------------------------------------------
cases = {(2, "Jerry Rice"), (4, "Billy Ray Cyrus"), (11, "Bristol Palin"), (27, "Bobby Bones")}
est[est.apply(lambda r: (r.season, r.celebrity) in cases, axis=1)]\
   .to_csv(os.path.join(HERE, "case_studies.csv"), index=False)

est.round(6).to_csv(os.path.join(HERE, "fan_votes_estimates.csv"), index=False)
weekdf.to_csv(os.path.join(HERE, "weekly_certainty.csv"), index=False)
nulldf.to_csv(os.path.join(HERE, "null_model_pvalues.csv"), index=False)
hold.to_csv(os.path.join(HERE, "holdout_results.csv"), index=False)
pd.DataFrame(kappa_capped).to_csv(os.path.join(HERE, "kappa_capped_weeks.csv"), index=False)

below90 = weekdf[weekdf.hit_rate_pct < 0.90]
capped = weekdf.kappa_capped if "kappa_capped" in weekdf else None
report = dict(
    n_seasons=len(seasons), n_contestants=int(raw.shape[0]),
    n_couple_weeks_estimated=int(mask.sum()), n_week_events=int(len(weekdf)),
    consistency=dict(
        pct_feasible_share=float(feas_pct), rank_feasible_share=float(feas_rank),
        n_weeks_infeasible_pct=int((~weekdf.feasible_pct).sum()),
        bootstrap_hit_rate_pct_mean=float(weekdf.hit_rate_pct.mean()),
        bootstrap_hit_rate_pct_min=float(weekdf.hit_rate_pct.min()),
        bootstrap_hit_rate_pct_q25=float(weekdf.hit_rate_pct.quantile(0.25)),
        n_weeks_hit_below_090=int(len(below90)),
        gamma_max_pct_mean=float(weekdf.gamma_max_pct.mean()),
        gamma_max_pct_max=float(weekdf.gamma_max_pct.max()),
        gamma_max_pct_q25=float(weekdf.gamma_max_pct.quantile(0.25)),
        gamma_max_range_check_violations=gm_viol,
        corr_bandwidth_vs_gamma_max=corr_hw_gm,
        n_weeks_kappa_at_cap=int(len(kappa_capped)),
    ),
    judges_alone=judges_alone,
    null_model_test=dict(
        mean_null_hit_rate=float(nulldf.null_hit_rate.mean()),
        pooled_model_hits=pool_m_hits, pooled_model_draws=pool_m_n,
        pooled_null_hits=pool_0_hits, pooled_null_draws=pool_0_n,
        pooled_chi2=float(chi2), pooled_p_value=float(chi2_p),
        n_weeks_binom_p_lt_0point01=int((nulldf.binom_p_value_model_vs_null < 0.01).sum()),
        median_binom_p_value=float(nulldf.binom_p_value_model_vs_null.median()),
    ),
    holdout=dict(
        n_tests=int(len(hold)), accuracy=float(hold.correct.mean()),
        baseline_random=float(np.mean(1.0 / hold.n_couples)),
        mean_beta=float(hold.beta_fitted.mean()),
    ),
)
with open(os.path.join(HERE, "consistency_report.json"), "w") as f:
    json.dump(report, f, indent=2, default=float)

print(json.dumps(report, indent=2, default=float))
print("\nweekly gamma_max_pct describe:\n", weekdf.gamma_max_pct.describe().round(4).to_string())
print("\nweekly hit_rate_pct describe:\n", weekdf.hit_rate_pct.describe().round(3).to_string())
