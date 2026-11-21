"""m2_fanshare.py -- fan-share identification stage ("Model-1-lite") for Model 2.

Model 2's plan consumes Model 1's posterior fan shares.  Model 1's outputs were not yet
available to this phase (parallel implementation), so this module reproduces the required
surface with a compact, deterministic version of the same identification logic:

Point identification (MAP, exact analytic gradients, L-BFGS-B):
    phi(c,w)   = softmax over the competing set of week w of
                 U(c,w) = C_run(c) + beta*judge_z(c,w) + theta*week(c,w)
    comb(c,w)  = 0.5*judge_share(c,w) + 0.5*phi(c,w)   (show's percentage method)
    P(E_w)     = Plackett-Luce set probability that the observed exit set E_w is the
                 bottom-|E_w| of comb under weights w_c = 1/comb_c (exact for |E|<=3).
Weak priors: C_run ~ N(0, 1.0^2), beta ~ N(1.5, 1^2), theta ~ N(0, 0.15^2).

Posterior (draw stage): personas ~ N(C_MAP, sd_person) with sd_person shrinking in the
number of ordinal facts touching the run (Laplace-style diagonal approximation);
500 within-week idiosyncrasy shake blocks x 1000 copula draws; running-fame feedback;
rank-constraint weights exp(-issue_score) per shake; weighted posterior mean/sd (and
weighted quantile bands) of phi per conctestant-week.  Weeks without elimination
information (week 1, finale, withdrawal contexts) inherit their run's persona and carry
congruently wider bands (see `band`, `certainty` columns).
"""
from __future__ import annotations

from itertools import permutations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

# ---- tunables (echoed into results.json)
PRIOR_C_SD = 1.00       # persona prior sd (log-odds scale => weak)
PRIOR_BETA_MU, PRIOR_BETA_SD = 1.5, 1.0
PRIOR_THETA_SD = 0.15
FINALE_W = 0.5          # soft weight on finale placement orderings
SHAKE_SD = 0.18         # idiosyncrasy shake sd (log-nu)
SHAKE_SLOPE = -0.06     # idiosyncrasy drift per 10 weeks of week index
CSIG_W = 1.00           # shake-weight temperature for the rank-constraint weights
CSIG_C = 1.20           # persona copula (posterior) sd cap
N_SHAKE = 500
N_COP = 1000
SEED_DRAWS = 2026
LOG_EPS = 1e-9
MARGIN_GOOD = 0.10      # tolerated share-gap violation before a margin issue
PENX_THR = 0.55         # judge-z threshold for "exit was not judge-distressed"
PENX_W = 0.15           # penalty weight for a non-judge-distressed exit


# ------------------------------------------------------------------ constraints
def build_constraints(pan, wt, exit_sets, ctx, ct):
    """E-type (vote-based exit sets) + F-type (finale placement orderings)."""
    cons = []
    for key in sorted(wt.keys()):
        s, w = key
        rows = wt[key]["rows"]
        runids = wt[key]["runids"]
        exids = exit_sets.get(key, set())
        if exids and key not in ctx:
            epos = [runids.index(r) for r in exids]
            cons.append(dict(kind="E", key=key, rows=rows, runids=runids,
                             epos=epos, weight=1.0))
    # finale ordering constraints: finalists' placement order at the finale week
    fin = ct[ct.result_type == "finalist"]
    for s, g in fin.groupby("season"):
        week = int(g["finale_week"].iloc[0])
        key = (int(s), week)
        if key not in wt:
            continue
        runids = wt[key]["runids"]
        pos_of = {r: i for i, r in enumerate(runids)}
        order = sorted(g["run_id"].astype(int).tolist(),
                       key=lambda r: -int(ct.loc[ct.run_id == r, "placement"].iloc[0]))
        if not all(r in pos_of for r in order):
            continue          # folded finalists not dancing at finale (defensive)
        cons.append(dict(kind="F", key=key, rows=wt[key]["rows"], runids=runids,
                         epos=[pos_of[r] for r in order], weight=FINALE_W))
    return cons


