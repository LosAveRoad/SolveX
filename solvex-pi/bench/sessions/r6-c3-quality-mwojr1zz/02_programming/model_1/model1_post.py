"""Model 1 stage B: per-season Laplace posterior, phi draws, importance weights.

Posterior factorizes across seasons (likelihood couples within season only;
priors are separable), so inference runs on per-season reduced objectives
theta_s = [v_s | g1_s | ka_s] with (eps, xi) pinned at the full MAP:
    nll_s(tv) = season-s exit weeks + season-s finale anchors + own priors.
Hessian by central finite differences of the EXACT reduced gradient (fast,
analytic-grad accuracy), then block Cholesky draws:
    theta_s^d = theta_MAP_s + z_d @ L_s^T ,   L_s = chol(Sigma_s).
 phi_d = softmax-outside(2 u_d - logx; chi=1000)  ->  shares on a fixed level.
Importance weights kill draws violating exit ordinal facts (kappa = KAPPA_W).
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import minimize
from model1_core import Model
from model1_obj import unpack, utl_vals, week_paths, pl_paths_grad


def pin_hyperparams(M: Model, th_full: np.ndarray):
    """Pin (eps, xi) at the full-MAP values for the reduced per-season objectives."""
    _, _, _, eps, xi = unpack(M, th_full)
    M._eps_hat = eps
    M._xi_hat = float(xi)


def season_slices(M: Model):
    """Cells/runs of each season are contiguous in the flat ordering."""
    out = []
    for si in range(M.S):
        runs = np.where(M.run_season == si)[0]
        c0 = M.run_vbase[runs[0]]
        c1 = M.run_vbase[runs[-1]] + M.run_nweeks[runs[-1]]
        out.append(dict(runs=runs, cells=np.arange(c0, c1)))
    return out


def season_parts(M: Model, sl: dict, si: int):
    """Exit weeks / finale-pair rows belonging to season si (local indices)."""
    ex_rows, ex_loc = [], []
    for w in range(len(M.ex_cells)):
        if M.ex_season[w] != si:
            continue
        loc = np.searchsorted(sl["cells"], M.ex_cells[w])
        ex_rows.append(w)
        ex_loc.append(loc)
    loc_of = {c: i for i, c in enumerate(sl["cells"].tolist())}
    p_rows = [k for k in range(len(M.pair_a))
              if M.pair_a[k] in loc_of and M.pair_b[k] in loc_of]
    p_a = np.array([loc_of[c] for c in M.pair_a[p_rows]], int)
    p_b = np.array([loc_of[c] for c in M.pair_b[p_rows]], int)
    return ex_rows, ex_loc, p_rows, p_a, p_b


def reduced_nll(M: Model, sl: dict, si: int, parts, tv: np.ndarray):
    """Season-si reduced negative log posterior of [v_s | g1_s | ka_s]."""
    from model1_core import ETA0, PAIR_MU, PAIR_SD, TAU_G, TAU_K, SIG_U, TAU_SEAS, SIG_XI
    ex_rows, ex_loc, p_rows, p_a, p_b = parts
    cells = sl["cells"]
    n_c, n_r = len(cells), len(sl["runs"])
    v = tv[:n_c]
    g1 = tv[n_c:n_c + n_r]
    ka = tv[n_c + n_r:]
    eps_hat = M._eps_hat[si]
    xi_hat = M._xi_hat
    dmem = M.dmem[cells]
    logx = M.logx[cells]
    xbar = M.xbar[cells]
    run_loc = M.run_of_flat[cells] - sl["runs"][0]   # within-season run ordinal
    u = xi_hat * xbar + v + g1[run_loc] + ka[run_loc] * dmem + eps_hat + 0.5 * logx
    nll = 0.0
    dU = np.zeros(n_c)
    for w, loc in zip(ex_rows, ex_loc):
        us = u[loc]
        m = int(M.ex_m[w])
        eta = ETA0 * m
        paths = week_paths(len(us), M.ex_mask[w], bool(M.ex_veto[w]))
        t, g = pl_paths_grad(us, paths)
        t = max(t, 1e-300)
        nll += -eta * np.log(t)
        np.add.at(dU, loc, -eta * g / t)
    if len(p_rows):
        slk = u[p_b] - u[p_a]
        d = (slk - PAIR_MU) / PAIR_SD
        nll += 0.5 * (d * d).sum()
        dd = d / PAIR_SD
        np.add.at(dU, p_b, dd)
        np.add.at(dU, p_a, -dd)
    nll += 0.5 * (v * v).sum() / SIG_U ** 2
    nll += 0.5 * (g1 * g1).sum() / TAU_G ** 2
    nll += 0.5 * (ka * ka).sum() / TAU_K ** 2
    # local cell offsets of each run's first week within the season block
    loc_base = M.run_vbase[sl["runs"]] - M.run_vbase[sl["runs"][0]]
    gr = np.zeros_like(tv)
    gr[:n_c] = dU + v / SIG_U ** 2
    gr[n_c:n_c + n_r] = np.add.reduceat(dU, loc_base) + g1 / TAU_G ** 2
    gr[n_c + n_r:] = np.add.reduceat(dU * dmem, loc_base) + ka / TAU_K ** 2
    return nll, gr, u


def season_posterior(M: Model, sl: dict, si: int, parts, th_full: np.ndarray,
                     fd_h: float = 1e-4, nugget0: float = 1e-8):
    """MAP polish + Laplace covariance of the reduced objective. Returns
    (nll, theta_map, u_map_reduced, Sigma, chol_ok, min_eig)."""
    n_c, n_r = len(sl["cells"]), len(sl["runs"])
    d = n_c + 2 * n_r
    tv0 = np.concatenate([th_full[:M.V][sl["cells"]],
                          th_full[M.o_g1:M.o_ka][sl["runs"]],
                          th_full[M.o_ka:M.o_eps][sl["runs"]]])
    f = lambda tv: reduced_nll(M, sl, si, parts, tv)[:2]
    res = minimize(f, tv0, jac=True, method="L-BFGS-B",
                   options=dict(maxiter=500, ftol=1e-13, gtol=1e-9))
    tv = res.x
    _, gr, u_red = reduced_nll(M, sl, si, parts, tv)
    H = np.zeros((d, d))
    for j in range(d):
        tp = tv.copy(); tp[j] += fd_h
        tm = tv.copy(); tm[j] -= fd_h
        H[:, j] = (f(tp)[1] - f(tm)[1]) / (2 * fd_h)
    H = 0.5 * (H + H.T)
    mineig = float(np.linalg.eigvalsh(H).min())
    Hs = H.copy()
    dd = np.arange(d)
    nug = nugget0
    L = None
    for _ in range(10):
        try:
            Lc = np.linalg.cholesky(Hs)
            cf = np.linalg.inv(Lc)
            Sigma = cf @ cf.T
            Sigma = 0.5 * (Sigma + Sigma.T)
            L = np.linalg.cholesky(Sigma)
            break
        except np.linalg.LinAlgError:
            Hs[dd, dd] += nug * np.maximum(np.diag(H), 1e-10)
            nug *= 10.0
    if L is None:                       # diagonal fallback
        Sigma = np.diag(1.0 / np.maximum(np.diag(Hs), 1e-6))
        L = np.sqrt(np.diag(Sigma))
    return float(res.fun), tv, u_red, Sigma, True, mineig


SIG_LAP_FALL_V = 0.6 ** 2     # fallback variance if a season block is not PD


def draw_all_seasons(M: Model, th_full: np.ndarray, n_draws: int,
                     rng: np.random.Generator):
    """Laplace draws for every season -> u_draw (n_draws, V) on the flat grid."""
    sls = season_slices(M)
    u_draw = np.zeros((n_draws, M.V))
    v_draw = np.zeros((n_draws, M.V))
    g1_draw = np.zeros((n_draws, M.R))
    ka_draw = np.zeros((n_draws, M.R))
    info = []
    for si in range(M.S):
        sl = sls[si]
        parts = season_parts(M, sl, si)
        _, tv, u_red, Sigma, ok, mineig = season_posterior(M, sl, si, parts, th_full)
        n_c, n_r = len(sl["cells"]), len(sl["runs"])
        d = n_c + 2 * n_r
        if not ok:
            Sigma = np.diag(np.concatenate([np.full(n_c, SIG_LAP_FALL_V),
                                            np.full(n_r, 4.0), np.full(n_r, 4.0)]))
        Z = rng.standard_normal((n_draws, d))
        Lc = np.linalg.cholesky(Sigma)
        draw = tv[None, :] + Z @ Lc.T
        u_draw[:, sl["cells"]] = u_red[None, :] + (draw[:, :n_c] - tv[None, :n_c])
        v_draw[:, sl["cells"]] = draw[:, :n_c]
        g1_draw[:, sl["runs"]] = draw[:, n_c:n_c + n_r]
        ka_draw[:, sl["runs"]] = draw[:, n_c + n_r:]
        info.append(dict(season=int(M.season_names[si]), dim=d, laplace_ok=bool(ok),
                         hess_min_eig=mineig))
    return u_draw, v_draw, g1_draw, ka_draw, info
def season_posterior(M: Model, sl: dict, si: int, parts, th_full: np.ndarray,
                     fd_h: float = 1e-4, nugget0: float = 1e-8):
    """MAP polish + Laplace covariance of the reduced objective. Returns
    (nll, tv_map, u_map_red, Sigma, min_eig_pre_nugget)."""
    n_c, n_r = len(sl["cells"]), len(sl["runs"])
    d = n_c + 2 * n_r
    tv0 = np.concatenate([th_full[:M.V][sl["cells"]],
                          th_full[M.o_g1:M.o_ka][sl["runs"]],
                          th_full[M.o_ka:M.o_eps][sl["runs"]]])
    f = lambda tv: reduced_nll(M, sl, si, parts, tv)[:2]
    res = minimize(f, tv0, jac=True, method="L-BFGS-B",
                   options=dict(maxiter=500, ftol=1e-13, gtol=1e-9))
    tv = res.x
    _, gr, u_red = reduced_nll(M, sl, si, parts, tv)
    H = np.zeros((d, d))
    for j in range(d):
        tp = tv.copy(); tp[j] += fd_h
        tm = tv.copy(); tm[j] -= fd_h
        H[:, j] = (f(tp)[1] - f(tm)[1]) / (2 * fd_h)
    H = 0.5 * (H + H.T)
    mineig = float(np.linalg.eigvalsh(H).min())
    Hs = H.copy()
    dd = np.arange(d)
    nug = nugget0
    Sigma = None
    for _ in range(10):
        try:
            Lc = np.linalg.cholesky(Hs)
            cf = np.linalg.inv(Lc)
            Sigma = cf @ cf.T
            Sigma = 0.5 * (Sigma + Sigma.T)
            np.linalg.cholesky(Sigma)     # PD check
            break
        except np.linalg.LinAlgError:
            Hs[dd, dd] += nug * np.maximum(np.diag(H), 1e-10)
            nug *= 10.0
    if Sigma is None:                   # diagonal fallback
        Sigma = np.diag(1.0 / np.maximum(np.diag(Hs), 1e-6))
    return float(res.fun), tv, u_red, Sigma, mineig


def draw_all_seasons(M: Model, th_full: np.ndarray, n_draws: int,
                     rng: np.random.Generator):
    """Laplace draws per season -> u_draw (n_draws, V) including g1/ka shifts."""
    sls = season_slices(M)
    u_draw = np.zeros((n_draws, M.V))
    v_draw = np.zeros((n_draws, M.V))
    g1_draw = np.zeros((n_draws, M.R))
    ka_draw = np.zeros((n_draws, M.R))
    info = []
    for si in range(M.S):
        sl = sls[si]
        parts = season_parts(M, sl, si)
        nll_s, tv, u_red, Sigma, mineig = season_posterior(M, sl, si, parts, th_full)
        n_c, n_r = len(sl["cells"]), len(sl["runs"])
        d = n_c + 2 * n_r
        Z = rng.standard_normal((n_draws, d))
        Lc = np.linalg.cholesky(Sigma)
        draw = tv[None, :] + Z @ Lc.T
        cells = sl["cells"]
        run_loc = M.run_of_flat[cells] - sl["runs"][0]   # within-season run ordinal
        # total utl deviation = dv + dg1_run + dka_run * dmem
        dev = (draw[:, :n_c] - tv[None, :n_c])
        dev += (draw[:, n_c:n_c + n_r] - tv[None, n_c:n_c + n_r])[:, run_loc]
        dev += ((draw[:, n_c + n_r:] - tv[None, n_c + n_r:])[:, run_loc]
                * M.dmem[cells][None, :])
        u_draw[:, cells] = u_red[None, :] + dev
        v_draw[:, cells] = draw[:, :n_c]
        g1_draw[:, sl["runs"]] = draw[:, n_c:n_c + n_r]
        ka_draw[:, sl["runs"]] = draw[:, n_c + n_r:]
        info.append(dict(season=int(M.season_names[si]), dim=d, nll=float(nll_s),
                         hess_min_eig=mineig))
    return u_draw, v_draw, g1_draw, ka_draw, info
