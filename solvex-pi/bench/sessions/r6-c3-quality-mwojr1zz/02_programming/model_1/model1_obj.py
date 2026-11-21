"""Model 1 stage-A objective: ordinal elimination likelihood + priors + MAP.

Identified combination per contestant-week cell i:
    utl_i = xi*xbar_i + v_i + g1_r + ka_r*dmem_i + eps_s + 0.5*logx_i
  = log(percentage-method Combined) + within-week constant.
Elimination risk order = ascending utl (invariant to within-week shifts, so the
season fan climate eps_s and the softmax level stay prior-driven).

Exit-week likelihood, eta = ETA0*m per week (nll_w = -eta*log t_w):
  exact weeks (S<=27 singles + ALL multi-exit weeks): exits = combined bottom-m
      t = sum over m! orderings of Plackett-Luce path probabilities
  veto weeks (S>=28 single exit; that couple is only known to be in the bottom-2):
      t = P(exit drawn 1st) + sum_{j != exit} P(j drawn 1st) * P(exit drawn 2nd)
Generic path-enumeration gives t and d t/d us exactly (paths <= 15 per week).
Finale anchors: utl_worse - utl_better >= PAIR_MU softly, N(PAIR_MU, PAIR_SD^2).
"""
from __future__ import annotations
import itertools
import numpy as np
from scipy.optimize import minimize
from model1_core import Model, ETA0, PAIR_MU, PAIR_SD, TAU_G, TAU_K, SIG_U, \
    TAU_SEAS, SIG_XI

LOG_MIN = 1e-300
P_MIN = 1e-250


def unpack(M: Model, theta: np.ndarray):
    v = theta[M.o_v:M.o_g1]
    g1 = theta[M.o_g1:M.o_ka]
    ka = theta[M.o_ka:M.o_eps]
    eps = theta[M.o_eps:M.o_xi]
    xi = theta[M.o_xi]
    return v, g1, ka, eps, xi


def utl_vals(M: Model, theta: np.ndarray) -> np.ndarray:
    v, g1, ka, eps, xi = unpack(M, theta)
    return (xi * M.xbar + v + g1[M.run_of_flat] + ka[M.run_of_flat] * M.dmem
            + eps[M.season_of_flat] + 0.5 * M.logx)


def week_paths(n: int, mask: np.ndarray, veto: bool):
    """Enumerate selection paths for one exit week.
    Returns list of lists of step indices (couples drawn 1st, 2nd, ...)."""
    ex = [int(i) for i in np.where(mask)[0]]
    if len(ex) == 1:
        a = ex[0]
        if veto:
            return [[a]] + [[j, a] for j in range(n) if j != a]
        return [[a]]
    return [list(pp) for pp in itertools.permutations(ex)]


def pl_paths_grad(us: np.ndarray, paths) -> tuple:
    """t = sum of path probabilities over PL selections; also d t / d us.
    At-risk PL weights:  p_e = exp(-(us_e - min(us)))  -- LOW utl = HIGH risk.
    Path prob = prod_steps w(e|A),  w(e|A) = p_e / sum_{A} p."""
    n = len(us)
    p = np.exp(us.min() - us)
    t = 0.0
    g_p = np.zeros(n)
    for path in paths:
        avail = np.ones(n, bool)
        P = 1.0
        steps = []
        ok = True
        for e in path:
            S_A = p[avail].sum()
            if S_A <= 0:
                ok = False
                break
            w = p[e] / S_A
            P *= w
            steps.append((e, S_A, w, avail.copy()))
            avail[e] = False
            if P < P_MIN:
                ok = False
                break
        if not ok:
            continue
        t += P
        # dP/dp_k = P * sum_steps [ delta_{k,e}/p_e - 1{k in A_s}/S_A ]
        for (e, S_A, w, am) in steps:
            idx = np.where(am)[0]
            g_p[idx] -= P / S_A
            g_p[e] += P / p[e]
    g = -g_p * p                    # dp/dus = -p for at-risk weights exp(min-us)
    return t, g