# ------------------------------------------------------------------ MAP stage
def map_optimize(pan, wt, exit_sets, ctx, ct, maxiter=400):
    """Joint MAP over (C per run, beta, theta).  Returns dict with C (per run),
    beta, theta, diagnostics."""
    judge_z = pan["judge_z"].to_numpy(float)
    week_arr = pan["week"].to_numpy(float)
    pos = pan["run_id"].to_numpy(int)
    nrow, n_runs = len(pan), int(pos.max()) + 1
    cons = build_constraints(pan, wt, exit_sets, ctx, ct)

    # static per-constraint structures
    C_ = []
    for c in cons:
        rows = c["rows"]
        C_.append(dict(kind=c["kind"], weight=c["weight"], n=len(c["runids"]),
                       jz=judge_z[rows], wk=week_arr[rows],
                       cpos=np.array(c["epos"], int),
                       jr=c["runids"]))
    run_mean_z = pd.Series(judge_z).groupby(pos).mean()

    def unpack(p):
        Cvec = p[:n_runs]
        beta, theta = p[n_runs], p[n_runs + 1]
        return Cvec, beta, theta

    def negll(p):
        Cvec, beta, theta = unpack(p)
        nll, gC, gb, gt = 0.0, np.zeros(n_runs), 0.0, 0.0
        for st in C_:
            U = Cvec[st["jr"]] + beta * st["jz"] + theta * st["wk"]
            U = U - U.max()
            e = np.exp(U)
            phi = e / e.sum()
            # combined scores and inverse weights
            x_share = st["_xshare"]
            cvec = 0.5 * (x_share + phi)
            w = 1.0 / cvec
            epos = st["cpos"]
            m = len(epos)
            # exact PL set probability gradient (sum over exit orderings for m<=3)
            # list() materialization is REQUIRED: permutations is a one-shot generator
            orders = list(permutations(range(m))) if m > 1 else [range(m)]
            gphi = np.zeros(st["n"])
            pl_list = []
            for od in orders:
                selp = [epos[k] for k in od]
                remaining = np.ones(st["n"], bool)
                ll_terms = []
                ok = True
                for idx in selp:
                    S = w[remaining].sum()
                    if S <= 0 or not np.isfinite(S):
                        ok = False
                        break
                    ll_terms.append(np.log(max(w[idx], LOG_EPS)) - np.log(S))
                    remaining[idx] = False
                if not ok:
                    continue
                pl_list.append(np.exp(sum(ll_terms)))
            if not pl_list:
                continue
            ptot = sum(pl_list)
            for od in orders:
                selp = [epos[k] for k in od]
                remaining = np.ones(st["n"], bool)
                ll_terms = []
                for idx in selp:
                    S = w[remaining].sum()
                    ll_terms.append(np.log(max(w[idx], LOG_EPS)) - np.log(S))
                    remaining[idx] = False
                p_o = np.exp(sum(ll_terms))
                if ptot <= 0:
                    continue
                pw = p_o / ptot
                # gradients of THIS order's log-likelihood wrt w
                remaining = np.ones(st["n"], bool)
                gw = np.zeros(st["n"])
                for idx in selp:
                    S = w[remaining].sum()
                    gw[idx] += 1.0 / max(w[idx], LOG_EPS)
                    gw[remaining] -= 1.0 / S
                    remaining[idx] = False
                gphi += pw * (-(w ** 2) / 2.0) * gw      # chain w -> phi
            # chain phi -> U (softmax Jacobian): dU_j = phi_j*(h_j - sum h phi)
            # NOTE: gphi = d(logP)/dphi but the objective is -log P  => negate here.
            gU = -phi * (gphi - float(np.dot(gphi, phi)))
            nll -= st["weight"] * np.log(max(ptot, LOG_EPS))
            gC_run = np.bincount(st["jr"], weights=st["weight"] * gU, minlength=n_runs)
            gC += gC_run
            gb += st["weight"] * float(np.dot(gU, st["jz"]))
            gt += st["weight"] * float(np.dot(gU, st["wk"]))
        # priors
        nll += 0.5 * np.sum(Cvec ** 2) / PRIOR_C_SD ** 2
        gC += Cvec / PRIOR_C_SD ** 2
        nll += 0.5 * (beta - PRIOR_BETA_MU) ** 2 / PRIOR_BETA_SD ** 2
        gb += (beta - PRIOR_BETA_MU) / PRIOR_BETA_SD ** 2
        nll += 0.5 * theta ** 2 / PRIOR_THETA_SD ** 2
        gt += theta / PRIOR_THETA_SD ** 2
        g = np.concatenate([gC, [gb, gt]])
        return nll, g

    # precompute judge shares per constraint set
    for st, c in zip(C_, cons):
        x = wt[c["key"]]["isd"]
        st["_xshare"] = x / x.sum()

    p0 = np.concatenate([0.30 * run_mean_z.reindex(range(n_runs)).fillna(0.0).to_numpy(),
                         [1.5, 0.0]])
    res = minimize(negll, p0, jac=True, method="L-BFGS-B",
                   options=dict(maxiter=maxiter, maxls=40))
    Cmap, beta, theta = unpack(res.x)
    return dict(C=np.asarray(Cmap), beta=float(beta), theta=float(theta),
                ok=bool(res.success), nit=int(res.nit), nll=float(res.fun),
                n_cons=len(cons), n_runs=n_runs)


