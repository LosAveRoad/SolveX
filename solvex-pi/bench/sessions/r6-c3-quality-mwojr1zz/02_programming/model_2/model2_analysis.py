"""model2_analysis.py -- Model 2 driver: surfaces, decomposition, LOSO, pro rankings."""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from scipy import stats as sps

from m2_data import load_all, rcs_design, RCS_KNOTS_AGE, RCS_KNOTS_WEEK
import m2_fanshare as MF

SEED = 2026
N_PERM = 1000         # permutation draws per block (deterministic stream)
N_BOOT = 2000         # cluster bootstrap draws for pro-effect CIs
OUT = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
       "r6-c3-quality-mwojr1zz/02_programming/model_2")


def build_blocks(pan):
    season_d = pd.get_dummies(pan["season"].astype(int), prefix="S", drop_first=True)
    pro_d = pd.get_dummies(pan["pro"].astype(str), prefix="P", drop_first=True)
    ind_d = pd.get_dummies(pan["celebrity_industry"].astype(str), prefix="I",
                           drop_first=True)
    age_b = rcs_design(pan["celebrity_age_during_season"].to_numpy(float), RCS_KNOTS_AGE)
    wk_b = rcs_design(pan["week"].to_numpy(float), RCS_KNOTS_WEEK)
    multi = pan["multi_dance_week"].to_numpy(float)[:, None]
    blocks = {"season": season_d.to_numpy(float), "pro": pro_d.to_numpy(float),
              "industry": ind_d.to_numpy(float), "age": age_b, "week": wk_b,
              "multi": multi}
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


def block_cols(names, tag):
    pref = {"season": "season_", "pro": "pro_", "industry": "ind_",
            "age": "age_", "week": "wk_", "multi": "multi"}[tag]
    return [i for i, nm in enumerate(names) if nm.startswith(pref)]


def rss_of(y, X):
    pinv = np.linalg.pinv(X.T @ X)
    b = pinv @ X.T @ y
    r = y - X @ b
    return float(r @ r)


def ols_fit(y, X, groups):
    n, p = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    resid = y - X @ b
    rss = float(resid @ resid)
    uniq, inv = np.unique(groups, return_inverse=True)
    G = len(uniq)
    Xr = X * resid[:, None]
    sum_Xr = np.zeros((G, p))
    np.add.at(sum_Xr, inv, Xr)
    meat = sum_Xr.T @ sum_Xr
    corr = (G / (G - 1.0)) * ((n - 1.0) / max(n - p, 1))
    V = corr * (XtX_inv @ meat @ XtX_inv)
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    tv = np.where(se > 0, b / np.where(se > 0, se, 1.0), 0.0)
    pvals = 2 * sps.t.sf(np.abs(tv), max(n - p, 1))
    return dict(b=b, se=se, t=tv, p=pvals, fitted=X @ b, rss=rss, n=n)


def _center_contrast(b, cols, names, pan, kind):
    """Centered level effects: level coef minus the row-weighted mean level effect.

    Design level names carry the dummy prefix ("P_"/"I_": the dummies were built with
    pd.get_dummies(prefix="P"/"I")), so strip it before the row-share weight lookup.
    The reference level (dropped by drop_first=True coding) has coefficient 0 and row
    weight 1 - sum(weights of the estimated levels), making `center` a true row-weighted
    contrast over ALL levels including the reference."""
    prefix = "pro_" if kind == "pro" else "ind_"
    raw_levels = [nm[len(prefix):] for nm in names if nm.startswith(prefix)]
    level_names = [l[2:] if l.startswith(("P_", "I_")) else l for l in raw_levels]
    beta_aug = np.concatenate([[0.0], b[cols]])     # reference level -> coefficient 0
    lab = pan["pro"].to_numpy() if kind == "pro" else pan["celebrity_industry"].to_numpy()
    lv, cnt = np.unique(lab, return_counts=True)
    w = dict(zip(lv, cnt / cnt.sum()))
    wv = np.array([w.get(l, 0.0) for l in level_names])
    wv = np.concatenate([[1.0 - wv.sum()], wv])     # reference level's row share
    center = float(wv @ beta_aug)
    return {l: float(beta_aug[i + 1] - center) for i, l in enumerate(level_names)}


