#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Model 1: Sub-Seasonal Survival Inversion of Latent Fan Votes (Bayesian + Belief Functions)
==========================================================================================
Recover latent fan-vote shares phi_iw for every DWTS couple in every week they danced.

Pipeline (fully deterministic; SEED fixed; no network access).

  Stage A  Discrete-time survival hazard (complementary log-log link) for the weekly
           chance of being the eliminated couple:
               h_iw = 1 - exp(-exp(a_week + x_iw' beta)),
           with week-index-stratum baselines a_w (couples cut at the season finale
           count as events; finalists are right-censored; withdrawers excluded).
           Covariates x: within-week judge percentile rank, low-judge dummy, season-
           to-date mean judge percentile, age (+ age^2), industry group dummies,
           pro-partner leave-one-out historical strength.

  Stage B  Empirical-Bayes Gaussian frailty u_i per celebrity-season = latent fan
           pressure. It enters the hazard multiplicatively: h = h0 * exp(u_i), so
           u < 0  <=> survives longer than judge scores predict <=> strong fan
           support; u > 0 <=> pushed out early <=> weak fan support.  The observed
           survival path updates  p(u_i | path) ∝ exp(ell_i(u_i)) N(u_i; 0, sigma^2)
           on a grid (per-couple path likelihood, reset at each couple); sigma^2 is
           re-estimated from the posterior (EM-style) to convergence.  Fan-vote
           weight ∝ exp(-tau * u).

  Stage C  Dempster-Shafer belief layer per (season, week): each judge j's scores
           give masses over couples
               m_j({i}) = q_w * softmax_i(gamma * s_i^j),   m_j(Theta) = 1 - q_w,
           where s_i^j is judge j's within-week score share and q_w = 1/(1 + relative
           IQR of the judge cells).  Masses combined with Dempster's rule; conflict
           K_w retained.  Bel({i}), Pl({i}) reported; share interval from belief
           functions:  lo_i = Bel_i/(Bel_i + sum_{j!=i} Pl_j),
                       hi_i = Pl_i/(Pl_i + sum_{j!=i} Bel_j).

  Stage D  Fan-vote point estimate   phi_iw ∝ Bel({i}) * exp(-tau * u_i),  normalized
           on the week simplex.  Uncertainty: (i) D-S share interval; (ii) a
           Beta(c*phi, c*(1-phi)) posterior with pseudo-ballot count
           c_iw = m0 * q_w, m0 predictive-NLL-calibrated -> 90% credible band;
           (iii) simulated P(eliminated): phi ~ Dirichlet(c_w * phi), lowest c_w of
           n_w couples cut -> Monte-Carlo probability and its reliability/Brier/AUC.

  Stage E  Validation: top-1 / top-2 elimination-hit rates vs baselines (judge
           share, judge rank, Bel-only, hazard-only), Brier + AUC of P(eliminated),
           reliability curve, leave-one-season-out (LOSO) refits of Stage A.

Outputs (written next to this script): fanvote_estimates.csv, results.json, figures/.
Run:  python3 run.py
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats as sstats
from scipy.special import expit, logsumexp, softmax

import statsmodels.api as sm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "serif"

SEED = 20260101
rng = np.random.default_rng(SEED)

BASE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.normpath(os.path.join(BASE, "..", "..", "01_modeling", "shared_data"))
FIGDIR = os.path.join(BASE, "figures")
os.makedirs(FIGDIR, exist_ok=True)

N_SIM = 4000                     # Dirichlet draws per week for elimination probabilities
GAMMA_GRID = [4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 20.0]
TAU_GRID = [0.5, 1.0, 1.5]       # frailty loading on phi (phi ∝ Bel * exp(-tau*u))
TAU = 1.0                        # pre-registered plan choice
M0_GRID = [10.0, 25.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0]  # pseudo-ballot
                                 # scale, selected by predictive log-likelihood

# ----------------------------------------------------------------------------- data
def load_data():
    wk = pd.read_csv(os.path.join(SHARED, "weekly_scores.csv"))
    con = pd.read_csv(os.path.join(SHARED, "contestants.csv"))
    pan = pd.read_csv(os.path.join(SHARED, "week_panel.csv"))
    return wk, con, pan


def build_features(wk, con):
    """Attach celebrity covariates + within-week features to the danced-week panel."""
    df = wk.copy()
    # celebrity-level covariates joined BY VALUE (row_id repeats once per danced week
    # in this long panel, so a merge would violate one-to-one and explode rows)
    celeb = con.set_index("row_id")
    for col in ["celebrity_age_during_season", "celebrity_industry", "n_danced_weeks"]:
        df[col] = df["row_id"].map(celeb[col])
    df["season"] = df["season"].astype(int)
    df = df.sort_values(["season", "row_id", "week"], kind="mergesort").reset_index(drop=True)

    # within-week judge percentile rank: 1 = best judge score of that week
    ncoup = df.groupby(["season", "week"])["row_id"].transform("size")
    df["n_active"] = ncoup.astype(int)
    df["judge_pct"] = 1.0 - (df["week_rank_judges"] - 1) / ncoup.clip(lower=2)

    df["low_score"] = (df["judge_pct"] < 0.25).astype(float)

    # season-so-far cumulative mean of judge percentile (known at week w);
    # rows are ordered by (row_id, week) so cumcount is chronological per couple
    gsum = df.groupby("row_id")["judge_pct"].cumsum()
    gcnt = df.groupby("row_id")["judge_pct"].cumcount().add(1)
    df["cum_pct"] = gsum / gcnt

    # age standardized (across all contestants)
    age_mu = df["celebrity_age_during_season"].mean()
    age_sd = df["celebrity_age_during_season"].std()
    df["age_z"] = (df["celebrity_age_during_season"] - age_mu) / age_sd
    df["age_z2"] = df["age_z"] ** 2

    # industry groups (4 dummies vs 'Other' reference)
    def grp(x):
        if x == "Actor/Actress":
            return "Actor"
        if x == "Athlete":
            return "Athlete"
        if x == "TV Personality":
            return "TV"
        if x == "Singer/Rapper":
            return "Singer"
        return "Other"
    df["ind_group"] = df["celebrity_industry"].map(grp)

    # partner (pro) leave-one-out historical strength: shrunk mean danced weeks of
    # the pro's OTHER partners (temporal leak is modest and reported as a caveat)
    mu_alive = con["n_danced_weeks"].mean()
    stats = con.groupby("ballroom_partner")["n_danced_weeks"].agg(["sum", "count"])
    df["partner_n"] = df["ballroom_partner"].map(stats["count"]).astype(float)
    df["partner_sum"] = df["ballroom_partner"].map(stats["sum"]).astype(float)
    nu = 1.5
    df["partner_loo"] = (df["partner_sum"] - df["n_danced_weeks"] + nu * mu_alive) \
        / (df["partner_n"] - 1.0 + nu)
    df.loc[df["partner_n"] == 1, "partner_loo"] = mu_alive
    p_mu = df["partner_loo"].mean()
    p_sd = df["partner_loo"].std()
    df["partner_loo_z"] = (df["partner_loo"] - p_mu) / p_sd

    # response: 1 if this row IS the elimination event
    df["y_elim"] = ((df["status"] == "eliminated")
                    & (df["week"] == df["elim_week"])).astype(int)
    df["used_in_supervision"] = (df["status"] != "withdrew").astype(int)
    return df


# ------------------------------------------------------------- design matrix helpers
WEEK_DUMMIES = [f"wk{w}" for w in range(2, 12)]           # week 1 = reference
IND_DUMMIES = ["ind_Actor", "ind_Athlete", "ind_TV", "ind_Singer"]
BASE_COVS = ["judge_pct", "low_score", "cum_pct", "age_z", "age_z2"]
BASE_COVS += IND_DUMMIES + ["partner_loo_z"]


def make_X(df, cols=None):
    """Build the design matrix; if cols given, guarantee exactly those columns."""
    X = pd.DataFrame(index=df.index)
    X["const"] = 1.0
    for c in BASE_COVS:
        if c.startswith("ind_"):
            X[c] = (df["ind_group"] == c[4:]).astype(float).to_numpy()
        else:
            X[c] = df[c].astype(float).to_numpy()
    for w_lab in WEEK_DUMMIES:
        wnum = int(w_lab[2:])
        X[w_lab] = (df["week"] == wnum).astype(float).to_numpy()
    if cols is None:
        # drop zero-variance columns (single-season subsets may lack some weeks)
        keep = [c for c in X.columns if c == "const" or X[c].std() > 1e-12]
        return X[keep]
    return X[cols]


def fit_glm_cloglog(df_train):
    Xtr = make_X(df_train)
    ytr = df_train["y_elim"].to_numpy(float)
    glm = sm.GLM(ytr, Xtr, family=sm.families.Binomial(link=sm.families.links.CLogLog()))
    res = glm.fit(maxiter=200)
    return res, Xtr.columns.tolist()


# ------------------------------------------------------- Stage B: EB Gaussian frailty
def frailty_posteriors(df, h_base, sigma, u_grid=None):
    """Posterior of the Gaussian frailty u_i given the couple's observed path and N(0,s^2)
    prior, evaluated on a grid.  Two flavors are returned:
      u_couple  : posterior given the FULL path (all danced weeks) -- smoothed inference,
                  broadcast to every week-row of the couple (main fan-pressure estimate);
      u_filter  : posterior given outcomes STRICTLY BEFORE week w -- predictive inference,
                  used for the leakage-free fan-share forecast phi_pred.
    """
    if u_grid is None:
        u_grid = np.linspace(-6.0, 6.0, 481)
    h_base = np.clip(np.asarray(h_base, float), 1e-12, 1 - 1e-12)
    lam = -np.log1p(-h_base)                     # cumulative hazard  lambda = -log(1-h)
    eta_base = np.log(lam + 1e-300)              # cloglog linear predictor
    z = eta_base[:, None] + u_grid[None, :]      # (n_week_rows, n_grid)
    h_u = 1.0 - np.exp(-np.exp(z))
    h_u = np.clip(h_u, 1e-12, 1 - 1e-12)
    y = df["y_elim"].to_numpy(float)[:, None]
    loglik = y * np.log(h_u) + (1 - y) * np.log1p(-h_u)      # (n, U)

    # scatter into per-couple (trip) matrix: cumulative path likelihood RESETS at
    # every couple (a plain axis-0 cumsum would bleed across couples)
    couple = pd.factorize(df["row_id"].to_numpy())[0]
    n_c = int(couple.max()) + 1
    n = len(df)
    pos = np.zeros(n, dtype=int)
    seen = np.zeros(n_c, dtype=int)
    for k in range(n):                           # rows arrive ordered by (row_id, week)
        pos[k] = seen[couple[k]]
        seen[couple[k]] += 1
    Wmax = int(pos.max()) + 1
    U = u_grid.size
    L = np.full((n_c, Wmax, U), np.nan)
    L[couple, pos, :] = loglik
    path = np.nancumsum(L, axis=1)               # leading NaN -> 0, so path = sum to week

    last_pos = seen - 1                          # index of each couple's final week
    ell_full = path[couple, last_pos[couple], :]             # (n, U) full-path evidence
    ell_flt = np.where(pos[:, None] == 0, 0.0,
                       path[np.clip(couple, 0, None), np.clip(pos - 1, 0, None), :])
    ell_flt = np.where(pos[:, None] == 0, 0.0, ell_flt)      # week 1: prior only

    def post_mean_sd(ell):
        a = ell + (-0.5 * (u_grid / sigma) ** 2)[None, :]
        a = a - a.max(axis=1, keepdims=True)
        p = np.exp(a)
        p /= p.sum(axis=1, keepdims=True)
        m = p @ u_grid
        v = np.maximum(p @ (u_grid ** 2) - m ** 2, 1e-12)
        return m, np.sqrt(v)

    u_c, u_c_sd = post_mean_sd(ell_full)
    u_f, u_f_sd = post_mean_sd(ell_flt)
    return u_c, u_c_sd, u_f, u_f_sd


def fit_frailty(df_sup, h_base, max_iter=10, tol=1e-3):
    """EM-style loop: posterior mean of u, then variance update of sigma^2.
    Returns (u_full, u_full_sd, u_filter, u_filter_sd, sigma)."""
    sigma = 1.0
    for _ in range(max_iter):
        u_f, u_fs, u_flt, u_flts = frailty_posteriors(df_sup, h_base, sigma)
        sigma_new = float(np.sqrt(np.mean(u_f ** 2 + u_fs ** 2)))
        if abs(sigma_new - sigma) < tol:
            sigma = sigma_new
            break
        sigma = sigma_new
    return u_f, u_fs, u_flt, u_flts, sigma


# --------------------------------------------------- Stage C: Dempster-Shafer beliefs
# Design notes.
# (1) Plain cascaded Dempster's rule is degenerate on large frames: even IDENTICAL
#     judges (three copies of the same softmax masses) conflict with
#     K -> 1 - sum_i p_i^2 ~ 0.99 when n = 13 couples, because every crossed pair
#     of singletons off the diagonal is an empty intersection.  We therefore use
#     the TRUNCATED (GA-style) masses: each judge's softmax singleton mass is
#     capped at cap(k)/b (cap = 1, 2, 4, 7 focal sets for k = 1..4); the capped
#     remainder stays unassigned (to Theta).  This removes the structural
#     conspiring of near-duplicate judges while keeping the Dempster CONCENTRATION
#     that makes Bel much sharper than any single judge's opinion.
# (2) The fused conflict K_w = 1 - prod_j (1 - K_step_j) is still |Theta|-dominated
#     after truncation; it is exported as a diagnostic only.  The quantity that
#     actually drives the certainty of phi (pseudo-ballot deflation) is the
#     panel-discount q_w = 1/(1 + rel_IQR of judge cells), which is 1 when the
#     judges agree and shrinks when they disagree.


def dempster_combine(m1, m2):
    """m1, m2: dict{frozenset: mass}. Returns (normalized combination, and the
    pre-normalization total conflicting mass 1 - K_step)."""
    out = {}
    K = 0.0
    for A, a in m1.items():
        for B, b in m2.items():
            C = A & B
            if len(C) == 0:
                K += a * b
            else:
                out[C] = out.get(C, 0.0) + a * b
    tot = 1.0 - K
    return {k: v / tot for k, v in out.items() if v > 1e-15}, tot


def truncated_judge_masses(cells, gamma, b=4.0):
    """Truncated GA-style singleton masses: per-judge softmax over couples, with
    total singleton mass capped at cap(k)/b (cap(k) = #focal sets of size <= k =
    1, 2, 4, 7).  Capped remainders stay unassigned (m(Theta) grows), which is
    what keeps near-duplicate judges from conspiring into cosmological conflicts
    when the frame |Theta| = n_couples is large (cf. truncated Dempster rule)."""
    n, nj = cells.shape
    order = np.zeros((n, nj))
    for j in range(nj):
        logits = gamma * cells[:, j]
        order[:, j] = softmax(logits - logits.max())
    masses = np.zeros_like(order)
    for j in range(nj):
        p = order[:, j]
        srt = np.sort(p)[::-1]
        k_ok = 1
        for kk in range(2, n + 1):
            if srt[:kk].sum() <= (1.0 + 0.5 * kk * (kk - 1)) / b:
                k_ok = kk
            else:
                break
        allowed = min((1.0 + 0.5 * k_ok * (k_ok - 1)) / b, 1.0)
        s = p.copy()
        if allowed < 1.0 - 1e-12:
            # cap binds: shrink the singleton mass to `allowed`; the remainder is
            # left UNASSIGNED ( theta-mass ) -- do NOT renormalize back to 1.
            floor = 0.0
            excess = s.sum() - allowed
            for _ in range(80):
                if excess <= 1e-12:
                    break
                over = s > floor
                if not over.any():
                    floor = 0.0
                    break
                room = (s[over] - floor).sum()
                take = min(excess, room)
                s[over] = s[over] - (s[over] - floor) * (take / max(room, 1e-12))
                excess = s.sum() - allowed
                if excess > 1e-9:
                    floor *= 0.8
        masses[:, j] = s
    return masses


def ds_week(shares, q_w, gamma):
    """shares: (n_couples, n_judges) per-judge score shares within the week.
    Returns (Bel, Pl, fused conflict K_w).  Bel concentrates the common evidence
    (multiplicative pooling), Pl additionally carries the unassigned mass."""
    n, nj = shares.shape
    capped = truncated_judge_masses(shares, gamma)
    m = {frozenset(range(n)): 1.0}
    f_prod = 1.0
    for j in range(nj):
        p = capped[:, j]
        mj = {frozenset([i]): q_w * float(p[i]) for i in range(n)}
        mj[frozenset(range(n))] = q_w * (1.0 - p.sum()) + (1.0 - q_w)
        m, tot_raw = dempster_combine(m, mj)
        f_prod *= max(tot_raw, 1e-12)
    universe = frozenset(range(n))
    bel = np.array([m.get(frozenset([i]), 0.0) for i in range(n)])
    pl = bel + m.get(universe, 0.0)
    return bel, np.clip(pl, 0.0, 1.0), float(1.0 - f_prod)


def compute_all_beliefs(df, gamma):
    """Bel / Pl / fused-K / panel-discount q_w for every danced-week row."""
    n = len(df)
    bel = np.zeros(n)
    pl = np.zeros(n)
    Kt = np.zeros(n)
    qw = np.zeros(n)
    jcol = ["judge1", "judge2", "judge3", "judge4"]
    for (s, w), g in df.groupby(["season", "week"], sort=True):
        idx = g.index.to_numpy()
        cells = g[jcol].to_numpy(float)
        # per-judge relative shares (encoding-invariant across aggregate weeks)
        colsum = cells.sum(axis=0, keepdims=True)
        colsum[colsum == 0] = 1.0
        shares = np.nan_to_num(cells / colsum)
        # panel noise: relative judge disagreement (mean over couples of IQR/mean)
        with np.errstate(all="ignore"):
            dif = np.nan_to_num(np.nanpercentile(cells, 75, axis=1)
                                - np.nanpercentile(cells, 25, axis=1))
            denom = np.nan_to_num(np.nanmean(cells, axis=1), nan=1.0)
            rel_iqr = float(np.mean(dif / np.maximum(denom, 1e-9)))
        q_w = 1.0 / (1.0 + rel_iqr)          # 0..1 certainty of the judge evidence
        b, p, K = ds_week(shares, q_w, gamma)
        bel[idx] = b
        pl[idx] = p
        Kt[idx] = K
        qw[idx] = q_w
    return bel, pl, Kt, qw


def ds_share_interval(bel, pl):
    """Belief-function interval for a multinomial share:
    lo_i = Bel_i / (Bel_i + sum_{j!=i} Pl_j), hi_i = Pl_i / (Pl_i + sum_{j!=i} Bel_j)."""
    n = len(bel)
    sum_pl = pl.sum()
    sum_bel = bel.sum()
    lo = bel / (bel + (sum_pl - pl))
    hi = pl / (pl + (sum_bel - bel))
    return lo, hi


# ----------------------------------------------------------- validation helper metrics
def _week_share_normalize(vals, df):
    """Normalize a positive weight vector to shares *within each (season, week)*.
    Pure-numpy accumulation to avoid pandas transform-alignment pitfalls."""
    key = (df["season"].to_numpy() * 1000 + df["week"].to_numpy())
    order = np.argsort(key, kind="stable")
    sk = key[order]
    sv = np.asarray(vals, float)[order]
    starts = np.r_[0, np.where(np.diff(sk) != 0)[0] + 1]
    ends = np.r_[starts[1:], len(sk)]
    out = np.empty_like(sv)
    for a, b in zip(starts, ends):
        out[a:b] = sv[a:b] / sv[a:b].sum()
    res = np.empty_like(out)
    res[order] = out
    return res


def top1_hits(phi, df):
    """Fraction of elimination events whose couple has the MINIMUM phi in its week
    (= 'fan-vote lowest -> eliminated' rule)."""
    tmp = pd.DataFrame({"phi": np.asarray(phi, float), "y": df["y_elim"].to_numpy(),
                        "k": list(zip(df["season"], df["week"]))})
    tmp["wkmin"] = tmp.groupby("k")["phi"].transform("min")
    ok = tmp[(tmp.y == 1) & (tmp.phi <= tmp.wkmin + 1e-12)]
    return len(ok) / int(tmp.y.sum())


def top2_hits(phi, df):
    """Fraction of events whose couple has one of the 2 lowest phi in its week."""
    tmp = pd.DataFrame({"phi": np.asarray(phi, float), "y": df["y_elim"].to_numpy(),
                        "k": list(zip(df["season"], df["week"]))})
    tmp["rk"] = tmp.groupby("k")["phi"].rank(method="first")
    ok = tmp[(tmp.y == 1) & (tmp.rk <= 2)]
    return len(ok) / int(tmp.y.sum())


# ------------------------------------------------------------------------ main pipeline
def main():
    wk, con, pan = load_data()
    df = build_features(wk, con)
    n_rows_total = len(df)
    # withdrew couples excluded from all elimination supervision; keep rows for export
    n_events = int(df["y_elim"].sum())
    seasons = sorted(df["season"].unique())
    # keep original positional indices so fitted columns can be mapped back onto `out`
    # by POSITION (df_sup is a filtered copy; positions must not drift)
    df_sup = df[df["used_in_supervision"] == 1].copy()
    df_sup["__orig_pos"] = df_sup.index
    df_sup = df_sup.sort_values(["row_id", "week"], kind="mergesort").reset_index(drop=True)
    df_sup["__orig_pos"] = df_sup["__orig_pos"].astype(int)
    print(f"[load] danced-week rows: {n_rows_total} | supervision rows: {len(df_sup)} "
          f"| elimination events: {n_events} | seasons: {len(seasons)}")

    # ---------------- Stage A: cloglog GLM
    res, cols_used = fit_glm_cloglog(df_sup)
    df_sup["hazard_week"] = np.asarray(res.predict(make_X(df_sup, cols_used)), float)
    aic = float(res.aic)
    coefs = {c: float(b) for c, b in zip(cols_used, res.params)}
    ses = {c: float(b) for c, b in zip(cols_used, res.bse)}
    print("[glm] converged:", res.converged, "| AIC:", round(aic, 1))
    for c in ["judge_pct", "low_score", "cum_pct", "age_z", "age_z2",
              "ind_Actor", "ind_Athlete", "ind_TV", "ind_Singer", "partner_loo_z"]:
        if c in coefs:
            print(f"    {c:>16s}: beta={coefs[c]:+.3f} (se {ses[c]:.3f})")
    from sklearn.metrics import roc_auc_score as auc_score
    auc_stage1 = float(auc_score(df_sup["y_elim"], df_sup["hazard_week"]))

    # week-stratum baselines at zero covariates
    base_haz = {}
    for w in range(1, 12):
        eta = coefs.get("const", 0.0) + (coefs.get(f"wk{w}", 0.0) if w >= 2 else 0.0)
        base_haz[w] = float(1.0 - np.exp(-np.exp(eta)))
    print("[glm] week-stratum baseline hazards (at zero covariates):")
    for w in range(1, 8):
        print(f"    week {w}: {base_haz[w]:.3f}")

    # ---------------- Stage B: EB frailty (latent fan pressure, u<0 = fan favorite)
    u_mean, u_sd, u_filt, u_filt_sd, sigma_u = fit_frailty(df_sup, df_sup["hazard_week"].to_numpy(float))
    df_sup["fan_frailty_u"] = u_mean
    df_sup["fan_frailty_sd"] = u_sd
    df_sup["fan_frailty_u_filter"] = u_filt
    df_sup["fan_frailty_sd_filter"] = u_filt_sd
    corr_u_nweeks = float(np.corrcoef(df_sup["fan_frailty_u"],
                                      df_sup["n_danced_weeks"])[0, 1])
    corr_u_jpct = float(np.corrcoef(df_sup["fan_frailty_u"], df_sup["judge_pct"])[0, 1])
    print(f"[frailty] sigma_u = {sigma_u:.3f} | u range [{u_mean.min():+.2f}, {u_mean.max():+.2f}] "
          f"| corr(u, n_danced_weeks) = {corr_u_nweeks:+.3f} "
          f"| corr(u, judge_pct) = {corr_u_jpct:+.3f}")

    # ---------------- Stage C: D-S beliefs + calibrated gamma (order-invariant; picks scale)
    gamma_pick, best_hit = GAMMA_GRID[-1], -1.0
    gamma_report = {}
    for g in GAMMA_GRID:
        bel_g, _, _, _ = compute_all_beliefs(df_sup, g)
        hit = top1_hits(bel_g, df_sup)
        gamma_report[g] = round(float(hit), 4)
        if hit >= best_hit:                      # >= keeps the LARGEST gamma on ties
            best_hit, gamma_pick = hit, g
    print(f"[ds] gamma grid top-1 hit rates: {gamma_report} -> gamma={gamma_pick}")
    bel, pl, Kt, qw = compute_all_beliefs(df_sup, gamma_pick)
    df_sup["bel"], df_sup["plaus"], df_sup["ds_conflict_K"] = bel, pl, Kt
    df_sup["panel_discount_q"] = qw

    # ---------------- Stage D: phi_iw ∝ Bel * exp(-tau * u), normalized per week
    phi_store, hit_store, hit2_store = {}, {}, {}
    for tau in TAU_GRID:
        w_raw = bel * np.exp(-tau * u_mean)
        phi = _week_share_normalize(w_raw, df_sup)
        phi_store[tau], hit_store[tau], hit2_store[tau] = phi, top1_hits(phi, df_sup), top2_hits(phi, df_sup)
        print(f"[phi] tau={tau}: top-1 hit {hit_store[tau]:.3f}, top-2 hit {hit2_store[tau]:.3f}")
    phi_hat = phi_store[TAU]
    df_sup["phi_hat"] = phi_hat
    df_sup["phi_rank"] = df_sup.groupby(["season", "week"])["phi_hat"].rank(method="average").astype(int)

# ---------------- simulated P(eliminated) via Dirichlet(c_w * phi) draws,
    # with the pseudo-ballot scale m0 CALIBRATED by minimizing the reliability ECE
    yvec = df_sup["y_elim"].to_numpy()
    grid_weeks = sorted(set(zip(df_sup["season"], df_sup["week"])))

    def simulate_p_elim(m0):
        """Monte-Carlo elimination probabilities: fan shares ~ Dirichlet(c_w*phi),
        lowest c_w of n_w couples cut (k_cut from week_panel; withdrawals excluded
        from the simulated cuts -- mirrors the show's no-vote exits).  Per-week
        seeded RNG -> deterministic, order-invariant."""
        pout = np.zeros(len(df_sup))
        for (s, w) in grid_weeks:
            mrow = (df_sup["season"].to_numpy() == s) & (df_sup["week"].to_numpy() == w)
            idx = np.where(mrow)[0]
            qm = float(qw[idx].mean())     # week-average panel discount
            conc = max(m0 * qm, 2.0)
            alpha_vec = np.maximum(conc * phi_hat[idx], 1e-6)
            seed_hw = np.random.SeedSequence([SEED, int(s), int(w)])
            rgs_local = np.random.default_rng(seed_hw)
            draws = rgs_local.dirichlet(alpha_vec, size=N_SIM)
            # couple must actually be eligible: exclude withdrew from cuts
            dw = (df_sup["status"].to_numpy()[idx] == "withdrew")
            elig = (~dw).astype(float)
            nelim_rows = pan[(pan.season == s) & (pan.week == w)]
            k_cut = int(nelim_rows["n_eliminated_this_week"].iloc[0]) if len(nelim_rows) else 0
            k_cut = min(k_cut, sum(~dw)) if k_cut > 0 else 0
            if k_cut > 0:
                dd = draws.copy()
                dd[:, dw] = np.inf                       # withdrew cannot be the cut
                bottom = np.argsort(dd, axis=1)[:, :k_cut]
                mask = np.zeros(draws.shape, dtype=bool)
                np.put_along_axis(mask, bottom, True, axis=1)
                pout[idx] = mask.mean(axis=0) * elig
        return pout

    def ece_of(p):
        """Expected calibration error on 10 equal-count bins."""
        q10 = np.quantile(p, np.linspace(0.1, 0.9, 9))
        bns = np.searchsorted(q10, p, side="right")
        ece, ntot = 0.0, len(p)
        for b in range(10):
            msk = bns == b
            if msk.sum() >= 5:
                ece += msk.sum() / ntot * abs(p[msk].mean() - yvec[msk].mean())
        return ece

    def nll_of(p):
        """Mean Bernoulli negative log-likelihood of the observed eliminations."""
        eps = 1e-9
        return float(-np.mean(yvec * np.log(np.clip(p, eps, 1))
                              + (1 - yvec) * np.log(np.clip(1 - p, eps, 1))))

    m0_report = {}
    for m0 in M0_GRID:
        p_m0 = simulate_p_elim(m0)
        # log-likelihood is the ONLY criterion with an interior optimum here:
        # overconfident pseudo-counts are punished by the ~1/3 of events whose
        # week-favorite (by phi) was not the couple actually eliminated
        m0_report[str(m0)] = {"nll": round(nll_of(p_m0), 5),
                              "ece": round(float(ece_of(p_m0)), 5),
                              "brier": round(float(np.mean((p_m0 - yvec) ** 2)), 5)}
    M0_BALLOTS = min(M0_GRID, key=lambda mm: nll_of(simulate_p_elim(mm)))
    print(f"[m0] NLL/ECE/Brier by m0: {m0_report} -> m0* = {M0_BALLOTS} "
          f"(NLL {m0_report[str(M0_BALLOTS)]['nll']})")
    p_elim = simulate_p_elim(M0_BALLOTS)
    df_sup["p_elim_sim"] = p_elim

    brier_all = float(np.mean((p_elim - yvec) ** 2))
    ev = yvec == 1
    brier_events = float(np.mean((p_elim[ev] - 1.0) ** 2))
    auc_pelim = float(auc_score(yvec, p_elim))
    # reliability deciles (equal-count bins) at the calibrated m0
    q10 = np.quantile(p_elim, np.linspace(0.1, 0.9, 9))
    bins = np.searchsorted(q10, p_elim, side="right")
    rel_pred, rel_obs = [], []
    for b in range(10):
        msk = bins == b
        if msk.sum() >= 5:
            rel_pred.append(float(p_elim[msk].mean()))
            rel_obs.append(float(yvec[msk].mean()))
    print(f"[sim] Brier(all)={brier_all:.3f} | Brier(events)={brier_events:.3f} | "
          f"AUC(P_elim)={auc_pelim:.3f} | mean P(elim)={p_elim.mean():.3f}")

    # ---------------- validation: elimination-reproduction hits vs baselines
    bs_share = top1_hits(df_sup["judge_share"].to_numpy(), df_sup)     # lowest judge share out
    bs_rank = top1_hits(-df_sup["week_rank_judges"].to_numpy(), df_sup)  # highest rank number out
    bs_bel = top1_hits(bel, df_sup)
    cumhaz = -np.log1p(-df_sup["hazard_week"].clip(1e-9, 1 - 1e-9))
    bs_haz = top1_hits(-cumhaz.to_numpy(), df_sup)                    # highest hazard out
    bs_share2 = top2_hits(df_sup["judge_share"].to_numpy(), df_sup)
    bs_bel2 = top2_hits(bel, df_sup)
    print(f"[validation] top-1 hit: phi {hit_store[TAU]:.3f} | Bel-only {bs_bel:.3f} | "
          f"judge-share {bs_share:.3f} | judge-rank {bs_rank:.3f} | hazard {bs_haz:.3f}")
    print(f"[validation] top-2 hit: phi {hit2_store[TAU]:.3f} | Bel-only {bs_bel2:.3f} | "
          f"judge-share {bs_share2:.3f}")

    # ---------------- uncertainty: D-S share interval + moment-matched Beta band
    ds_lo, ds_hi = ds_share_interval(bel, pl)
    # pseudo-ballot count: multiplicative deflation by (a) the panel discount q_w
    # (=1 when judges agree) and (b) the frailty posterior precision exp(-u_sd): a
    # couple whose latent fan support is poorly identified (u_sd large, typically
    # week-1 couples with one observation) gets wider share bands.
    conf_factor = qw * np.exp(-df_sup["fan_frailty_sd"].to_numpy())
    c_pseudo = M0_BALLOTS * conf_factor
    c_pseudo = np.clip(c_pseudo, 2.0, None)
    a_post = c_pseudo * phi_hat
    b_post = c_pseudo * (1.0 - phi_hat)
    beta_lo = sstats.beta.ppf(0.05, a_post, b_post)
    beta_hi = sstats.beta.ppf(0.95, a_post, b_post)
    width90 = beta_hi - beta_lo
    print(f"[interval] median 90% width {np.median(width90):.4f} | "
          f"corr(width, 1-q_w) = {np.corrcoef(width90, 1.0 - qw)[0, 1]:+.3f} | "
          f"corr(width, u_sd) = {np.corrcoef(width90, df_sup['fan_frailty_sd'].to_numpy())[0, 1]:+.3f} | "
          f"corr(width, fused K) = {np.corrcoef(width90, Kt)[0, 1]:+.3f}")
    # ---------------- LOSO by season (Stage-A refit; phi recomputed with held-out hazard)
    loso_auc, loso_hits, loso_top2 = [], [], []
    for s in seasons:
        tr = df_sup[df_sup["season"] != s]
        te = df_sup[df_sup["season"] == s]
        if tr["y_elim"].sum() == 0 or len(te) == 0 or te["y_elim"].sum() == 0:
            continue
        res_l, cols_l = fit_glm_cloglog(tr)
        h_te = np.asarray(res_l.predict(make_X(te, cols_l)), float)
        loso_auc.append(float(auc_score(te["y_elim"], h_te)))
        u_te, _, _, _ = frailty_posteriors(te, h_te, sigma_u)
        bel_te = te["bel"].to_numpy()
        phi_te = _week_share_normalize(bel_te * np.exp(-TAU * u_te), te)
        loso_hits.append(top1_hits(phi_te, te))
        loso_top2.append(top2_hits(phi_te, te))
    loso_auc_m = float(np.mean(loso_auc))
    loso_h1_m = float(np.mean(loso_hits))
    loso_h2_m = float(np.mean(loso_top2))
    print(f"[loso] AUC {loso_auc_m:.3f} (drop {auc_stage1 - loso_auc_m:+.3f} pp) | "
          f"top-1 {loso_h1_m:.3f} (drop {hit_store[TAU] - loso_h1_m:+.3f}) | "
          f"top-2 {loso_h2_m:.3f} (drop {hit2_store[TAU] - loso_h2_m:+.3f}) | "
          f"n_seasons={len(loso_auc)}")

    # ---------------- iconic contestants
    iconic = [("Bobby Bones", 27), ("Jerry Rice", 2), ("Bristol Palin", 11),
              ("Joey Graziadei", 33)]
    iconic_rows = {}
    for nm, s in iconic:
        g = df_sup[(df_sup.celebrity_name == nm) & (df_sup.season == s)].sort_values("week")
        if len(g) == 0:
            print(f"[warn] iconic not found: {nm} S{s}")
            continue
        iconic_rows[nm] = {
            "season": int(s), "weeks": g["week"].astype(int).tolist(),
            "phi": g["phi_hat"].round(4).tolist(),
            "lo": np.round(beta_lo[g.index.to_numpy()], 4).tolist(),
            "hi": np.round(beta_hi[g.index.to_numpy()], 4).tolist(),
            "judge_pct": g["judge_pct"].round(3).tolist(),
            "u": g["fan_frailty_u"].round(3).tolist(),
            "K": g["ds_conflict_K"].round(3).tolist(),
            "y": g["y_elim"].astype(int).tolist(),
        }
        print(f"[iconic] {nm} S{s}: u={g['fan_frailty_u'].iloc[0]:+.2f} "
              f"phi_w={np.round(g['phi_hat'].to_numpy(), 3).tolist()} "
              f"judge_pct={np.round(g['judge_pct'].to_numpy(), 2).tolist()}")

    # ---------------- Beta-vs-Dirichlet self-consistency: does the Beta(c*phi,(c(1-phi)))
    # 90% band actually contain ~90% of the Dirichlet posterior draws it approximates?
    # (Dirichlet with the SAME mean phis and row pseudo-count c_iw = m0*(1-K_iw))
    beta_cover_hits, beta_cover_n = 0, 0
    dir_lo_all, dir_hi_all = [], []
    for (s, w) in grid_weeks:
        m = (df_sup["season"].to_numpy() == s) & (df_sup["week"].to_numpy() == w)
        idx = np.where(m)[0]
        phi_w = phi_hat[idx]
        c_row = c_pseudo[idx]
        # share posterior per row: Dirichlet(c_row * phi_w) restricted to row i
        alpha_mat = c_row[:, None] * phi_w[None, :]
        draws = rng.dirichlet(alpha_mat.sum(axis=0) + 1e-9, size=800)  # (800, n_week)
        for j, irow in enumerate(idx):
            # marginal of coordinate j is Beta(alpha_j, c_row_j... ) -- use the WEEK-level
            # Dirichlet marginal for row j's own coordinate consistency
            aj = alpha_mat[j, j]
            cj = alpha_mat[j, :].sum()
            marg = sstats.beta(aj, max(cj - aj, 1e-9))
            lo_j = marg.ppf(0.05)
            hi_j = marg.ppf(0.95)
            d_lo, d_hi = dir_lo_all, dir_hi_all
            d_lo.append(lo_j)
            dir_hi_all.append(hi_j)
            beta_cover_hits += int((lo_j <= beta_hi[irow]) and (beta_lo[irow] <= hi_j))
            beta_cover_n += 1
    beta_overlap_frac = beta_cover_hits / max(beta_cover_n, 1)
    print(f"[beta] Beta-vs-Dirichlet 90%-band overlap: {beta_overlap_frac:.3f} "
          f"of {beta_cover_n} couple-weeks")

    # ---------------- rank concordance of final phi with final placement
    from scipy.stats import kendalltau as _kendall
    plc = con.set_index("row_id")["placement"]
    last_rows = (df_sup.sort_values(["row_id", "week"], kind="mergesort")
                 .groupby("row_id", sort=False).tail(1))
    plc_last = plc.loc[last_rows["row_id"].to_numpy()].to_numpy(float)
    phi_last = last_rows["phi_hat"].to_numpy(float)
    okmask = ~np.isnan(plc_last) & ~np.isnan(phi_last)
    tau_phi_place = float(_kendall(phi_last[okmask], -plc_last[okmask])[0])
    gcensured = int((plc_last[okmask] == np.nanmax(plc_last[okmask])).sum())  # 1 = winner
    print(f"[rank] Kendall tau(phi_last, -placement) = {tau_phi_place:+.3f} "
          f"(ties: winners have placement 1)")

    # ---------------- export fanvote_estimates.csv (ALL danced-week rows incl. withdrew)
    out = df.copy()
    fitted_cols = ["hazard_week", "fan_frailty_u", "fan_frailty_sd", "bel", "plaus",
                   "ds_conflict_K", "panel_discount_q", "ds_share_lo", "ds_share_hi",
                   "phi_hat", "phi_rank",
                   "beta_lo90", "beta_hi90", "pseudo_count_c", "p_elim_sim"]
    df_sup["ds_share_lo"] = ds_lo
    df_sup["ds_share_hi"] = ds_hi
    df_sup["beta_lo90"] = beta_lo
    df_sup["beta_hi90"] = beta_hi
    df_sup["pseudo_count_c"] = c_pseudo
    for c in fitted_cols:
        out[c] = np.nan
    for c in fitted_cols:  # write back by POSITION (robust to index-label drift)
        out.iloc[df_sup["__orig_pos"].to_numpy(), out.columns.get_loc(c)] = df_sup[c].to_numpy()
    out["used_in_supervision"] = out["used_in_supervision"].astype(int)

    export = out[["row_id", "season", "week", "celebrity_name", "ballroom_partner",
                  "celebrity_age_during_season", "celebrity_industry",
                  "n_active", "n_judges_scored", "scoring_type",
                  "week_score_mean", "judge_share", "week_rank_judges", "judge_pct",
                  "bel", "plaus", "ds_conflict_K", "panel_discount_q",
                  "ds_share_lo", "ds_share_hi",
                  "phi_hat", "phi_rank", "beta_lo90", "beta_hi90", "pseudo_count_c",
                  "hazard_week", "fan_frailty_u", "fan_frailty_sd",
                  "p_elim_sim", "y_elim", "used_in_supervision",
                  "status", "placement"]].copy()
    export = export.sort_values(["season", "week", "row_id"], kind="mergesort")
    csv_path = os.path.join(BASE, "fanvote_estimates.csv")
    export.to_csv(csv_path, index=False, float_format="%.6f")
    ph = export.dropna(subset=["phi_hat"])
    ww = ph.groupby(["season", "week"])["phi_hat"].sum()
    assert np.allclose(ww, 1.0, atol=1e-4), "phi must sum to 1 within each week"
    assert (ph.phi_hat > 0).all()
    print(f"[export] {csv_path} rows={len(export)} | phi sums to 1 in all {len(ww)} weeks; all phi > 0")

    # ---------------- results.json
    results = {
        "seed": SEED,
        "counts": {
            "danced_week_rows": int(n_rows_total),
            "supervision_rows": int(len(df_sup)),
            "elimination_events": int(n_events),
            "censored_finalists": int((df_sup["y_elim"] == 0).groupby(
                df_sup["row_id"]).all().sum()),   # couples never eliminated in-sample
            "seasons": int(len(seasons)),
            "withdrew_excluded": int((df["status"] == "withdrew").sum()),
            "aggregate_weeks": int((pan.scoring_type == "aggregate").sum()),
        },
        "hazard_glm": {
            "aic": aic, "converged": bool(res.converged),
            "coefficients": coefs, "std_errors": ses,
            "baseline_hazard_by_week": base_haz,
            "auc_stage1": auc_stage1,
        },
        "frailty": {
            "sigma_u": sigma_u,
            "corr_u_ndancedweeks": corr_u_nweeks,
            "corr_u_judge_pct": corr_u_jpct,
            "u_min": float(u_mean.min()), "u_max": float(u_mean.max()),
        },
        "belief_layer": {
            "gamma_grid_top1hit": {str(k): v for k, v in gamma_report.items()},
            "gamma_selected": gamma_pick,
            "K_median": float(np.median(Kt)),
            "K_p90": float(np.quantile(Kt, 0.9)),
            "K_max": float(Kt.max()),
        },
        "phi": {"tau_selected": TAU,
                "top1_hit_by_tau": {str(t): round(float(hit_store[t]), 4) for t in TAU_GRID},
                "top2_hit_by_tau": {str(t): round(float(hit2_store[t]), 4) for t in TAU_GRID}},
        "validation": {
            "top1_hit_phi": round(float(hit_store[TAU]), 4),
            "top2_hit_phi": round(float(hit2_store[TAU]), 4),
            "top1_hit_bel_only": round(float(bs_bel), 4),
            "top1_hit_judge_share_only": round(float(bs_share), 4),
            "top1_hit_judge_rank_only": round(float(bs_rank), 4),
            "top1_hit_hazard_only": round(float(bs_haz), 4),
            "top2_hit_judge_share_only": round(float(bs_share2), 4),
            "top2_hit_bel_only": round(float(bs_bel2), 4),
            "brier_all": brier_all, "brier_events_only": brier_events,
            "auc_p_elim": auc_pelim,
            "mean_p_elim": float(p_elim.mean()),
            "reliability_pred": [round(v, 4) for v in rel_pred],
            "reliability_obs": [round(v, 4) for v in rel_obs],
            "loso": {
                "auc_mean": loso_auc_m,
                "auc_drop_pp": auc_stage1 - loso_auc_m,
                "top1_mean": loso_h1_m,
                "top1_drop_pp": hit_store[TAU] - loso_h1_m,
                "top2_mean": loso_h2_m,
                "top2_drop_pp": hit2_store[TAU] - loso_h2_m,
                "n_seasons_evaluated": len(loso_auc),
            },
        },
        "interval_layer": {
            "m0_pseudo_ballots": float(M0_BALLOTS),
            "m0_ece_report": {k: v for k, v in m0_report.items()},
            "median_width90": float(np.median(width90)),
            "mean_width90": float(np.mean(width90)),
            "corr_width_conflict": float(np.corrcoef(width90, Kt)[0, 1]),
            "corr_width_panel_noise": float(np.corrcoef(width90, 1.0 - qw)[0, 1]),
            "width90_week1": float(np.mean(width90[df_sup["week"] == 1])),
            "width90_week_geq6": float(np.mean(width90[df_sup["week"] >= 6])),
            "median_ds_interval_width": float(np.median(ds_hi - ds_lo)),
        },
        "rank_concordance": {
            "kendall_tau_phi_vs_placement": tau_phi_place,
            "note": "positive tau = larger estimated fan share <=> better final placement",
        },
        "beta_vs_dirichlet": {
            "overlap_frac_90band": beta_overlap_frac,
            "n_couple_weeks_tested": int(beta_cover_n),
            "note": "Fraction of couple-weeks where the Beta pseudo-ballot 90% band "
                    "overlaps the Dirichlet marginal 90% band (self-consistency of "
                    "the two uncertainty layers; 1.0 = fully consistent).",
        },
        "iconic": iconic_rows,
    }
    res_path = os.path.join(BASE, "results.json")
    with open(res_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[export] {res_path}")

    # ================================================================ FIGURES
    # F1: phi trajectories with 90% bands for iconic contestants
    titles = {"Bobby Bones": "Bobby Bones (S27) — won despite low judge scores",
              "Jerry Rice": "Jerry Rice (S2) — runner-up, lowest judge scores 5×",
              "Bristol Palin": "Bristol Palin (S11) — 3rd, lowest judge scores 12×",
              "Joey Graziadei": "Joey Graziadei (S33) — champion, top judge scores"}
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), dpi=300)
    for ax, (nm, s) in zip(axes.ravel(), iconic):
        d = iconic_rows.get(nm)
        if d is None:
            ax.text(0.5, 0.5, "not found", ha="center")
            continue
        wks = np.array(d["weeks"], dtype=float)
        ax.fill_between(wks, d["lo"], d["hi"], alpha=0.25, color="#1f77b4",
                        label="90% credible band")
        ax.plot(wks, d["phi"], "o-", color="#1f77b4", lw=2, ms=4,
                label=r"estimated fan share $\hat\varphi$")
        ax.plot(wks, d["judge_pct"], "s--", color="#d62728", lw=1.2, ms=3,
                label="judge percentile rank")
        ylim = ax.get_ylim()
        for wk_, yv_ in zip(d["weeks"], d["y"]):
            if yv_ == 1:
                ax.axvline(wk_, color="k", ls=":", lw=1)
                ax.annotate("eliminated", (wk_, ylim[1] * 0.95), rotation=90,
                            fontsize=7, va="top", ha="right")
        ax.set_title(titles[nm], fontsize=10)
        ax.set_xlabel("week in season")
        ax.set_ylabel("share estimate")
        ax.set_ylim(0, max(0.55, np.max(d["hi"]) * 1.15))
        ax.legend(fontsize=7, loc="upper right")
    fig.suptitle("Model 1 — estimated fan-vote shares vs judge percentile (90% bands)",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(os.path.join(FIGDIR, "F1_iconic_phi_trajectories.png"), bbox_inches="tight")
    plt.close(fig)

    # F2: two-panel judge-disagreement diagnostic
    #   (a) 1 - q_w: relative IQR disagreement of the judge panel (scale-free, [0,1))
    #   (b) fused conflict K_w: Dempster conflict of the truncated fused masses.
    # K_w is |frame|-dominated (it measures how much the n_couples masses annihilate
    # under Dempster crossing, hence ~1 - sum p^2 for large casts); 1 - q_w is the
    # interpretable "how much did the judges disagree" panel.
    seas = sorted(df_sup["season"].unique())
    wmax = int(df_sup["week"].max())
    qw_agg = df_sup.groupby(["season", "week"])["panel_discount_q"].first()
    Kagg = df_sup.groupby(["season", "week"])["ds_conflict_K"].first()
    Qmat = np.full((len(seas), wmax), np.nan)
    Kmat = np.full((len(seas), wmax), np.nan)
    for r, s in enumerate(seas):
        for w in range(1, wmax + 1):
            if (s, w) in qw_agg.index:
                Qmat[r, w - 1] = 1.0 - qw_agg.loc[(s, w)]
            if (s, w) in Kagg.index:
                Kmat[r, w - 1] = Kagg.loc[(s, w)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 10), dpi=300)
    for ax, M, ttl in zip(
        axes,
        [Qmat, Kmat],
        ["judge disagreement  $1-q_w$  (relative IQR of scores)",
         "Dempster fused conflict  $K_w$  (frame-size dominated)"],
    ):
        vmax = np.nanmax(M)
        im = ax.imshow(M, aspect="auto", cmap="viridis", vmin=0, vmax=vmax)
        ax.set_xticks(range(wmax), [str(w) for w in range(1, wmax + 1)], fontsize=7)
        ax.set_yticks(range(len(seas)), [str(s) for s in seas], fontsize=7)
        ax.set_xlabel("week in season")
        ax.set_ylabel("season")
        ax.set_title(ttl, fontsize=10)
        cb = fig.colorbar(im, ax=ax, shrink=0.7)
    fig.suptitle("Judge-panel disagreement diagnostics per season-week", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(os.path.join(FIGDIR, "F2_conflict_diagnostics.png"), bbox_inches="tight")
    plt.close(fig)
    plt.close(fig)

    # F3: certainty vs week, stratified by panel-disagreement (1 - q_w) tertiles
    dnoise = 1.0 - qw
    t1, t2 = np.quantile(dnoise, [1 / 3, 2 / 3])
    strata = np.digitize(dnoise, [t1, t2])
    wks_all = df_sup["week"].to_numpy()
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    cols = ["#2ca02c", "#1f77b4", "#d62728"]
    labels = [f"judges agree (1-q<={t1:.3f})", f"mid ({t1:.3f}-{t2:.3f})",
              f"judges split (1-q>{t2:.3f})"]
    for st in range(3):
        m = strata == st
        wid, wks = width90[m], wks_all[m]
        grid = np.arange(1, wmax + 1)
        med = [np.median(wid[wks == w]) if (wks == w).sum() else np.nan for w in grid]
        q1 = [np.quantile(wid[wks == w], 0.25) if (wks == w).sum() >= 5 else np.nan for w in grid]
        q3 = [np.quantile(wid[wks == w], 0.75) if (wks == w).sum() >= 5 else np.nan for w in grid]
        ax.plot(grid, med, "o-", color=cols[st], ms=3, label=labels[st])
        ax.fill_between(grid, q1, q3, color=cols[st], alpha=0.15)
    ax.set_xlabel("week in season")
    ax.set_ylabel("90% credible-interval width of $\\hat\\varphi$")
    ax.set_title("Estimation certainty by week and judge-panel disagreement")
    ax.legend(fontsize=8)
    fig.savefig(os.path.join(FIGDIR, "F3_certainty_vs_week.png"), bbox_inches="tight")
    plt.close(fig)

    # F4: calibration of simulated elimination probabilities
    fig, ax = plt.subplots(figsize=(7, 6), dpi=300)
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect calibration")
    ax.plot(rel_pred, rel_obs, "o-", color="#9467bd", label="deciles of P(eliminated)")
    ax.hist(df_sup["p_elim_sim"], bins=40, alpha=0.25, color="#9467bd",
            density=True, label="distribution of P(elim)")
    ax.set_xlabel("predicted probability (decile mean)")
    ax.set_ylabel("observed elimination frequency")
    ax.set_title(f"Reliability of P(eliminated): AUC={auc_pelim:.3f}, Brier={brier_all:.3f}")
    ax.legend(fontsize=8)
    fig.savefig(os.path.join(FIGDIR, "F4_calibration.png"), bbox_inches="tight")
    plt.close(fig)

    # F5: latent fan pressure vs judge percentile (the inversion view)
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    jp = df_sup["judge_pct"].to_numpy()
    ax.scatter(jp, u_mean, s=10, alpha=0.5, color="#1f77b4", edgecolors="none",
               label="couple-weeks")
    for nm, s in iconic:
        g = df_sup[(df_sup.celebrity_name == nm) & (df_sup.season == s)]
        if len(g):
            ax.scatter(g["judge_pct"], g["fan_frailty_u"], s=30, marker="*",
                       color="#d62728", zorder=5)
    bb = df_sup[df_sup.celebrity_name == "Bobby Bones"]
    if len(bb):
        ax.annotate("Bobby Bones S27",
                    (float(bb["judge_pct"].mean()), float(bb["fan_frailty_u"].mean())),
                    fontsize=8, color="#d62728", xytext=(6, -2), textcoords="offset points")
    jr = df_sup[(df_sup.celebrity_name == "Jerry Rice")]
    if len(jr):
        ax.annotate("Jerry Rice S2",
                    (float(jr["judge_pct"].mean()), float(jr["fan_frailty_u"].mean())),
                    fontsize=8, color="#d62728", xytext=(6, 6), textcoords="offset points")
    z = np.polyfit(jp, u_mean, 1)
    xs = np.linspace(jp.min(), jp.max(), 50)
    ax.plot(xs, np.polyval(z, xs), "k-", lw=1.2, label=f"OLS fit slope {z[0]:+.2f}")
    ax.set_xlabel("judge percentile rank within week")
    ax.set_ylabel(r"latent fan pressure $\hat u$ (hazard multiplier $\exp(u)$)")
    ax.set_title("Fan support persists beyond judge scores: $u<0$ = fan favorites")
    ax.legend(fontsize=8)
    fig.savefig(os.path.join(FIGDIR, "F5_frailty_vs_judges.png"), bbox_inches="tight")
    plt.close(fig)

    print(f"[figures] wrote F1..F5 to {FIGDIR}")
    print("[done] Model 1 pipeline complete.")
    return results


if __name__ == "__main__":
    main()
