"""Model 1 main pipeline: MAP -> per-season Laplace draws -> phi -> importance
weights -> weighted fan-share stats -> validation -> CSV / NPZ / results.json.
(run.py calls pipeline(); model1_figs.py makes the figures.)"""
from __future__ import annotations
import itertools, json, time
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import minimize
from scipy.stats import kendalltau
from model1_core import (load_data, build_model, softmax_phi, phi_ren_of,
                         ETA0, KAPPA_W, N_DRAWS, SEED, CV_LOW, CV_HIGH)
from model1_obj import map_optimize, neg_log_post, unpack, week_paths, pl_paths_grad
from model1_post import draw_all_seasons, pin_hyperparams

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent.parent / "01_modeling" / "shared_data"
CHI = 1000.0          # softmax outside mass: phi0 ~ 1e-3 per week


def path_prob(us: np.ndarray, mask: np.ndarray, veto: bool) -> float:
    paths = week_paths(len(us), mask, veto)
    t, _ = pl_paths_grad(us, paths)
    return float(t)


def compute_phi_draws(u_draw: np.ndarray, M):
    n_draws = u_draw.shape[0]
    z = 2.0 * u_draw - M.logx[None, :]
    phi = np.empty_like(z)
    ren = np.empty_like(z)
    mu = np.log(CHI)
    for d in range(n_draws):
        phi[d], _ = softmax_phi(z[d], M.wk_perm, M.wk_off, mu=mu)
        ren[d] = phi_ren_of(phi[d], M.wk_perm, M.wk_off)
    return phi, ren


def importance_weights(u_draw, ren_draw, M, kappa: float = KAPPA_W):
    """Per-draw count of violated exit facts (ordinal argmin violations) and
    exp(-kappa * #violations) weights. Also returns the zero-violation mask:
    when enough draws satisfy every ordinal fact, that subset IS the posterior
    conditional on all eliminations (rejection sampling on the feasible cone)."""
    D = u_draw.shape[0]
    viol = np.zeros(D)
    n_rankgrid = 0
    for w in range(len(M.ex_cells)):
        cells = M.ex_cells[w]
        ud = u_draw[:, cells]
        m = int(M.ex_m[w])
        umin = ud.min(axis=1, keepdims=True)
        pr = np.exp(umin - ud)
        exs = np.where(M.ex_mask[w])[0]
        if m == 1 and not M.ex_veto[w]:
            a = int(exs[0])
            # violated: exit is NOT the worst combined
            viol += (pd_danger := None) if False else (ud[:, a] > ud.min(axis=1) + 1e-9)
        else:
            # violated: the exit set is not the bottom-m (count misplaced exits)
            # threshold = m-th smallest utl among all; exits above it are misplaced
            kth = np.partition(ud, m - 1, axis=1)[:, m - 1]
            viol += (ud[:, exs] > kth[:, None] + 1e-9).sum(axis=1)
        if bool(M.ex_rankgrid[w]):
            n_rankgrid += 1
            rd = ren_draw[:, cells]
            if m == 1:
                a = int(exs[0])
                viol += (rd[:, a] > rd.min(axis=1) + 1e-9)
            else:
                stays = np.where(~M.ex_mask[w])[0]
                viol += (rd[:, exs].max(1) > rd[:, stays].min(1) + 1e-9)
    lw = -kappa * viol
    lw -= lw.max()
    wts = np.exp(lw)
    wts /= wts.sum()
    return wts, viol, n_rankgrid


def weighted_quantile(draw: np.ndarray, wts: np.ndarray, qs=(0.025, 0.5, 0.975)):
    order = np.argsort(draw, axis=0)
    cw = np.cumsum(wts[order], axis=0)
    out = []
    for q in qs:
        idx = np.argmax(cw >= q, axis=0)
        cols = np.arange(draw.shape[1])
        out.append(draw[order[idx, cols], cols])
    return out