def contrast_center(b, cols, names, pan, kind):
    """The row-weighted center used by _center_contrast: the mean level effect over
    ALL levels (reference included with coefficient 0 and its true row share
    1 - sum(other weights)).  A centered contrast therefore has weighted mean 0, and
    the reference level's centered effect is exactly -contrast_center(...)."""
    prefix = "pro_" if kind == "pro" else "ind_"
    raw = [nm[len(prefix):] for nm in names if nm.startswith(prefix)]
    level_names = [l[2:] if l.startswith(("P_", "I_")) else l for l in raw]
    beta_aug = np.concatenate([[0.0], b[cols]])
    lab = pan["pro"].to_numpy() if kind == "pro" else pan["celebrity_industry"].to_numpy()
    lv, cnt = np.unique(lab, return_counts=True)
    w = dict(zip(lv, cnt / cnt.sum()))
    wv = np.array([w.get(l, 0.0) for l in level_names])
    wv = np.concatenate([[1.0 - wv.sum()], wv])
    return float(wv @ beta_aug)


def pro_effects(pan, X, names, fitJ, fitF):
    cols = np.array(block_cols(names, "pro"), int)
    effJ = _center_contrast(fitJ["b"], cols, names, pan, "pro")
    effF = _center_contrast(fitF["b"], cols, names, pan, "pro")
    pros = sorted(effJ)
    return (dict(pro=pros, effect=[effJ[p] for p in pros]),
            dict(pro=pros, effect=[effF[p] for p in pros]))


def labels_for_perm(pan, tag, first_idx, run_ids):
    """Run-level label vector for a class (length = n runs) -> row-expanded labels."""
    if tag == "pro":
        v = pan["pro"].to_numpy()[first_idx]
    elif tag == "industry":
        v = pan["celebrity_industry"].to_numpy()[first_idx]
    elif tag == "age":
        v = pan["celebrity_age_during_season"].to_numpy(float)[first_idx]
    elif tag == "week":
        v = pan["week"].to_numpy(float)
        return v, "row"
    elif tag == "multi":
        v = pan["multi_dance_week"].to_numpy(float)
        return v, "row"
    run_of_first = run_ids[first_idx]
    # return RUN-LEVEL labels (length n_runs); permutation_decomp permutes and expands
    return v, "run"


