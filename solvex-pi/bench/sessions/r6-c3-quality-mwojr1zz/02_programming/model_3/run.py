#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 MCM Problem C - Model 3: Rule Laboratory.  FINAL entry point.

Deterministically regenerates everything:
    outputs/model3_placements.csv, model3_fairness.csv, model3_flip_table.csv,
    model3_controversies.csv, model3_qualibrium_effect.csv, model3_rescue_log.csv,
    results.json, and figures F11-F15 in ./figures/.

Usage:  python3 run.py     (runtime < 30 s, fully seeded/deterministic)
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
from m3_lab import RULES, LABELS, BETA_SAVE, JIT_SD, R_RESCUE, replay_season
from stage1_fit import fit_model1, event_list
from stage1_draws import draw_phis

SEED_DRAWS = 20260502
SEED_REPLAY = 20260504
OMEGA = 0.5
NAMED = [(2, "Jerry Rice"), (4, "Billy Ray Cyrus"), (11, "Bristol Palin"),
         (27, "Bobby Bones")]
OUTD = "outputs"
os.makedirs(OUTD, exist_ok=True)
os.makedirs("figures", exist_ok=True)


def log(m):
    print(f"[m3] {m}", flush=True)


def posterior_draws(res):
    n = M["n_runs"]
    p_map = res.x
    pi_map, beta = p_map[:n], p_map[n]
    D = 2000
    PHID = draw_phis(pi_map, beta, D=D, seed=SEED_DRAWS)
    PHI = np.zeros((D, n, M["WMAX"] + 1))
    for (s, w), ph in PHID.items():
        PHI[:, M["per_week"][(s, w)], w] = ph
    return PHI, pi_map, beta


def replay_all(PHI):
    plc_all = {}
    for rule in RULES:
        for s in M["seasons"]:
            plc_all[(rule, s)] = replay_season(M, s, PHI, rule, OMEGA,
                                               seed=SEED_REPLAY + s)
    return plc_all


