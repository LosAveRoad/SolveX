#!/usr/bin/env python3
"""
Model 2 runner: Judge-Fan Fusion Engine — rank vs percentage combination rules.

Deterministic end-to-end (SEED=42):
  A. calibrate (U coordinate ascent  x  theta/sigma grid, composite pseudo-likelihood
     of the observed elimination record under the era-correct rule);
  B. invert phi for every celebrity-week + 90% bands (profile-grid parameter
     posterior  x  lognormal vote noise);
  C. observed-era replay validation (cut-match, bottom Jaccard, placement MAE/tau);
  D. counterfactual replays under Rule R (rank), Rule P (percentage), Rule Z
     (z-scored) with same fan votes -> rule-disagreement gamma_s;
  E. controversy table + fan-vote flip multipliers (elasticity);
  F. dance-off overlay for S28+;
  G. recommendation metrics (judge-consistency tau, fan-voice Gini, shock rate);
  H. results.json + CSVs + figures F4-F8 + handoff.json.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model2_lib as M  # noqa: E402

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

plt.rcParams["font.family"] = "serif"

OUT = HERE
FIGDIR = os.path.join(HERE, "figures")
SHARED = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
          "r7-c3-submit-mwp2gic2/01_modeling/shared_data")
os.makedirs(FIGDIR, exist_ok=True)

RESULTS = {}


def log(*a):
    print(*a, flush=True)


# ==================================================================================
# Step A: calibration
# ==================================================================================
def calibrate(corpus, blocks=3):
    """Alternate U coordinate ascent <-> (alpha,beta,sigma) grid; keep the best-seen
    (theta, U) by composite loglik, then run one refinement cycle (CA at best theta,
    grid at refined U), retaining the better of the two (monotone bookkeeping)."""
    U = {}
    theta = (1.0, 0.5)
    sigma = 0.15
    best = None
    trace = []
    for block in range(blocks):
        U, _ = corpus.coord_ascent_U(theta, sigma, u_init=U, sweeps=2, verbose=False)
        theta, _ = corpus.grid_theta(U, verbose=False)
        sigma = theta[2]
        ll = corpus.total_ll(theta, sigma, U)
        trace.append({"block": block + 1, "alpha": theta[0], "beta": theta[1],
                      "sigma": sigma, "loglik": ll})
        log(f"  block {block+1}: alpha={theta[0]}, beta={theta[1]}, sigma={sigma}, "
            f"loglik={ll:.2f}")
        if best is None or ll > best[0]:
            best = (ll, dict(U), theta)
    # refinement cycle at the best-seen solution
    ll0, U_best0, theta_best0 = best
    U_ref, _ = corpus.coord_ascent_U(theta_best0, theta_best0[2],
                                     u_init=U_best0, sweeps=2, verbose=False)
    theta_ref, _ = corpus.grid_theta(U_ref, verbose=False)
    ll_ref = corpus.total_ll(theta_ref, theta_ref[2], U_ref)
    trace.append({"block": "refine", "alpha": theta_ref[0], "beta": theta_ref[1],
                  "sigma": theta_ref[2], "loglik": ll_ref})
    log(f"  refine: alpha={theta_ref[0]}, beta={theta_ref[1]}, sigma={theta_ref[2]}, "
        f"loglik={ll_ref:.2f}")
    if ll_ref >= ll0:
        U, theta = U_ref, theta_ref
    else:
        U, theta = U_best0, theta_best0
    return U, theta, trace


# ==================================================================================
# Step B: phi inversion + 90% bands
# ==================================================================================
def invert_phi(corpus, U, theta_hat, n_post=120):
    alpha, beta = theta_hat[0], theta_hat[1]
    post, post_grid = corpus.theta_posterior_samples(theta_hat, U, n_samples=n_post)
    A, B = post.alpha.to_numpy(), post.beta.to_numpy()

    rows = []
    M_BAND = 150
    for s in sorted(corpus.ctxs):
        ctx = corpus.ctxs[s]
        career = corpus.careers[s]
        for wi, wc in enumerate(ctx["week_ctx"]):
            u = np.array([U.get(r, 0.0) for r in wc["row_ids"]])
            log_rho = np.log(wc["rho"])
            log_cJ = np.log(np.maximum(career[wi], 1e-9))
            phi = M.phi_point(u, log_rho, log_cJ, alpha, beta)
            # (a) parameter-posterior band: point phi per posterior draw
            band = np.empty((len(post), len(wc["row_ids"])))
            for di in range(len(post)):
                band[di] = M.phi_point(u, log_rho, log_cJ, A[di], B[di])
            # (b) vote-noise band (lognormal, common random numbers)
            d = phi[None, :] * np.exp(theta_hat[2] * wc["eps"][:M_BAND])
            d = d / d.sum(axis=1, keepdims=True)
            lo = np.minimum(np.percentile(band, 5, axis=0), np.percentile(d, 5, axis=0))
            hi = np.maximum(np.percentile(band, 95, axis=0), np.percentile(d, 95, axis=0))
            for j, rid in enumerate(wc["row_ids"]):
                rows.append({"row_id": rid, "season": s, "week": wc["week"],
                             "celebrity_name": wc["names"][j],
                             "phi_hat": phi[j], "phi_lo90": lo[j], "phi_hi90": hi[j],
                             "judge_score": wc["S"][j], "judge_share": wc["rho"][j],
                             "n_active": len(wc["row_ids"])})
    phi_tab = pd.DataFrame(rows).sort_values(["season", "week", "phi_hat"],
                                             ascending=[True, True, False])
    return phi_tab, post_grid


# ==================================================================================
# Step C: observed-era validation
# ==================================================================================
def validate_observed_era(corpus, U, theta):
    rows = []
    for s in sorted(corpus.ctxs):
        ctx = corpus.ctxs[s]
        rule, doff = M.era_rule(s)
        res = M.simulate_season(ctx, theta, U, rule, dance_off=doff)
        met = M.season_reproduction(res, ctx)
        met.update({"season": s, "rule": rule + ("+danceoff" if doff else "")})
        rows.append(met)
    val_tab = pd.DataFrame(rows)
    pooled = {"cut_match_rate": float(val_tab.cut_match_rate.mean()),
              "bottom_jaccard_mean": float(val_tab.bottom_jaccard_mean.mean()),
              "placement_mae_mean": float(val_tab.placement_mae.mean()),
              "placement_tau_mean": float(val_tab.placement_tau.mean()),
              "n_seasons": int(len(val_tab))}
    return val_tab, pooled


# ==================================================================================
# Step D: counterfactual replays (R, P, Z everywhere; dance-off overlays for S28+)
# ==================================================================================
def replay_seasons(corpus, U, theta):
    season_runs = {}
    replay_rows = []
    for s in sorted(corpus.ctxs):
        ctx = corpus.ctxs[s]
        runs = {}
        for rule, doff, key in [("rank", False, "R"), ("pct", False, "P"),
                                ("z", False, "Z")]:
            res = M.simulate_season(ctx, theta, U, rule, dance_off=doff)
            runs[key] = res
            met = M.season_reproduction(res, ctx)
            met.update({"season": s, "rule": key})
            replay_rows.append(met)
        rule_obs, doff_obs = M.era_rule(s)
        runs["obs"] = M.simulate_season(ctx, theta, U, rule_obs, dance_off=doff_obs)
        if s >= 28:
            runs["R_doff"] = M.simulate_season(ctx, theta, U, "rank", dance_off=True)
            runs["P_doff"] = M.simulate_season(ctx, theta, U, "pct", dance_off=True)
        season_runs[s] = runs

    # weekly elimination-set table + gamma_s
    replay_tab = []
    gamma_rows = []
    for s in sorted(corpus.ctxs):
        ctx = corpus.ctxs[s]
        runs = season_runs[s]
        obs_by_week = {wc["week"]: set(np.array(wc["row_ids"])[wc["elim_here"]])
                       for wc in ctx["week_ctx"]}
        n_dis = n_elim_weeks = 0
        for wi, wc in enumerate(ctx["week_ctx"]):
            w, k = wc["week"], ctx["kvec"][wi]
            names = ctx["names"]

            def fmt(st):
                return ";".join(names[i] for i in sorted(st))
            row = {"season": s, "week": w, "k": k,
                   "obs": fmt(obs_by_week.get(w, set()))}
            for key in ["R", "P", "Z", "obs"]:
                st = set(runs[key]["records"][wi]["cut_ids"])
                row[key] = fmt(st)
                row[f"{key}_match_obs"] = bool(st == obs_by_week.get(w, set()))
            if k > 0:
                n_elim_weeks += 1
                if set(runs["R"]["records"][wi]["cut_ids"]) != \
                        set(runs["P"]["records"][wi]["cut_ids"]):
                    n_dis += 1
            replay_tab.append(row)
        gamma_rows.append({"season": s, "weeks_with_elim": n_elim_weeks,
                           "disagreement_weeks_R_vs_P": n_dis,
                           "gamma_s": n_dis / max(n_elim_weeks, 1)})
    return season_runs, pd.DataFrame(replay_tab), pd.DataFrame(gamma_rows)


# ==================================================================================
# Step E: controversy table + flip multipliers
# ==================================================================================
def s28plus_rule_overlay(corpus, U, theta):
    """S28+: event-weighted cut reproduction under all four rule/stage combos
    (rank / percentage, with / without the judges' dance-off). Identifies what
    drives the S28+ divergence between the engine and the observed record."""
    rows = []
    for rule, doff, key in [("rank", False, "R"), ("pct", False, "P"),
                            ("rank", True, "R_doff"), ("pct", True, "P_doff")]:
        matched = events = 0
        jac_vals = []
        for s in range(28, 35):
            ctx = corpus.ctxs[s]
            res = M.simulate_season(ctx, theta, U, rule, dance_off=doff)
            m = M.season_reproduction(res, ctx)
            matched += m["matched_events"]
            events += m["total_cut_events"]
            jac_vals.append(m["bottom_jaccard_mean"])
        rows.append({"rule": key, "matched_events": matched, "cut_events": events,
                     "event_rate": matched / events,
                     "mean_bottom_jaccard": float(np.mean(jac_vals))})
    return pd.DataFrame(rows)


def hdi_bound_sensitivity(corpus, U, theta, phi_tab, named):
    """Plan-required HDI-bound counterfactuals: re-run Rule R and Rule P
    controversate replays with the focal celebrity's phi at its 90% band edges
    (lo/hi in every week they danced; other couples at point phi), via the
    phi-mult-weekly hook. Verdicts robust = placement direction unchanged."""
    rows = []
    for nm, s in named:
        ctx = corpus.ctxs[s]
        cnd = ctx["roster"][ctx["roster"].celebrity_name == nm]
        if not len(cnd):
            continue
        rid = int(cnd.row_id.iloc[0])
        d = phi_tab[(phi_tab.celebrity_name == nm) & (phi_tab.season == s)].sort_values("week")
        if not len(d):
            continue
        lo_m = (d.phi_lo90 / d.phi_hat).to_numpy()
        hi_m = (d.phi_hi90 / d.phi_hat).to_numpy()
        row = {"celebrity": nm, "season": s}
        for rule, key in [("rank", "R"), ("pct", "P")]:
            base = M.simulate_season(ctx, theta, U, rule, dance_off=False)
            row[f"{key}_base"] = base["placements"][rid]
            for tag, mults in [("lo", lo_m), ("hi", hi_m)]:
                res = M.simulate_season(ctx, theta, U, rule, dance_off=False,
                                        phi_mult_weekly={rid: list(mults)})
                row[f"{key}_{tag}"] = res["placements"][rid]
        rows.append(row)
    return pd.DataFrame(rows)


def analyze_controversies(corpus, U, theta, season_runs):
    named = [("Jerry Rice", 2), ("Billy Ray Cyrus", 4), ("Bristol Palin", 11),
             ("Bobby Bones", 27), ("Mya", 9), ("Donny Osmond", 9),
             ("Sabrina Bryan", 5), ("Sabrina Bryan", 15)]
    rows, flip_rows = [], []
    seen = set()
    mults = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
    for nm, s in named:
        ctx = corpus.ctxs[s]
        cnd = ctx["roster"][ctx["roster"].celebrity_name == nm]
        if not len(cnd):
            log(f"  !! {nm} not in S{s}")
            continue
        rid = int(cnd.row_id.iloc[0])
        if (nm, s) in seen:
            continue
        seen.add((nm, s))
        runs = season_runs[s]
        obs_place = float(cnd.placement.iloc[0])
        rule, _ = M.era_rule(s)
        # dance-off overlay for this season and contestant (S28+ only difference)
        r_do = M.simulate_season(ctx, theta, U, rule, dance_off=True)
        n_flip_doff = sum(1 for r in runs["R"]["placements"]
                          if r in r_do["placements"] and
                          abs(runs["R"]["placements"][r] - r_do["placements"][r]) >= 1e-9)
        row = {"celebrity": nm, "season": s,
               "obs_placement": obs_place,
               "obs_results": cnd.results.iloc[0],
               "R_placement": runs["R"]["placements"][rid],
               "P_placement": runs["P"]["placements"][rid],
               "Z_placement": runs["Z"]["placements"][rid],
               "obs_rule_placement": runs["obs"]["placements"][rid],
               "R_doff_placement": r_do["placements"][rid],
               "danceoff_flips_in_season": n_flip_doff,
               "mean_judge_score": float(cnd.mean_week_score.iloc[0])}
        # elasticity probes: placement delta for +/- fan multipliers (from week 1)
        probes = {}
        for m in mults:
            if m == 1.0:
                continue
            rU = M.simulate_season(ctx, theta, U, "rank", dance_off=False,
                                   phi_mult={rid: m}, mult_from_week=1)
            rP = M.simulate_season(ctx, theta, U, "pct", dance_off=False,
                                   phi_mult={rid: m}, mult_from_week=1)
            row[f"R_place_x{m:g}"] = rU["placements"][rid]
            row[f"P_place_x{m:g}"] = rP["placements"][rid]
            flip_rows.append({"celebrity": nm, "season": s, "multiplier": m,
                              "R_placement": rU["placements"][rid],
                              "P_placement": rP["placements"][rid]})
            probes[m] = (rU["placements"][rid], rP["placements"][rid])
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(flip_rows)


# ==================================================================================
# Step F: dance-off overlay (S28+): with vs without judge dance-off under Rule R
# ==================================================================================
def danceoff_overlay(corpus, U, theta, season_runs):
    """S28+: compare Rule R without vs with the judges' dance-off stage."""
    rows = []
    for s in sorted(corpus.ctxs):
        if s < 28:
            continue
        ctx = corpus.ctxs[s]
        r_no = season_runs[s]["R"]
        r_do = M.simulate_season(ctx, theta, U, "rank", dance_off=True)
        p_do = M.simulate_season(ctx, theta, U, "pct", dance_off=True)
        n_elim = sum(1 for wi in range(len(ctx["week_ctx"])) if ctx["kvec"][wi] > 0)
        weeks_changed = [ctx["week_ctx"][wi]["week"]
                         for wi in range(len(ctx["week_ctx"]))
                         if ctx["kvec"][wi] > 0 and
                         set(r_no["records"][wi]["cut_ids"]) !=
                         set(r_do["records"][wi]["cut_ids"])]
        n_flip = sum(1 for r in r_no["placements"]
                     if r in r_do["placements"]
                     and abs(r_no["placements"][r] - r_do["placements"][r]) >= 1e-9)
        rows.append({"season": s, "elim_weeks": n_elim,
                     "weeks_danceoff_changes_cut": len(weeks_changed),
                     "changed_weeks": ";".join(str(w) for w in weeks_changed),
                     "n_placements_shifted": n_flip})
    return pd.DataFrame(rows)



# ==================================================================================
# Step G: recommendation metrics
# ==================================================================================
def recommendation_metrics(corpus, U, theta, season_runs):
    rows = []
    for s in sorted(corpus.ctxs):
        ctx = corpus.ctxs[s]
        runs = season_runs[s]
        roster_idx = ctx["roster"].set_index("row_id")
        rids = list(roster_idx.index)
        # season mean judge percentile per contestant (medium of weekly percentiles)
        acc = {}
        for wc in ctx["week_ctx"]:
            pr = pd.Series(wc["S"]).rank(pct=True).to_numpy()
            for rid, p in zip(wc["row_ids"], pr):
                acc.setdefault(rid, []).append(p)
        mean_jp = {r: float(np.mean(v)) for r, v in acc.items()}
        row = {"season": s}
        for key in ["R", "P", "Z"]:
            res = runs[key]
            pl = res["placements"]
            mask = [r for r in rids if r in pl and np.isfinite(pl[r])]
            row[f"{key}_tau"] = M.kendall_tau([mean_jp[r] for r in mask],
                                              [pl[r] for r in mask])
            # fan-voice Gini of total phi within season
            tot_phi = {r: 0.0 for r in rids}
            for rec in res["records"]:
                for rid, p in zip(rec["rows"], rec["phi"]):
                    if rid in tot_phi:
                        tot_phi[rid] += p
            row[f"{key}_gini"] = M.gini(list(tot_phi.values()))
            # shock rate: cuts hitting a current top-3 phi couple
            shocks = tot_cuts = 0
            for rec in res["records"]:
                if rec["k"] > 0 and len(rec["rows"]) > 3:
                    top3 = set(np.array(rec["rows"])[np.argsort(-rec["phi"])[:3]])
                    shocks += len(top3 & set(rec["cut_ids"]))
                    tot_cuts += rec["k"]
            row[f"{key}_shock_rate"] = shocks / max(tot_cuts, 1)
        rows.append(row)
    return pd.DataFrame(rows)


# ==================================================================================
# Step H: figures
# ==================================================================================
def make_figures(corpus, phi_tab, val_tab, gamma_tab, season_runs, ctab, flip_tab,
                 rec_tab, metric_tabs, doff_tab=None, hdib_tab=None):
    figs = {}

    # ---- F4: rule-disagreement rate by season (bar) + era shading ----
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    colors = ["#c44e52" if g > 0 else "#4c72b0" for g in gamma_tab.gamma_s]
    ax.bar(gamma_tab.season, gamma_tab.gamma_s, color=colors)
    ax.axvspan(2.5, 27.5, color="grey", alpha=0.08)
    ax.text(15, gamma_tab.gamma_s.max() * 1.02, "percentage era (S3-27)",
            ha="center", fontsize=9, color="grey")
    ax.set_xlabel("season")
    ax.set_ylabel(r"rule-disagreement rate $\gamma_s$  (weeks R$\neq$P / elim weeks)")
    ax.set_title("Weekly elimination disagreement between rank and percentage rules")
    ax.set_ylim(0, max(0.55, gamma_tab.gamma_s.max() * 1.15))
    fig.savefig(os.path.join(FIGDIR, "F4_gamma_by_season.png"), bbox_inches="tight")
    plt.close(fig)
    figs["F4_gamma_by_season"] = "weekly disagreement rate between rules per season"

    # ---- F5: placement-flow (observed -> Rule R -> Rule P) for controversies ----
    # per-contestant panel rows (row height fixed) -> no overlapping labels; a
    # symbol legend identifies observed / R / P; arrows show the shift direction.
    n_rows = len(ctab)
    fig, ax = plt.subplots(figsize=(9, 0.72 * n_rows + 2.0), dpi=300)
    for i, (_, r) in enumerate(ctab.iterrows()):
        y = n_rows - 1 - i                    # first contestant on top
        jc = max(11.0, float(r.obs_placement), float(r.R_placement),
                 float(r.P_placement))
        y_obs = y - 0.40 * r.obs_placement / jc
        y_R = y - 0.40 * r.R_placement / jc
        y_P = y - 0.40 * r.P_placement / jc
        ax.annotate("", xy=(1.0, y_R), xytext=(0.0, y_obs),
                    arrowprops=dict(arrowstyle="->", color="#4c72b0", lw=1.2,
                                    connectionstyle="arc3,rad=-0.22"))
        ax.annotate("", xy=(1.0, y_P), xytext=(0.0, y_obs),
                    arrowprops=dict(arrowstyle="->", color="#c44e52", lw=1.2,
                                    connectionstyle="arc3,rad=0.22"))
        for xx, yy, c, mk in [(0.0, y_obs, "#555555", "o"),
                              (1.0, y_R, "#4c72b0", "o"),
                              (1.0, y_P, "#c44e52", "^")]:
            ax.scatter([xx], [yy], color=c, marker=mk, s=38, zorder=3)
        ax.text(-0.03, y_obs, f"obs {int(r.obs_placement)}", ha="right", va="center",
                fontsize=8.5, color="#555555")
        ax.text(1.03, y_R, f"R {int(r.R_placement)}", va="center", fontsize=8.5,
                color="#4c72b0")
        ax.text(1.13, y_P, f"P {int(r.P_placement)}", va="center", fontsize=8.5,
                color="#c44e52")
        ax.text(1.26, y, f"{r.celebrity} (S{int(r.season)})", va="center", fontsize=9.5)
    ax.set_xlim(-0.30, 1.75)
    ax.set_ylim(-0.55, n_rows + 0.35)
    ax.set_xticks([0.0, 1.0])
    ax.set_xticklabels(["observed placement", "counterfactual placement"])
    ax.set_yticks([])
    handles = [plt.Line2D([], [], color="#555555", marker="o", ls="", label="observed"),
               plt.Line2D([], [], color="#4c72b0", marker="o", ls="", label="Rule R (rank)"),
               plt.Line2D([], [], color="#c44e52", marker="^", ls="", label="Rule P (percentage)")]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.02),
              ncol=3, fontsize=8.5, frameon=False)
    ax.set_title("Named controversies: observed placement vs replay under each rule",
                 fontsize=11.5, y=1.10)
    for sp in ["top", "right", "left"]:
        ax.spines[sp].set_visible(False)
    fig.savefig(os.path.join(FIGDIR, "F5_placement_flow.png"), bbox_inches="tight")
    plt.close(fig)
    figs["F5_placement_flow"] = "controversy placements under each rule"

    # ---- F6: judge-consistency vs fan-impact scatter (per season, R vs P) ----
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.scatter(rec_tab.R_tau, rec_tab.R_gini, color="#4c72b0", s=26,
               label="Rule R (rank)")
    ax.scatter(rec_tab.P_tau, rec_tab.P_gini, color="#c44e52", s=26, marker="^",
               label="Rule P (percentage)")
    for _, r in rec_tab.iterrows():   # connect seasons
        ax.plot([r.R_tau, r.P_tau], [r.R_gini, r.P_gini], color="grey",
                alpha=0.25, lw=0.7)
    ax.set_xlabel("judge-consistency  (Kendall τ between placement and mean judge percentile; τ → −1 = judge-consistent)")
    ax.set_ylabel("fan-voice dispersion (Gini of total φ̂ per contestant)")
    ax.set_title("Rank vs percentage rule across all seasons")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, "F6_tau_vs_gini.png"), bbox_inches="tight")
    plt.close(fig)
    figs["F6_tau_vs_gini"] = "judge-consistency vs fan-impact per rule"

    # ---- F7: player trajectory with band (Bobby Bones S27) ----
    figs.update(plot_trajectory(phi_tab, "Bobby Bones", 27, "F7_bobbybones_phi.png"))
    figs.update(plot_trajectory(phi_tab, "Jerry Rice", 2, "F7_jerryrice_phi.png"))

    # ---- F8: phi band width by week (certainty) ----
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    phi_tab2 = phi_tab.copy()
    phi_tab2["rel_width"] = (phi_tab2.phi_hi90 - phi_tab2.phi_lo90) / \
        phi_tab2.phi_hat.clip(lower=1e-6)
    med = phi_tab2.groupby("week").rel_width.median()
    q1 = phi_tab2.groupby("week").rel_width.quantile(0.25)
    q3 = phi_tab2.groupby("week").rel_width.quantile(0.75)
    ax.fill_between(med.index, q1, q3, alpha=0.3, color="#4c72b0", label="IQR")
    ax.plot(med.index, med, color="#4c72b0", marker="o", label="median")
    ax.set_xlabel("week in season"); ax.set_ylabel("relative 90% band width of φ̂")
    ax.set_title("Fan-vote estimate certainty by week")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, "F8_bandwidth_by_week.png"), bbox_inches="tight")
    plt.close(fig)
    figs["F8_bandwidth_by_week"] = "certainty of φ̂ across weeks"

    # ---- F9: validation (cut-match by season, era-correct) ----
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    val_sorted = val_tab.sort_values("season")
    ax.bar(val_sorted.season, val_sorted.cut_match_rate,
           color=["#55a868" if c >= 0.5 else "#c44e52" for c in
                  val_sorted.cut_match_rate])
    ax.axhline(val_tab.cut_match_rate.mean(), color="black", ls="--",
               label=f"pooled mean = {val_tab.cut_match_rate.mean():.2f}")
    ax.set_xlabel("season"); ax.set_ylabel("exact cut-match rate vs observed")
    ax.set_title("Observed-era rule replay: eliminated-couple reproduction")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, "F9_validation_by_season.png"),
                bbox_inches="tight")
    plt.close(fig)
    figs["F9_validation_by_season"] = "era-correct replay reproduction per season"

    # ---- F10: controversy flip curves (placement vs fan multiplier) ----
    if flip_tab is not None and len(flip_tab):
        fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
        palette = plt.cm.tab10(np.linspace(0, 1, 10))
        combos = flip_tab.groupby(["celebrity", "season"])
        for i, ((nm, s), d) in enumerate(combos):
            c = palette[i % 10]
            d = d.sort_values("multiplier")
            ax.plot(d.multiplier, d.R_placement, marker="o", color=c, ls="-",
                    label=f"{nm} S{s} — R")
            ax.plot(d.multiplier, d.P_placement, marker="^", color=c, ls="--",
                    label=f"{nm} S{s} — P")
        ax.set_xscale("log", base=2)
        ax.set_xticks(mults := [0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0])
        ax.set_xticklabels(["x0.125", "x0.25", "x0.5", "x1", "x2", "x4", "x8", "x16"])
        ax.invert_yaxis()
        ax.set_xlabel("fan-vote multiplier applied to the celebrity (from week 1)")
        ax.set_ylabel("final placement (1 = winner)")
        ax.set_title("Flip curves: celebrity placement vs fan-vote multiplier")
        ax.legend(fontsize=6.5, ncol=2)
        fig.savefig(os.path.join(FIGDIR, "F10_flip_curves.png"), bbox_inches="tight")
        plt.close(fig)
        figs["F10_flip_curves"] = "controversy flip curves (placement vs fan multiplier)"

    # ---- F11: dance-off overlay effect by season (S28+) ----
    if doff_tab is not None and len(doff_tab):
        fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
        ax.bar(doff_tab.season - 0.18, doff_tab.elim_weeks, width=0.36,
               color="#bbbbbb", label="elimination weeks")
        ax.bar(doff_tab.season + 0.18, doff_tab.weeks_danceoff_changes_cut,
               width=0.36, color="#c44e52",
               label="weeks where dance-off stage changes the cut")
        ax.set_xticks(doff_tab.season)
        ax.set_xlabel("season (28+)"); ax.set_ylabel("weeks")
        ax.set_title("Judges' dance-off overlay: changed eliminations per season")
        ax.legend()
        fig.savefig(os.path.join(FIGDIR, "F11_danceoff_flips.png"), bbox_inches="tight")
        plt.close(fig)
        figs["F11_danceoff_flips"] = "dance-off overlay effect by season (S28+)"

    # ---- F12: HDI-bound sensitivity (placement at phi 90% band edges) ----
    if hdib_tab is not None and len(hdib_tab):
        fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
        labels, base_r, lo_r, hi_r, base_p, lo_p, hi_p = [], [], [], [], [], [], []
        for _, r in hdib_tab.iterrows():
            labels.append(f"{r.celebrity}\\nS{int(r.season)}")
            base_r.append(r.R_base); lo_r.append(r.R_lo); hi_r.append(r.R_hi)
            base_p.append(r.P_base); lo_p.append(r.P_lo); hi_p.append(r.P_hi)
        x = np.arange(len(labels))
        w = 0.32
        ax.errorbar(x - w/2, base_r, yerr=[np.array(base_r)-np.minimum(lo_r, hi_r),
                                           np.maximum(lo_r, hi_r)-np.array(base_r)],
                    fmt="o", color="#4c72b0", capsize=4, label="Rule R (rank)")
        ax.errorbar(x + w/2, base_p, yerr=[np.array(base_p)-np.minimum(lo_p, hi_p),
                                           np.maximum(lo_p, hi_p)-np.array(base_p)],
                    fmt="^", color="#c44e52", capsize=4, label="Rule P (percentage)")
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_ylabel("final placement (1 = winner)")
        ax.set_title("HDI-bound sensitivity: controversy placements with $\\hat{\\varphi}$"
                     " at its 90% band edges (vs point estimate)")
        ax.legend()
        fig.savefig(os.path.join(FIGDIR, "F12_hdi_sensitivity.png"), bbox_inches="tight")
        plt.close(fig)
        figs["F12_hdi_sensitivity"] = "HDI-bound sensitivity of controversy placements"

    return figs