def permutation_decomp(pan, yJ, yF, X, names, n_perm=N_PERM, seed=SEED):
    """Partial R^2 of each design block + within-season permutation nulls.

    run-level attributes (pro/industry/age): permuted across runs within a season;
    row-level covariates (week: within run; multi: within season).  Splines rebuilt
    for age/week; dummy blocks re-aligned to the same column count as the original.
    Returns tidy DataFrame(surface, block, R, p_perm, null_q95, null_mean, z_perm).
    """
    run_ids = pan["run_id"].to_numpy(int)
    season_arr = pan["season"].to_numpy(int)
    first_idx = pd.Series(np.arange(len(pan))).groupby(run_ids).first().to_numpy()
    run_of_first = run_ids[first_idx]
    sea_of_first = season_arr[first_idx]
    rng = np.random.default_rng(seed)
    out = []
    for tag in ("pro", "industry", "age", "week", "multi"):
        cols = np.array(block_cols(names, tag), int)
        keep = np.setdiff1d(np.arange(X.shape[1]), cols)
        r_red_J = rss_of(yJ, X[:, keep])
        r_red_F = rss_of(yF, X[:, keep])
        R_J = 1.0 - rss_of(yJ, X) / r_red_J
        R_F = 1.0 - rss_of(yF, X) / r_red_F
        null_J, null_F = np.empty(n_perm), np.empty(n_perm)
        lab0, mode = labels_for_perm(pan, tag, first_idx, run_ids)
        # permutation scheme per block (documented):
        #   pro/industry/age: run-level attributes, shuffled across runs WITHIN season
        #   week: row-level, shuffled WITHIN each run (destroys learning alignment)
        #   multi: row-level, shuffled WITHIN season
        # permuted pro/industry dummy blocks use the SAME drop_first=True coding and
        # identical column set/order as the observed design; run-level labels that
        # permute to the reference level produce an all-zero row (drop_first coding).
        if tag in ("pro", "industry"):
            dprep = "P" if tag == "pro" else "I"
            obs_levels = [nm[len("pro_") if tag == "pro" else len("ind_"):]
                          for nm in names if nm.startswith("pro_" if tag == "pro"
                                                           else "ind_")]
        for i in range(n_perm):
            if mode == "run":
                lab = lab0.copy()
                for s in np.unique(sea_of_first):
                    m = sea_of_first == s
                    lab[m] = rng.permutation(lab0[m])
                expand = pd.Series(lab, index=run_of_first).reindex(run_ids).to_numpy()
                if tag in ("pro", "industry"):
                    d = pd.get_dummies(pd.Series(expand).astype(str), prefix=dprep,
                                       drop_first=True)
                    d = d.reindex(columns=obs_levels, fill_value=0)
                    Bp = d.to_numpy(float)
                else:
                    Bp = rcs_design(expand.astype(float), RCS_KNOTS_AGE)
            elif tag == "week":
                dfw = pd.DataFrame({"r": run_ids, "w": lab0})
                perm = lab0.copy()
                for _, g in dfw.groupby("r"):
                    perm[g.index.to_numpy()] = rng.permutation(g["w"].to_numpy())
                Bp = rcs_design(perm, RCS_KNOTS_WEEK)
            else:
                dfs = pd.DataFrame({"s": season_arr, "v": lab0})
                perm = lab0.copy()
                for _, g in dfs.groupby("s"):
                    perm[g.index.to_numpy()] = rng.permutation(g["v"].to_numpy())
                Bp = perm[:, None]
            Xp = X.copy()
            Xp[:, cols] = Bp
            null_J[i] = 1.0 - rss_of(yJ, Xp) / r_red_J
            null_F[i] = 1.0 - rss_of(yF, Xp) / r_red_F
        for surf, R, null in (("judge", R_J, null_J), ("fan", R_F, null_F)):
            mu, sd = float(null.mean()), float(null.std(ddof=1))
            out.append(dict(surface=surf, block=tag, R=R,
                            p_perm=(float(np.sum(null >= R)) + 1.0) / (n_perm + 1.0),
                            null_q95=float(np.quantile(null, 0.95)), null_mean=mu,
                            z_perm=float((R - mu) / sd) if sd > 0 else np.nan))
    for surf, y in (("judge", yJ), ("fan", yF)):
        cols = np.array(block_cols(names, "season"), int)
        keep = np.setdiff1d(np.arange(X.shape[1]), cols)
        out.append(dict(surface=surf, block="season",
                        R=1.0 - rss_of(y, X) / rss_of(y, X[:, keep]),
                        p_perm=np.nan, null_q95=np.nan, null_mean=np.nan,
                        z_perm=np.nan))
    return pd.DataFrame(out)


def residual_icc(pan, y, fitted):
    resid = y - fitted
    g = pd.Series(resid).groupby(pan["run_id"].to_numpy(int))
    m = g.mean().to_numpy(float)
    n = g.size().to_numpy(float)
    mu = np.average(m, weights=n)
    between = float(np.average((m - mu) ** 2, weights=n))
    return between / max(float(np.var(resid, ddof=1)), 1e-12)