def neg_log_post(M: Model, theta: np.ndarray, drop_week=None, return_parts=False):
    """Negative log posterior and analytic gradient (full batch)."""
    v, g1, ka, eps, xi = unpack(M, theta)
    u = utl_vals(M, theta)
    nll = 0.0
    dU = np.zeros(M.V)
    W = len(M.ex_cells)
    for w in range(W):
        if drop_week is not None and w == drop_week:
            continue
        cells = M.ex_cells[w]
        us = u[cells]
        m = int(M.ex_m[w])
        eta = ETA0 * m
        paths = week_paths(len(us), M.ex_mask[w], bool(M.ex_veto[w]))
        t, g = pl_paths_grad(us, paths)
        t = max(t, LOG_MIN)
        nll += -eta * np.log(t)
        np.add.at(dU, cells, -eta * g / t)
    # finale placement anchors
    if len(M.pair_a):
        sl = u[M.pair_b] - u[M.pair_a]
        d = (sl - PAIR_MU) / PAIR_SD
        nll += 0.5 * (d * d).sum()
        dd = d / PAIR_SD          # d nll/d sl_k = (sl-mu)/PAIR_SD^2 = d/PAIR_SD
        np.add.at(dU, M.pair_b, dd)
        np.add.at(dU, M.pair_a, -dd)
    # priors
    nll += 0.5 * (v * v).sum() / SIG_U ** 2
    nll += 0.5 * (g1 * g1).sum() / TAU_G ** 2
    nll += 0.5 * (ka * ka).sum() / TAU_K ** 2
    nll += 0.5 * (eps * eps).sum() / TAU_SEAS ** 2
    nll += 0.5 * xi * xi / SIG_XI ** 2
    # gradient
    gr = np.zeros(M.n_theta)
    gr[M.o_v:M.o_g1] = dU + v / SIG_U ** 2
    gr[M.o_g1:M.o_ka] = np.add.reduceat(dU, M.run_vbase) + g1 / TAU_G ** 2
    gr[M.o_ka:M.o_eps] = np.add.reduceat(dU * M.dmem, M.run_vbase) + ka / TAU_K ** 2
    gr[M.o_eps:M.o_xi] = np.bincount(M.season_of_flat, weights=dU, minlength=M.S) \
        + eps / TAU_SEAS ** 2
    gr[M.o_xi] = float((dU * M.xbar).sum()) + xi / SIG_XI ** 2
    if return_parts:
        return nll, gr, u
    return nll, gr


def map_optimize(M: Model, rng: np.random.Generator, n_start: int = 4,
                 maxiter: int = 1500, verbose: bool = False, drop_week=None):
    """Multi-start L-BFGS-B; returns (nll, theta)."""
    starts = []
    t0 = np.zeros(M.n_theta)
    t0[M.o_xi] = 14.0                      # cold start: fans mostly track judges
    starts.append(t0.copy())
    t1 = t0.copy()
    t1[M.o_xi] = 6.0
    t1[M.o_v:M.o_g1] = rng.normal(0, .2, M.V)
    starts.append(t1)
    t2 = t0.copy()
    t2[M.o_xi] = 25.0
    starts.append(t2)
    t3 = t0.copy()
    t3[M.o_xi] = 9.0
    t3[M.o_g1:M.o_ka] = rng.normal(0, .5, M.R)
    starts.append(t3)
    best = (np.inf, None)
    for k in range(n_start):
        th = starts[k % len(starts)].copy()
        if k >= len(starts):
            th = best[1] + rng.normal(0, 0.05, M.n_theta)
        res = minimize(lambda tv, mm: neg_log_post(mm, tv, drop_week=drop_week), th,
                       args=(M,), jac=True,
                       method="L-BFGS-B",
                       options=dict(maxiter=maxiter, ftol=1e-13, gtol=1e-9))
        if res.fun < best[0]:
            best = (float(res.fun), res.x.copy())
        if verbose:
            print(f"  start {k}: nll={res.fun:.1f}")
    res = minimize(lambda tv, mm: neg_log_post(mm, tv, drop_week=drop_week), best[1],
                   args=(M,), jac=True,
                   method="L-BFGS-B",
                   options=dict(maxiter=maxiter, ftol=1e-15, gtol=1e-10))
    if res.fun < best[0]:
        best = (float(res.fun), res.x.copy())
    return best
