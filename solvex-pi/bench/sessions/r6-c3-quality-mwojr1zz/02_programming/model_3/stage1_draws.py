"""Posterior fan-share draws: per-week Laplace MVN around the MAP utilities.

Model-1 identification (stage1_fit, verified on 2 FD gradient checks):
  a(c,w)   = pi_c + beta*z_x(c,w)      comb = 0.5*x~ + 0.5*softmax(a)
  likelihood: exact PL bottom-m set over all 265 vote-exit weeks.
Posterior utility draws: a^(d) ~ N(a_MAP, H_w^{-1}) per week with weekly
softmax-block Hessian H_w = KAPPA^2 (diag(phi) - phi phi'), eigenvalue floor
EIG_FLOOR.  Plus limited-information blur SIG_MID (SIG_W1 in week 1).
phi^(d)_{c,w} = softmax(a^(d)) within that week's competing set.
"""
import numpy as np
from m3_core import M

KAPPA = 20.0
EIG_FLOOR = 1e-8
SIG_MID = 0.15
SIG_W1 = 0.30


def draw_phis(pi_map, beta, D, seed=20260502):
    rng = np.random.default_rng(seed)
    PHID = {}
    for (s, w), pool in M["per_week"].items():
        pool = np.asarray(pool, dtype=int)
        K = len(pool)
        z = M["zx"][(s, w)].astype(float)
        a_map = pi_map[pool] + beta * z
        phi_map = np.exp(a_map - a_map.max()); phi_map /= phi_map.sum()
        Hw = KAPPA**2 * (np.diag(phi_map) - np.outer(phi_map, phi_map))
        ev, V = np.linalg.eigh(Hw)
        ev = np.clip(ev, EIG_FLOOR, None)
        Sig = (V * (1.0 / ev)) @ V.T
        Lc = np.linalg.cholesky(Sig + 1e-10 * np.eye(K))
        eps = rng.standard_normal((D, K))
        blur_sd = SIG_W1 if w == 1 else SIG_MID
        blur = rng.normal(0.0, blur_sd, size=(D, K))
        a_d = a_map[None, :] + eps @ Lc.T + blur
        e = np.exp(a_d - a_d.max(axis=1, keepdims=True))
        PHID[(s, w)] = e / e.sum(axis=1, keepdims=True)
    return PHID