def loso_r2_nofe(pan, yJ, yF, X, names=None):
    """LOSO variant WITHOUT the season block (dropped from train and test):
    measures pure covariate transfer across seasons (season levels are structurally
    untransferable; this isolates what the model CAN carry to a new season)."""
    seasons = pan["season"].to_numpy(int)
    keep = ([0] + [i for i, nm in enumerate(names)
                   if not nm.startswith("season_")]) if names is not None else \
        list(range(X.shape[1]))
    Xr = X[:, keep]
    res = {}
    for tag, y in (("judge", yJ), ("fan", yF)):
        yhat = np.full(len(y), np.nan)
        for s in np.unique(seasons):
            tr, te = seasons != s, seasons == s
            b = np.linalg.pinv(Xr[tr].T @ Xr[tr]) @ Xr[tr].T @ y[tr]
            yhat[te] = Xr[te] @ b
        res[tag] = float(1.0 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    return res


def paired_week_slopes(pan):
    """Within-run improvement drift (runs with >=4 weeks): mean(last3 - first2) for
    judge z (relative), judge per-judge level (absolute), and logit fan share."""
    tmp = pan[["run_id", "week", "judge_z", "weekly_total", "n_judges_judged",
               "fanshare"]].copy()
    tmp["per_judge"] = tmp["weekly_total"] / tmp["n_judges_judged"].clip(lower=1)
    tmp["lf"] = np.log((tmp.fanshare.clip(1e-6, 1 - 1e-6) + 8e-5) /
                       (1 - tmp.fanshare.clip(1e-6, 1 - 1e-6) + 8e-5))
    out = {"n_runs": 0}
    import scipy.stats as sps
    for col, key in (("judge_z", "djudge_z"), ("per_judge", "dper_judge"),
                     ("lf", "dlogitfan")):
        vals = []
        for _, g in tmp.groupby("run_id"):
            if len(g) >= 4:
                g = g.sort_values("week")
                vals.append(float(g.tail(3)[col].mean() - g.head(2)[col].mean()))
        tt = sps.ttest_1samp(vals, 0.0)
        out[key] = round(float(np.mean(vals)), 4)
        out[key + "_p"] = round(float(tt.pvalue), 6)
        if key == "djudge_z":
            out["n_runs"] = len(vals)
    return out


def loso_r2(pan, yJ, yF, X, names=None):
    """Leave-one-season-out honest R2, two variants:

    raw: test season's dummy columns zeroed (level unseen in training).
    recal: same, but the intercept is recalibrated on the test season's mean residual
        (the honest "new-season drift absorbed" variant; isolates covariate transfer).
    """
    seasons = pan["season"].to_numpy(int)
    res = {}
    season_cols = ([i for i, nm in enumerate(names) if nm.startswith("season_")]
                   if names is not None else [])
    for tag, y in (("judge", yJ), ("fan", yF)):
        yhat = np.full(len(y), np.nan)
        yhat_rec = np.full(len(y), np.nan)
        for s in np.unique(seasons):
            tr, te = seasons != s, seasons == s
            Xte = X[te].copy()
            if season_cols:
                Xte[:, season_cols] = 0.0
            b = np.linalg.pinv(X[tr].T @ X[tr]) @ X[tr].T @ y[tr]
            yhat[te] = Xte @ b
            # intercept-recalibrated variant: shift predictions by the training-model
            # in-sample mean residual; equivalently, add the test-season mean of
            # (training-model-implied HELD-OUT residual): use the affine calibration
            # that would have been available: alpha_s = mean(y[te]) - mean(yhat[te])
            # is NOT honest (uses test labels); use instead the CALIBRATION from the
            # run-level residual of the immediately PREVIOUS season (drift model):
            prev_s = s - 1
            if prev_s in np.unique(seasons):
                m_prev = seasons == prev_s
                Xte_prev = X[m_prev].copy()
                if season_cols:
                    Xte_prev[:, season_cols] = 0.0
                cal = float(np.mean(y[m_prev] - Xte_prev @ b))
            else:
                cal = 0.0
            yhat_rec[te] = Xte @ b + cal
        res[tag] = float(1.0 - ((y - yhat) ** 2).sum() / ((y - y.mean()) ** 2).sum())
        res[tag + "_recal"] = float(1.0 - ((y - yhat_rec) ** 2).sum()
                                     / ((y - y.mean()) ** 2).sum())
    return res


def platform_drift(pan, yF):
    """Fan-surface levels + judge-fan divergence by era (single pass; the divergence
    metrics are the platform-shift evidence: |fan-judge| mean gap and the within-week
    fan-judge rank correlation (Spearman, robust to within-week scale differences)."""
    eras = pd.cut(pan["season"], bins=[0, 17, 27, 34],
                  labels=["2005-2012 (S1-17)", "2013-2020 (S18-27)",
                          "2021-2025 (S28-34)"])
    out = []
    fanshare = pan["fanshare"].to_numpy()
    jshare = pan["judge_share"].to_numpy()
    for e, g in pan.groupby(eras, observed=True):
        idx = g.index.to_numpy()
        cors = []
        for _, gg in g.groupby(["season", "week"]):
            if len(gg) > 2:
                c = gg["fanshare"].corr(gg["judge_share"], method="spearman")
                if np.isfinite(c):
                    cors.append(c)
        rats = []
        for _, gg in g.groupby(["season", "week"]):
            sh = np.sort(gg["fanshare"].to_numpy())
            if sh[0] > 1e-6:
                rats.append(sh[-1] / sh[0])
        out.append(dict(era=str(e), n_rows=len(g),
                        mean_logit_fanshare=round(float(yF[idx].mean()), 4),
                        mean_fanshare=round(float(fanshare[idx].mean()), 4),
                        mean_abs_gap_fan_judge=round(
                            float(np.abs(fanshare[idx] - jshare[idx]).mean()), 4),
                        mean_withinweek_fanjudge_spearman=round(float(np.mean(cors)), 3),
                        median_topbottom_share_ratio=round(float(np.median(rats)), 2)))
    return pd.DataFrame(out)
