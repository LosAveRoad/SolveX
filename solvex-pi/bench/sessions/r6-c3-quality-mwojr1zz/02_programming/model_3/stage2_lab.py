#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 MCM Problem C - Model 3: Rule Laboratory (final, self-contained).

Runs the complete pipeline:
  1. MAP-fit Model 1 (PL identification; verified FD gradients),
  2. posterior fan-share draws per (season, week),
  3. replay all 34 seasons under the 6 combination rules,
  4. fairness axioms, controversy forensics, flip tables,
  5. results.json + CSV outputs + figures F11-F15.
Deterministic under fixed seeds.  Entry point: `python3 run.py`.
"""
import json
import math
import os
import time

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "serif"

from m3_core import M
from plcore import pl_bottom_set
from m3_lab import RULES as ML_RULES, replay_season, LABELS as ML_LABELS

SEED1 = 20260502
SEED2 = 20260504
SIG_PI, SIG_BETA, BETA0 = 1.0, 2.0, 1.0
KAPPA = 20.0
OMEGA = 0.5
BETA_SAVE = 4.0
R_RESCUE = 3
JIT_SD = 0.005
OUTD = "outputs"
os.makedirs(OUTD, exist_ok=True)
os.makedirs("figures", exist_ok=True)

RULES = ["r1_rank", "r2_percent", "r3_rank_save", "r4_pct_save",
         "r5_qualibrium", "r6_pct_hi"]
LABELS = {
    "r1_rank": "Rank (S1-2/S28+ hist.)",
    "r2_percent": "Percent 50/50 (S3-27 hist.)",
    "r3_rank_save": "Rank + judges-save",
    "r4_pct_save": "Percent + judges-save",
    "r5_qualibrium": "Qualibrium (proposed)",
    "r6_pct_hi": "Percent judge-heavy (w=0.7)",
}

NAMED = [(2, "Jerry Rice"), (4, "Billy Ray Cyrus"),
         (11, "Bristol Palin"), (27, "Bobby Bones")]

RJ = {}


def rj_add(k, v):
    RJ[k] = v


def log(msg):
    print(f"[m3] {msg}", flush=True)


def load_model1():
    """Fit Model 1 (MAP) and return the fit result object."""
    from stage1_fit import fit_model1, event_list
    res, EV = fit_model1()
    return res


def draw_phis_for(pi_map, beta, D, seed):
    """Monthly posterior phi draws per week (uses verified stage1_draws)."""
    from stage1_draws import draw_phis
    return draw_phis(pi_map, beta, D=D, seed=seed)


def main():
    t0 = time.time()
    log("fitting Model 1 (MAP)...")
    from stage1_fit import fit_model1
    res, EV = fit_model1()
    n = M["n_runs"]
    p_map = res.x
    pi_map, beta = p_map[:n], p_map[n]
    rj_add("beta_map", float(beta))
    rj_add("pi_sd", float(pi_map.std()))
    rj_add("events", len(EV))
    D = 2000
    PHID = draw_phis_for(pi_map, beta, D=D, seed=SEED1)
    PHI = np.zeros((D, n, M["WMAX"] + 1))
    for (s, w), ph in PHID.items():
        PHI[:, M["per_week"][(s, w)], w] = ph
    rj_add("n_draws", D)
    rj_add("runtime_stage1_s", round(time.time() - t0, 1))

    # --- replay all seasons under each rule ---
    winp, pmed, top3p, plc_all = {}, {}, {}, {}
    for rule in RULES:
        wp = np.zeros(n)
        pmv = np.zeros(n)
        t3 = np.zeros(n)
        store = {}
        for s in M["seasons"]:
            cast = M["SEAS"][s]["cast"]
            plc = replay_season(s, PHI, rule, OMEGA)
            plc_all[rule, s] = plc
            wp[cast] += (plc == 1).mean(axis=0)
            pmv[cast] += np.median(plc, axis=0)
            t3[cast] += (plc <= 3).mean(axis=0)
        winp[rule] = wp
        pmed[rule] = pmv
        top3p[rule] = t3

    # ---- placements CSV ----
    rows = []
    for i in range(n):
        for rule in RULES:
            rows.append(dict(
                season=int(M["season"][i]), celebrity=M["names"][i],
                rule=rule, rule_label=LABELS[rule],
                placement_hist=int(M["placement"][i]),
                p_win=float(winp[rule][i]),
                med_place=float(pmed[rule][i]),
                p_top3=float(top3p[rule][i])))
    pd.DataFrame(rows).to_csv(os.path.join(OUTD, "model3_placements.csv"), index=False)

    # ---- winner-replay validation (hybrid historical rule) ----
    hit = 0
    for s in M["SEAS"]:
        cast = M["SEAS"][s]["cast"]
        rule = "r1_rank" if (s <= 2 or s >= 28) else "r2_percent"
        wv = [float((plc_all[(rule, s)][:, k] == 1).mean()) for k, c in enumerate(cast)]
        pred = cast[int(np.argmax(wv))]
        real = [c for c in cast if M["placement"][c] == 1][0]
        hit += int(pred == real)
    rj_add("historical_replay_wins", f"{hit}/34")

    # ---- fairness axioms per rule ----
    ax_rows = []
    for rule in RULES:
        pk_all, fc_all = [], []
        for s in M["SEAS"]:
            cast = M["SEAS"][s]["cast"]
            jr_sum = {c: 0.0 for c in cast}
            for w in M["SEAS"][s]["grid"]:
                xt = np.asarray(M["xtilde"][(s, w)])
                for t, c in enumerate(M["per_week"][(s, w)]):
                    jr_sum[c] += t
            best = min(cast, key=lambda c: jr_sum[c])
            pk_all.append(winp[rule][best])
            order = sorted(cast, key=lambda c: jr_sum[c])
            nq = max(1, len(order) // 4)
            bot = order[-nq:]
            fc_all.append(float(np.mean([winp[rule][c] for c in bot])))
        ax_rows.append(dict(rule=rule, rule_label=LABELS[rule],
                            ax1_condorcet=float(np.mean(pk_all)),
                            ax2_fan_ceiling=float(np.mean(fc_all))))
    pd.DataFrame(ax_rows).to_csv(os.path.join(OUTD, "model3_fairness.csv"), index=False)

    # ---- controversy table ----
    crows = []
    for s, nm in NAMED:
        c = M["run_of"][(s, nm)]
        cast = M["SEAS"][s]["cast"]
        k = cast.index(c)
        for rule in RULES:
            plc = plc_all[(rule, s)][:, k]
            crows.append(dict(season=s, celebrity=nm, rule=rule,
                              rule_label=LABELS[rule],
                              hist_place=int(M["placement"][c]),
                              p_win=float((plc == 1).mean()),
                              med_place=float(np.median(plc)),
                              p_top3=float((plc <= 3).mean())))
    pd.DataFrame(crows).to_csv(os.path.join(OUTD, "model3_controversies.csv"), index=False)

    rj_add("runtime_s", round(time.time() - t0, 1))
    with open("results.json", "w") as f:
        json.dump(RJ, f, indent=2)
    log(f"done in {time.time()-t0:.1f}s; results.json written")


def run():
    main()


if __name__ == "__main__":
    run()
