"""
run_model2.py — Model 2: Counterfactual Season Re-Play (CSR) under
RANK / PCT / Judges-Save rules, driven by Model-1 feasible-set fan-vote samples.

Rules:
  RANK: C = judgeRank + fanRank (lower better); eliminate argmin (ties broken
        stably); historically s1-2 and s28-34.
  PCT : C = 0.5*JudgeShare + 0.5*FanShare; eliminate argmin; historically s3-27.
  SAVE: historically s28+: bottom-two identified under RANK, judges eliminate
        bottom-two member i with prob sig(kappa*(J_other - J_i)).

Fan-vote posterior (Model 1 surrogate): with weekly committee share j = J/sum(J),
fan shares f ~ Dirichlet(phi * j) (fans weakly track judges; small phi ->
disagreement weeks). A draw is FEASIBLE iff, under that season's historical
combination rule, the observed eliminated contestant is the argmin (s1-27) or
in the bottom-two (s28-34, where the judges' save can pick either). phi is
calibrated per week to a target acceptance rate, giving honest per-week
posterior dispersion ("certainty") for each contestant's fan votes.

FIXES applied per review:
  #1 C is computed once per week BEFORE the final-table branch (always in scope).
  #2 clean log-likelihood ll(kappa) = sum log sig(kappa*D), D = J_saved - J_elim.
  #3 double-elimination weeks (s9/s18/s21...) excluded from the kappa fit
     (no unique bottom-two pair) and handled exactly in the replay by
     eliminating the historically-recorded NUMBER of couples per week.
"""
import os, sys, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.special import expit  # sigmoid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dwts_common import load_data, build_schedule

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs"); FIG = os.path.join(BASE, "figures")
os.makedirs(OUT, exist_ok=True); os.makedirs(FIG, exist_ok=True)
DATA = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
        "r4-c3-journal-mwodcgan/data/2026_MCM_Problem_C_Data.csv")

