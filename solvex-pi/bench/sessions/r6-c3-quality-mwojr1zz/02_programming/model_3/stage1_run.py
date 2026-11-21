"""Run stage 1: MAP fit + draws + validation.  Produces stage1_draws.npz
(PHID per week) and prints the identification validation table."""
import time
import numpy as np
from m3_core import M
from stage1_fit import fit_model1
from stage1_draws import week_posterior_draws

if __name__ == "__main__":
    t0 = time.time()
    res, EV = fit_model1()
    n = M["n_runs"]
    p_map = res.x
    pi_map, beta = p_map[:n], p_map[n]

    # ---- validation: comb-recovery + baseline comparison ----
    cnt = dict(m1_top1=[0, 0], m1_top2=[0, 0], any_top3=[0, 0], exact=[0, 0],
               j_top1=[0, 0], j_top3=[0, 0])
    for pool, expos, z, xt, w in EV:
        pool = np.asarray(pool)
        pos = {c: t for t, c in enumerate(pool)}
        a = pi_map[pool] + beta * z
        phi = np.exp(a - a.max()); phi /= phi.sum()
        comb = 0.5 * xt + 0.5 * phi
        es = set(expos.tolist()); m = len(expos)
        worst = np.argsort(comb)
        if m == 1:
            cnt["m1_top1"][1] += 1; cnt["m1_top1"][0] += int(worst[0] in es)
            cnt["m1_top2"][1] += 1; cnt["m1_top2"][0] += int(es <= set(worst[:2].tolist()))
        cnt["any_top3"][1] += 1; cnt["any_top3"][0] += int(es <= set(worst[:max(3,m)].tolist()))
        cnt["exact"][1] += 1;  cnt["exact"][0] += int(es == set(worst[:m].tolist()))
        wj = np.argsort(xt)
        if m == 1:
            cnt["j_top1"][1] += 1; cnt["j_top1"][0] += int(wj[0] in es)
        cnt["j_top3"][1] += 1; cnt["j_top3"][0] += int(es <= set(wj[:max(3,m)].tolist()))

    print("=== identification validation (MAP, 265 exit weeks) ===")
    for k, (h, t) in cnt.items():
        print(f"  {k:10s}: {h:3d}/{t} = {h/t:.4f}")
    print(f"MAP: {time.time()-t0:.1f}s | beta={beta:.4f} | pi_sd={pi_map.std():.4f}")

    # ---- draws: per-week posterior fan shares ----
    t1 = time.time()
    PHID = week_posterior_draws(pi_map, beta, D=2000, seed=20260502)
    print(f"draws built in {time.time()-t1:.1f}s: {len(PHID)} weeks, "
          f"D per week = {next(iter(PHID.values())).shape[0]}")
    np.savez_compressed("stage1_phid.npz",
                        weeks=np.array(list(PHID.keys())),
                        **{f"w{s}_{w}": v for (s, w), v in PHID.items()})
    print("saved stage1_phid.npz")
    print(f"total stage-1 time: {time.time()-t0:.1f}s")