def pipeline(verbose: bool = True):
    t0 = time.time()
    M = build_model(load_data(SHARED))
    rng = np.random.default_rng(SEED)
    map_nll, th = map_optimize(M, rng, n_start=4)
    v_h, g1_h, ka_h, eps_h, xi_h = unpack(M, th)
    pin_hyperparams(M, th)
    u_map = (xi_h * M.xbar + v_h + g1_h[M.run_of_flat] + ka_h[M.run_of_flat] * M.dmem
             + eps_h[M.season_of_flat] + 0.5 * M.logx)
    if verbose:
        print(f"[1] MAP done: nll={map_nll:.2f} xi={xi_h:.3f} ({time.time()-t0:.1f}s)")
    u_draw, v_draw, g1_draw, ka_draw, lap_info = draw_all_seasons(
        M, th, N_DRAWS, np.random.default_rng(SEED + 1))
    phi_draw, ren_draw = compute_phi_draws(u_draw, M)
    if verbose:
        print(f"[2] draws done ({time.time()-t0:.1f}s)")
    wts, viol, n_rankgrid = importance_weights(u_draw, ren_draw, M, KAPPA_W)
    ess_exp = float(1.0 / (wts ** 2).sum())
    n_zero = int((viol == 0).sum())
    if n_zero >= 400:
        # primary posterior = draws consistent with ALL ordinal facts
        keep = viol == 0
        w_p = np.ones(int(keep.sum())) / float(keep.sum())
        weight_mode = "zero_violation_subset"
    else:
        # fallback: keep the least-violating quartile of draws, uniform weights
        n_keep = min(len(viol), max(400, int(0.25 * len(viol))))
        keep = np.argsort(viol, kind="stable")[:n_keep]
        w_p = np.ones(n_keep) / float(n_keep)
        weight_mode = "low_violation_top_quarter"
    rmean = w_p @ ren_draw[keep]
    rvar = np.maximum(w_p @ (ren_draw[keep] ** 2) - rmean ** 2, 0.0)
    rsd = np.sqrt(rvar)
    qlo, qmed, qhi = weighted_quantile(ren_draw[keep], w_p)
    phi_mean = w_p @ phi_draw[keep]
    cv = np.where(rmean > 1e-9, rsd / np.maximum(rmean, 1e-9), 0.0)
    iw_stats = dict(ess_exp=ess_exp, n_zero_violation=n_zero,
                    max_viol=float(viol.max()), mean_viol=float(viol.mean()))
    phi_map, _ = softmax_phi(2.0 * u_map - M.logx, M.wk_perm, M.wk_off, mu=np.log(CHI))
    ren_map = phi_ren_of(phi_map, M.wk_perm, M.wk_off)
    return dict(M=M, th=th, map_nll=map_nll, u_map=u_map, v=v_h, g1=g1_h, ka=ka_h,
             eps=eps_h, xi=xi_h, u_draw=u_draw, phi_draw=phi_draw,
             ren_draw=ren_draw, wts=w_p, keep_idx=keep, viol=viol, ess=ess_exp,
             iw_stats=iw_stats, weight_mode=weight_mode, n_rankgrid=n_rankgrid,
             n_zero=int(n_zero), rmean=rmean, rsd=rsd, qlo=qlo, qmed=qmed,
             qhi=qhi, cv=cv, phi_map=phi_map, ren_map=ren_map,
             phi_mean=phi_mean, lap_info=lap_info,
                seconds=time.time() - t0)


def exitfit_table(res: dict) -> pd.DataFrame:
    """Per exit week: posterior recovery diagnostics + baselines."""
    import math
    M = res["M"]
    rows = []
    keep = res["keep_idx"]
    for w in range(len(M.ex_cells)):
        cells = M.ex_cells[w]
        ud = res["u_draw"][keep][:, cells]
        m = int(M.ex_m[w])
        veto = bool(M.ex_veto[w])
        exs = np.where(M.ex_mask[w])[0]
        ex_set = set(exs.tolist())
        umin = ud.min(axis=1, keepdims=True)
        pr = np.exp(umin - ud)
        tp_d = np.zeros(ud.shape[0])
        for perm in itertools.permutations(exs.tolist()):
            avail = np.ones(len(cells), bool)
            P = np.ones(ud.shape[0])
            for e in perm:
                P *= pr[:, e] / (pr * avail[None, :]).sum(1)
                avail[e] = False
            tp_d += P
        p_cap = float(res["wts"] @ tp_d)
        p_cap_judge = path_prob(0.5 * M.logx[cells], M.ex_mask[w], veto)
        order = np.argsort(res["u_map"][cells])
        n, mm = len(cells), m
        rows.append(dict(
            season=int(M.season_names[M.ex_season[w]]),
            week=int(M.ex_week[w]),
            n_competing=len(cells),
            n_exits=m,
            veto_regime=int(veto),
            rank_grid=int(M.ex_rankgrid[w]),
            p_capture=p_cap,
            p_capture_judge=p_cap_judge,
            map_bottom_set_correct=int(set(order[:m].tolist()) == ex_set),
            exit_rank_in_order=";".join(str(int(np.where(order == e)[0][0]) + 1)
                                        for e in exs),
        ))
    df = pd.DataFrame(rows)
    uni = []
    for _, r in df.iterrows():
        n, m = int(r.n_competing), int(r.n_exits)
        if r.veto_regime == 1:
            uni.append(2.0 / n)
        else:
            denom = 1.0
            for j in range(m):
                denom *= (n - j)
            uni.append(math.factorial(m) / denom)
    df["p_capture_uniform"] = uni
    return df


