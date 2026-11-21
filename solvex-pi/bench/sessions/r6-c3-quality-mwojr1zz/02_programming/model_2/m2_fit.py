"""m2_fit.py -- Model 2 response-surface fitting, decomposition, and holdout.

Design (identical functional form on both surfaces, per the Model-2 plan):
    y = intercept + season FE + pro FE + industry FE
        + age RCS (knots 20/30/45/65) + week-in-run RCS (knots 1/3/6/10)
        + multi-dance flag

Surfaces:
    J: y^J = judge_z  (within season-week z-score of the weekly judge total;
                       dance-count/panel-size fair, sd==0 weeks -> 0)
    F: y^F = logit(fanshare + delta), delta = 8e-5 tiny offset (weekly share in (0,1))

Inference: OLS with celebrity-run cluster-robust covariance (421 clusters).
Variance decomposition R_k = 1 - RSS_restricted / RSS_full (partial R^2 eliminating
covariate class k from the design). Permutation null: shuffle class labels at run
level within season, recompute R_k (fixed streams).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from m2_data import rcs_design, RCS_KNOTS_AGE, RCS_KNOTS_WEEK

DELTA_LOGIT = 8e-5


# ------------------------------------------------------------------ design
def build_design(pan: pd.DataFrame):
    season_d = pd.get_dummies(pan["season"].astype(int), prefix="S", drop_first=True)
    pro_d = pd.get_dummies(pan["pro"].astype(str), prefix="P", drop_first=True)
    ind_d = pd.get_dummies(pan["celebrity_industry"].astype(str), prefix="I",
                           drop_first=True)
    age_b = rcs_design(pan["celebrity_age_during_season"].to_numpy(float), RCS_KNOTS_AGE)
    wk_b = rcs_design(pan["week"].to_numpy(float), RCS_KNOTS_WEEK)
    multi = pan["multi_dance_week"].to_numpy(float)[:, None]
    blocks = {
        "season": season_d.to_numpy(float),
        "pro": pro_d.to_numpy(float),
        "industry": ind_d.to_numpy(float),
        "age": age_b,
        "week": wk_b,
        "multi": multi,
    }
    names = (["intercept"]
             + [f"season_{c}" for c in season_d.columns]
             + [f"pro_{c}" for c in pro_d.columns]
             + [f"ind_{c}" for c in ind_d.columns]
             + [f"age_rcs{k}" for k in range(age_b.shape[1])]
             + [f"wk_rcs{k}" for k in range(wk_b.shape[1])]
             + ["multi_dance"])
    X = np.column_stack([np.ones(len(pan))] + [blocks[k] for k in
                                               ["season", "pro", "industry", "age",
                                                "week", "multi"]])
    return X, names, blocks


def block_slice(names, tag):
    """Column indices of a named block (pro_/ind_/age_/wk_/season_ prefix or multi)."""
    pref = {"season": "season_", "pro": "pro_", "industry": "ind_", "age": "age_",
            "week": "wk_", "multi": "multi_dance"}[tag]
    idx = [i for i, nm in enumerate(names) if nm.startswith(pref)]
    if tag == "multi":
        idx = [i for i, nm in enumerate(names) if nm == "multi_dance"]
    return np.array(idx, int)


def ols_fit(y, X, groups):
    """OLS with run-cluster robust covariance.  Returns params, bse, tvalues, pvalues,
    fitted, cov, rss, rank."""
    n, p = X.shape
    XtX = X.T @ X
    XtX_inv = np.linalg.pinv(XtX)
    XtX_inv_Xt = XtX_inv @ X.T
    b = XtX_inv_Xt @ y
    resid = y - X @ b
    fitted = X @ b
    rss = float(resid @ resid)
    # cluster-robust covariance (areg-style, drop empty clusters automatically)
    uniq, inv = np.unique(groups, return_inverse=True)
    k = len(uniq)
    meat = np.zeros((p, p))
    Xr = X * resid[:, None]
    # aggregate rows by cluster: sum of X_i e_i outer products
    sum_Xr = np.zeros((k, p))
    np.add.at(sum_Xr, inv, Xr)
    meat = sum_Xr.T @ sum_Xr
    G, N = k, n
    corr = (G / (G - 1.0)) * ((N - 1.0) / max(N - p, 1))
    V = corr * (XtX_inv @ meat @ XtX_inv)
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    with np.errstate(divide="ignore", invalid="ignore"):
        tvals = np.where(se > 0, b / se, 0.0)
    from scipy import stats as sps
    dfree = max(N - p, 1)
    pvals = 2 * sps.t.sf(np.abs(tvals), dfree)
    return dict(b=b, se=se, t=tvals, p=pvals, fitted=fitted, cov=V, rss=rss,
                rank=int(np.linalg.matrix_rank(X)), n=N)


def partial_r2(y, X, names, blocks, tag):
    """R_k = 1 - RSS(no class k) / RSS(full)."""
    full = ols_fit(y, X, np.zeros(len(y), int))
    drop = block_slice(names, tag)
    keep = np.setdiff1d(np.arange(X.shape[1]), drop)
    if len(keep) == 0:
        return 0.0
    Xr = X[:, keep]
    red = ols_fit(y, Xr, np.zeros(len(y), int))
    denom = float(((y - y.mean()) ** 2).sum())
    if full["rss"] >= red["rss"]:
        return 0.0
    return max(0.0, min(1.0, 1.0 - full["rss"] / red["rss"])) if denom > 0 else 0.0


# ------------------------------------------------------------------ surfaces
def fan_logit(share):
    s = np.clip(np.asarray(share, float), 1e-6, 1.0 - 1e-6)
    return np.log((s + DELTA_LOGIT) / (1.0 - s + DELTA_LOGIT))


def fit_surfaces(pan):
    X, names, blocks = build_design(pan)
    groups = pan["run_id"].to_numpy(int)
    yJ = pan["judge_z"].to_numpy(float)
    yF = fan_logit(pan["fanshare"].to_numpy(float))
    fitJ = ols_fit(yJ, X, groups)
    fitF = ols_fit(yF, X, groups)
    panels = dict(J=dict(y=yJ, fit=fitJ), F=dict(y=yF, fit=fitF))
    r2J = 1.0 - fitJ["rss"] / float(((yJ - yJ.mean()) ** 2).sum())
    r2F = 1.0 - fitF["rss"] / float(((yF - yF.mean()) ** 2).sum())
    return dict(X=X, names=names, blocks=blocks, panels=panels, r2=dict(J=r2J, F=r2F))


# ------------------------------------------------------------------ decomposition
def decomp(pan, fitobj, rng, n_perm=1000, perm_tags=("pro", "industry", "age", "week")):
    """R_k for both surfaces + permutation nulls (labels shuffled at RUN level within
    season, preserving the label distribution)."""
    X, names, blocks = fitobj["X"], fitobj["names"], fitobj["blocks"]
    res = []
    for surf in ("J", "F"):
        y = fitobj["panels"][surf]["y"]
        groups = pan["run_id"].to_numpy(int)
        seasons = pan["season"].to_numpy(int)
        for tag in ("pro", "industry", "age", "week", "season", "multi"):
            r_obs = partial_r2(y, X, names, blocks, tag)
            if tag not in perm_tags:
                res.append(dict(surface=surf, block=tag, R=r_obs, p_perm=np.nan,
                                null_q95=np.nan, z_perm=np.nan))
                continue
            null = np.empty(n_perm)
            for i in range(n_perm):
                Xp, namesp, _ = _permuted_design(pan, X, names, tag, rng)
                null[i] = partial_r2(y, Xp, namesp, None, tag)
            mu, sd = float(null.mean()), float(null.std(ddof=1))
            q95 = float(np.quantile(null, 0.95))
            pval = float((np.sum(null >= r_obs) + 1.0) / (n_perm + 1.0))
            z = (r_obs - mu) / sd if sd > 0 else np.nan
            res.append(dict(surface=surf, block=tag, R=r_obs, p_perm=pval,
                            null_q95=q95, z_perm=z))
        # u_c: between-run share of residual variance (ICC of residuals)
        resid = y - fitobj["panels"][surf]["fit"]["fitted"]
        rsum = pd.Series(resid).groupby(pan["run_id"].to_numpy(int)).agg(["mean", "size"])
        w = rsum["size"].to_numpy(float)
        between = float(np.average(rsum["mean"].to_numpy(float) ** 2, weights=w))
        total_var = float(np.var(resid, ddof=1))
        res.append(dict(surface=surf, block="residual-u_c",
                        R=total_var * between / max(total_var * total_var, 1e-12) if False else between / max(total_var, 1e-12),
                        p_perm=np.nan, null_q95=np.nan, z_perm=np.nan))
    return pd.DataFrame(res)


def _permuted_design(pan, X, names, tag, rng):
    """Return (X_perm, names, blocks_perm) with class-k labels shuffled at run level
    within season."""
    seasons = pan["season"].to_numpy(int)
    pos = pan["col_pro_pos"] if False else None  # (unused)
    out = X.copy()
    if tag == "pro":
        cols = block_slice(names, "pro")
        # build run -> onehot row mapping: pro dummies at (first row of run)
        run_ids = pan["run_id"].to_numpy(int)
        first_idx = pd.Series(np.arange(len(pan))).groupby(run_ids).first().to_numpy()
        lab = np.argmax(out[np.ix_(first_idx, cols)], axis=1) if len(cols) else None
        # shuffle run labels within season
        perm_lab = lab.copy()
        for s in np.unique(seasons[first_idx]):
            m = seasons[first_idx] == s
            v = lab[m]
            perm_lab[m] = rng.permutation(v)
        # rows of each run take their run's permuted one-hot
        run_of_first = run_ids[first_idx]
        lab_rowmap = dict(zip(run_of_first, perm_lab))
        newrows = np.array([lab_rowmap[r] for r in run_ids])
        out[:, cols] = 0.0
        out[np.arange(len(out)), cols[newrows]] = 1.0
    elif tag == "industry":
        cols = block_slice(names, "industry")
        run_ids = pan["run_id"].to_numpy(int)
        first_idx = pd.Series(np.arange(len(pan))).groupby(run_ids).first().to_numpy()
        lab = np.argmax(out[np.ix_(first_idx, cols)], axis=1)
        perm_lab = lab.copy()
        for s in np.unique(seasons[first_idx]):
            m = seasons[first_idx] == s
            perm_lab[m] = rng.permutation(lab[m])
        lab_rowmap = dict(zip(run_ids[first_idx], perm_lab))
        newrows = np.array([lab_rowmap[r] for r in run_ids])
        out[:, cols] = 0.0
        out[np.arange(len(out)), cols[newrows]] = 1.0
    elif tag == "age":
        cols = block_slice(names, "age")
        # continuous: must re-derive basis after shuffling ages (spline basis is
        # nonlinear in age).
        from m2_data import RCS_KNOTS_AGE, rcs_design
        run_ids = pan["run_id"].to_numpy(int)
        first_idx = pd.Series(np.arange(len(pan))).groupby(run_ids).first().to_numpy()
        # age per run from the linear column (col0 is age itself)
        age_run = out[first_idx, cols[0]]
        perm_age = age_run.copy()
        for s in np.unique(seasons[first_idx]):
            m = seasons[first_idx] == s
            perm_age[m] = rng.permutation(age_run[m])
        age_rowmap = dict(zip(run_ids[first_idx], perm_age))
        age_rows = np.array([age_rowmap[r] for r in run_ids])
        out[:, cols] = rcs_design(age_rows, RCS_KNOTS_AGE)
    elif tag == "week":
        cols = block_slice(names, "week")
        from m2_data import RCS_KNOTS_WEEK, rcs_design
        run_ids = pan["run_id"].to_numpy(int)
        first_idx = pd.Series(np.arange(len(pan))).groupby(run_ids).first().to_numpy()
        wk_run = out[first_idx, cols[0]]  # linear column is week itself
        perm_wk = wk_run.copy()
        for s in np.unique(seasons[first_idx]):
            m = seasons[first_idx] == s
            perm_wk[m] = rng.permutation(wk_run[m])
        wk_rowmap = dict(zip(run_ids[first_idx], perm_wk))
        wk_rows = np.array([wk_rowmap[r] for r in run_ids])
        out[:, cols] = rcs_design(wk_rows, RCS_KNOTS_WEEK)
    return out, names, None


# ------------------------------------------------------------------ LOSO honesty
def loso_r2(pan, fitobj):
    """Leave-one-season-out honest R^2 for both surfaces (refit without season s,
    predict season s)."""
    X, names = fitobj["X"], fitobj["names"]
    seasons = pan["season"].to_numpy(int)
    out = {}
    for surf in ("J", "F"):
        y = fitobj["panels"][surf]["y"]
        yhat = np.full(len(y), np.nan)
        for s in np.unique(seasons):
            tr = seasons != s
            te = ~tr
            Xt, yt = X[tr], y[tr]
            pinv = np.linalg.pinv(Xt.T @ Xt) @ Xt.T
            bs = pinv @ yt
            yhat[te] = X[te] @ bs
        r2 = 1.0 - float(((y - yhat) ** 2).sum()) / float(((y - y.mean()) ** 2).sum())
        out[surf] = r2
    return out


# ------------------------------------------------------------------ restricted spec
def restricted_pro_r2(pan, yJ, yF, X, names):
    """Sorting-adjusted ("honest lower bound") pro partial R2.

    Naive spec: pro block added last, after season+week+industry+age+multi.  But pro
    assignments are NOT random (producers hand better celebrities to star pros).  The
    restricted spec adds a pre-treatment fame control -- the celebrity's week-1 fan
    share (logit), observed BEFORE any week-2+ dance information -- so the pro block
    is identified from variance ORTHOGONAL to celebrity entry popularity.
    Returns dict(R_naive_J, R_naive_F, R_restricted_J, R_restricted_F).
    """
    out = {}
    # Fame control I: week-1 fan share (entry popularity, pre-treatment).
    w1 = pan[pan["week"] == 1][["run_id", "fanshare"]].set_index("run_id")["fanshare"]
    fame = w1.reindex(pan["run_id"].to_numpy()).to_numpy(float)
    fame = np.clip(fame, 1e-6, 1 - 1e-6)
    fame_l = np.log(fame / (1 - fame))
    # Fame control II (preferred): MAP persona C_run from the fanshare stage (pre-eval
    # popularity backed out of elimination constraints); its NAIVE week-1 reading is
    # contaminated by judge quality, so control BOTH.
    import m2_fanshare as MF
    pos = pan["run_id"].to_numpy(int)
    # persona vector is embedded in the fitted fans via map; re-derive cheaply:
    # persona = mean of U contribution over run rows minus beta*judge_z - theta*week
    # Not stored in pan; approximate with the run-mean of logit(fanshare) at WEEK 1
    # subtracting the fitted entry effect: use fame_l only (documented).
    cols_pro = block_slice(names, "pro")
    keep = np.setdiff1d(np.arange(X.shape[1]), cols_pro)
    mask = pan["week"].to_numpy() >= 2          # exclude premiere rows (sorting
                                                 # strongest there)
    for tag, y in (("judge", yJ), ("fan", yF)):
        r_full = rss_of(y[mask], X[mask])
        r_red = rss_of(y[mask], X[mask][:, keep])
        Xr = np.column_stack([X[mask][:, keep], fame_l[mask]])
        r_red_r = rss_of(y[mask], Xr)
        Xc = np.column_stack([Xr, X[mask][:, cols_pro]])
        r_full_r = rss_of(y[mask], Xc)
        out[f"R_pro_naive_{tag}_wk2plus"] = 1.0 - r_full / r_red
        out[f"R_fame_control_{tag}"] = 1.0 - r_red_r / r_red
        out[f"R_pro_restricted_{tag}"] = 1.0 - r_full_r / r_red_r
    return out


def rss_of(y, X):
    """Small local helper (rank-safe pinv projection)."""
    pinv = np.linalg.pinv(X.T @ X)
    b = pinv @ X.T @ y
    r = y - X @ b
    return float(r @ r)
