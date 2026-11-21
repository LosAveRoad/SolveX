"""Exact Plackett-Luce bottom-m set log-likelihood + gradient (log-space).

pl_bottom_set(aa, ex) -> (lse, grad):
  lse  = log P(exit set = ex | utilities aa), summed over all m! removal orders
  grad = d lse / d aa (vector of length K = len(aa))
"""
import math
import numpy as np
from itertools import permutations


def _lse(x):
    mx = x.max()
    return mx + math.log(np.exp(x - mx).sum())


def pl_bottom_set(aa, ex):
    """Log-space exact PL bottom-m set log-probability and gradient."""
    K = len(aa)
    m = len(ex)
    P = math.factorial(m)
    lps = np.empty(P)
    grads = np.zeros((P, K))
    for k, order in enumerate(permutations(list(ex))):
        lp = 0.0
        live = list(range(K))
        g = np.zeros(K)
        for e in order:
            lR = _lse(aa[live])
            lp += aa[e] - lR
            sm = np.exp(aa[live] - lR)
            for t, c in enumerate(live):
                g[c] -= sm[t]
            g[e] += 1.0
            live = [c for c in live if c != e]
        lps[k] = lp
        grads[k] = g
    mx = lps.max()
    lse = mx + math.log(np.exp(lps - mx).sum())
    pord = np.exp(lps - mx)
    pord /= pord.sum()
    return lse, pord @ grads