def fanshare_table(res: dict) -> pd.DataFrame:
    """Per contestant-week fan shares + uncertainty (the deliverable grid)."""
    M = res["M"]
    rows = []
    for seg in range(M.wk_off.size - 1):
        idx = M.wk_perm[M.wk_off[seg]:M.wk_off[seg + 1]]
        sea = int(M.season_names[M.wk_season[seg]])
        wk = int(M.wk_week[seg])
        rd = res["ren_draw"][:, idx]
        # fan-vs-judge tension: top-judge couple vs bottom-judge couple in this week
        hi = int(np.argmax(idx * 0 + res["u_map"][idx] - 0.5 * M.logx[idx]))
        rows_j = []
        for c in idx:
            run = int(M.run_of_flat[c])
            rows.append(dict(
                season=sea, week=wk, celebrity=M.run_name[run],
                partner=M.run_partner[run], industry=M.run_industry[run],
                age=int(M.run_age[run]), result_type=M.run_result[run],
                placement=int(M.run_pl[run]) if M.run_pl[run] else None,
                judge_total=float(M.tot[c]),
                judge_share=float(M.xbar[c]),
                phi_share=float(res["rmean"][c]),
                phi_sd=float(res["rsd"][c]),
                phi_lo95=float(res["qlo"][c]),
                phi_hi95=float(res["qhi"][c]),
                phi_cv=float(res["cv"][c]),
                phi_map=float(res["ren_map"][c]),
                u_hat=float(res["u_map"][c]),
            ))
    return pd.DataFrame(rows)


def popularity_table(res: dict) -> pd.DataFrame:
    """Weekly popularity curve (renormalized share) per run + vs-week-1 momentum."""
    M = res["M"]
    rows = []
    for r in range(M.R):
        vb = M.run_vbase[r]
        nw = int(M.run_nweeks[r])
        cells = np.arange(vb, vb + nw)
        sh = res["rmean"][cells]
        base = sh[0]
        for j, c in enumerate(cells):
            rows.append(dict(
                season=int(M.season_names[M.run_season[r]]),
                celebrity=M.run_name[r],
                week=j + 1,
                n_weeks_run=nw,
                phi_share=float(sh[j]),
                phi_sd=float(res["rsd"][c]),
                momentum=float(sh[j] - sh[j - 1]) if j > 0 else np.nan,
                rel_to_week1=float(sh[j] / base) if base > 0 else np.nan,
                frac_run_elapsed=float((j + 1) / nw),
            ))
    return pd.DataFrame(rows)