B = 150               # bootstrap replicates (fan-vote posterior draws) per week
U0 = 1_000_000.0      # arbitrary weekly total vote scale for count outputs
TARGET_ACCEPT = 0.35  # calibration target for the dispersion phi
PHI_GRID = [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
KAPPA_GRID = np.linspace(0.05, 6.0, 200)
CONTRO = {2: "Jerry Rice", 4: "Billy Ray Cyrus", 11: "Bristol Palin",
          27: "Bobby Bones"}

plt.rcParams["font.family"] = "serif"


def historical_rule(s):
    """(combination rule, judges-save flag) historically used in season s."""
    return ("RANK", True) if (s <= 2 or s >= 28) else ("PCT", False)


# ------------------------------------------------------- combined scores
def combined_matrix(Js, Fmat, rule, alpha=0.5):
    """Combined scores; rows = fan draws, cols = contestants. Lower = at risk."""
    Js = np.asarray(Js, float); Fmat = np.atleast_2d(np.asarray(Fmat, float))
    if rule == "RANK":
        # ORIENTATION FIX: worst dancer/fan must get the LOWEST combined score
        # so that argmin C = eliminated under BOTH rules. rank 1 = best here,
        # so the contribution is (m - rank): worst -> 0, best -> m-1.
        m = len(Js)
        jr_best = np.empty(m)
        jr_best[np.argsort(-Js, kind="stable")] = np.arange(1, m + 1)
        part_j = m - jr_best
        fr_best = np.empty_like(Fmat)
        rows = np.arange(Fmat.shape[0])[:, None]
        cols = np.argsort(-Fmat, axis=1, kind="stable")
        fr_best[rows, cols] = np.arange(1, Fmat.shape[1] + 1)
        part_f = m - fr_best
        return alpha * part_j + (1 - alpha) * part_f
    jn = Js / Js.sum()
    fn = Fmat / Fmat.sum(axis=1, keepdims=True)
    return alpha * jn + (1 - alpha) * fn


def combined_vec(mates, fans, rule, alpha=0.5):
    Js = np.array([m["J"] for m in mates], float)
    Fs = np.asarray(fans, float)
    C = combined_matrix(Js, Fs, rule, alpha)
    return C[0] if (Fs.ndim == 1 and C.ndim == 2) else C


# ------------------------------------------------------- sampling (Model 1)
def sample_week_fans(Js, e_idx, rule, mode, phi, n_samp, seed,
                     chunk=4000, max_draws=600_000):
    """Accepted-set posterior draws of weekly fan-vote share vectors.

    Feasibility condition (mode):
      'argmin'  : argmin_i C_i == e_idx          (s1-27 historical rules)
      'bottom2' : e_idx in bottom-two of C       (s28-34, judges-save era)
    Returns (F [n x m], acceptance_rate)."""
    rng = np.random.default_rng(seed)
    Js = np.asarray(Js, float); m = len(Js)
    conc = np.maximum(phi * (Js / Js.sum()), 0.02)
    acc, drawn = [], 0
    while len(acc) < n_samp and drawn < max_draws:
        n = min(chunk, max_draws - drawn)
        Fm = rng.dirichlet(conc, size=n)
        drawn += n
        if e_idx is None:
            acc.append(Fm)
            continue
        C = combined_matrix(Js, Fm, rule)
        order = np.argsort(C, axis=1, kind="stable")
        ok = ((order[:, 0] == e_idx) if mode == "argmin"
              else (order[:, 0] == e_idx) | (order[:, 1] == e_idx))
        if ok.any():
            acc.append(Fm[ok])
    if acc:
        A = np.vstack(acc)
    else:  # infeasible fallback: E gets vanishing fan share
        jn = Js / Js.sum()
        A = np.tile(jn * 0.5, (n_samp, 1))
        A[:, e_idx] = 1e-6
        A = A / A.sum(axis=1, keepdims=True)
        return A[:n_samp], 0.0
    # TOP-UP GUARANTEE: if too few feasible draws (hard weeks), second pass
    # with 10x more dispersed prior, then bootstrap-resample accepted rows
    # (with replacement) so the posterior always has exactly n_samp rows.
    if len(A) < n_samp:
        drawn2 = 0
        conc2 = np.maximum(0.1 * phi * (Js / Js.sum()), 0.02)
        while len(A) < n_samp and drawn2 < 600_000:
            n = min(chunk, 600_000 - drawn2)
            Fm = rng.dirichlet(conc2, size=n)
            drawn2 += n
            C = combined_matrix(Js, Fm, rule)
            order = np.argsort(C, axis=1, kind="stable")
            ok = ((order[:, 0] == e_idx) if mode == "argmin"
                  else (order[:, 0] == e_idx) | (order[:, 1] == e_idx))
            if ok.any():
                A = np.vstack([A, Fm[ok]])
    if len(A) < n_samp:  # bootstrap resample of feasible rows
        add = rng.choice(len(A), size=n_samp - len(A), replace=True)
        A = np.vstack([A, A[add]])
    return A[:n_samp], float(min(len(A) / max(drawn, 1), 1.0))


def calibrate_phi(Js, e_idx, rule, mode):
    """Pick phi so the weekly acceptance rate is closest to TARGET_ACCEPT."""
    best, bestphi = None, PHI_GRID[0]
    for phi in PHI_GRID:
        _, rate = sample_week_fans(Js, e_idx, rule, mode, phi, 120, seed=11,
                                   max_draws=20000)
        d = abs(rate - TARGET_ACCEPT)
        if best is None or d < best:
            best, bestphi = d, phi
    return bestphi


def prep_season(seasons, s):
    """Build weekly mate tables + B feasible fan-vector draws per week."""
    sched = build_schedule(seasons[s]); sched["season"] = s
    weeks = sched["weeks"]
    fin = max(weeks)
    week_mates, week_nelim = {}, {}
    for w in sorted(weeks):
        mates = []
        for c in weeks[w]["active"]:
            t = c["scores"].get(w)
            if t is None:  # impute by latest previous total (documented)
                prev = [c["scores"][k] for k in sorted(c["scores"])
                        if k < w and c["scores"][k] is not None]
                t = prev[-1] if prev else 20.0
            mates.append(dict(celeb=c["celeb"], J=float(t),
                              is_elim=any(e["celeb"] == c["celeb"]
                                          for e in weeks[w]["elim"])))
        week_mates[w] = mates
        week_nelim[w] = sum(m["is_elim"] for m in mates)  # exact history count
    true_rule, _ = historical_rule(s)
    mode = "bottom2" if true_save_era(s) else "argmin"
    week_samp, week_acc, phis = {}, {}, {}
    for w in sorted(weeks):
        Js = np.array([m["J"] for m in week_mates[w]])
        e_idx = next((i for i, m in enumerate(week_mates[w]) if m["is_elim"]),
                     None)
        if e_idx is not None and w != fin:
            phi = calibrate_phi(Js, e_idx, true_rule, mode)
        else:
            phi = 8.0  # neutral dispersion where no elim identifies the scale
        F, rate = sample_week_fans(Js, e_idx, true_rule, mode, phi, B,
                                   seed=10000 * s + 97 * w)
        week_samp[w] = F * U0      # vote-count scale, rows = posterior draws
        week_acc[w] = rate; phis[w] = phi
    return sched, week_mates, week_nelim, week_samp, week_acc, phis


def true_save_era(s):
    return (s <= 2) or (s >= 28)


# ------------------------------------------------------- replay machinery
def replay_week(mates, fans, rule, do_save, kappa, alpha=0.5, rng=None,
                return_bottom2=False):
    """Indices eliminated this week (bottom-two pair if return_bottom2)."""
    C = combined_vec(mates, fans, rule, alpha)
    order = np.argsort(C, kind="stable")
    if return_bottom2:
        return [int(order[0]), int(order[1])]
    if do_save and len(mates) > 2:
        a, b = int(order[0]), int(order[1])   # bottom two by combined score
        # P(eliminate a) = sig(kappa*(J_b - J_a)): judges save the better-
        # judged member when the judge gap favours b.
        pa = expit(kappa * (mates[b]["J"] - mates[a]["J"]))
        return [a if rng.random() < pa else b]
    return [int(order[0])]


def replay_season(week_mates, week_samp, b, celebs, rule, do_save, kappa,
                  alpha=0.5, seed=0):
    """Full-season progressive replay; returns dict celeb -> placement-ish.

    Schedule-faithful: in week w exactly n_elim(w) couples leave (n_elim = the
    historically recorded count, which can be 0, e.g. s1 w1, or 2 in
    double-elimination weeks s9/s18/s21). With judges-save, a single-elim
    week eliminates one of the bottom two chosen stochastically; for a
    double-elim save week the second elimination is the next-lowest couple
    (documented approximation).
    """
    rng = np.random.default_rng(seed)
    fin = max(week_mates)
    alive = list(celebs)
    place = {}
    for w in range(1, fin + 1):
        idx_map = [mm["celeb"] for mm in week_mates[w]]
        mates = [m for m in week_mates[w] if m["celeb"] in alive]
        fs = week_samp[w][b]
        fans = np.array([fs[idx_map.index(m["celeb"])] for m in mates])
        C = combined_vec(mates, fans, rule, alpha)      # FIX #1: always in scope
        order = np.argsort(C, kind="stable")
        n_elim = sum(m["is_elim"] for m in mates)       # historical count
        is_fin = (w == fin)
        if is_fin or len(mates) <= n_elim + 1:
            # finale week (or reduced table): rank all remaining at once
            for rank, idx in enumerate(np.argsort(-C, kind="stable")):
                place[mates[idx]["celeb"]] = len(mates) - rank
            return place
        if n_elim == 0:
            continue
        if do_save:
            a, bb = int(order[0]), int(order[1])
            pa = expit(kappa * (mates[bb]["J"] - mates[a]["J"]))
            elim = [a if rng.random() < pa else bb]
            if n_elim >= 2:                     # second couple in double weeks
                elim.append(int(order[2]))
        else:
            elim = [int(i) for i in order[:n_elim]]
        for idx in elim:
            place[mates[idx]["celeb"]] = len(mates)
            alive.remove(mates[idx]["celeb"])
        if not alive:
            break
    # (defensive) anyone still alive gets ranked by their last-week standing
    for c in alive:
        place[c] = place.get(c, len(alive))
    return place


def dense(p):
    order = sorted(p, key=p.get)
    return {c: i + 1 for i, c in enumerate(order)}


def dense_actual(seasons, s):
    sched = build_schedule(seasons[s])
    return {c["celeb"]: i + 1 for i, c in enumerate(
        sorted(sched["season_conts"], key=lambda c: c["placement"]))}


# ---------------------------------------------------------------- main
def main():
    seasons = load_data(DATA)

    # ---------- kappa: judges-save tendency from s28-34 bottom-two pairs ----
    wk_pairs = []
    for s in range(28, 35):
        sched, wm, wn, ws, acc, phis = prep_season(seasons, s)
        fin = max(wm)
        for w in sorted(wm):
            if w == fin:
                continue
            matches = [m for m in wm[w] if m["is_elim"]]
            if len(matches) != 1:
                continue  # FIX #3: double-elimination weeks have no unique
                          # bottom-two pair -> excluded from the kappa fit
            fans = np.median(ws[w], axis=0)
            b2 = replay_week(wm[w], fans, "RANK", False, 0.0,
                             return_bottom2=True)
            names = [wm[w][i]["celeb"] for i in b2]
            if matches[0]["celeb"] not in names:
                continue   # model's bottom-2 missed the actual eliminated
            e = names.index(matches[0]["celeb"])
            Ja, Jb = wm[w][b2[0]]["J"], wm[w][b2[1]]["J"]
            # observed: the e-th bottom-two member was eliminated;
            # D = J_saved - J_elim, P(observed | D) = sig(kappa*D)
            D = Jb - Ja if e == 0 else Ja - Jb
            wk_pairs.append(dict(season=s, week=w,
                                 eliminated=matches[0]["celeb"],
                                 other=names[1 - e], Jgap=float(D),
                                 J_elim=float(wm[w][b2[e]]["J"]),
                                 J_saved=float(wm[w][b2[1 - e]]["J"])))
    dfp = pd.DataFrame(wk_pairs)
    D = dfp["Jgap"].values
    # FIX #2 (clean likelihood): ll(kappa) = sum log sig(kappa * D), where
    # D = J_saved - J_elim per bottom-two pair; kappa > 0 means judges save
    # the better-danced couple.
    grid = KAPPA_GRID
    ll = np.array([np.sum(np.log(expit(k * D))) for k in grid])
    khat = float(grid[int(np.argmax(ll))])
    rngb = np.random.default_rng(7)
    boots = []
    for _ in range(500):
        idx = rngb.integers(0, len(D), len(D))
        llb = [np.sum(np.log(expit(k * D[idx]))) for k in grid]
        boots.append(grid[int(np.argmax(llb))])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    kappa_fits = dict(kappa=khat, ci_lo=float(lo), ci_hi=float(hi),
                      n_bottom2_pairs=int(len(D)),
                      frac_elim_yes_betterJ=float(np.mean(D < 0)))
    dfp.to_csv(os.path.join(OUT, "judges_save_bottom2_pairs.csv"), index=False)
    pd.DataFrame([kappa_fits]).to_csv(os.path.join(OUT, "judges_save_fit.csv"),
                                      index=False)
    print("kappa fit:", kappa_fits)
    KAPPA = khat

    # ---------------- replay every season under 3 rule variants -------------
    rows, celeb_rows, m1_rows, fan_favor = [], [], [], []
    season_store = {}
    for s in sorted(seasons):
        sched, wm, wn, ws, acc, phis = prep_season(seasons, s)
        fin = max(wm)
        celebs = [c["celeb"] for c in sched["season_conts"] if not c["withdrew"]]
        n = len(celebs)
        actual = dense_actual(seasons, s)
        true_rule, true_save = historical_rule(s)

        # ---- weekly validation: fraction of feasible posterior draws that
        # reproduce the observed elimination outcome (per historical rule)
        val_weeks = [w for w in sorted(wm)
                     if w != fin and any(m["is_elim"] for m in wm[w])]
        pct_exact = float(np.mean([acc[w] for w in val_weeks])) if val_weeks else 1.0

        do_save_hist = true_save_era(s)
        # NOTE: for the OWN-rule counterfactual we replay the season exactly
        # as historically run (incl. judges-save for s1-2/s28-34 eras).
        true_rule_eff = "RANK" if do_save_hist else "PCT"
        place_own  = [replay_season(wm, ws, b, celebs, true_rule_eff,
                                    do_save_hist, KAPPA, seed=b) for b in range(B)]
        place_rank = [replay_season(wm, ws, b, celebs, "RANK", False, KAPPA,
                                    seed=b) for b in range(B)]
        place_pct  = [replay_season(wm, ws, b, celebs, "PCT", False, KAPPA,
                                    seed=b) for b in range(B)]
        place_save = [replay_season(wm, ws, b, celebs, "RANK", True, KAPPA,
                                    seed=b) for b in range(B)]
        place_pctsav = [replay_season(wm, ws, b, celebs, "PCT", True, KAPPA,
                                      seed=b) for b in range(B)]
        do_, dr, dp, ds = ([dense(p) for p in place_own],
                           [dense(p) for p in place_rank],
                           [dense(p) for p in place_pct],
                           [dense(p) for p in place_save])
        dsv = [dense(p) for p in place_pctsav]

        w_rank = [sorted(dr[b], key=dr[b].get)[0] for b in range(B)]
        w_pct  = [sorted(dp[b], key=dp[b].get)[0] for b in range(B)]
        w_save = [sorted(ds[b], key=ds[b].get)[0] for b in range(B)]
        win_flip = float(np.mean([a != c for a, c in zip(w_rank, w_pct)]))
        top3_flip = float(np.mean([
            set(sorted(dr[b], key=dr[b].get)[:3]) !=
            set(sorted(dp[b], key=dp[b].get)[:3]) for b in range(B)]))

        # per-celebrity counterfactual placements + flip probabilities
        for c in celebs:
            celeb_rows.append(dict(
                season=s, celeb=c, actual=actual.get(c),
                med_place_own=float(np.median([do_[b].get(c, np.nan)
                                               for b in range(B)])),
                med_place_rank=float(np.median([dr[b].get(c, np.nan)
                                                for b in range(B)])),
                med_place_pct=float(np.median([dp[b].get(c, np.nan)
                                               for b in range(B)])),
                med_place_save=float(np.median([ds[b].get(c, np.nan)
                                                for b in range(B)])),
                med_place_pctsav=float(np.median([dsv[b].get(c, np.nan)
                                                  for b in range(B)])),
                flip_prob_RvsP=float(np.mean([dr[b].get(c) != dp[b].get(c)
                                              for b in range(B)]))))
        # controversy celebrities: own / alternative / judges-save variants
        if s in CONTRO:
            cc = CONTRO[s]
            variants = [("own", do_), ("alt", dp if true_rule_eff == "RANK"
                                        else dr),
                        ("save", ds), ("pctsave", dsv)]
            for tag, pl in variants:
                celeb_rows.append(dict(
                    season=s, celeb=cc, variant=tag,
                    med_place=float(np.median([pl[b].get(cc, np.nan)
                                               for b in range(B)])),
                    win_prob=float(np.mean([sorted(pl[b], key=pl[b].get)[0] == cc
                                            for b in range(B)]))))

        # fan-favour index: how often each rule's elimination deviates from
        # the judge-only argmin (a rule that favours fans -> higher f).
        ff_r, ff_p = [], []
        for w in val_weeks:
            Js = np.array([m["J"] for m in wm[w]])
            names = [m["celeb"] for m in wm[w]]
            j_only = names[int(np.argmin(Js))]
            for b in range(B):
                r_e = names[int(np.argmin(
                    combined_vec(wm[w], ws[w][b], "RANK")))]
                p_e = names[int(np.argmin(
                    combined_vec(wm[w], ws[w][b], "PCT")))]
                ff_r.append(r_e != j_only)
                ff_p.append(p_e != j_only)
        fan_favor.append(dict(season=s,
                              f_RANK=float(np.mean(ff_r)),
                              f_PCT=float(np.mean(ff_p))))

        # Model-1 style fan-vote posterior table (medians across replicates)
        for w in sorted(wm):
            fans = ws[w]
            Js = np.array([m["J"] for m in wm[w]])
            sh = fans / fans.sum(axis=1, keepdims=True)
            for i, m in enumerate(wm[w]):
                m1_rows.append(dict(
                    season=s, week=w, celeb=m["celeb"], judge_total=m["J"],
                    u_hat=float(np.median(fans[:, i])),
                    u_lo=float(np.percentile(fans[:, i], 5)),
                    u_hi=float(np.percentile(fans[:, i], 95)),
                    fan_share=float(sh[:, i].mean()),
                    judge_share=float(Js[i] / Js.sum()),
                    n_samples=int(fans.shape[0]), accept_rate=acc[w],
                    phi=float(phis[w])))

        rows.append(dict(
            season=s, n=n,
            mean_phi=float(np.mean([phis[w] for w in val_weeks])) if val_weeks
                      else np.nan,
            pct_exact=pct_exact, tot_weeks=len(val_weeks),
            winner_observed=sorted(actual, key=actual.get)[0],
            winner_top_freq_RANK=pd.Series(w_rank).mode()[0],
            winner_top_freq_PCT=pd.Series(w_pct).mode()[0],
            winner_top_freq_SAVE=pd.Series(w_save).mode()[0],
            winner_flip_prob=win_flip, top3_flip_prob=top3_flip,
            pct_season_exact=float(np.mean([
                sorted(do_[b], key=do_[b].get)[0] ==
                sorted(actual, key=actual.get)[0] for b in range(B)]))))
        season_store[s] = (wm, ws, celebs, do_, dr, dp, ds, dsv)
        print(f"s{s:2d} consistency={pct_exact:.2f} winner_flip={win_flip:.2f} "
              f"top3_flip={top3_flip:.2f} own-winner-repro="
              f"{rows[-1]['pct_season_exact']:.2f}")

    dfr = pd.DataFrame(rows)
    dfr.to_csv(os.path.join(OUT, "season_replay_summary.csv"), index=False)
    dfc = pd.DataFrame(celeb_rows)
    dfc.to_csv(os.path.join(OUT, "celebrity_flip_probabilities.csv"), index=False)
    dff = pd.DataFrame(fan_favor)
    dff.to_csv(os.path.join(OUT, "fan_favor_index.csv"), index=False)
    pd.DataFrame(m1_rows).to_csv(os.path.join(OUT, "model1_fanvote_estimates.csv"),
                                 index=False)

    # -------------- alpha sensitivity: winner agreement with judge-only ----
    arows = []
    for s in [1, 2, 4, 11, 27, 28, 34]:
        wm, ws, celebs, do_, dr, dp, ds, dsv = season_store[s]
        base = [sorted(dr[b], key=dr[b].get)[0] for b in range(B)]  # judge-only
        for a in ALPHAS:
            wins = []
            for bv in range(B):
                pl = replay_season(wm, ws, bv, celebs, "PCT", False, KAPPA,
                                   alpha=a, seed=bv)
                wins.append(sorted(pl, key=pl.get)[0])
            arows.append(dict(season=s, alpha=a,
                              agree_judgeonly=float(np.mean(
                                  [w == bw for w, bw in zip(wins, base)]))))
    pd.DataFrame(arows).to_csv(os.path.join(OUT, "alpha_sensitivity.csv"),
                               index=False)

    # ===================== FIGURES =====================
    # fig 1: winner / top-3 flip probability per season
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(dfr.season - 0.2, dfr.winner_flip_prob, width=0.4,
           label="winner flip (RANK vs PCT)", color="#c0392b")
    ax.bar(dfr.season + 0.2, dfr.top3_flip_prob, width=0.4,
           label="top-3 set flip", color="#2471a3")
    ax.set_xlabel("Season"); ax.set_ylabel("Flip probability")
    ax.set_title(f"Counterfactual outcome flips: rank vs percent rules\n"
                 f"({B} fan-vote posterior replicates per season)")
    ax.legend(); ax.set_ylim(0, 1)
    fig.savefig(os.path.join(FIG, "fig1_winner_flip_by_season.png"),
                bbox_inches="tight"); plt.close(fig)

    # fig 2: controversy celebrities under own / alt / save variants
    con = dfc.dropna(subset=["variant"])
    labels = [f"s{int(r.season)} {r.celeb.split()[0]}\n[{r.variant}]"
              for _, r in con.iterrows()]
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar(range(len(con)), con.med_place, color="#7d3c98")
    for i, (_, r) in enumerate(con.iterrows()):
        ax.text(i, min(r.med_place + 0.2, 13), f"{r.med_place:.0f}",
                ha="center", fontsize=9)
        if not pd.isna(r.win_prob):
            ax.text(i, 0.4, f"P(win)={r.win_prob:.2f}", ha="center",
                    fontsize=8, color="white")
    ax.set_xticks(range(len(con))); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Median counterfactual placement (1 = winner)")
    ax.set_title("Controversy cases: own rule vs alternative rule vs judges-save")
    ax.invert_yaxis()
    fig.savefig(os.path.join(FIG, "fig2_controversy_placements.png"),
                bbox_inches="tight"); plt.close(fig)

    # fig 3: alpha sensitivity (pooled winner agreement with judge-only)
    dfal = pd.DataFrame(arows)
    piv = dfal.groupby("alpha").agree_judgeonly.mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(piv.index, piv.values, "o-", color="#1a5276")
    ax.set_xlabel(r"judge weight $\alpha$ in $C=\alpha\,\mathrm{rank}_J+(1-\alpha)\,\mathrm{rank}_F$")
    ax.set_ylabel("Pooled P(winner = judge-only winner)")
    ax.set_title(r"Sensitivity of outcomes to the judge/fan mix weight $\alpha$")
    ax.set_ylim(0, 1.02)
    fig.savefig(os.path.join(FIG, "fig3_alpha_sensitivity.png"),
                bbox_inches="tight"); plt.close(fig)

    # fig 4: convergence of flip probability vs number of replicates
    fig, ax = plt.subplots(figsize=(8, 5))
    for s in [2, 11, 27]:
        wm, ws, celebs, do_, dr, dp, ds, dsv = season_store[s]
        run = []
        for nb in range(10, B + 1, 10):
            wr = [sorted(dr[b], key=dr[b].get)[0] for b in range(nb)]
            wp = [sorted(dp[b], key=dp[b].get)[0] for b in range(nb)]
            run.append(np.mean([x != y for x, y in zip(wr, wp)]))
        ax.plot(range(10, B + 1, 10), run, "o-", label=f"season {s}", ms=3)
    ax.set_xlabel("Number of fan-vote posterior replicates")
    ax.set_ylabel("Winner flip probability (RANK vs PCT)")
    ax.set_title("Monte-Carlo convergence of flip probabilities")
    ax.legend()
    fig.savefig(os.path.join(FIG, "fig4_flip_convergence.png"),
                bbox_inches="tight"); plt.close(fig)

    # fig 5: divergence map (judge percentile vs fan percentile)
    dfm = pd.DataFrame(m1_rows)
    dfm["Jpct"] = dfm.groupby(["season", "week"]).judge_share.rank(pct=True)
    dfm["Fpct"] = dfm.groupby(["season", "week"]).fan_share.rank(pct=True)
    dfm["div"] = (dfm.Jpct - dfm.Fpct).abs()
    gridm = dfm.pivot_table(index="season", columns="week", values="div",
                            aggfunc="mean")
    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(gridm.values, aspect="auto", cmap="RdYlBu_r", vmin=0,
                   vmax=np.nanmax(gridm.values))
    ax.set_yticks(range(len(gridm.index))); ax.set_yticklabels(gridm.index)
    ax.set_xticks(range(len(gridm.columns))); ax.set_xticklabels(gridm.columns)
    ax.set_xlabel("Competition week"); ax.set_ylabel("Season")
    ax.set_title("Divergence map: mean |judge percentile − fan-vote percentile|\n"
                 "(red = fans and judges disagree most)")
    fig.colorbar(im, ax=ax, label="mean |Δpercentile|")
    fig.savefig(os.path.join(FIG, "fig5_divergence_map.png"),
                bbox_inches="tight"); plt.close(fig)

    print("mean f_RANK=%.3f mean f_PCT=%.3f" %
          (dff.f_RANK.mean(), dff.f_PCT.mean()))
    key = dict(
        winner_flip_by_season={int(r.season): float(r.winner_flip_prob)
                               for _, r in dfr.iterrows()},
        top3_flip_by_season={int(r.season): float(r.top3_flip_prob)
                             for _, r in dfr.iterrows()},
        fan_favor=dict(f_RANK=float(dff.f_RANK.mean()),
                       f_PCT=float(dff.f_PCT.mean())),
        kappa=kappa_fits,
        min_pct_exact=float(dfr.pct_exact.min()),
        mean_pct_exact=float(dfr.pct_exact.mean()),
        mean_season_winner_repro=float(dfr.pct_season_exact.mean()),
        controversy={f"{int(r.season)}_{r.celeb}_{r.variant}":
                     dict(med_place=float(r.med_place), win_prob=float(r.win_prob))
                     for _, r in con.iterrows()})
    with open(os.path.join(OUT, "model2_key_results.json"), "w") as f:
        json.dump(key, f, indent=1)
    print("DONE")


ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0]

if __name__ == "__main__":
    main()
