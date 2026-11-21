#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""m3_core.py - shared data + season structures (Model 3, 2026 MCM Problem C).

Conventions (shared_data/data_dictionary.md):
- a vote exit's basis week = the couple's last danced week (`last_week`);
- folded finalists (last_week < finale_week: S1 Joey McIntyre, S3 Joey
  Lawrence) are semifinal VOTE CUTS -> vote exits at their basis week;
- 7 'eliminated' rows exit at the finale-episode vote cut (in season_weeks
  n_eliminated for finale weeks);
- withdrawals never count as vote exits;
- within-week judge share x~(c,w) = weekly_total / sum of that week's totals.
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.normpath(os.path.join(HERE, "..", "..", "01_modeling", "shared_data"))


def load_core():
    con = pd.read_csv(os.path.join(SHARED, "contestants.csv"))
    ws = pd.read_csv(os.path.join(SHARED, "week_scores.csv"))
    sw = pd.read_csv(os.path.join(SHARED, "season_weeks.csv"))
    con = con.sort_values(["season", "celebrity_name"]).reset_index(drop=True)
    return con, ws, sw


def build_structures(con, ws, sw):
    M = {}
    M["con"] = con
    M["n_runs"] = len(con)
    M["names"] = con.celebrity_name.tolist()
    run_of = {(int(r.season), r.celebrity_name): i for i, r in con.iterrows()}
    M["run_of"] = run_of
    M["season"] = con.season.values.astype(int)
    M["last_week"] = con.last_week.values.astype(int)
    M["placement"] = con.placement.values.astype(int)
    M["res_type"] = con.result_type.values

    WMAX = int(max(sw.week.max(), con.finale_week.max()))
    M["WMAX"] = WMAX
    TT = np.full((M["n_runs"], WMAX + 1), np.nan)
    for r in ws.itertuples():
        TT[run_of[(int(r.season), r.celebrity_name)], int(r.week)] = r.weekly_total
    M["TT"] = TT

    per_week, xtilde, zx = {}, {}, {}
    for (s, w), g in ws.groupby(["season", "week"]):
        idx = np.array(sorted(run_of[(int(s), nm)] for nm in g.celebrity_name), dtype=int)
        per_week[(int(s), int(w))] = idx
        t = TT[idx, w]
        xtilde[(int(s), int(w))] = t / t.sum()
        zx[(int(s), int(w))] = (t - t.mean()) / (t.std(ddof=0) + 1e-12)
    M["per_week"], M["xtilde"], M["zx"] = per_week, xtilde, zx

    # vote-exit key + folded cuts + withdrawals + finale ranks
    ex, folded, wd, fin_rank = {}, {}, {}, {}
    for r in con.itertuples():
        si, lw, fw = int(r.season), int(r.last_week), int(r.finale_week)
        cid = run_of[(si, r.celebrity_name)]
        if r.result_type == "eliminated":
            ex.setdefault((si, lw), []).append(cid)
        elif r.result_type == "finalist" and lw < fw:
            folded.setdefault((si, lw), []).append(cid)
            ex.setdefault((si, lw), []).append(cid)
        elif r.result_type == "finalist" and lw == fw:
            fin_rank.setdefault(si, []).append((cid, int(r.placement)))
        elif r.result_type == "withdrew":
            wd.setdefault((si, lw), []).append(cid)
    M["exit_key"] = {k: sorted(v) for k, v in ex.items()}
    M["folded"] = folded
    M["wd_key"] = wd
    M["fin_rank"] = fin_rank

    SEAS = {}
    for s, g in sw.groupby("season"):
        w_arr = g.week.values.astype(int)
        fin = int(w_arr[g.is_finale_week.values.astype(bool)][0])
        m_w = dict(zip(w_arr, g.n_eliminated.astype(int)))
        for (ss, wk), v in folded.items():
            if ss == s and wk in m_w and wk < fin:
                m_w[wk] += len(v)
        cast = [run_of[(int(s), nm)] for nm in con.loc[con.season == s, "celebrity_name"]]
        SEAS[int(s)] = dict(grid=w_arr, m_w=m_w, fin=fin, cast=cast)
    M["SEAS"] = SEAS
    M["seasons"] = sorted(SEAS.keys())
    return M


M = build_structures(*load_core())

if __name__ == "__main__":
    print("vote-exit events:", sum(len(v) for v in M["exit_key"].values()),
          "| exit weeks:", len(M["exit_key"]),
          "| folded:", {k: [M["names"][i] for i in v] for k, v in M["folded"].items()},
          "| withdrawals:", len(M["wd_key"]))
