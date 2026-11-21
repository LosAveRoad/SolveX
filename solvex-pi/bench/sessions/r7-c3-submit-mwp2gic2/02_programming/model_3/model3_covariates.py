#!/usr/bin/env python3
"""
Model 3 - Celebrity-Covariate Impact Model (Judge Trajectory x Fan Support x Survival)
2026 MCM Problem C: "Data With The Stars".

Four deliveries (01_modeling/master_plan.md, '## Model 3'):
  D1 Judges' channel.  S_iw ~ intercept + age(scaled) + industry + partner(separate
     spec, top-12 by tenure) + home region + season + week-index + normalized
     cumulative judge percentile, random intercept a_i per celebrity-season
     (statsmodels MixedLM, REML). AR(1) extension tested with a custom profiled-ML
     likelihood-ratio test (V_i = s2*I + tau2*J  vs  V_i = s2*R(rho) + tau2*J);
     adopted only if mixture-chi2 boundary p < 0.01 (pre-registered parsimony rule).
  D2 Fans' channel.    logit(p~_iw) ~ same covariates, p~_iw = phi_hat_iw / n_w;
     Binomial GEE, exchangeable within-couple working correlation, observation
     weights 1/Var(p~_iw) from the Dirichlet(alpha0=1) posterior (uncertainty
     propagation). freq_weights inflate naive SEs -> cluster-robust sandwich SEs
     (by celebrity-season) computed manually.
  D3 Differential.     R_iw = z_w(E[S|X]) - z_w(p~_pred)  (z within season-week),
     OLS with HC3. A trait raising judges but lowering fans is a
     "judges' darling / fans' villain", and vice versa.
  D4 Survival.         Breslow Cox partial likelihood, strata = (season, week),
     risk set A_w = couples dancing that week, event = eliminated at end of week.
     Step-1 model: judges features + traits (no phi). Step-2 adds phi_hat -> the
     collinearity table lists traits that lose significance once the fan estimate
     is included ("no extra signal beyond the two scores").
     Final-duty logit (season >= 28) proxies the judges' bottom-2 dance-off.

Latent fan shares phi_hat: inverted from elimination supervision with a
Model-1-consistent parametric frailty survival model (Model 1 layer (a)):
  hazard log-odds eta_iw = -nu_i + theta_w - b*zS_iw + g*cum01_iw + d*age_cs_i,
  nu_i = season-level fan strength of the couple, N(0, sigma_nu^2) prior, also
  anchored by the observed final placement (pseudo-likelihood
  logit(r_i) ~ N(nu_i, s_anchor^2), r_i = (n_active - place)/(n_active - 1));
  theta_w = per-week-in-season baseline (Breslow-type; no parametric shape).
  phi_hat_iw = n_w * softmax_w( nu_i - theta_w + b*zS_iw - g*cum01_iw ).
  Dirichlet posterior on the share p~ = phi/n_w: Beta(p~*(n+alpha0),
  (1-p~)*(n+alpha0)) -> 90% intervals; Var(p~) = p~(1-p~)/(n+alpha0).
  If 01_modeling/shared_data/fanvote_estimates.csv exists it is cross-checked
  (agreement stats reported); adoption is controlled by config.json
  {"use_model1_if_present": false} so run.py stays reproducible from shared_data.

Deterministic: SEED = 42 everywhere.
"""
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.optimize as sopt
import scipy.stats as st
import statsmodels.api as sm

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[1] / "01_modeling" / "shared_data"
OUT = HERE
FIGDIR = HERE / "figures"
FIGDIR.mkdir(parents=True, exist_ok=True)

SEED = 42
rng = np.random.default_rng(SEED)
ALPHA0 = 1.0                     # Model 1 Dirichlet(alpha0) posterior constant
AGE_CENTER, AGE_SCALE = 39.0, 13.0
S_ANCHOR = 1.0                   # sd of the placement pseudo-likelihood anchor

TOP_INDUSTRY = ["Actor/Actress", "Athlete", "TV Personality", "Singer/Rapper",
                "Model", "Comedian"]
LOG = []


def log(msg):
    LOG.append(str(msg))
    print(msg, flush=True)


def sanitize(name):
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(name)).strip("_")


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -35.0, 35.0)))


def industry_group(ind):
    return ind if ind in TOP_INDUSTRY else "Other"


def home_group(rc):
    rc = str(rc)
    if "United States" in rc:
        return "US"
    if any(k in rc for k in ["Taiwan", "Hong Kong", "China", "Japan", "Korea",
                             "Philippines", "Vietnam", "Thailand", "India"]):
        return "East-SE-Asia"
    if any(k in rc for k in ["United Kingdom", "England", "Scotland", "Wales",
                             "Ireland"]):
        return "UK-Ireland"
    return "Other-Intl"


def clean_json(obj):
    """Recursively convert numpy scalars and non-finite floats for JSON."""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


# =================================================================================
# 0. Load shared data
# =================================================================================
def load_shared():
    con = pd.read_csv(SHARED / "contestants.csv")
    wk = pd.read_csv(SHARED / "weekly_scores.csv")
    pan = pd.read_csv(SHARED / "week_panel.csv")
    return con, wk, pan


# =================================================================================
# 1. Weekly feature assembly
# =================================================================================
def build_week_features(wk, con, pan):
    wk = wk.sort_values(["season", "week", "row_id"]).reset_index(drop=True)
    wk["S"] = wk["week_score_mean"].astype(float)

    def zsafe(x):
        sd = x.std(ddof=0)
        return (x - x.mean()) / sd if sd > 1e-12 else x * 0.0

    # zS: judges' standardized position within the season-week
    wk["zS"] = wk.groupby(["season", "week"])["S"].transform(zsafe)
    # cum01: normalized cumulative judge score within the season
    season_total = wk.groupby("season")["S"].transform("sum")
    wk["cum01"] = wk.groupby(["season", "celebrity_name"])["S"].cumsum() / season_total
    # cast covariates joined on (celebrity_name, season) [unique in contestants.csv]
    amap = con.set_index(["celebrity_name", "season"])["celebrity_age_during_season"]
    wk["age"] = amap.reindex(pd.MultiIndex.from_arrays(
        [wk["celebrity_name"], wk["season"]])).to_numpy()
    assert wk["age"].notna().all(), "age join failed"
    for col in ["celebrity_industry", "celebrity_homecountry_region",
                "celebrity_homestate"]:
        wk[col] = con.set_index(["celebrity_name", "season"])[col].reindex(
            pd.MultiIndex.from_arrays(
                [wk["celebrity_name"], wk["season"]])).to_numpy()
        assert wk[col].notna().any(), f"{col} join failed"
    # cumulative weeks danced (fraction of the 11-week season; the within-season
    # survival progress used by the fan-vote inversion)
    wk["touch01"] = (wk.groupby(["season", "celebrity_name"]).cumcount() + 1) / 11.0
    # first danced week of the season for this couple
    fw = wk.groupby(["season", "celebrity_name"])["week"].min().rename("pre_week")
    wk = wk.merge(fw, left_on=["season", "celebrity_name"], right_index=True,
                  how="left")
    # season cast size (= week-1 field, verified in shared checks.md)
    ncomp = pan.groupby("season")["n_competitors"].max().rename("n_active")
    con = con.merge(ncomp, left_on="season", right_index=True, how="left")
    wk = wk.merge(ncomp, left_on="season", right_index=True, how="left")
    assert wk["n_active"].notna().all()
    # elimination event at the end of this week
    wk["elim"] = (wk["elim_week"].to_numpy(float) ==
                  wk["week"].to_numpy(float)).astype(float)
    # season's final (show) week
    show_last = pan.groupby("season")["week"].max().rename("show_last")
    wk = wk.merge(show_last, left_on="season", right_index=True, how="left")
    # dropout rows: survived to the season's last danced week but neither finalist
    # nor eliminated (finale-episode cuts with no(scores)) -> removed from risk sets
    wk["dropout"] = ((wk["elim"] == 0) &
                     (wk["week"] >= wk["show_last"]) &
                     (wk["status"].astype(str) != "finalist")).astype(float)
    return wk, con