def plot_trajectory(phi_tab, celeb, season, fname):
    d = phi_tab[(phi_tab.celebrity_name == celeb) & (phi_tab.season == season)]
    if not len(d):
        return {}
    d = d.sort_values("week")
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.plot(d.week, d.phi_hat, marker="o", color="#4c72b0", label="φ̂ point estimate")
    ax.fill_between(d.week, d.phi_lo90, d.phi_hi90, alpha=0.25, color="#4c72b0",
                    label="90% band (parameter ⊕ vote noise)")
    # judge-share reference
    ax.plot(d.week, d.judge_share, marker="s", color="#55a868", ls="--",
            label="judge share")
    for _, r in d.iterrows():
        ax.annotate(f"{r.judge_score:.1f}", (r.week, r.phi_hi90),
                    textcoords="offset points", xytext=(0, 4), fontsize=7,
                    ha="center", color="#555555")
    ax.set_xlabel("week"); ax.set_ylabel("fan-vote share φ̂")
    ax.set_title(f"{celeb} (Season {season}): estimated fan-vote share")
    ax.legend()
    fig.savefig(os.path.join(FIGDIR, fname), bbox_inches="tight")
    plt.close(fig)
    return {fname: f"{celeb} S{season} fan-vote trajectory with 90% band"}