def validation(res: dict) -> dict:
    """All Model-1 validation metrics (no ground truth needed -- the observed
    eliminations ARE the test targets). Returns a metrics dict."""
    M = res["M"]
    ef = exitfit_table(res)
    exact = ef[ef.veto_regime == 0]
    single = exact[exact.n_exits == 1]
    multi = exact[exact.n_exits >= 2]
    veto = ef[ef.veto_regime == 1]

    met = {}
    met["n_exit_weeks"] = int(len(ef))
    met["n_single_exact"] = int(len(single))
    met["n_multi_exact"] = int(len(multi))
    met["n_veto_weeks"] = int(len(veto))
    met["hit_rate_single"] = float(single.map_bottom_set_correct.mean())
    met["hit_rate_multi"] = float(multi.map_bottom_set_correct.mean())
    # hard judge-only baseline: argmin of the weekly judge total must be the exit
    judge_argmin_hits = 0
    for w in range(len(M.ex_cells)):
        if M.ex_veto[w] or M.ex_m[w] != 1:
            continue
        cells = M.ex_cells[w]
        if int(np.argmin(M.tot[cells])) == int(np.argmax(M.ex_mask[w])):
            judge_argmin_hits += 1
    met["hit_rate_single_exact_judge_only"] = judge_argmin_hits / max(int(len(single)), 1)
    met["n_single_exact"] = int(len(single))
    # mean capture probabilities (soft PL baselines), renamed for clarity
    met["mean_p_capture_judge_single"] = float(single.p_capture_judge.mean())
    met["mean_p_capture_judge_multi"] = float(multi.p_capture_judge.mean())
    met["mean_p_capture"] = float(ef.p_capture.mean())
    if len(veto):
        ranks = veto.exit_rank_in_order.apply(
            lambda s: min(int(t) for t in str(s).split(";")))
        met["veto_bottom2_rate"] = float((ranks <= 2).mean())
    else:
        met["veto_bottom2_rate"] = float("nan")
    met["logloss_model"] = float(-np.log(ef.p_capture.clip(1e-12)).mean())
    met["logloss_judge"] = float(-np.log(ef.p_capture_judge.clip(1e-12)).mean())
    met["logloss_uniform"] = float(-np.log(ef.p_capture_uniform.clip(1e-12)).mean())
    met["mean_p_capture_exact"] = float(exact.p_capture.mean())
    met["mean_p_capture_judge_exact"] = float(exact.p_capture_judge.mean())
    met["mean_p_capture_uniform_exact"] = float(exact.p_capture_uniform.mean())
    met["mean_p_capture_judge_all"] = float(ef.p_capture_judge.mean())
    met["mean_p_capture_uniform_all"] = float(ef.p_capture_uniform.mean())

    # judge-vs-fan tension: weekly sd of (z_fan - z_judge)
    tens = []
    for seg in range(M.wk_off.size - 1):
        idx = M.wk_perm[M.wk_off[seg]:M.wk_off[seg + 1]]
        if len(idx) < 3:
            continue
        zf = res["u_map"][idx] - 0.5 * M.logx[idx]      # fan z on log-share scale
        zj = M.logx[idx] - M.logx[idx].mean()
        tens.append((zf - zf.mean()).std(ddof=1) + (zj - zj.mean()).std(ddof=1))
    met["mean_weekly_fanjudge_tension"] = float(np.mean(tens))

    # coverage of the 95% interval on renormalized shares
    cover_map = (res["qlo"] <= res["ren_map"]) & (res["ren_map"] <= res["qhi"])
    cover_mean = (res["qlo"] <= res["rmean"]) & (res["rmean"] <= res["qhi"])
    met["coverage_95_map_point"] = float(cover_map.mean())
    met["coverage_95_postmean"] = float(cover_mean.mean())
    # CV by week position: week-1 rows vs mid-run rows
    isw1 = M.week_of_flat == 1
    mid = (M.week_of_flat >= 3) & (M.week_of_flat <= np.quantile(M.week_of_flat, 0.8))
    met["cv_week1"] = float(res["cv"][isw1].mean())
    met["cv_midrun"] = float(res["cv"][mid].mean())
    met["cv_contrast"] = met["cv_week1"] / met["cv_midrun"]
    met["cv_low_frac"] = float((res["cv"] < CV_LOW).mean())
    met["cv_high_frac"] = float((res["cv"] > CV_HIGH).mean())
    # drawing-level agreement
    met["ess"] = res["ess"]
    met["n_total_pairs"] = int(len(M.pair_a))
    met["pair_anchor_rmse"] = float(np.sqrt(np.mean(np.maximum(
        0.5 - (res["u_map"][M.pair_b] - res["u_map"][M.pair_a]), 0) ** 2))) \
        if len(M.pair_a) else 0.0
    met["map_theta_sd_v"] = float(res["v"].std())
    met["map_theta_sd_g1"] = float(res["g1"].std())
    met["map_theta_sd_ka"] = float(res["ka"].std())
    return met