def finalize_personas(ct, mres, pan):
    """Final persona levels: MAP; withdrawals blended with the dance-quality warm start."""
    C = mres["C"].copy()
    pos = pan["run_id"].to_numpy(int)
    run_mean_z = pd.Series(pan["judge_z"].to_numpy(float)).groupby(pos).mean()
    wd = ct.loc[ct.result_type == "withdrew", "run_id"].astype(int).to_numpy()
    for r in wd:
        C[r] = 0.30 * float(run_mean_z.get(r, 0.0))
    return C


# ------------------------------------------------------------------ draw stage
def compute_fanshare(pan, wt, exit_sets, ctx, ct, mres, n_shake=500, n_cop=1000,
                     seed=SEED_DRAWS):
    """Weighted shake-copula posterior => deterministic fan-share surface.

    Populates pan columns: fanshare, fanshare_sd, fanshare_lo95, fanshare_hi95,
    judge_share.  Returns (pan, stats dict).
    """
    beta0, theta0 = mres["beta"], mres["theta"]
    Cfin = finalize_personas(ct, mres, pan)
    judge_z = pan["judge_z"].to_numpy(float)
    week_idx = pan["week_idx"].to_numpy(float)
    week_arr = pan["week"].to_numpy(float)
    pos = pan["run_id"].to_numpy(int)
    nrow = len(pan)
    n_runs = mres["n_runs"]
    weeks_sorted = sorted(wt.keys())

    # per-run ordinal-info count for Laplace-style persona shrinkage
    n_pl = np.zeros(n_runs)
    cons = build_constraints(pan, wt, exit_sets, ctx, ct)
    for c in cons:
        epos = c["epos"]
        jr = c["runids"]
        for idx in epos:
            n_pl[jr[idx]] += 1.0
        # survivors of elimination constraints carry a soft "not bottom-m" fact
        if c["kind"] == "E":
            eset = set(epos)
            for i, r in enumerate(jr):
                if i not in eset:
                    n_pl[r] += 0.5
    sd_person = CSIG_C / np.sqrt(1.0 + n_pl)

    rng = np.random.default_rng(seed)
    JIT = rng.normal(0.0, 0.03, size=(nrow, n_cop)).astype(np.float32)
    base_U = Cfin[pos] + beta0 * judge_z + theta0 * week_arr       # (nrow,)
    phi_shake = np.zeros((n_shake, nrow), dtype=np.float32)
    issue_scores = np.zeros(n_shake, dtype=np.float64)

    for sh in range(n_shake):
        nu = rng.normal(0.0, SHAKE_SD, nrow) + SHAKE_SLOPE * week_idx / 10.0
        Cd = rng.normal(0.0, 1.0, n_runs) * sd_person    # persona copula draw (static)
        U = base_U + nu + Cd[pos]
        feedback = np.zeros(nrow)
        for key in weeks_sorted:
            rows = wt[key]["rows"]
            Uw = U[rows] + feedback[rows]
            M = Uw[:, None] + JIT[rows]                  # (n, n_cop)
            M -= M.max(axis=0, keepdims=True)
            eM = np.exp(M)
            Pw = eM / eM.sum(axis=0, keepdims=True)
            pm = Pw.mean(axis=1)
            phi_shake[sh, rows] += pm.astype(np.float32)
            feedback[rows] = pm                          # running fame for next week
            # issue score (rank-constraint weight) for this shake
            exids = exit_sets.get(key, set())
            if exids and key not in ctx:
                x = wt[key]["isd"]
                x_share = x / x.sum()
                jmax = int(np.argmax(x))
                runids = wt[key]["runids"]
                for rid in exids:
                    i = runids.index(rid)
                    gap = float(pm[i]) - float(x_share[jmax])
                    if gap > MARGIN_GOOD:
                        issue_scores[sh] += (gap - MARGIN_GOOD)
                    if judge_z[rows[i]] >= -PENX_THR:
                        issue_scores[sh] += PENX_W

    # rank-constraint weights over shakes (perplexity = exp(entropy of normalized wts))
    w_raw = np.exp(-CSIG_W * issue_scores)
    wts = w_raw / w_raw.sum()
    ent = -float(np.sum(wts * np.log(np.maximum(wts, LOG_EPS))))
    perplexity = float(np.exp(ent))
    phi64 = phi_shake.astype(np.float64)
    Phi_bar = (wts[:, None] * phi64).sum(axis=0)
    Phi_sq = (wts[:, None] * phi64 ** 2).sum(axis=0)
    sd = np.sqrt(np.maximum(Phi_sq - Phi_bar ** 2, 0.0))

    # weighted 2.5/97.5 percentiles per row (posterior band)
    order = np.argsort(phi_shake, axis=0).astype(np.int64)      # (n_shake, nrow)
    w_sorted = wts[order]                                       # weights aligned to
    # each column's sorted draws; cumulate ALONG the sorted axis per column
    cum = np.cumsum(w_sorted, axis=0) - 0.5 * w_sorted          # midpoint CDF at sorted
    lo_idx = np.argmin(np.abs(cum - 0.025), axis=0)
    hi_idx = np.argmin(np.abs(cum - 0.975), axis=0)
    sorted_phi = np.take_along_axis(phi_shake, order, axis=0)
    lo95 = np.take_along_axis(sorted_phi, lo_idx[None, :], axis=0)[0].astype(np.float64)
    hi95 = np.take_along_axis(sorted_phi, hi_idx[None, :], axis=0)[0].astype(np.float64)

    pan["fanshare"] = Phi_bar
    pan["fanshare_sd"] = sd
    pan["fanshare_lo95"] = lo95
    pan["fanshare_hi95"] = hi95
    grp = pan.groupby(["season", "week"])["weekly_total"]
    pan["judge_share"] = pan["weekly_total"] / grp.transform("sum")

    stats = dict(issue_score_mean=float(issue_scores.mean()),
                 issue_score_max=float(issue_scores.max()),
                 shake_weight_perplexity=perplexity,
                 n_shakes=int(n_shake), n_cop=int(n_cop),
                 zero_share_rows=int((Phi_bar <= 1e-12).sum()),
                 persona_sd_mean=float(sd_person.mean()))
    return pan, stats