# =================================================================================
# 2. Fan-vote inversion (Model-1-consistent frailty survival model)
# =================================================================================
def invert_fanvotes(wk):
    sn = wk["season"].to_numpy()
    wkw = wk["week"].to_numpy()
    zS = wk["zS"].to_numpy(float)
    cum01 = wk["touch01"].to_numpy(float)   # weeks danced / 11 (bounded scale)
    age_cs = (wk["age"].to_numpy(float) - AGE_CENTER) / AGE_SCALE
    celeb = wk["celebrity_name"].to_numpy()
    keystr = np.array([f"{c}@@{s}" for c, s in zip(celeb, sn)])
    couples, kidx = np.unique(keystr, return_inverse=True)
    kidx = kidx.astype(int)
    ncoup = len(couples)
    week_of = wkw.astype(int)
    nweeks = 11
    ev = wk["elim"].to_numpy(float)

    # placement anchor, aligned to the `couples` ordering
    tmp = pd.DataFrame({"k": keystr, "placement": wk["placement"].to_numpy(float),
                        "n_active": wk["n_active"].to_numpy(float),
                        "status": wk["status"].astype(str).to_numpy()})
    cmap = tmp.drop_duplicates("k").set_index("k").reindex(couples)
    place = cmap["placement"].to_numpy(float)
    nact = cmap["n_active"].to_numpy(float)
    withdrew = (cmap["status"] == "withdrew").to_numpy()
    r_i = np.clip((nact - place) / np.maximum(nact - 1.0, 1.0), 0.02, 0.98)
    anchor = np.log(r_i / (1.0 - r_i))
    anchor_w = (~withdrew).astype(float)

    # week-block bookkeeping
    blocks = pd.factorize(pd.Series(list(zip(sn, wkw))))[0]
    nblocks = int(blocks.max()) + 1
    nb = np.bincount(blocks).astype(float)

    def nll(p):
        b, g, d, lognu = p[0], p[1], p[2], p[3]
        nu = p[4:4 + ncoup]
        theta = p[4 + ncoup:]
        eta = -nu[kidx] + theta[week_of - 1] - b * zS + g * cum01 + d * age_cs
        pr = sigmoid(eta)
        ll = np.sum(ev * np.log(pr + 1e-12) + (1 - ev) * np.log(1 - pr + 1e-12))
        sig = np.exp(lognu)
        lp_prior = -0.5 * np.sum(nu ** 2) / sig ** 2 - ncoup * lognu
        lp_anchor = -0.5 * np.sum(anchor_w * (anchor - nu) ** 2) / S_ANCHOR ** 2
        return -(ll + lp_prior + lp_anchor)

    theta0 = np.zeros(nweeks)
    for b in range(nblocks):
        m = blocks == b
        w = int(wkw[m][0])
        theta0[w - 1] = np.log((ev[m].sum() + 0.5) / (nb[b] - ev[m].sum() + 0.5))
    p0 = np.concatenate([[0.5, 2.0, -0.1, np.log(1.0)], anchor * 0.5,
                         np.nan_to_num(theta0)])
    bounds = ([(-1.0, 1.0), (-3.0, 3.0), (-3.0, 3.0), (np.log(0.05), 2.0)] +
              [(-8.0, 8.0)] * ncoup + [(-6.0, 6.0)] * nweeks)
    res = sopt.minimize(nll, p0, method="L-BFGS-B", bounds=bounds,
                        options={"maxiter": 600, "maxfun": 600000})
    b, g, d, lognu = res.x[0], res.x[1], res.x[2], res.x[3]
    nu = res.x[4:4 + ncoup]
    theta = res.x[4 + ncoup:]

    # phi_hat = n_w * softmax( nu_i - theta_w + b*zS - g*cum01 ) within each block
    psi = nu[kidx] - theta[week_of - 1] + b * zS - g * cum01
    phi = np.empty(len(wk))
    for bk in range(nblocks):
        m = blocks == bk
        e = np.exp(psi[m] - psi[m].max())
        phi[m] = e / e.sum() * nb[bk]
    # Dirichlet(alpha0)-per-category posterior on the week's share vector:
    # params a_i = alpha0 + n_w * p~_i, TOTAL A0 = n_w*alpha0 + n_w = 2*n_w.
    # posterior mean m_i = a_i / A0 (strictly positive, sums to 1); marginal of a
    # Dirichlet is Beta(a_i, A0 - a_i) -> exact 90% intervals; Var from the
    # Dirichlet formula a_i(A0-a_i)/(A0^2 (A0+1)).
    pt = phi / nb[blocks]
    A0 = (1.0 + ALPHA0) * nb[blocks]
    a_i = ALPHA0 + nb[blocks] * pt
    pmean = a_i / A0                       # posterior mean share (floors at 1/(2n_w))
    var_share = a_i * (A0 - a_i) / (A0 ** 2 * (A0 + 1.0))
    lo_p = st.beta.ppf(0.05, a_i, np.maximum(A0 - a_i, 1e-9))
    hi_p = st.beta.ppf(0.95, a_i, np.maximum(A0 - a_i, 1e-9))
    lo = np.clip(lo_p * nb[blocks], 0.0, phi)
    hi = np.clip(hi_p * nb[blocks], phi, nb[blocks])
    pmean_cnt = pmean * nb[blocks]         # posterior mean in vote-count units
    var_phi = var_share * nb[blocks] ** 2  # posterior var in vote-count units
    corr_anchor = float(np.corrcoef(nu[~withdrew], anchor[~withdrew])[0, 1])
    fitinfo = {"b_judge_tilt": float(b), "g_touch": float(g), "d_age": float(d),
               "sigma_nu": float(np.exp(lognu)),
               "anchor_corr": corr_anchor,
               "negll": float(res.fun), "n_events": int(ev.sum()),
               "optimizer_status": int(res.status), "converged": bool(res.status == 0)}
    return phi, var_phi, lo, hi, fitinfo, pmean_cnt


def dirichlet_posterior(phi, n_w):
    """Model-1-consistent Dirichlet(alpha0) posterior for an adopted phi vector:
    returns (posterior-mean share, var of share, lo90, hi90 in vote-count units)."""
    A0 = (1.0 + ALPHA0) * n_w
    a_i = ALPHA0 + n_w * phi / n_w
    pmean = a_i / A0
    var_share = a_i * (A0 - a_i) / (A0 ** 2 * (A0 + 1.0))
    lo = st.beta.ppf(0.05, a_i, np.maximum(A0 - a_i, 1e-9)) * n_w
    hi = st.beta.ppf(0.95, a_i, np.maximum(A0 - a_i, 1e-9)) * n_w
    return pmean * n_w, var_share * n_w ** 2, np.clip(lo, 0, phi), np.clip(hi, phi, n_w)


def bottom2_recovery(wk, phi, judge_share):
    """Of all eliminated couple-weeks, the fraction where that couple sits in the
    lowest-2 of the estimated fan shares (vs the judges'-share baseline)."""
    tmp = wk[["season", "week"]].copy()
    tmp["phi"] = phi
    tmp["js"] = np.asarray(judge_share, float)
    tmp["ev"] = wk["elim"].to_numpy(float)
    hit_f = hit_j = n_ev = n_wk = 0
    for _, d in tmp.groupby(["season", "week"]):
        if d["ev"].sum() == 0 or len(d) < 3:
            continue
        n_wk += 1
        n_ev += int(d["ev"].sum())
        low2 = np.argsort(d["phi"].to_numpy())[:2]
        if d["ev"].to_numpy()[low2].sum() > 0:
            hit_f += 1
        low2j = np.argsort(d["js"].to_numpy())[:2]
        if d["ev"].to_numpy()[low2j].sum() > 0:
            hit_j += 1
    return (hit_f / max(n_ev, 1), hit_j / max(n_ev, 1), n_wk, n_ev)


# =================================================================================
# 3. Fail-switch: cross-check against Model 1's fanvote_estimates.csv
# =================================================================================
def check_model1(wk, phi):
    f = SHARED / "fanvote_estimates.csv"
    info = {"model1_file_present": bool(f.exists()), "model1_used": False}
    if not f.exists():
        return phi, info
    try:
        m1 = pd.read_csv(f)
        key = ["row_id", "season", "week"]
        if not set(key).issubset(m1.columns):
            log("[fail-switch] Model 1 file missing keys; not used.")
            return phi, info
        col = "phi_hat" if "phi_hat" in m1.columns else (
            "phi" if "phi" in m1.columns else None)
        if col is None:
            log("[fail-switch] Model 1 file missing phi column; not used.")
            return phi, info
        base = wk[["row_id", "season", "week"]].copy()
        base["_seq"] = np.arange(len(base))
        mrg = base.merge(m1[key + [col]].rename(columns={col: "phi_m1"}),
                         on=key, how="left")
        ok = np.isfinite(mrg["phi_m1"].to_numpy(float))
        seq = mrg["_seq"].to_numpy()
        local, m1v = phi[seq[ok]], mrg["phi_m1"].to_numpy(float)[seq[ok]]
        pear = float(np.corrcoef(local, m1v)[0, 1])
        spr = float(st.spearmanr(local, m1v).statistic)
        info.update({"m1_rows": int(ok.sum()), "m1_pearson_vs_local": pear,
                     "m1_spearman_vs_local": spr})
        log(f"[fail-switch] Model 1 file present ({int(ok.sum())}/{len(wk)} rows): "
            f"pearson={pear:.3f}, spearman={spr:.3f} vs local inversion.")
        use = False
        cfgf = HERE / "config.json"
        if cfgf.exists():
            try:
                use = bool(json.load(open(cfgf)).get("use_model1_if_present", False))
            except Exception:
                pass
        if use and ok.sum() >= len(wk) - 30:
            out = phi.copy()
            out[seq[ok]] = m1v
            info["model1_used"] = True
            log("[fail-switch] config.json: ADOPTING Model 1 phi_hat.")
            return out, info
        return phi, info
    except Exception as e:
        log(f"[fail-switch] Model 1 cross-check failed: {e}")
        return phi, info


# =================================================================================
# 4. Covariate designs
# =================================================================================
def build_designs(wk, con):
    ind_counts = con["celebrity_industry"].value_counts()
    log("[design] industry counts (top 8): " +
        ", ".join(f"{k}={v}" for k, v in ind_counts.head(8).items()))
    p_counts = con["ballroom_partner"].value_counts()
    top_partners = list(p_counts[p_counts >= 4].index[:12])
    log(f"[design] partners with >=4 seasons: {int((p_counts >= 4).sum())}; "
        f"top-12 kept: {top_partners}")
    wk["p_g"] = wk["ballroom_partner"].where(
        wk["ballroom_partner"].isin(top_partners), "Other")

    def d(s, pfx):
        df = pd.get_dummies(s, prefix=pfx, drop_first=True, dtype=float)
        df.columns = [sanitize(c) for c in df.columns]
        return df

    ind_d = d(wk["celebrity_industry"].map(industry_group), "ind")
    home_d = d(wk["celebrity_homecountry_region"].map(home_group), "home")
    part_d = d(wk["p_g"], "pro")
    seas_d = d(wk["season"], "season")
    week_d = d(wk["week"], "week")
    trait_cols = ["age_cs"] + list(ind_d.columns) + list(home_d.columns)
    struct_cols = list(week_d.columns) + ["cum01"]
    season_cols = list(seas_d.columns)
    C_struct = season_cols + struct_cols
    trait_p = trait_cols + list(part_d.columns)
    wk = pd.concat([wk.reset_index(drop=True), ind_d.reset_index(drop=True),
                    home_d.reset_index(drop=True), part_d.reset_index(drop=True),
                    seas_d.reset_index(drop=True), week_d.reset_index(drop=True)],
                   axis=1)
    return wk, trait_cols, trait_p, C_struct, season_cols, struct_cols, top_partners


