"""m3_lab.py - six-rule replay engine, per posterior draw (final)."""
import math
import numpy as np

RULES = ["r1_rank", "r2_percent", "r3_rank_save", "r4_pct_save",
         "r5_qualibrium", "r6_pct_hi"]
SAVE_RULES = {"r3_rank_save", "r4_pct_save"}
LABELS = {
    "r1_rank": "Rank (S1-2/S28+ hist.)",
    "r2_percent": "Percent 50/50 (S3-27 hist.)",
    "r3_rank_save": "Rank + judges-save",
    "r4_pct_save": "Percent + judges-save",
    "r5_qualibrium": "Qualibrium (proposed)",
    "r6_pct_hi": "Percent judge-heavy (w=0.7)",
}
BETA_SAVE = 4.0
JIT_SD = 0.005
R_RESCUE = 3


def judge_ranks(xt):
    xt = np.asarray(xt)
    if xt.ndim == 1:
        r = np.empty(xt.shape[0], dtype=int)
        r[np.argsort(-xt, kind="stable")] = 1 + np.arange(xt.shape[0])
        return r
    r = np.empty(xt.shape, dtype=int)
    r[np.argsort(-xt, axis=1, kind="stable")] = 1 + np.arange(xt.shape[1])[None, :]
    return r


def fan_ranks(frd):
    orda = np.argsort(-frd, axis=1, kind="stable")
    r = np.empty(frd.shape, dtype=int)
    np.put_along_axis(r, orda, np.arange(1, frd.shape[1] + 1)[None, :], axis=1)
    return r


def replay_season(M, s, PHI, rule, omega=0.5, seed=20260504):
    """Replay season s under `rule` for every posterior draw.

    Returns plc (D, n_c): counterfactual placement per cast member (1 = win).
    Per week: fr rows = this week's DRAWN fan shares of the survivors; per
    survivor, judge signals come from that week's per_vote vectors."""
    S = M["SEAS"][s]
    cast = list(S["cast"])
    n_c = len(cast)
    pos = {c: k for k, c in enumerate(cast)}
    D = PHI.shape[0]
    plc = np.zeros((D, n_c), dtype=int)
    rng = np.random.default_rng(seed)
    pools = sorted({(s, w) for (s, w) in M["per_week"] if s == s and w in set(S["grid"].tolist())})
    pool = list(cast)
    placed = n_c
    done = False
    for wi, w in enumerate(S["grid"]):
        if done:
            break
        k_true = len(M["per_week"][(s, int(w))])
        pool = list(M["per_week"][(s, int(w))])  # REAL competing set this week
        m = int(S["m_w"][w])
        k = len(pool)
        if k <= m + 1:                           # finale-like remainder
            for c in pool:
                plc[:, pos[c]] = 1
            break
        # judge + fan signals for exactly the couples dancing this week
        pool_arr = np.asarray(pool, dtype=int)
        xt = np.asarray(M["xtilde"][(s, int(w))], dtype=float)
        fr = PHI[:, pool_arr, w]
        jr = judge_ranks(xt).astype(float)
        jitter = rng.normal(0.0, JIT_SD, size=(D, k))
        if rule == "r1_rank":
            comb = jr[None, :] + fan_ranks(fr) + jitter
            epos = np.argsort(-comb, axis=1)[:, :m]
        elif rule in ("r2_percent", "r6_pct_hi"):
            om = 0.7 if rule == "r6_pct_hi" else omega
            comb = om * xt[None, :] + (1 - om) * fr + jitter
            epos = np.argsort(comb, axis=1)[:, :m]
        elif rule in SAVE_RULES:
            if rule == "r3_rank_save":
                base = jr[None, :] + fan_ranks(fr) + jitter
            else:
                base = omega * xt[None, :] + (1 - omega) * fr + jitter
            orda = np.argsort(base, axis=1)
            a_idx, b_idx = orda[:, 0], orda[:, 1]
            gap = xt[a_idx] - xt[b_idx]
            p_save_a = 1.0 / (1.0 + math.exp(-BETA_SAVE * float(np.mean(gap))))
            save_a = rng.random(D) < p_save_a
            epos = np.where(save_a, b_idx, a_idx)
        elif rule == "r5_qualibrium":
            om_w = 0.3 + 0.4 * (w / S["fin"])
            comb = om_w * xt[None, :] + (1 - om_w) * fr + jitter
            if fr.shape[1] > R_RESCUE:
                thresh = np.partition(fr, -R_RESCUE, axis=1)[:, -R_RESCUE]
                rescued = fr >= thresh[:, None]
            else:
                rescued = np.ones_like(fr, dtype=bool)
            comb_masked = np.where(rescued, 10.0 + comb, comb)
            epos = np.argsort(comb_masked, axis=1)[:, :m]
        else:
            raise ValueError(rule)
        epos = np.asarray(epos, dtype=int)
        if epos.ndim == 1:
            epos = epos[:, None]
        for d in range(D):
            for e in epos[d]:
                plc[d, pos[pool[e]]] = placed
        placed -= m
        gone = set(np.unique(epos).tolist())
        pool = [c for ci, c in enumerate(pool) if ci not in gone]
        if not pool:
            break
    for c in pool:
        plc[:, pos[c]] = 1
    return plc