def leave_one_week_out(res: dict, n_weeks: int = 12, seed: int = 7) -> pd.DataFrame:
    """LOO stability: refit without week w's elimination; compare phi ranks."""
    M = res["M"]
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(M.ex_cells), size=min(n_weeks, len(M.ex_cells)),
                      replace=False)
    rows = []
    for w in pick:
        nll_loo, th_loo = map_optimize(M, rng, n_start=1, drop_week=int(w))
        v, g1, ka, eps, xi = unpack(M, th_loo)
        u_l = (xi * M.xbar + v + g1[M.run_of_flat] + ka[M.run_of_flat] * M.dmem
               + eps[M.season_of_flat] + 0.5 * M.logx)
        # compare within the season of week w
        sea = M.ex_season[w]
        c_mask = M.season_of_flat == sea
        tau_all = kendalltau(res["u_map"][c_mask], u_l[c_mask]).statistic
        # restrict to the exit week cells + its season finals (local structure)
        cells = M.ex_cells[w]
        tau_local = kendalltau(res["u_map"][cells], u_l[cells]).statistic
        rows.append(dict(season=int(M.season_names[sea]), week=int(M.ex_week[w]),
                         tau_season_same=tau_all, tau_exit_week=tau_local))
    return pd.DataFrame(rows)


def main(outdir: Path = HERE):
    outdir = Path(outdir)
    res = pipeline(verbose=True)
    M = res["M"]
    met = validation(res)

    # ridge baseline for the rejected fish (judge-only + prior mean) comparison
    ef = exitfit_table(res)
    fan = fanshare_table(res)
    pop = popularity_table(res)
    # margin: top-2 combined-rank gap per week on the percent grid
    loo = leave_one_week_out(res)
    met["loo_tau_mean"] = float(loo.tau_season_same.mean())
    met["loo_tau_season_min"] = float(loo.tau_season_same.min())
    met["loo_tau_min"] = float(loo.tau_exit_week.min())
    met["loo_tau_local_mean"] = float(loo.tau_exit_week.mean())

    # ---------------- write outputs ----------------
    fan.to_csv(outdir / "model1_fanshare.csv", index=False)
    ef.to_csv(outdir / "model1_exitfit.csv", index=False)
    pop.to_csv(outdir / "model1_popularity_timeseries.csv", index=False)
    np.savez_compressed(outdir / "model1_draws.npz",
                        u_draw=res["u_draw"], ren_draw=res["ren_draw"],
                        wts=res["wts"], viol=res["viol"], u_map=res["u_map"])
    loo.to_csv(outdir / "model1_loo.csv", index=False)
    # aggregate LOO exit-week-scope mean tau, computed from the written csv
    loo_csv = pd.read_csv(outdir / "model1_loo.csv")
    met["loo_tau_local_mean"] = float(loo_csv.tau_exit_week.mean())
    met["loo_tau_mean"] = float(loo_csv.tau_season_same.mean())
    met["loo_tau_season_min"] = float(loo_csv.tau_season_same.min())
    met["loo_tau_min"] = float(loo_csv.tau_exit_week.min())
    keep = res["keep_idx"]
    w_all = np.zeros(len(res["viol"]))
    w_all[keep] = res["wts"]
    ds = pd.DataFrame({
        "draw": np.arange(len(res["viol"])),
        "weight": w_all,
        "violation": res["viol"],
        "kept": np.isin(np.arange(len(res["viol"])), keep).astype(int),
    })
    ds.to_csv(outdir / "model1_draw_summary.csv", index=False)

    # NOTE: wall-clock timing is intentionally NOT stored here (it makes
    # results.json machine/run dependent and breaks the reproducibility check).
    summary = {
        "map_nll": res["map_nll"],
        "xi_hat": float(res["xi"]),
        "season_eps": res["eps"].tolist(),
        "g1_sd": float(res["g1"].std()),
        "ka_sd": float(res["ka"].std()),
        "nlatent": int(M.V),
        "n_params": int(M.n_theta),
        "metrics": met,
        "laplace": res["lap_info"],
    }
    with open(outdir / "results.json", "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary["metrics"], indent=1, default=float))
    print(f"total time {res['seconds']:.1f}s")
    return res, met


if __name__ == "__main__":
    main()