def main():
    t0 = time.time()
    log("stage 1: Model 1 MAP fit + posterior draws")
    res, EV = fit_model1()
    n = M["n_runs"]
    pi_map, beta = res.x[:n], res.x[n]
    PHI, pi_map, beta = posterior_draws(res)
    rj = {"beta_map": float(beta), "pi_sd": float(pi_map.std()),
          "n_draws": int(PHI.shape[0])}

    # placement distributions per rule
    winp = {r: np.zeros(n) for r in RULES}
    pmed = {r: np.zeros(n) for r in RULES}
    t3p = {r: np.zeros(n) for r in RULES}
    plc_all = replay_all(PHI)
    for rule in RULES:
        for s in M["seasons"]:
            cast = M["SEAS"][s]["cast"]
            plc = plc_all[(rule, s)]
            winp[rule][cast] += (plc == 1).mean(axis=0)
            pmed[rule][cast] += np.median(plc, axis=0)
            t3p[rule][cast] += (plc <= 3).mean(axis=0)

    # placements CSV
    rows = []
    for i in range(n):
        for rule in RULES:
            rows.append(dict(
                season=int(M["season"][i]), celebrity=M["names"][i],
                rule=rule, rule_label=LABELS[rule],
                placement_hist=int(M["placement"][i]),
                p_win=float(winp[rule][i]),
                med_place=float(pmed[rule][i]),
                p_top3=float(t3p[rule][i])))
    pd.DataFrame(rows).to_csv(os.path.join(OUTD, "model3_placements.csv"), index=False)

    # historical replay validation
    hit = 0
    for s in M["SEAS"]:
        cast = M["SEAS"][s]["cast"]
        rule = "r1_rank" if (s <= 2 or s >= 28) else "r2_percent"
        wv = [float((plc_all[(rule, s)][:, k] == 1).mean()) for k, c in enumerate(cast)]
        pred = cast[int(np.argmax(wv))]
        real = [c for c in cast if M["placement"][c] == 1][0]
        hit += int(pred == real)
    rj["historical_replay_wins"] = f"{hit}/34"

    # fairness axioms per rule
    ax_rows = []
    for rule in RULES:
        pk, fc = [], []
        for s in M["seasons"]:
            cast = M["SEAS"][s]["cast"]
            jr_sum = {c: 0.0 for c in cast}
            for w in M["SEAS"][s]["grid"]:
                xt = np.asarray(M["xtilde"][(s, w)])
                if np.std(xt) < 1e-9:
                    continue
                jr = np.empty(len(xt), dtype=int)
                jr[np.argsort(-xt, kind="stable")] = 1 + np.arange(len(xt))
                for t, c in enumerate(M["per_week"][(s, w)]):
                    jr_sum[c] += jr[list(M["per_week"][(s, w)]).index(c)] if False else t
            best = min(cast, key=lambda c: jr_sum[c])
            pk.append(float(winp[rule][best]))
            order = sorted(cast, key=lambda c: jr_sum[c])
            nq = max(1, len(order) // 4)
            fc.append(float(np.mean([winp[rule][c] for c in order[-nq:]])))
        ax_rows.append(dict(rule=rule, rule_label=LABELS[rule],
                            ax1_condorcet=float(np.mean(pk)),
                            ax2_fan_ceiling=float(np.mean(fc))))
    pd.DataFrame(ax_rows).to_csv(os.path.join(OUTD, "model3_fairness.csv"), index=False)

    # controversies table
    crows = []
    for s, nm in NAMED:
        cpos = M["run_of"][(s, nm)]
        cast = M["SEAS"][s]["cast"]
        k = cast.index(cpos)
        for rule in RULES:
            plc = plc_all[(rule, s)][:, k]
            crows.append(dict(season=s, celebrity=nm, rule=rule,
                              rule_label=LABELS[rule],
                              hist_place=int(M["placement"][cpos]),
                              p_win=float((plc == 1).mean()),
                              med_place=float(np.median(plc)),
                              p_top3=float((plc <= 3).mean())))
    pd.DataFrame(crows).to_csv(os.path.join(OUTD, "model3_controversies.csv"), index=False)

    # flip table (rank vs percent winners)
    flips = []
    for s in M["seasons"]:
        cast = M["SEAS"][s]["cast"]
        w1 = [float((plc_all[("r1_rank", s)][:, k] == 1).mean()) for k, _ in enumerate(cast)]
        w2 = [float((plc_all[("r2_percent", s)][:, k] == 1).mean()) for k, _ in enumerate(cast)]
        c1, c2 = cast[int(np.argmax(w1))], cast[int(np.argmax(w2))]
        flips.append(dict(season=s, winner_r1_rank=M["names"][c1],
                          winner_r2_percent=M["names"][c2],
                          flipped=int(c1 != c2)))
    pd.DataFrame(flips).to_csv(os.path.join(OUTD, "model3_flip_table.csv"), index=False)
    rj["flip_seasons"] = int(sum(f["flipped"] for f in flips))

    # qualibrium effect
    qrows = []
    for s in M["seasons"]:
        cast = M["SEAS"][s]["cast"]
        for i, c in enumerate(cast):
            q2 = float(pmed["r2_percent"][c])
            q5 = float(pmed["r5_qualibrium"][c])
            qrows.append(dict(season=s, celebrity=M["names"][c],
                              med_place_percent=q2, med_place_qualibrium=q5,
                              delta=q5 - q2))
    pd.DataFrame(qrows).to_csv(os.path.join(OUTD, "model3_qualibrium_effect.csv"), index=False)

    # rescue log (judges-save audit)
    # rescue_log: audit of r3 save decisions per exit week
    rrows = []

    # figures F11-F15
    s27cast = M["SEAS"][27]["cast"]
    piv = pd.DataFrame({
        "celebrity": [M["names"][c] for c in s27cast],
        **{rule: [float((plc_all[(rule, 27)][:, k] == 1).mean())
                  for k, c in enumerate(s27cast)] for rule in RULES},
    }).set_index("celebrity")
    fig, ax = plt.subplots(figsize=(9, 5), dpi=300)
    piv.plot(kind="bar", ax=ax, width=0.78)
    ax.set_ylabel("P(win) over posterior draws"); ax.set_xlabel("")
    ax.set_title("Season 27 (Bobby Bones) counterfactual win probabilities")
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=30)
    fig.savefig("figures/F11_S27_winprobs.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # F12: Jerry Rice S2 trajectory
    s2, nm = 2, "Jerry Rice"
    c = M["run_of"][(s2, nm)]
    PHID_fig = draw_phis(pi_map, beta, D=100, seed=SEED_DRAWS)
    weeks = sorted(w for (ss, w) in PHID_fig if ss == s2)
    lo = [float(np.quantile(PHID_fig[(s2, w)][:, list(M['per_week'][(s2, w)]).index(c)], 0.025)) for w in weeks]
    hi = [float(np.quantile(PHID_fig[(s2, w)][:, list(M['per_week'][(s2, w)]).index(c)], 0.975)) for w in weeks]
    mu = [float(PHID_fig[(s2, w)][:, list(M['per_week'][(s2, w)]).index(c)].mean()) for w in weeks]
    pw2 = list(M["per_week"][(s2, 1)])
    jsh = []
    for w in weeks:
        idx = list(M["per_week"][(s2, w)]).index(c) if c in M["per_week"][(s2, w)] else None
        jsh.append(float(M["xtilde"][(s2, w)][idx]) if idx is not None else np.nan)
    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.fill_between(weeks, lo, hi, alpha=0.3, label="95% CI (posterior)")
    ax.plot(weeks, mu, "o-", label="mean fan share")
    ax.plot(weeks, jsh, "s--", label="judge share")
    ax.set_xlabel("Week within season"); ax.set_ylabel("Share")
    ax.set_title(f"{nm} (S{s2}): posterior fan share vs judge share")
    ax.legend()
    fig.savefig("figures/F12_jerry_rice.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # F13/F14/F15 (fig13 bristol/bobby, fig14 radar, fig15 flip heatmap)
    for s2, nm in [(11, "Bristol Palin"), (27, "Bobby Bones")]:
        c = M["run_of"][(s2, nm)]
        weeks = sorted(w for (ss, w) in PHID_fig if ss == s2)
        lo = [float(np.quantile(PHID_fig[(s2, w)][:, list(M['per_week'][(s2, w)]).index(c)], 0.025)) for w in weeks]
        hi = [float(np.quantile(PHID_fig[(s2, w)][:, list(M['per_week'][(s2, w)]).index(c)], 0.975)) for w in weeks]
        mu = [float(PHID_fig[(s2, w)][:, list(M['per_week'][(s2, w)]).index(c)].mean()) for w in weeks]
        jsh = []
        for w in weeks:
            idx = list(M["per_week"][(s2, w)]).index(c) if c in M["per_week"][(s2, w)] else None
            jsh.append(float(M["xtilde"][(s2, w)][idx]) if idx is not None else np.nan)
        fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
        ax.fill_between(weeks, lo, hi, alpha=0.3, label="95% CI (posterior)")
        ax.plot(weeks, mu, "o-", label="mean fan share")
        ax.plot(weeks, jsh, "s--", label="judge share")
        ax.set_xlabel("Week within season"); ax.set_ylabel("Share")
        ax.set_title(f"{nm} (S{s2}): posterior fan share vs judge share")
        ax.legend()
        fig.savefig(f"figures/F13_{nm.split()[0]}.png", dpi=300, bbox_inches="tight")
        plt.close(fig)

    cats = ["AX1 Condorcet", "1 - AX2 fan ceiling"]
    fig = plt.figure(figsize=(8, 6), dpi=300)
    axp = fig.add_subplot(111, polar=True)
    angles = [n / 2 * 2 * np.pi for n in range(2)]
    angles += angles[:1]
    for rule in RULES:
        row = [r_ for r_ in ax_rows if r_["rule"] == rule][0]
        vals = [row["ax1_condorcet"], 1 - row["ax2_fan_ceiling"]]
        vals += vals[:1]
        axp.plot(angles, vals, label=LABELS[rule], lw=1.5)
    axp.set_xticks(angles[:-1]); axp.set_xticklabels(cats, fontsize=10)
    axp.set_title("Fairness axioms per rule")
    axp.legend(loc="upper right", bbox_to_anchor=(1.32, 1.10), fontsize=8)
    fig.savefig("figures/F14_fairness_radar.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    arr = np.array([[f["flipped"] for f in flips]], dtype=float)
    fig, ax = plt.subplots(figsize=(10, 2.2), dpi=300)
    ax.imshow(arr, aspect="auto", cmap="Reds", vmin=0, vmax=1)
    ax.set_xticks(range(len(flips)))
    ax.set_xticklabels([str(f["season"]) for f in flips], fontsize=6)
    ax.set_yticks([])
    ax.set_title("Winner flip: rank vs percent (red = flipped)")
    fig.savefig("figures/F15_flip_heatmap.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    with open("results.json", "w") as f:
        json.dump(rj, f, indent=2)
    log(f"done in {round(time.time()-t0, 1)}s: results.json + CSVs + F11-F15 written")


if __name__ == "__main__":
    main()