# ==================================================================================
def main():
    t_start = time.time()
    ws, cont = M.load_data()
    corpus = M.Corpus(ws, cont)
    n_cw = sum(len(wc["row_ids"]) for c in corpus.ctxs.values()
               for wc in c["week_ctx"])
    log(f"corpus: {len(corpus.ctxs)} seasons, {n_cw} couple-weeks")


    # A. calibration
    log("== A: calibration ==")
    U, theta, cal_trace = calibrate(corpus)
    alpha, beta, sigma = theta
    composite_ll = corpus.total_ll(theta, sigma, U)
    log(f"   composite loglik = {composite_ll:.2f}")

    # B. phi inversion
    log("== B: fan-vote inversion ==")
    phi_tab, post_grid = invert_phi(corpus, U, theta, n_post=120)
    phi_tab.to_csv(os.path.join(OUT, "fanvote_estimates.csv"), index=False)
    post_grid.to_csv(os.path.join(OUT, "calibration_grid.csv"), index=False)
    u_tab = pd.DataFrame([{"row_id": r,
                           "celebrity_name": corpus.all_names.get(r, f"row{r}"),
                           "u_fan_appeal": u} for r, u in sorted(U.items())])
    u_tab.sort_values("u_fan_appeal", ascending=False).to_csv(
        os.path.join(OUT, "u_fan_appeal.csv"), index=False)

    # C. observed-era validation
    log("== C: observed-era validation ==")
    val_tab, pooled = validate_observed_era(corpus, U, theta)
    val_tab.to_csv(os.path.join(OUT, "replay_validation_by_season.csv"), index=False)
    log(f"   pooled: cut-match {pooled['cut_match_rate']:.3f}, "
        f"bottom-Jaccard {pooled['bottom_jaccard_mean']:.3f}, "
        f"placement-MAE {pooled['placement_mae_mean']:.2f}, "
        f"placement-tau {pooled['placement_tau_mean']:.3f}")
    # era-pooled reproduction (rank era S1-2, percentage era S3-27, dance-off era S28+)
    era_pooled = {}
    for era_name, mask in [("S1-2_rank", val_tab.season <= 2),
                           ("S3-27_pct", (val_tab.season >= 3) & (val_tab.season <= 27)),
                           ("S28plus_rank_danceoff", val_tab.season >= 28)]:
        sub = val_tab[mask]
        era_pooled[era_name] = {
            "n_seasons": int(len(sub)),
            "cut_match_rate": float(sub.cut_match_rate.mean()),
            "bottom_jaccard_mean": float(sub.bottom_jaccard_mean.mean()),
            "placement_mae_mean": float(sub.placement_mae.mean()),
            "placement_tau_mean": float(sub.placement_tau.mean()),
        }
    RESULTS["reproduction_by_era"] = era_pooled
    for k, v in era_pooled.items():
        log(f"   era {k}: cut-match {v['cut_match_rate']:.3f} "
            f"(Jaccard {v['bottom_jaccard_mean']:.3f})")

    # D. counterfactual replays
    log("== D: counterfactual replays ==")
    season_runs, replay_tab, gamma_tab = replay_seasons(corpus, U, theta)
    replay_tab.to_csv(os.path.join(OUT, "rule_replay.csv"), index=False)
    gamma_tab.to_csv(os.path.join(OUT, "rule_disagreement_by_season.csv"), index=False)
    n_dis_zero = int((gamma_tab.gamma_s == 0).sum())
    log(f"   mean gamma_s = {gamma_tab.gamma_s.mean():.3f}; "
        f"{n_dis_zero} seasons with zero R/P disagreement; "
        f"max gamma_s {gamma_tab.gamma_s.max():.3f} (S{int(gamma_tab.season[gamma_tab.gamma_s.idxmax()])})")

    # E. controversies
    log("== E: controversies ==")
    ctab, flip_tab = analyze_controversies(corpus, U, theta, season_runs)
    ctab.to_csv(os.path.join(OUT, "controversy_table.csv"), index=False)
    flip_tab.to_csv(os.path.join(OUT, "controversy_flip_curves.csv"), index=False)
    log(ctab[["celebrity", "season", "obs_placement", "R_placement", "P_placement",
              "Z_placement"]].to_string(index=False))

    # F. dance-off overlay + S28+ rule/stage ledger
    log("== F: dance-off overlay ==")
    doff_tab = danceoff_overlay(corpus, U, theta, season_runs)
    doff_tab.to_csv(os.path.join(OUT, "danceoff_overlay_by_season.csv"), index=False)
    log(doff_tab.to_string(index=False))
    s28_tab = s28plus_rule_overlay(corpus, U, theta)
    s28_tab.to_csv(os.path.join(OUT, "s28plus_rule_overlay.csv"), index=False)
    log("  S28+ event-weighted reproduction by rule/stage combo:")
    log(s28_tab.to_string(index=False))
    RESULTS["s28plus_overlay"] = s28_tab.to_dict("records")

    # F2. HDI-bound sensitivity (plan-required): controversy under phi at 90% edges
    log("== F2: HDI-bound sensitivity ==")
    named = [("Jerry Rice", 2), ("Billy Ray Cyrus", 4), ("Bristol Palin", 11),
             ("Bobby Bones", 27), ("Mya", 9), ("Donny Osmond", 9),
             ("Sabrina Bryan", 5), ("Sabrina Bryan", 15)]
    hdi_tab = hdi_bound_sensitivity(corpus, U, theta, phi_tab, named)
    hdi_tab.to_csv(os.path.join(OUT, "hdi_bound_sensitivity.csv"), index=False)
    log(hdi_tab.to_string(index=False))
    RESULTS["hdi_bound_sensitivity"] = hdi_tab.to_dict("records")

    # G. recommendation metrics
    log("== G: recommendation metrics ==")
    rec_tab = recommendation_metrics(corpus, U, theta, season_runs)
    rec_tab.to_csv(os.path.join(OUT, "rule_metrics_by_season.csv"), index=False)
    rec_avg = {c: float(rec_tab[c].mean()) for c in rec_tab.columns if c != "season"}
    for key in ["R", "P", "Z"]:
        log(f"   {key}: tau={rec_avg[key+'_tau']:.3f} gini={rec_avg[key+'_gini']:.3f} "
            f"shock={rec_avg[key+'_shock_rate']:.3f}")

    # shared-data copies for downstream models (fanvote_estimates CSV identical to
    # local output; rule_replay likewise)
    shared_copies_prefixed = [("fanvote_estimates.csv", phi_tab),
                              ("rule_replay.csv", replay_tab),
                              ("controversy_table.csv", ctab)]
    copy_report = {}
    for fname, tab in shared_copies_prefixed:
        try:
            tab.to_csv(os.path.join(SHARED, "model2_" + fname), index=False)
            copy_report[fname] = "ok"
        except Exception as e:
            copy_report[fname] = f"skipped: {type(e).__name__}"
            log(f"   (shared_data copy skipped for {fname}: {type(e).__name__})")
    log("   shared_data copies: " + ", ".join(f"{k}={v}" for k, v in copy_report.items()))
    RESULTS["shared_data_copies"] = copy_report

    # results.json
    RESULTS.update({
        "meta": {"seed": M.SEED,
                 "n_seasons": len(corpus.ctxs),
                 "n_season_weeks": int(sum(len(c["week_ctx"])
                                           for c in corpus.ctxs.values())),
                 "n_couple_weeks": int(sum(len(wc["row_ids"]) for c in
                                           corpus.ctxs.values()
                                           for wc in c["week_ctx"])),
                 "n_elim_obs": int(sum(int(wc["elim_here"].sum())
                                       for c in corpus.ctxs.values()
                                       for wc in c["week_ctx"]))},
        "calibration": {"alpha": alpha, "beta": beta, "sigma": sigma,
                        "composite_loglik": composite_ll, "trace": cal_trace,
                        "n_params_U": len(U)},
        "phi_certainty": {
            "n_cells": int(len(phi_tab)),
            "mean_phi_hat": float(phi_tab.phi_hat.mean()),
            "median_rel_band_width":
                float(np.median((phi_tab.phi_hi90 - phi_tab.phi_lo90) /
                                phi_tab.phi_hat.clip(lower=1e-9))),
            "band_width_p10_abs": float((phi_tab.phi_hi90 - phi_tab.phi_lo90).quantile(0.1)),
            "band_width_p90_abs": float((phi_tab.phi_hi90 - phi_tab.phi_lo90).quantile(0.9)),
        },
        "reproduction_pooled": pooled,
        "gamma": {"mean_gamma_s": float(gamma_tab.gamma_s.mean()),
                  "median_gamma_s": float(gamma_tab.gamma_s.median()),
                  "n_seasons_zero_disagreement": n_dis_zero,
                  "seasons_zero": [int(x) for x in
                                   gamma_tab.loc[gamma_tab.gamma_s == 0, "season"]],
                  "max_gamma_season": int(gamma_tab.season[gamma_tab.gamma_s.idxmax()]),
                  "max_gamma_value": float(gamma_tab.gamma_s.max()),
                  "per_season": gamma_tab.to_dict("records")},
        "controversies": ctab.replace({np.nan: None}).to_dict("records"),
        "danceoff_overlay": doff_tab.to_dict("records"),
        "recommendation_avg": {key: {sub: rec_avg[f"{key}_{sub_name}"]
                                     for sub, sub_name in
                                     [("tau", "tau"), ("gini", "gini"),
                                      ("shock_rate", "shock_rate")]}
                               for key in ["R", "P", "Z"]},
    })

    # figures
    log("== H: figures ==")
    figs = make_figures(corpus, phi_tab, val_tab, gamma_tab, season_runs, ctab,
                        flip_tab, rec_tab, None, doff_tab=doff_tab,
                        hdib_tab=hdi_tab)
    RESULTS["figures"] = figs

    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    # handoff.json
    with open(os.path.join(OUT, "handoff.json"), "w") as f:
        json.dump({"status": "ok", "issues": [], "fixInstructions": "",
                   "summaryPath": os.path.join(OUT, "results_summary.md")}, f, indent=2)

    log(f"\nAll done in {time.time()-t_start:.0f}s.")
    return corpus, U, theta, phi_tab, val_tab, gamma_tab, ctab, rec_tab


if __name__ == "__main__":
    main()
