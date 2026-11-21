"""Diagnose curvature: per-event Hessian of -loglik wrt pooled utilities."""
import numpy as np
from m3_core import M
from plcore import pl_bottom_set

KAPPA = 20.0

# one real event: S2 week 2
s, w = 2, 2
pool = np.asarray(M["per_week"][(s, w)])
z = np.asarray(M["zx"][(s, w)])
xt = np.asarray(M["xtilde"][(s, w)])
ex = np.asarray([{c: t for t, c in enumerate(pool)}[e] for e in M["exit_key"][(s, w)]])
K = len(pool)
print("pool size:", K, "| m:", len(ex))


def ll_of(pi):
    phi = np.exp(pi - pi.max()); phi /= phi.sum()
    comb = 0.5*xt + 0.5*phi
    val, _ = pl_bottom_set(-KAPPA*comb, ex)
    return val


pi0 = np.zeros(K)
H = np.zeros((K, K))
d = 1e-4
for t in range(K):
    for u in range(t, K):
        if t == u:
            app = pi0.copy(); app[t] += d
            apm = pi0.copy(); apm[t] -= d
            H[t, t] = -(ll_of(app) - 2*ll_of(pi0) + ll_of(apm)) / d**2
        else:
            app = pi0.copy(); app[t] += d; app[u] += d
            ap1 = pi0.copy(); ap1[t] += d; ap1[u] -= d
            ap2 = pi0.copy(); ap2[t] -= d; ap2[u] += d
            ap3 = pi0.copy(); ap3[t] -= d; ap3[u] -= d
            H[t, u] = H[u, t] = -(ll_of(app) - ll_of(ap1) - ll_of(ap2) + ll_of(ap3)) / (4*d*d)
print("event -loglik Hessian diag (should be >= 0):", np.round(np.diag(H), 3))
ev = np.linalg.eigvalsh(H)
print("event -loglik Hessian eigenvalues:", np.round(ev, 3))
