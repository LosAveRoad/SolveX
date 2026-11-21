"""Stage 1: Model-1 MAP fit + Laplace posterior fan-share draws.

Identification model (rule-faithful, 50/50 percentage combination grid):
    utility  a(c,w) = pi_c + beta * z_x(c,w)
    comb(c,w)= 0.5*x~(c,w) + 0.5*phi(c,w)
    likelihood: observed exit set must be the comb-worst m_w each week.
Priors: pi ~ N(0,1) i.i.d.; beta ~ N(1, 2^2).
"""
import math
import time
import numpy as np
from m3_core import M
from plcore import pl_bottom_set

KAPPA = 20.0
SIG_PI, SIG_BETA = 1.0, 2.0
BETA0 = 1.0


def event_list():
    EV = []
    for (s, w), pool in M["per_week"].items():
        ex = M["exit_key"].get((s, w), [])
        if not ex:
            continue
        pos = {c: t for t, c in enumerate(np.asarray(pool))}
        EV.append((np.asarray(pool), np.array([pos[e] for e in ex], dtype=int),
                   M["zx"][(s, w)], np.asarray(M["xtilde"][(s, w)]), w))
    return EV


def fit_model1():
    n = M["n_runs"]
    EV = event_list()

    def negobj(p):
        pi, beta = p[:n], p[n]
        obj = 0.5*float(pi@(pi/SIG_PI**2)) + 0.5*((beta-BETA0)/SIG_BETA)**2
        gpi = pi/SIG_PI**2
        gb = (beta-BETA0)/SIG_BETA**2
        for pool, expos, z, xt, w in EV:
            a = pi[pool] + beta*z
            phi = np.exp(a - a.max()); phi /= phi.sum()
            comb = 0.5*xt + 0.5*phi
            val, gcomb = pl_bottom_set(-KAPPA*comb, expos)
            obj -= val
            gc = KAPPA * gcomb                # grad of -logP wrt comb
            ga = (1-KAPPA*0)*0.5*phi*(gc - float(gc @ phi))
            np.add.at(gpi, pool, ga)
            gb += float(ga @ z)
        return obj, np.concatenate([gpi, [gb]])

    from scipy.optimize import minimize
    res = minimize(negobj, np.zeros(n + 1), jac=True, method="L-BFGS-B",
                   options=dict(maxiter=2000, maxfun=6000))
    return res, EV


if __name__ == "__main__":
    t0 = time.time()
    res, EV = fit_model1()
    print(f"MAP fit: f={res.fun:.2f} beta={res.x[M['n_runs']]:.4f}, "
          f"{time.time()-t0:.1f}s", flush=True)
    np.save("stage1_pmap.npy", res.x)