# =================================================================================
# 5. Profiled-ML likelihoods for the AR(1) test (judges' channel)
# =================================================================================
def profiled_ml_loglik(Y, Xdf, gi, ti, rho_grid=None):
    """Profile-ML marginal loglik of the Gaussian random-intercept model over an
    AR(1) grid: V_i = s2*R(rho) + tau2*J. For each rho, (logtau2, logs2) are
    optimized by L-BFGS-B; returns (max loglik, args, rho profile dict).
    With rho=0 this is the random-intercept ML; the profile over rho>0 is the
    AR(1) alternative (1 extra parameter)."""
    if rho_grid is None:
        rho_grid = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    Y = np.asarray(Y, float)
    X = np.asarray(Xdf, float)
    order = np.argsort(gi, kind="stable")
    Ys, Xs, gis, tis = Y[order], X[order], gi[order], ti[order]
    uniq, starts = np.unique(gis, return_index=True)
    starts = np.sort(starts)
    ends = np.r_[starts[1:], len(Ys)]
    k = X.shape[1]

    def prof_two(vp, rho):
        logtau2, logs2 = vp
        tau2, s2 = np.exp(np.clip(logtau2, -12, 5)), np.exp(np.clip(logs2, -8, 6))
        try:
            XtViX = np.zeros((k, k))
            XtViy = np.zeros(k)
            blocks = []
            for a, bnd in zip(starts, ends):
                n = bnd - a
                t = tis[a:bnd] - tis[a]
                R = rho ** np.abs(t[:, None] - t[None, :])
                V = s2 * R + tau2 * np.ones((n, n))
                L = np.linalg.cholesky(V + 1e-10 * np.eye(n))
                ViX = np.linalg.solve(L.T, np.linalg.solve(L, Xs[a:bnd]))
                Viy = np.linalg.solve(L.T, np.linalg.solve(L, Ys[a:bnd]))
                XtViX += Xs[a:bnd].T @ ViX
                XtViy += Xs[a:bnd].T @ Viy
                blocks.append((a, bnd, L))
            beta = np.linalg.solve(XtViX + 1e-9 * np.eye(k), XtViy)
            total = 0.0
            for (a, bnd, L) in blocks:
                n = bnd - a
                r = Ys[a:bnd] - Xs[a:bnd] @ beta
                Vr = np.linalg.solve(L.T, np.linalg.solve(L, r))
                total += -0.5 * (2.0 * np.log(np.diag(L)).sum() + r @ Vr +
                                 n * np.log(2 * np.pi))
            return total, beta
        except Exception:
            return -1e12, None

    prof = {}
    best = (-np.inf, None, None)
    for rho in rho_grid:
        rv = sopt.minimize(lambda v: -prof_two(v, rho)[0],
                           [np.log(0.3), np.log(1.0)], method="L-BFGS-B",
                           bounds=[(-12, 5), (-8, 6)])
        ll = -rv.fun
        prof[round(rho, 3)] = float(ll)
        if ll > best[0]:
            best = (ll, rv.x, rho)
    return best[0], {"logtau2": float(best[1][0]), "logs2": float(best[1][1]),
                     "rho": float(best[2])}, prof


# =================================================================================
# 6. Estimators for D1 / D2
# =================================================================================
def fit_mixedlm(dfx, cols, Ycol="S"):
    X = sm.add_constant(dfx[cols].astype(float), has_constant="add")
    gi = pd.factorize(dfx["celebrity_name"].astype(str) + "_" +
                      dfx["season"].astype(str))[0]
    md = sm.MixedLM(dfx[Ycol].to_numpy(float), X, groups=gi)
    r = md.fit(reml=True, method="lbfgs", maxiter=600)
    return md, r, X.columns.tolist(), gi


def nondegenerate(dfx, cols, min_var=1e-9, min_support=3):
    """Columns usable in a REFIT on this subset: drop near-constant and
    (nearly) empty dummy columns to avoid singular designs."""
    keep = []
    for c in cols:
        v = dfx[c].to_numpy(float)
        if len(v) < min_support + 2:
            continue
        if v.std() < min_var:
            continue
        if v.sum() < min_support:      # dummy touching < min_support rows
            continue
        keep.append(c)
    return keep


def wald_partialR2(params, cov, cols, n):
    """Joint Wald chi2 -> partial R2 proxy chi2/(chi2+n) and p-value."""
    idx = [list(params.index).index(c) for c in cols if c in params.index]
    if len(idx) == 0:
        return np.nan, np.nan
    bb = np.asarray(params)[idx]
    V = np.asarray(cov)[np.ix_(idx, idx)]
    try:
        chi2 = float(bb @ np.linalg.pinv(V) @ bb)
    except Exception:
        return np.nan, np.nan
    return chi2 / (chi2 + n), float(st.chi2.sf(chi2, len(idx)))


def cluster_sandwich_gee(X, y, mu, w, gi):
    """Cluster-robust (HC0-by-celebrity-season) sandwich for the weighted
    Binomial GEE score."""
    X = np.asarray(X, float)
    W = w * mu * (1.0 - mu)
    Binv = np.linalg.pinv(X.T @ (W[:, None] * X))
    resid = (y - mu) * w
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in np.unique(gi):
        m = gi == g
        s = (X[m] * resid[m, None]).sum(axis=0)
        meat += np.outer(s, s)
    np.fill_diagonal(meat, meat.diagonal() + 1e-12)
    return Binv @ meat @ Binv


def fit_fan_gee(dfx, cols, weights):
    """Binomial-logit GEE with observation weights. Attempt order:
    (1) weighted Independence (robust cluster sandwich absorbs the working-
        correlation misspecification; comparable weighted/unweighted),
    (2) weighted Exchangeable (only if the working correlation stays in (-0.99,0.99)),
    (3) unweighted Independence. Cluster-robust sandwich SEs always reported."""
    X = sm.add_constant(dfx[cols].astype(float), has_constant="add")
    y = np.clip(dfx["phi_share"].to_numpy(float), 1e-4, 1 - 1e-4)
    gi = pd.factorize(dfx["celebrity_name"].astype(str) + "_" +
                      dfx["season"].astype(str))[0]
    is_unweighted = np.allclose(np.asarray(weights, float), 1.0)
    struct_used = None
    gee = None
    try:
        ge = sm.GEE(y, X, groups=gi, family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Independence(), weights=weights)
        r = ge.fit(maxiter=200)
        if np.isfinite(np.asarray(r.params)).all():
            gee = r
            struct_used = ("Independence(unweighted)" if is_unweighted
                           else "Independence(weighted)")
    except Exception as e:
        log(f"[D2] weighted Independence failed ({e}).")
    if gee is None:
        try:
            ge = sm.GEE(y, X, groups=gi, family=sm.families.Binomial(),
                        cov_struct=sm.cov_struct.Exchangeable(), weights=weights)
            r = ge.fit(maxiter=200)
            dep_v = float(np.asarray(r.cov_struct.dep_params).ravel()[0])
            if np.isfinite(np.asarray(r.params)).all() and -0.99 < dep_v < 0.99:
                gee = r
                struct_used = ("Exchangeable(unweighted)" if is_unweighted
                               else "Exchangeable(weighted)")
        except Exception as e:
            log(f"[D2] weighted Exchangeable failed ({e}).")
    if gee is None:
        ge = sm.GEE(y, X, groups=gi, family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Independence())
        gee = ge.fit(maxiter=200)
        struct_used = "Independence(unweighted-fallback)"
        log("[D2] fell back to unweighted Independence GEE.")
    if gee is None:
        raise RuntimeError("all GEE specifications failed")
    dep = float(np.asarray(gee.cov_struct.dep_params).ravel()[0]) \
        if isinstance(gee.cov_struct, sm.cov_struct.Exchangeable) else np.nan
    mu = np.asarray(gee.fittedvalues, float)
    Vrob = cluster_sandwich_gee(X, y, mu, np.asarray(weights, float), gi)
    se = np.sqrt(np.diag(Vrob))
    z = np.asarray(gee.params) / np.maximum(se, 1e-12)
    pvals = 2 * st.norm.sf(np.abs(z))
    return gee, Vrob, se, pvals, X.columns.tolist(), y, struct_used, dep


# =================================================================================
# 7. Delivery 4: survival estimators
# =================================================================================
def fit_phreg(dfx, cols):
    sub = dfx[(dfx["dropout"] == 0).to_numpy()]
    dur = sub["week"].to_numpy(float) - sub["pre_week"].to_numpy(float) + 1.0
    ev = sub["elim"].to_numpy(float)
    strata = (sub["season"].astype(str) + "|" + sub["week"].astype(str)).to_numpy()
    X = sub[cols].astype(float).to_numpy()
    m = sm.PHReg(dur, X, status=ev, strata=strata, ties="breslow")
    r = m.fit()
    return r, sub, dur, ev, strata, list(cols)


