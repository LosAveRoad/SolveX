"""Model 1 core: data assembly into flat arrays + model constants + betting rules.

Latent per contestant-week cell i (run r(i), season s(i)):
    utl_i = xi*xbar_i + v_i + g1_r + ka_r*dmem_i + eps_s + 0.5*logx_i
  = log(percentage-method Combined) + within-week constant; eliminations identify
  it exactly up to within-week shifts (those shift out of the softmax).
  xbar  = weekly judge total / week sum        dmem: run-decay shape (centered)
  v ~ N(0, SIG_U^2) weekly idiosyncrasy;  g1_r ~ N(0,TAU_G^2) run popularity;
  ka_r ~ N(0,TAU_K^2) decay strength;  eps_s ~ N(0,TAU_SEAS^2) season climate;
  xi ~ N(0, SIG_XI^2) judge sensitivity of fan votes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field

# ---------------- tunable constants (all weights/priors in one place) --------
ETA0 = 0.5          # likelihood weight per exit event
PAIR_MU = 0.5       # finale-placement slack mean (utl_worse - utl_better >= mu)
PAIR_SD = 4.0       # finale-placement slack sd (weak anchor)
TAU_G = 2.0         # prior sd of run-level popularity g1
TAU_K = 2.0         # prior sd of decay strength ka
SIG_U = 0.6         # fixed prior sd of weekly fan idiosyncrasy v
TAU_SEAS = 0.75     # fixed prior sd of season fan climate eps
SIG_XI = 2.0        # prior sd of judge sensitivity xi
N_DRAWS = 4000      # stage-B posterior draws
KAPPA_W = 1.0       # rank-violation importance weight kappa
SEED = 20260205     # master seed
RANK_GRID_SEASONS = frozenset([1, 2] + list(range(28, 35)))  # rank-method seasons
SIG_MU = 0.60       # spectator mass sd on the softmax grid (z + log x scale)
CV_LOW, CV_HIGH = 0.050, 0.090   # certainty tiers on phi_ren CV


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class Model:
    # flat per contestant-week arrays (run-major; ordered by season, name, week)
    V: int
    R: int
    season_of_flat: np.ndarray
    week_of_flat: np.ndarray
    run_of_flat: np.ndarray
    xbar: np.ndarray        # judge share within (season,week)
    zsc: np.ndarray         # judge z within (season,week) (reporting)
    logx: np.ndarray
    tot: np.ndarray
    celeb: list
    # runs
    run_season: np.ndarray
    run_name: list
    run_partner: list
    run_industry: list
    run_age: np.ndarray
    run_nweeks: np.ndarray
    run_pl: np.ndarray
    run_vbase: np.ndarray
    run_last_week: np.ndarray
    run_result: list
    dmem: np.ndarray
    # exit weeks (risk support excludes same-week withdrawals)
    ex_cells: list
    ex_mask: list
    ex_m: np.ndarray
    ex_season: np.ndarray
    ex_week: np.ndarray
    ex_veto: np.ndarray     # 1 = S>=28 single exit (bottom-2 membership only)
    ex_rankgrid: np.ndarray # 1 = rank-sum grid for draw violations
    ex_wk_seg: np.ndarray
    # all weeks
    wk_perm: np.ndarray
    wk_off: np.ndarray
    wk_season: np.ndarray
    wk_week: np.ndarray
    wk_isfinale: np.ndarray
    wk_seg_of_flat: np.ndarray
    wk_nc: np.ndarray
    wk_key_of: list
    # finale placement pairs
    pair_a: np.ndarray
    pair_b: np.ndarray
    # packing
    S: int
    season_names: np.ndarray
    n_theta: int = 0
    o_v: int = 0
    o_g1: int = 0
    o_ka: int = 0
    o_eps: int = 0
    o_xi: int = 0
    meta: dict = field(default_factory=dict)


def load_data(shared_dir) -> dict:
    from pathlib import Path
    shared = Path(shared_dir)
    return {"contestants": pd.read_csv(shared / "contestants.csv"),
            "week_scores": pd.read_csv(shared / "week_scores.csv"),
            "season_weeks": pd.read_csv(shared / "season_weeks.csv")}


def build_model_part1(data: dict):
    """Runs, flat cells, judge totals, decay shape. Returns a dict of parts."""
    ct, wc, sw = data["contestants"], data["week_scores"], data["season_weeks"]
    seasons = np.sort(ct.season.unique())
    S = len(seasons)
    season_ix = {int(s): i for i, s in enumerate(seasons)}
    ct = ct.sort_values(["season", "celebrity_name"]).reset_index(drop=True)
    R = len(ct)
    run_season = ct.season.map(season_ix).to_numpy()
    run_name = ct.celebrity_name.tolist()
    run_partner = ct.partner_primary.tolist()
    run_industry = ct.celebrity_industry.tolist()
    run_age = ct.celebrity_age_during_season.to_numpy(float)
    run_nweeks = ct.n_weeks_active.to_numpy(int)
    run_pl = ct.placement.fillna(0).to_numpy(int)
    run_last = ct.last_week.to_numpy(int)
    run_result = ct.result_type.tolist()
    run_keys = {(int(r.season), r.celebrity_name): i for i, r in ct.iterrows()}
    run_vbase = np.zeros(R, int)
    run_vbase[1:] = np.cumsum(run_nweeks)[:-1]
    V = int(run_nweeks.sum())
    flat_run = np.repeat(np.arange(R), run_nweeks)
    flat_week = np.concatenate([np.arange(1, n + 1) for n in run_nweeks])
    flat_season = run_season[flat_run]
    # cells of each (season,week)
    sw_key = {(int(r.season), int(r.week)): k for k, r in sw.iterrows()}
    n_weeks = len(sw)
    cells_of_week = [[] for _ in range(n_weeks)]
    wk_seg_of_flat = np.zeros(V, int)
    for i in range(V):
        k = sw_key[(int(ct.season[flat_run[i]]), int(flat_week[i]))]
        cells_of_week[k].append(i)
        wk_seg_of_flat[i] = k
    # weekly judge totals onto cells
    wc_lookup = {(int(r.season), r.celebrity_name, int(r.week)): float(r.weekly_total)
                 for r in wc.itertuples()}
    tot = np.full(V, np.nan)
    for i in range(V):
        tot[i] = wc_lookup[(int(ct.season[flat_run[i]]), run_name[flat_run[i]],
                            int(flat_week[i]))]
    assert np.isfinite(tot).all(), "every dancer-week must have a judge total"
    xbar = np.zeros(V)
    zsc = np.zeros(V)
    for k in range(n_weeks):
        idx = np.array(cells_of_week[k])
        t = tot[idx]
        xbar[idx] = t / t.sum()
        sd = t.std()
        zsc[idx] = 0.0 if sd < 1e-9 else (t - t.mean()) / sd
    logx = np.log(tot)
    # decay shape dmem (weeks-remaining fraction, centered within run)
    n_r = run_nweeks[flat_run]
    frac_left = (n_r - flat_week + 1.0) / np.maximum(n_r - 1.0, 1.0)
    membar = np.array([frac_left[flat_run == c].mean() for c in range(R)])[flat_run]
    dmem = frac_left - membar
    celeb = [run_name[c] for c in flat_run]
    return dict(ct=ct, sw=sw, seasons=seasons, season_ix=season_ix, S=S, R=R,
                run_season=run_season, run_name=run_name, run_partner=run_partner,
                run_industry=run_industry, run_age=run_age, run_nweeks=run_nweeks,
                run_pl=run_pl, run_last=run_last, run_result=run_result,
                run_keys=run_keys, run_vbase=run_vbase, V=V,
                flat_run=flat_run, flat_week=flat_week, flat_season=flat_season,
                cells_of_week=cells_of_week, wk_seg_of_flat=wk_seg_of_flat,
                tot=tot, xbar=xbar, zsc=zsc, logx=logx, dmem=dmem, celeb=celeb)


def build_model_part2(P: dict) -> Model:
    """Exit weeks, week segments, finale anchors; assembles the Model."""
    ct, sw = P["ct"], P["sw"]
    season_ix, R, V = P["season_ix"], P["R"], P["V"]
    run_keys, run_vbase = P["run_keys"], P["run_vbase"]

    exits_by_key, wd_by_key = {}, {}
    for i, r in ct.iterrows():
        if r.result_type == "eliminated":
            exits_by_key.setdefault((int(r.season), int(r.last_week)), []).append(
                run_keys[(int(r.season), r.celebrity_name)])
        elif r.result_type == "withdrew":
            wd_by_key.setdefault((int(r.season), int(r.last_week)), []).append(
                run_keys[(int(r.season), r.celebrity_name)])

    n_weeks = len(sw)
    cells_of_week = P["cells_of_week"]
    ex_cells, ex_mask, ex_season, ex_week = [], [], [], []
    ex_m, ex_veto, ex_rankgrid, ex_wk_seg = [], [], [], []
    wd_cells_by_week = {}
    for k, r in sw.iterrows():
        wd = wd_by_key.get((int(r.season), int(r.week)), [])
        if wd:
            wd_cells_by_week[k] = [run_vbase[c] + int(r.week) - 1 for c in wd]
        if r.n_eliminated <= 0:
            continue
        all_cells = np.array(cells_of_week[k])
        wd_cells = set(wd_cells_by_week.get(k, []))
        risk = np.array([c for c in all_cells if c not in wd_cells], int)
        exit_runs = sorted(exits_by_key.get((int(r.season), int(r.week)), []))
        assert len(exit_runs) == int(r.n_eliminated), f"exit count mismatch {r.season},{r.week}"
        exit_cells = [run_vbase[c] + int(r.week) - 1 for c in exit_runs]
        assert set(exit_cells) <= set(risk.tolist()), f"exit not competing {r.season},{r.week}"
        mask = np.isin(risk, exit_cells)
        assert int(mask.sum()) == len(exit_cells)
        m = int(r.n_eliminated)
        nveto = 1 if (r.season >= 28 and m == 1) else 0
        assert (not nveto) or len(risk) >= 3, f"veto week {r.season},{r.week} too small"
        ex_cells.append(risk)
        ex_mask.append(mask)
        ex_season.append(season_ix[int(r.season)])
        ex_week.append(int(r.week))
        ex_m.append(m)
        ex_veto.append(nveto)
        ex_rankgrid.append(1 if int(r.season) in RANK_GRID_SEASONS else 0)
        ex_wk_seg.append(k)

    wk_perm = np.concatenate([np.array(cells_of_week[k]) for k in range(n_weeks)])
    sizes = np.array([len(cells_of_week[k]) for k in range(n_weeks)])
    wk_off = np.zeros(len(sizes) + 1, int)
    wk_off[1:] = np.cumsum(sizes)
    wk_season = np.array([season_ix[int(sw.season[k])] for k in range(n_weeks)])
    wk_week = np.array([int(sw.week[k]) for k in range(n_weeks)])
    wk_isfinale = np.array([bool(sw.is_finale_week[k]) for k in range(n_weeks)])
    wk_nc = sw.n_competing.to_numpy(int)
    wk_key_of = [(int(r.season), int(r.week)) for _, r in sw.iterrows()]

    # finale placement anchors (skip tied placements; only co-danced weeks)
    pa, pb = [], []
    fin_rows = ct[ct.result_type == "finalist"]
    for s in P["seasons"]:
        fin = fin_rows[fin_rows.season == s].sort_values("placement")
        recs = list(fin.itertuples())
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                # placement-ascending: recs[j] has the larger placement => worse
                w_, b_ = recs[j], recs[i]
                if w_.placement == b_.placement:
                    continue
                nw = min(int(w_.n_weeks_active), int(b_.n_weeks_active))
                ba = run_vbase[run_keys[(int(w_.season), w_.celebrity_name)]]
                bb = run_vbase[run_keys[(int(b_.season), b_.celebrity_name)]]
                for wk in range(1, nw + 1):
                    pa.append(ba + wk - 1)
                    pb.append(bb + wk - 1)

    M = Model(
        V=V, R=R,
        season_of_flat=P["flat_season"], week_of_flat=P["flat_week"],
        run_of_flat=P["flat_run"], xbar=P["xbar"], zsc=P["zsc"], logx=P["logx"],
        tot=P["tot"], celeb=P["celeb"],
        run_season=P["run_season"], run_name=P["run_name"], run_partner=P["run_partner"],
        run_industry=P["run_industry"], run_age=P["run_age"], run_nweeks=P["run_nweeks"],
        run_pl=P["run_pl"], run_vbase=P["run_vbase"], run_last_week=P["run_last"],
        run_result=P["run_result"], dmem=P["dmem"],
        ex_cells=ex_cells, ex_mask=ex_mask, ex_m=np.array(ex_m),
        ex_season=np.array(ex_season), ex_week=np.array(ex_week),
        ex_veto=np.array(ex_veto), ex_rankgrid=np.array(ex_rankgrid),
        ex_wk_seg=np.array(ex_wk_seg),
        wk_perm=wk_perm, wk_off=wk_off, wk_season=wk_season, wk_week=wk_week,
        wk_isfinale=wk_isfinale, wk_seg_of_flat=P["wk_seg_of_flat"], wk_nc=wk_nc,
        wk_key_of=wk_key_of,
        pair_a=np.array(pa, int), pair_b=np.array(pb, int),
        S=P["S"], season_names=P["seasons"],
    )
    # theta = [v (V) | g1 (R) | ka (R) | eps (S) | xi]
    M.n_theta = V + 2 * R + P["S"] + 1
    M.o_v, M.o_g1, M.o_ka = 0, V, V + R
    M.o_eps = V + 2 * R
    M.o_xi = M.o_eps + P["S"]
    M.meta = dict(wd_cells_by_week=wd_cells_by_week)
    return M


def build_model(data: dict) -> Model:
    return build_model_part2(build_model_part1(data))


# ---------------- betting rules & combined-score transforms ------------------
def softmax_outside(z: np.ndarray, seg_off: np.ndarray, perm: np.ndarray,
                    mu: float = SIG_MU) -> np.ndarray:
    """phi = exp(z)/(exp(mu) + sum exp(z)) per week segment (outside phi0)."""
    zp = z[perm]
    zs = np.add.reduceat(zp, seg_off[:-1])
    m = np.maximum(zs.max(), mu)
    e = np.exp(zp - m)
    es = np.add.reduceat(e, seg_off[:-1])
    denom = np.exp(mu - m) + es
    phi = e / np.repeat(denom, np.diff(seg_off))
    out = np.zeros_like(phi)
    out[perm] = phi
    return out


def phi_recover(utl: np.ndarray, logx: np.ndarray, mu: float = SIG_MU):
    """Fan utility z = 2*utl - logx; phi on the softmax-with-outside grid.
    Renormalized within-week shares phi_ren (sums to 1) also returned."""
    z = 2.0 * utl - logx
    phi = softmax_outside(z, None, None, mu)  # replaced in caller (needs segments)
    raise NotImplementedError


def softmax_phi(z: np.ndarray, wk_perm: np.ndarray, wk_off: np.ndarray,
                mu: float = SIG_MU):
    """Vectorized softmax with outside mass; returns phi (V,) and phi0 (n_weeks,).
    phi0 = exp(mu)/(exp(mu)+sum exp(z)) is the no-vote share of the week."""
    zp = z[wk_perm]
    zs = np.add.reduceat(zp, wk_off[:-1])
    m = np.maximum(zs, mu)                    # segmentwise max(zs, mu)
    e = np.exp(zp - np.repeat(m, np.diff(wk_off)))
    es = np.add.reduceat(e, wk_off[:-1])
    denom = np.exp(mu - m) + es
    phi0 = np.exp(mu - m) / denom
    phi_seg = e / np.repeat(denom, np.diff(wk_off))
    phi = np.zeros_like(z)
    phi[wk_perm] = phi_seg
    return phi, phi0


def phi_ren_of(phi: np.ndarray, wk_perm: np.ndarray, wk_off: np.ndarray) -> np.ndarray:
    """Within-week renormalized shares (exclude non-voters)."""
    zp = phi[wk_perm]
    ss = np.add.reduceat(zp, wk_off[:-1])
    ren = zp / np.repeat(ss, np.diff(wk_off))
    out = np.zeros_like(phi)
    out[wk_perm] = ren
    return out