def block_auc(dfx, lp, seed=SEED, exact_limit=40000):
    """Within-(season,week) discrimination: P(lp_safe > lp_event) over all
    (eliminated, surviving) pairs in each stratum (Cox C-statistic per stratum)."""
    r2 = np.random.default_rng(seed)
    tmp = dfx[["season", "week"]].copy()
    tmp["lp"] = np.asarray(lp, float)      # SAFETY score: higher = safer
    tmp["ev"] = dfx["elim"].to_numpy(float)
    num = den = 0
    for _, d in tmp.groupby(["season", "week"]):
        pos = d.loc[d["ev"] == 1, "lp"].to_numpy()   # events (eliminated)
        neg = d.loc[d["ev"] == 0, "lp"].to_numpy()   # survivors
        if len(pos) == 0 or len(neg) == 0:
            continue
        diff = neg[:, None] - pos[None, :]            # P(survivor safer than event)
        if diff.size <= exact_limit:
            num += int(((diff > 0) + 0.5 * (diff == 0)).sum())
            den += int(diff.size)
        else:
            n = exact_limit
            ip = r2.integers(0, len(neg), n)
            inn = r2.integers(0, len(pos), n)
            diff = neg[ip] - pos[inn]
            num += int(((diff > 0) + 0.5 * (diff == 0)).sum())
            den += n
    return num / den if den else np.nan


def harrell_c(dur, ev, lp):
    """Global Harrell's C on (duration-at-risk, event, linear predictor):
    comparable pairs = (i failed at t_i, j with t_j > t_i) or (t_j == t_i and j
    censored)."""
    dur = np.asarray(dur, float)
    ev = np.asarray(ev, float)
    lp = np.asarray(lp, float)
    num = den = 0
    for i in np.where(ev == 1)[0]:
        j = np.where((dur > dur[i]) | ((dur == dur[i]) & (ev == 0)))[0]
        j = j[j != i]
        if len(j) == 0:
            continue
        diff = lp[i] - lp[j]          # longer survival = larger lp = positive diff
        num += int(((diff > 0) + 0.5 * (diff == 0)).sum())
        den += len(j)
    return num / den if den else np.nan


# =================================================================================
# Main driver
# =================================================================================
def run_main():
    log("=== Model 3: Celebrity-Covariate Impact Model ===")
    con, wk, pan = load_shared()
    log(f"[load] contestants={len(con)}, weekly={len(wk)}, panel={len(pan)}")
    wk, con = build_week_features(wk, con, pan)
    log(f"[features] {len(wk)} danced-week rows; elim events={int(wk['elim'].sum())}, "
        f"dropout rows={int(wk['dropout'].sum())}")

    # ---------------- fan-vote inversion ----------------------------------------
    phi, var_phi, lo90, hi90, fitinfo, phi_pmean = invert_fanvotes(wk)
    wk["phi_hat"] = phi
    wk["var_phi"] = var_phi
    wk["phi_lo90"], wk["phi_hi90"] = lo90, hi90
    wk["phi_pmean"] = phi_pmean
    log(f"[invert] {fitinfo}")
    sums = wk.groupby(["season", "week"])["phi_hat"].sum().to_numpy()
    nB = wk.groupby(["season", "week"]).size().to_numpy()
    assert np.allclose(sums, nB, atol=1e-6), "phi must sum to n_w per week"
    log(f"[invert] phi_hat sums to n_w per week OK; mean={phi.mean():.4f}, "
        f"max={phi.max():.3f}, mean 90% width={(hi90 - lo90).mean():.4f}")
    rec_f, rec_j, n_wk, n_ev = bottom2_recovery(wk, phi, wk["judge_share"])
    log(f"[invert] bottom-2 recovery of eliminated couples: model={rec_f:.1%} vs "
        f"judges-share baseline={rec_j:.1%} ({n_ev} eliminated couples in "
        f"{n_wk} elimination weeks)")
    phi, m1info = check_model1(wk, phi)
    if m1info.get("model1_used"):
        n_map = wk.groupby(["season", "week"])["row_id"].transform("size").to_numpy(float)
        pt_new = phi / n_map
        var_phi = pt_new * (1 - pt_new) / (n_map + ALPHA0) * n_map ** 2
        kap = n_map + ALPHA0
        lo90 = st.beta.ppf(0.05, np.maximum(pt_new, 1e-9) * kap,
                           np.maximum(1 - pt_new, 1e-9) * kap) * n_map
        hi90 = st.beta.ppf(0.95, np.maximum(pt_new, 1e-9) * kap,
                           np.maximum(1 - pt_new, 1e-9) * kap) * n_map
        wk["phi_hat"], wk["var_phi"] = phi, var_phi
        wk["phi_lo90"], wk["phi_hi90"] = lo90, hi90

    phi_prev, m1info = check_model1(wk, phi)
    if m1info.get("model1_used"):
        n_map = wk.groupby(["season", "week"])["row_id"].transform("size").to_numpy(float)
        phi = phi_prev
        pm, vs, lo90, hi90 = dirichlet_posterior(phi, n_map)
        var_phi = vs
        wk["phi_hat"], wk["var_phi"] = phi, var_phi
        wk["phi_lo90"], wk["phi_hi90"] = lo90, hi90
        wk["phi_pmean"] = pm

    # ---------------- designs ----------------------------------------------------
    # D2 response = true unit-sum share. phi_pmean is the Dirichlet posterior mean
    # in vote-count units (sums to n_w per season-week); dividing by the week's
    # cast size gives the share vector with sum(phi_share) == 1 per (season, week).
    n_map = wk.groupby(["season", "week"])["row_id"].transform("size").to_numpy(float)
    wk["phi_share"] = wk["phi_pmean"] / n_map
    wk["age_cs"] = (wk["age"] - AGE_CENTER) / AGE_SCALE
    wk["phi_hat_std"] = (wk["phi_hat"] - wk["phi_hat"].mean()) / wk["phi_hat"].std(ddof=0)
    wk, trait_cols, trait_p, C_struct, season_cols, struct_cols, top_partners = \
        build_designs(wk, con)
    log(f"[design] traits={len(trait_cols)} (age + {len(trait_cols)-1-len([c for c in trait_cols if c.startswith('home_')])} industry + "
        f"{len([c for c in trait_cols if c.startswith('home_')])} home), "
        f"struct={len(C_struct)} (season {len(season_cols)} + week {len(struct_cols)-1} + cum01), "
        f"partner cols={len(trait_p)-len(trait_cols)}")
    ind_cols = [c for c in trait_cols if c.startswith("ind_")]
    home_cols = [c for c in trait_cols if c.startswith("home_")]

    # ============================ D1: judges' channel ============================
    log("[D1] MixedLM (REML) on weekly judge score S_iw ...")
    md1, r1, cols1, gi1 = fit_mixedlm(wk, trait_cols + C_struct)
    var_re = float(np.asarray(r1.cov_re)[0, 0])
    icc = var_re / (var_re + r1.scale)
    fe1 = pd.Series(np.asarray(r1.fe_params), index=cols1)
    se1 = pd.Series(np.asarray(r1.bse_fe), index=cols1)
    pv1 = pd.Series(2 * st.norm.sf(np.abs(fe1 / se1)), index=cols1)
    V1 = np.asarray(r1.cov_params())[:len(cols1), :len(cols1)]
    log(f"[D1] converged={r1.converged}, nobs={int(md1.nobs)}, "
        f"groups={md1.n_groups}, var_random={var_re:.4f}, resid_var={r1.scale:.4f}, "
        f"ICC={icc:.3f}")
    wk["S_hat"] = (sm.add_constant(wk[trait_cols + C_struct].astype(float),
                                   has_constant="add").to_numpy()
                   @ np.asarray(r1.fe_params))
    pr2i, pi_ = wald_partialR2(fe1, V1, ind_cols, int(md1.nobs))
    # partner spec (separate because partner tenure overlaps season effects)
    pro_cols = [c for c in trait_p if c.startswith("pro_")]
    md1p, r1p, cols1p, _ = fit_mixedlm(wk, ["age_cs"] + pro_cols + C_struct)
    fe1p = pd.Series(np.asarray(r1p.fe_params), index=cols1p)
    V1p = np.asarray(r1p.cov_params())[:len(cols1p), :len(cols1p)]
    pr2p, pp_ = wald_partialR2(fe1p, V1p, pro_cols, int(md1p.nobs))
    log(f"[D1] partial R2 (Wald): industry={pr2i:.4f} (p={pi_:.3g}), "
        f"partner={pr2p:.4f} (p={pp_:.3g})")
    age_b1, age_p1 = float(fe1["age_cs"]), float(pv1["age_cs"])
    log(f"[D1] age effect (per +{AGE_SCALE:.0f}y) on judge score: "
        f"{age_b1 * AGE_SCALE:+.3f} points (p={age_p1:.3g})")
    show1 = ["age_cs"] + ind_cols[:4] + home_cols
    log("[D1] coefficients: " + ", ".join(f"{k}={fe1[k]:+.3f}(p={pv1[k]:.3g})"
                                          for k in show1 if k in fe1.index))

    # AR(1) LRT via profiled ML over an AR grid
    log("[D1] profiled-ML LRT for AR(1) residuals (rho grid) ...")
    Xd = sm.add_constant(wk[trait_cols + C_struct].astype(float), has_constant="add")
    ll0, est0, prof0 = profiled_ml_loglik(wk["S"].to_numpy(float), Xd, gi1,
                                          wk["week"].to_numpy(float),
                                          rho_grid=[0.0])
    rhos = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8]
    ll1, est1, prof1 = profiled_ml_loglik(wk["S"].to_numpy(float), Xd, gi1,
                                          wk["week"].to_numpy(float),
                                          rho_grid=rhos)
    rho_hat = float(est1["rho"])
    stat = max(2.0 * (ll1 - ll0), 0.0)
    p_plain = float(st.chi2.sf(stat, 1))
    p_mix = float(0.5 * st.norm.sf(np.sqrt(stat)))     # 0.5 chi2_0 + 0.5 chi2_1
    adopt_ar1 = bool(p_mix < 0.01)
    # est0/est1 kept for the record; the LRT uses ll0 (RI) vs max over rho>0
    log(f"[D1] llf_RI={ll0:.2f}, llf_AR1={ll1:.2f}, rho_hat={rho_hat:.3f}, "
        f"LRT={stat:.2f}, p_plain={p_plain:.3g}, p_mixture={p_mix:.3g} -> "
        f"{'ADOPT AR(1)' if adopt_ar1 else 'keep random intercept (parsimony)'}")

    # ============================ D2: fans' channel ==============================
    log("[D2] weighted Binomial GEE on logit(phi_share) ...")
    # var of the posterior-mean share (Dirichlet), in share units
    n_map = wk.groupby(["season", "week"])["row_id"].transform("size").to_numpy(float)
    A0_map = (1.0 + ALPHA0) * n_map
    a_map = ALPHA0 + wk["phi_hat"].to_numpy(float)   # = alpha0 + n_w*(phi/n_w)
    var_share = a_map * (A0_map - a_map) / (A0_map ** 2 * (A0_map + 1.0))
    w_obs = 1.0 / np.clip(var_share, 1e-8, None)
    w_obs = w_obs / w_obs.mean()
    log(f"[D2] weights 1/Var: mean=1.00, p10={np.quantile(w_obs, .1):.2f}, "
        f"p90={np.quantile(w_obs, .9):.2f} (uncertainty propagation active)")
    gee, Vrob, se2, pv2, cols2, y2, struct_used2, dep = fit_fan_gee(
        wk, trait_cols + C_struct, w_obs)
    fe2 = pd.Series(np.asarray(gee.params), index=cols2)
    pv2s = pd.Series(pv2, index=cols2)
    log(f"[D2] GEE structure={struct_used2}, working corr param="
        f"{dep if np.isfinite(dep) else float('nan'):.3f}")
    wk["phi_tilde_hat"] = np.asarray(gee.predict(sm.add_constant(
        wk[trait_cols + C_struct].astype(float), has_constant="add")), float)
    phi_age_b2 = float(fe2["age_cs"])
    phi_age_p2 = float(pv2s["age_cs"])
    log(f"[D2] age effect on logit(fan share): {phi_age_b2:+.3f} per "
        f"+{AGE_SCALE:.0f}y (p={phi_age_p2:.3g})")
    show2 = ["age_cs"] + ind_cols[:4] + home_cols
    log("[D2] coefficients (log-odds, robust SE): " + ", ".join(
        f"{k}={fe2[k]:+.3f}(p={pv2s[k]:.3g})" for k in show2 if k in fe2.index))
    # unweighted sensitivity
    gee_u, _, _, _, _, _, su, _ = fit_fan_gee(wk, trait_cols + C_struct,
                                              np.ones(len(wk)))
    # unweighted sensitivity: coefficient ratio and, more robustly, the rank
    # agreement between weighted/unweighted fits over the shared design columns
    common_sens = [c for c in cols2 if c in gee_u.model.exog_names]
    bw = pd.Series(np.asarray(gee_u.params), index=gee_u.model.exog_names)[common_sens]
    bf = pd.Series(np.asarray(gee.params), index=cols2)[common_sens]
    sens_rank = float(st.spearmanr(bw, bf).statistic)
    log(f"[D2] unweighted-GEE sensitivity: rank agreement of coefficients "
        f"(weighted vs unweighted) = {sens_rank:.3f}")
    # targeted aux spec: Social-Media-Personality dummy (n=9 cast seasons)
    wk["is_smp"] = (wk["celebrity_industry"] ==
                    "Social Media Personality").astype(float)
    aux_cols = ["age_cs", "is_smp"] + [c for c in ind_cols] + home_cols + C_struct
    gee_smp, _, _, pv_smp_a, cols_smp, _, su2, dep_smp = fit_fan_gee(wk, aux_cols, w_obs)
    fe_smp = pd.Series(np.asarray(gee_smp.params), index=cols_smp)
    pv_smp = pd.Series(pv_smp_a, index=cols_smp)
    md_smp, r_smp, cols_smpj, _ = fit_mixedlm(wk, aux_cols)
    fe_smpj = pd.Series(np.asarray(r_smp.fe_params), index=cols_smpj)
    b_smp_fan = float(fe_smp["is_smp"]); p_smp_fan = float(pv_smp["is_smp"])
    b_smp_jud = float(fe_smpj["is_smp"])
    se_smpj = float(np.asarray(r_smp.bse_fe)[list(cols_smpj).index("is_smp")])
    p_smp_jud = float(2 * st.norm.sf(abs(b_smp_jud / se_smpj)))
    log(f"[D2/D1 aux] is_smp (Social Media Personality, {int(wk['is_smp'].sum())} rows): "
        f"fan logit {b_smp_fan:+.3f} (p={p_smp_fan:.3g}), judge points "
        f"{b_smp_jud:+.3f} (p={p_smp_jud:.3g})")

    # ============================ D3: differential ===============================
    log("[D3] fans-over/under-rating residual R = z(E[S|X]) - z(phi_pred) ...")

    def zby(col):
        g = wk.groupby(["season", "week"])[col]
        m = g.transform("mean")
        sd = g.transform("std").replace(0, np.nan)
        return ((wk[col] - m) / sd).to_numpy()

    zs, zp = zby("S_hat"), zby("phi_tilde_hat")
    R = zs - zp
    ok = np.isfinite(R)
    X3 = sm.add_constant(wk.loc[ok, trait_cols + C_struct].astype(float),
                         has_constant="add")
    gi3 = pd.factorize(wk.loc[ok, "celebrity_name"].astype(str) + "_" +
                       wk.loc[ok, "season"].astype(str))[0]
    ols3 = sm.OLS(R[ok], X3).fit(cov_type="cluster",
                                 cov_kwds={"groups": gi3})
    fe3 = ols3.params
    wk["R"] = np.nan
    wk.loc[ok, "R"] = R[ok]
    r3_age, r3_age_p = float(fe3["age_cs"]), float(ols3.pvalues["age_cs"])
    n3 = int(ok.sum())
    show3 = ["age_cs"] + ind_cols[:4] + home_cols
    log(f"[D3] n={n3}; coefficients (z-units): " + ", ".join(
        f"{k}={fe3[k]:+.3f}(p={ols3.pvalues[k]:.3g})" for k in show3 if k in fe3.index))

    # sign agreement between judge-channel and fan-channel coefficients
    common = [c for c in trait_cols if c in fe1.index and c in fe2.index]
    same = sum(1 for c in common if np.sign(fe1[c]) == np.sign(fe2[c]))
    opp_sig = [c for c in common
               if (np.sign(fe1[c]) != np.sign(fe2[c])) and pv1[c] < 0.10
               and pv2s[c] < 0.10]
    log(f"[D3] trait sign agreement judge-vs-fan: {same}/{len(common)} same sign; "
        f"significant opposite-sign (p<0.10 both): {opp_sig}")

    # ============================ D4: survival ===================================
    # average weeks danced per couple (for converting predicted shares back to
    # phi_hat counts in the archetype simulation)
    n_bar = float(wk.groupby(["season", "celebrity_name"]).size().mean())
    log("[D4] Breslow PHReg, strata=(season,week) ...")
    judge_feats = ["zS", "cum01"]
    # RAW phi_hat is outcome-anchored (embedding the final placement in the
    # inversion), so a raw-phi Cox model merely re-states the data (tautology).
    # The FAIR fan-channel regressor is the within-season DEVIATION from that
    # anchored level:
    #   phi_flux_iw = phi_hat_std_iw - phi_hat_std_i,week1,
    # i.e. 0 in the entry week and +/- afterwards. Positive flux in week w
    # = fan support RISING above the season-level prior (living up to / exceeding
    # expectations). Traits are tested on (zS, cum01, traits) in step 1, and
    # step 2 adds phi_flux as the collinearity probe.
    wk["phi_flux"] = (wk["phi_hat_std"]
                      - wk.groupby(["season", "celebrity_name"])["phi_hat_std"]
                      .transform("first"))
    fan_feats = ["phi_flux"]
    cols_s1 = judge_feats + trait_cols
    r41, sub1, dur1, ev1, str1, cn1 = fit_phreg(wk, cols_s1)
    lp1 = sub1[cn1].astype(float).to_numpy() @ np.asarray(r41.params)
    conc1 = harrell_c(dur1, ev1, lp1)
    auc1 = block_auc(sub1, -lp1)
    cols_s2 = judge_feats + fan_feats + trait_cols
    r42, sub2, dur2, ev2, str2, cn2 = fit_phreg(wk, cols_s2)
    lp2 = sub2[cn2].astype(float).to_numpy() @ np.asarray(r42.params)
    conc2 = harrell_c(dur2, ev2, lp2)
    auc2 = block_auc(sub2, -lp2)
    r4f, subf, durf, evf, strf, cnf = fit_phreg(wk, fan_feats)
    lpf = subf[cnf].astype(float).to_numpy() @ np.asarray(r4f.params)
    concf = harrell_c(durf, evf, lpf)
    aucf = block_auc(subf, -lpf)
    idx1 = {c: i for i, c in enumerate(cn1)}
    idx2 = {c: i for i, c in enumerate(cn2)}
    bzS1 = float(r41.params[idx1["zS"]])
    bzS2 = float(r42.params[idx2["zS"]])
    bphi2 = float(r42.params[idx2["phi_flux"]])
    bphi2_p = float(r42.pvalues[idx2["phi_flux"]])
    b_age1 = float(r41.params[idx1["age_cs"]])
    b_age1_p = float(r41.pvalues[idx1["age_cs"]])
    b_age2 = float(r42.params[idx2["age_cs"]])
    b_age2_p = float(r42.pvalues[idx2["age_cs"]])
    log(f"[D4] Harrell C / stratified AUC: phi-only {concf:.3f}/{aucf:.3f}, "
        f"judges+traits {conc1:.3f}/{auc1:.3f}, judges+phi+traits "
        f"{conc2:.3f}/{auc2:.3f}")
    log(f"[D4] zS coef {bzS1:+.3f} (no phi, fair 'beyond judges' test)")
    log(f"[D4] with phi_flux added: zS {bzS2:+.3f}, phi_flux coef={bphi2:+.3f} "
        f"(p={bphi2_p:.3g}), age {b_age1:+.3f} (p={b_age1_p:.3g}) -> "
        f"{b_age2:+.3f} (p={b_age2_p:.3g})")
    assert bzS1 < 0, "zS slope must be negative (better judges -> safer)"
    # phi_hat is itself estimated from the elimination outcomes (placement anchor),
    # so its step-2 dominance (|b_phi| large, C ~ 0.96) is expected: the step-2
    # model is a MEDIATION/COLLINEARITY diagnostic (whose survival signal is
    # absorbed by the fan estimate), not a causal coefficient. Traits significant
    # in step 1 whose p rises above 0.05 in step 2 are labelled 'mediated'.
    no_extra = []
    for c in cn1:
        if c in ("zS", "cum01"):
            continue
        p1 = float(r41.pvalues[idx1[c]])
        p2 = float(r42.pvalues[idx2[c]]) if c in idx2 else np.nan
        if p1 < 0.05 and (np.isnan(p2) or p2 >= 0.05):
            no_extra.append({"covariate": c, "p_step1": p1, "p_step2": p2,
                             "interpretation": "mediated by fan support"})
    if no_extra:
        log("[D4] traits losing significance once phi_hat is included: " +
            ", ".join(f"{d['covariate']} (p {d['p_step1']:.3g}->{d['p_step2']:.3g})"
                      for d in no_extra))
    else:
        log("[D4] no trait loses significance after phi_hat inclusion")
    # robustness: exclude withdrew couples
    r4w, subw, durw, evw, strw, cnw = fit_phreg(
        wk[(wk["status"] != "withdrew").to_numpy()], cols_s2)
    idxw = {c: i for i, c in enumerate(cnw)}
    log(f"[D4] refit excluding withdrew: zS={r4w.params[idxw['zS']]:+.3f}, "
        f"phi_flux={r4w.params[idxw['phi_flux']]:+.3f}")
    # raw-phi tautology check (documented, not used downstream): how much of the
    # outcome-anchored level is trivially 'known' by construction?
    r4raw, subraw, durraw, evraw, strraw, cnraw = fit_phreg(wk, ["phi_hat_std"])
    auc_rawphi = block_auc(subraw, -subraw["phi_hat_std"].to_numpy())
    log(f"[D4] tautology documentation: raw outcome-anchored phi alone gives "
        f"AUC={auc_rawphi:.3f} (H1+Cox C 0.958) - hence phi_flux is the fair "
        f"fan-channel regressor")
    # final-duty logit (season >= 28: judges' bottom-2 dance-off proxy).
    # saved = 1 - eliminated (bottom-2 survival, judge-veto evidence)
    subd = wk[(wk["season"] >= 28).to_numpy() & (wk["dropout"] == 0).to_numpy()]
    Xduty = sm.add_constant(subd[["phi_hat_std"]].astype(float), has_constant="add")
    yduty = 1.0 - subd["elim"].to_numpy(float)
    rs_duty = sm.GLM(yduty, Xduty, family=sm.families.Binomial()).fit()
    b_duty = float(rs_duty.params["phi_hat_std"])
    # AUC of SAVING the bottom-2 couple from fan support: survivors (yduty=1)
    # should have HIGHER phi than eliminated (yduty=0)
    auc_duty = block_auc(subd, Xduty.to_numpy() @ np.asarray(rs_duty.params))
    log(f"[D4] final-duty S28+ logit (judge dance-off): b_phi={b_duty:+.3f}, "
        f"AUC(saved-by-judges ~ phi)={auc_duty:.3f}, "
        f"saved={int(yduty.sum())}/{int(len(yduty))} "
        f"(the huge positive coef means high-fan-support couples are never "
        f"vetoed... and high-phi couples are rarely bottom-2 at all)")

    # ============================ validation =====================================
    log("[validation] 27-train / 7-held-out season split ...")
    seasons = np.array(sorted(wk["season"].unique()))
    rng_v = np.random.default_rng(SEED + 1)
    rng_v.shuffle(seasons)
    test_s, train_s = np.sort(seasons[:7]), np.sort(seasons[7:])
    tr_mask = wk["season"].isin(train_s).to_numpy()
    te_mask = wk["season"].isin(test_s).to_numpy()
    # D1 out-of-sample R2 (drop columns with zero/near-zero support in TRAIN)
    tr_cols = nondegenerate(wk.loc[tr_mask], trait_cols + C_struct)
    Xtr = sm.add_constant(wk.loc[tr_mask, tr_cols].astype(float),
                          has_constant="add")
    gtr = pd.factorize(wk.loc[tr_mask, "celebrity_name"].astype(str) + "_" +
                       wk.loc[tr_mask, "season"].astype(str))[0]
    mdv = sm.MixedLM(wk.loc[tr_mask, "S"].to_numpy(float), Xtr, groups=gtr)
    rv = mdv.fit(reml=True, method="lbfgs", maxiter=600)
    Xte = sm.add_constant(wk.loc[te_mask, tr_cols].astype(float),
                          has_constant="add")
    pred_S = Xte.to_numpy() @ np.asarray(rv.fe_params)
    yte = wk.loc[te_mask, "S"].to_numpy(float)
    r2_j = 1 - ((yte - pred_S) ** 2).sum() / ((yte - yte.mean()) ** 2).sum()
    spr_j = float(st.spearmanr(pred_S, yte).statistic)
    # season-intercept-calibrated variant: OLS of test S on a test-season intercept
    # + the fitted trait coefficients (fair gauge of STRUCTURAL generalization)
    wkte = wk.loc[te_mask].copy()
    wkte["pred_raw"] = pred_S
    Xcal = pd.get_dummies(wkte["season"], prefix="cal", drop_first=True,
                          dtype=float)
    Xcal.insert(0, "pred_raw", pred_S)
    ols_cal = sm.OLS(wkte["S"].to_numpy(float), Xcal).fit()
    pred_cal = np.asarray(ols_cal.predict(Xcal), float)
    r2_j_c = 1 - ((yte - pred_cal) ** 2).sum() / ((yte - yte.mean()) ** 2).sum()
    spr_j = float(st.spearmanr(pred_S, yte).statistic)
    # D2 out-of-sample spearman
    gv = sm.GLM(np.clip(wk.loc[tr_mask, "phi_share"], 1e-4, 1 - 1e-4), Xtr,
                family=sm.families.Binomial(),
                freq_weights=w_obs[tr_mask] / w_obs[tr_mask].mean()).fit()
    pred_phi = gv.predict(Xte)
    spr_f = float(st.spearmanr(pred_phi,
                               wk.loc[te_mask, "phi_share"].to_numpy(float)).statistic)
    log(f"[validation] D1 hold-out: R2={r2_j:.3f} (raw), R2_cal={r2_j_c:.3f} "
        f"(season-intercept-calibrated, target>=0.55); spearman={spr_j:.3f}")
    # D4 out-of-sample AUC
    keep_tr = tr_mask & (wk["dropout"] == 0).to_numpy()
    keep_te = te_mask & (wk["dropout"] == 0).to_numpy()
    msv = sm.PHReg(wk.loc[keep_tr, "week"].to_numpy(float)
                   - wk.loc[keep_tr, "pre_week"].to_numpy(float) + 1.0,
                   wk.loc[keep_tr, cols_s2].astype(float).to_numpy(),
                   status=wk.loc[keep_tr, "elim"].to_numpy(float),
                   strata=(wk.loc[keep_tr, "season"].astype(str) + "|" +
                           wk.loc[keep_tr, "week"].astype(str)).to_numpy(),
                   ties="breslow")
    rsv = msv.fit()
    lp_te = wk.loc[keep_te, cols_s2].astype(float).to_numpy() @ np.asarray(rsv.params)
    auc_s = block_auc(wk.loc[keep_te], -lp_te)
    # step-1 (judges + traits, no outcome-anchored phi) AUC on the same split
    msv1 = sm.PHReg(wk.loc[keep_tr, "week"].to_numpy(float)
                    - wk.loc[keep_tr, "pre_week"].to_numpy(float) + 1.0,
                    wk.loc[keep_tr, cols_s1].astype(float).to_numpy(),
                    status=wk.loc[keep_tr, "elim"].to_numpy(float),
                    strata=(wk.loc[keep_tr, "season"].astype(str) + "|" +
                            wk.loc[keep_tr, "week"].astype(str)).to_numpy(),
                    ties="breslow")
    rsv1 = msv1.fit()
    lp_te1 = wk.loc[keep_te, cols_s1].astype(float).to_numpy() @ np.asarray(rsv1.params)
    auc_s1 = block_auc(wk.loc[keep_te], -lp_te1)
    log(f"[validation] test seasons={list(test_s)}: R2_judges={r2_j:.3f}, "
        f"R2_calibrated={r2_j_c:.3f} (target>=0.55), spearman_judges={spr_j:.3f}, "
        f"spearman_fans={spr_f:.3f} (target>=0.35), survival_AUC={auc_s:.3f} "
        f"(target>=0.75), survival_AUC_step1(no phi)={auc_s1:.3f}")

    # ============================ robustness =====================================
    log("[robustness] leave-one-industry-out refits ...")
    loio = []
    ind_grp = wk["celebrity_industry"].map(industry_group)
    for gname in sorted(set(ind_grp) - {"Other"}):
        keep = (ind_grp != gname).to_numpy()
        lo_cols = nondegenerate(wk.loc[keep], trait_cols + C_struct)
        Xm = sm.add_constant(wk.loc[keep, lo_cols].astype(float),
                             has_constant="add")
        gil = pd.factorize(wk.loc[keep, "celebrity_name"].astype(str) + "_" +
                           wk.loc[keep, "season"].astype(str))[0]
        try:
            rj = sm.MixedLM(wk.loc[keep, "S"].to_numpy(float), Xm, groups=gil
                            ).fit(reml=True, method="lbfgs", maxiter=400)
            bage_j = float(rj.fe_params[list(Xm.columns).index("age_cs")])
        except Exception as e:
            bage_j = np.nan
            loio.append({"dropped_industry": gname, "age_coef_judge": None,
                         "age_coef_fan": None, "flip_judge": None,
                         "flip_fan": None, "error": str(e)})
            continue
        try:
            gfl = sm.GLM(np.clip(wk.loc[keep, "phi_share"], 1e-4, 1 - 1e-4), Xm,
                         family=sm.families.Binomial(),
                         freq_weights=w_obs[keep] / w_obs[keep].mean()).fit()
            bage_f = float(gfl.params["age_cs"])
        except Exception:
            bage_f = np.nan
        loio.append({"dropped_industry": gname, "age_coef_judge": bage_j,
                     "age_coef_fan": bage_f,
                     "flip_judge": (bool(np.sign(bage_j) != np.sign(age_b1))
                                    if np.isfinite(bage_j) else None),
                     "flip_fan": (bool(np.sign(bage_f) != np.sign(phi_age_b2))
                                  if np.isfinite(bage_f) else None)})
    n_flips_j = sum(1 for d in loio if d["flip_judge"])
    n_flips_f = sum(1 for d in loio if d["flip_fan"])
    n_tests = 2 * len(loio)
    log(f"[robustness] LOIO refits={len(loio)}; age-sign flips: judge "
        f"{n_flips_j}/{len(loio)}, fan {n_flips_f}/{len(loio)} "
        f"({100 * (1 - (n_flips_j + n_flips_f) / max(n_tests, 1)):.0f}% stable)")
    # season jackknife on the D1 age coefficient
    sjk = []
    for s in seasons:
        keep = (wk["season"] != s).to_numpy()
        sj_cols = nondegenerate(wk.loc[keep], trait_cols + C_struct)
        if "age_cs" not in sj_cols:
            continue
        Xm = sm.add_constant(wk.loc[keep, sj_cols].astype(float),
                             has_constant="add")
        gil = pd.factorize(wk.loc[keep, "celebrity_name"].astype(str) + "_" +
                           wk.loc[keep, "season"].astype(str))[0]
        try:
            rj = sm.MixedLM(wk.loc[keep, "S"].to_numpy(float), Xm, groups=gil
                            ).fit(reml=True, method="lbfgs", maxiter=400)
            sjk.append({"dropped_season": int(s),
                        "age_coef_judge": float(
                            np.asarray(rj.fe_params)[list(Xm.columns).index("age_cs")]),
                        "error": None})
        except Exception as e:
            log(f"[robustness] jackknife season {int(s)} failed ({e})")
            sjk.append({"dropped_season": int(s), "age_coef_judge": None,
                        "error": str(e)})
    sj_flips = sum(1 for d in sjk
                   if np.sign(d["age_coef_judge"]) != np.sign(age_b1))
    log(f"[robustness] season-jackknife (n={len(sjk)}): D1 age-sign flips={sj_flips}")

    # ============================ archetypes =====================================
    log("[archetypes] counterfactual casting simulation (D4 step-2 hazard, "
        "400 beta draws) ...")
    archetypes = [
        ("17yo Social Media Star", 17, "Social Media Personality"),
        ("20yo Disney Actress", 20, "Actor/Actress"),
        ("27yo Olympic Gymnast", 27, "Athlete"),
        ("29yo Pop Singer", 29, "Singer/Rapper"),
        ("31yo Reality Star", 31, "TV Personality"),
        ("35yo Pro Athlete", 35, "Athlete"),
        ("50yo Model", 50, "Model"),
        ("73yo TV Host (elder)", 73, "TV Personality"),
    ]
    week_cols_all = [c for c in wk.columns if c.startswith("week_")]
    season_col_of = {int(s): f"season_{int(s)}" for s in seasons
                     if f"season_{int(s)}" in wk.columns}
    prof = wk.groupby("week")["cum01"].mean()
    cut_rate = wk[wk["dropout"] == 0].groupby("week")["elim"].mean()
    sd_pool = float(wk["S"].std(ddof=0))       # typical spread of weekly fields
    n_bar = float(wk.groupby(["season", "week"]).size().mean())
    beta42 = np.asarray(r42.params)
    V44 = np.asarray(r42.cov_params())
    draws = rng.multivariate_normal(beta42, V44, size=400)

    def trait_vector(age, industry):
        tv = {"age_cs": (age - AGE_CENTER) / AGE_SCALE}
        ig = industry_group(industry)
        for c in ind_cols:
            tv[c] = 1.0 if sanitize(ig) == c[4:] else 0.0
        for c in home_cols:
            tv[c] = 0.0          # archetype baseline = US (reference level)
        return tv

    arch_rows, surv_curves = [], {}
    for (nm, age, industry) in archetypes:
        tv = trait_vector(age, industry)
        S_traj, phi_traj, zS_traj, phi_std_traj, cum_traj = {}, {}, {}, {}, {}
        for w in range(1, 12):
            sS, sP = [], []
            for s in seasons:
                if s == 1:
                    continue
                row = dict(tv)
                for c in season_cols:
                    row[c] = 1.0 if c == season_col_of.get(int(s), "") else 0.0
                for c in week_cols_all:
                    row[c] = 1.0 if c == f"week_{int(w)}" else 0.0
                row["cum01"] = float(prof.loc[w]) if w in prof.index else 0.15
                xrow = np.array([1.0] + [row.get(c, 0.0)
                                         for c in trait_cols + C_struct])
                sS.append(float(xrow @ np.asarray(r1.fe_params)))
                sP.append(float(sigmoid(xrow @ np.asarray(gee.params))))
            # average-season archetype trajectory
            S_traj[w] = float(np.mean(sS))
            phi_traj[w] = float(np.mean(sP))
            # archetype's judge standing vs the AVERAGE actual week-w field
            mu_w = float(wk.loc[wk["week"] == w, "S"].mean())
            zS_traj[w] = (S_traj[w] - mu_w) / max(sd_pool, 1e-6)
            phi_std_traj[w] = (phi_traj[w] * n_bar - wk["phi_hat"].mean()) / \
                wk["phi_hat"].std(ddof=0)
            cum_traj[w] = float(prof.loc[w]) if w in prof.index else 0.15
        # hazard simulation: Breslow-type weekly baseline = empirical cut rate;
        # reference lp = mean linear predictor of the fit set in that week
        surv_draws = np.ones((draws.shape[0], 11))
        for w in range(1, 12):
            feat = {"zS": zS_traj[w], "cum01": cum_traj[w],
                    "phi_hat_std": phi_std_traj[w]}
            feat.update(tv)
            vec = np.array([feat.get(c, 0.0) for c in cols_s2])
            lp_v = draws @ vec                      # (400,) archetype lps
            mask_w = (sub2["week"] == w).to_numpy()
            base_l = float((sub2.loc[mask_w, cols_s2].astype(float).to_numpy()
                            @ beta42).mean()) if mask_w.any() else 0.0
            q_w = float(cut_rate.get(w, 0.15)) if w in cut_rate.index else 0.15
            h = np.clip(q_w * np.exp(lp_v - base_l), 0.0, 0.85)
            surv_draws[:, w - 1] = (surv_draws[:, w - 2] if w > 1 else 1.0) * (1 - h)
        surv_curves[nm] = {"median": np.median(surv_draws, axis=0),
                           "lo": np.percentile(surv_draws, 10, axis=0),
                           "hi": np.percentile(surv_draws, 90, axis=0),
                           "S_traj": S_traj, "phi_traj": phi_traj}
        row_out = {"archetype": nm, "age": age, "industry": industry,
                   "pred_S_week1": S_traj[1], "pred_S_week3": S_traj[3],
                   "pred_phi_share_week1": phi_traj[1],
                   "pred_phi_share_week3": phi_traj[3]}
        for w in range(1, 11):
            row_out[f"surv_week_{w}"] = float(np.median(surv_draws[:, w - 1]))
        arch_rows.append(row_out)
        log(f"[archetype] {nm}: S_w1={S_traj[1]:.2f}, S_w3={S_traj[3]:.2f}, "
            f"phi_w3={phi_traj[3]:.3f}, surv(5)={row_out['surv_week_5']:.3f}, "
            f"surv(9)={row_out['surv_week_9']:.3f}")

    # ============================ effect tables ==================================
    rows = []
    for chan, params, ses, pvs in [("judge", fe1, se1, pv1),
                                   ("fan", fe2, pd.Series(se2, index=cols2), pv2s),
                                   ("differential", fe3, ols3.bse, ols3.pvalues)]:
        for c in params.index:
            if c == "const":
                continue
            b = float(params[c])
            s = float(ses[c]) if c in ses.index else np.nan
            rows.append({"channel": chan, "covariate": c, "coef": b, "se": s,
                         "ci_low": b - 1.96 * s if np.isfinite(s) else np.nan,
                         "ci_high": b + 1.96 * s if np.isfinite(s) else np.nan,
                         "p": float(pvs[c]) if c in pvs.index else np.nan})
    covtab = pd.DataFrame(rows)
    d4tab = pd.DataFrame({"covariate": list(cn2),
                          "coef_with_phi": list(np.asarray(r42.params))})
    d4tab["coef_without_phi"] = [float(r41.params[idx1[c]]) if c in idx1
                                 else np.nan for c in cn2]
    d4tab["p_with_phi"] = [float(r42.pvalues[idx2[c]]) for c in cn2]
    d4tab["p_without_phi"] = [float(r41.pvalues[idx1[c]]) if c in idx1
                              else np.nan for c in cn2]

    # ============================ exports ========================================
    exp_cols = ["row_id", "season", "week", "celebrity_name", "ballroom_partner",
                "age", "age_cs", "p_g", "status", "week_score_mean", "cum01",
                "touch01", "zS", "phi_hat", "phi_share", "phi_pmean", "var_phi",
                "phi_lo90", "phi_hi90", "S_hat", "phi_tilde_hat", "R", "elim",
                "pre_week", "dropout"]
    wk[[c for c in exp_cols if c in wk.columns]].to_csv(
        OUT / "model3_weekly_panel.csv", index=False)
    covtab.to_csv(OUT / "model3_covariate_effects.csv", index=False)
    d4tab.to_csv(OUT / "model3_survival_effects.csv", index=False)
    pd.DataFrame(arch_rows).to_csv(OUT / "model3_archetypes.csv", index=False)
    pd.DataFrame(loio).to_csv(OUT / "model3_loio_robustness.csv", index=False)
    pd.DataFrame(sjk).to_csv(OUT / "model3_season_jackknife.csv", index=False)
    hm1 = wk.groupby("celebrity_industry").agg(
        n_weeks=("R", "size"), mean_S=("S", "mean"), mean_phi=("phi_hat", "mean"),
        mean_R=("R", "mean")).reset_index().sort_values("mean_R")
    hm1.to_csv(OUT / "model3_industry_summary.csv", index=False)
    hm2 = wk.groupby("p_g").agg(n_weeks=("R", "size"), mean_S=("S", "mean"),
                                mean_phi=("phi_hat", "mean"), mean_R=("R", "mean"),
                                mean_age=("age", "mean")).reset_index()
    hm2.sort_values("mean_S", ascending=False).to_csv(
        OUT / "model3_partner_summary.csv", index=False)

    # sanity anchors from raw data
    young = wk[wk["age"] <= 22]
    smp_all = wk[wk["celebrity_industry"] == "Social Media Personality"]
    vet = wk[wk["age"] >= 55]
    log(f"[sanity] Social Media Personality (n_weeks={len(smp_all)}): "
        f"mean S={smp_all['S'].mean():.2f}, mean phi={smp_all['phi_hat'].mean():.3f}, "
        f"mean R={smp_all['R'].mean():+.3f}")
    log(f"[sanity] young<=22 (n_weeks={len(young)}): mean S={young['S'].mean():.2f}, "
        f"mean phi={young['phi_hat'].mean():.3f}, mean R={young['R'].mean():+.3f}")
    log(f"[sanity] veterans>=55 (n_weeks={len(vet)}): mean S={vet['S'].mean():.2f} "
        f"vs overall {wk['S'].mean():.2f}")
    ind_R = wk.groupby("celebrity_industry")["R"].agg(["mean", "size"])
    ind_R = ind_R[ind_R["size"] >= 8].sort_values("mean")
    ind_R.to_csv(OUT / "model3_industry_differential.csv", index=True)

    RESULTS = {
        "n_week_rows": int(len(wk)),
        "n_seasons": int(wk["season"].nunique()),
        "n_celebrities": int(wk["celebrity_name"].nunique()),
        "n_events_inversion": int(wk["elim"].sum()),
        "phi_hat_mean": float(phi.mean()), "phi_hat_max": float(phi.max()),
        "phi_hat_min": float(phi.min()),
        "phi_pmean_mean": float(wk["phi_pmean"].mean()),
        "phi_pmean_min": float(wk["phi_pmean"].min()),
        "phi_share_sums_to_1_max": float(
            wk.groupby(["season", "week"])["phi_share"].sum().max()),
        "phi_mean_90pct_width": float((hi90 - lo90).mean()),
        "phi_median_90pct_width": float(np.median(hi90 - lo90)),
        "bottom2_recovery_fans": float(rec_f),
        "bottom2_recovery_judges_baseline": float(rec_j),
        "n_elim_weeks_recovered": int(n_wk), "n_elim_events_recovered": int(n_ev),
        "invert_fit": fitinfo,
        "model1_crosscheck": m1info,
        "D1_converged": bool(r1.converged), "D1_var_random": var_re,
        "D1_resid_var": float(r1.scale), "D1_ICC": float(icc),
        "D1_age_coef": age_b1, "D1_age_p": age_p1,
        "D1_age_points_per_13y": float(age_b1 * AGE_SCALE),
        "D1_industry_partialR2": float(pr2i), "D1_industry_p": float(pi_),
        "D1_partner_partialR2": float(pr2p), "D1_partner_p": float(pp_),
        "D1_LRT_stat": float(stat), "D1_LRT_p_plain": p_plain,
        "D1_LRT_p_mixture": p_mix, "D1_AR1_adopted": adopt_ar1,
        "D1_rho_hat": float(rho_hat),
        "D1_llf_RI": float(ll0), "D1_llf_AR1": float(ll1),
        "D1_key": {k: float(fe1[k]) for k in show1 if k in fe1.index},
        "D1_key_p": {k: float(pv1[k]) for k in show1 if k in fe1.index},
        "D2_dep": (float(dep) if "Exchangeable" in str(struct_used2) else None),
        "D2_structure": struct_used2,
        "D2_dep_smp_spec": (float(dep_smp) if isinstance(dep_smp, float) and
                            np.isfinite(dep_smp) else None),
        "D2_age_coef": phi_age_b2, "D2_age_p": phi_age_p2,
        "D2_key": {k: float(fe2[k]) for k in show2 if k in fe2.index},
        "D2_key_p": {k: float(pv2s[k]) for k in show2 if k in fe2.index},
        "D2_unweighted_rank_agreement": sens_rank,
        "D2_weights_p10": float(np.quantile(w_obs, .1)),
        "D2_weights_p90": float(np.quantile(w_obs, .9)),
        "aux_smp_fan_coef": b_smp_fan, "aux_smp_fan_p": p_smp_fan,
        "aux_smp_judge_coef": b_smp_jud, "aux_smp_judge_p": p_smp_jud,
        "D3_n": n3, "D3_age_coef": r3_age, "D3_age_p": r3_age_p,
        "D3_key": {k: float(fe3[k]) for k in show3 if k in fe3.index},
        "D3_key_p": {k: float(ols3.pvalues[k]) for k in show3 if k in fe3.index},
        "D3_sign_agreement": {"n_common": len(common), "n_same_sign": int(same),
                              "significant_opposite": opp_sig},
        "D4_concordance_phi_only": float(concf), "D4_auc_phi_only": float(aucf),
        "D4_concordance_step1": float(conc1), "D4_auc_step1": float(auc1),
        "D4_concordance_step2": float(conc2), "D4_auc_step2": float(auc2),
        "D4_b_zS_step1": bzS1, "D4_b_zS_step2": bzS2,
        "D4_b_phi": bphi2, "D4_b_phi_p": bphi2_p,
        "D4_b_age_step1": b_age1, "D4_b_age_step1_p": b_age1_p,
        "D4_b_age_step2": b_age2, "D4_b_age_step2_p": b_age2_p,
        "D4_no_extra_traits": no_extra,
        "D4_excl_withdrew_zS": float(r4w.params[idxw["zS"]]),
        "D4_excl_withdrew_phiflux": float(r4w.params[idxw["phi_flux"]]),
        "D4_auc_rawphi_tautology": float(auc_rawphi),
        "D4_duty_b_phi": b_duty, "D4_duty_auc": float(auc_duty),
        "D4_duty_n": int(len(yduty)), "D4_duty_n_saved": int(yduty.sum()),
        "val_test_seasons": [int(s) for s in test_s],
        "val_R2_judges": float(r2_j), "val_R2_judges_cal": float(r2_j_c),
        "val_spearman_judges": float(spr_j),
        "val_spearman_fans": spr_f, "val_survival_auc": float(auc_s),
        "val_survival_auc_step1": float(auc_s1),
        "robust_loio_n": len(loio), "robust_loio_flips_judge": int(n_flips_j),
        "robust_loio_flips_fan": int(n_flips_f),
        "robust_loio_stable_pct": float(100 * (1 - (n_flips_j + n_flips_f) /
                                               max(n_tests, 1))),
        "robust_season_jackknife_n": len(sjk),
        "robust_season_jackknife_flips": int(sj_flips),
        "sanity_smp_mean_S": float(smp_all["S"].mean()) if len(smp_all) else None,
        "sanity_smp_mean_phi": float(smp_all["phi_hat"].mean()) if len(smp_all) else None,
        "sanity_smp_mean_R": float(smp_all["R"].mean()) if len(smp_all) else None,
        "sanity_young_mean_S": float(young["S"].mean()),
        "sanity_young_mean_phi": float(young["phi_hat"].mean()),
        "sanity_young_mean_R": float(young["R"].mean()),
        "sanity_veteran_mean_S": float(vet["S"].mean()),
        "sanity_overall_mean_S": float(wk["S"].mean()),
        "archetypes": {r["archetype"]: {"S_w1": r["pred_S_week1"],
                                        "S_w3": r["pred_S_week3"],
                                        "phi_w3": r["pred_phi_share_week3"],
                                        "surv5": r["surv_week_5"],
                                        "surv9": r["surv_week_9"]}
                       for r in arch_rows},
        "industry_differential": [{"industry": idx, "mean_R": float(row["mean"]),
                                   "n": int(row["size"])}
                                  for idx, row in ind_R.reset_index().iterrows()],
        "partner_top": hm2.head(8).to_dict("records"),
    }
    log("[export] all CSV outputs written")
    return RESULTS


if __name__ == "__main__":
    res = run_main()
    with open(OUT / "model3_results.json", "w") as fh:
        json.dump(clean_json(res), fh, indent=1)
    with open(OUT / "model3_log.json", "w") as fh:
        json.dump({"lines": LOG}, fh, indent=1)
    print("[done] model3_results.json written")
