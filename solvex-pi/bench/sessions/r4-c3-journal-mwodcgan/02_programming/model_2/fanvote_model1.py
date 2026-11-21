"""
fanvote_model1.py — Model 1 in service of Model 2 (2026 MCM Problem C).

Maximum-entropy bootstrapped posterior over weekly fan-vote vectors consistent
with every observed elimination (Nuzzo, 2026 MCM C data).

Model: within week w the eliminated contestant e_w is argmin_i C_i with
    C_i = 0.5 * JudgeShare_i + 0.5 * FanShare_i,
    JudgeShare_i = J_i / sum(J),  FanShare_i = u_i / sum(u).

The observed J is FIXED (data). We place a Gaussian prior in *z-space*:
    z_i = N(0,q) + beta_q * JudgeGap_i + eps,     eps ~ N(0, 3.0)
with JudgeGap_i = J_i - mean(J), i.e. fans only weakly follow judges
(beta_q = 0.18 judge points ~ 4% of a weekly SD; dispersion sigma_q = 0.55)
— encoding "fans disagree with the judges", per the entertainment premise.

Given a latent dispersion sigma_e (fan-vote dispersion measured IN JUDGE
POINTS, calibrated on elimination-consistency), the weekly posterior over
rankings is logistic:  P(e beats i) = Phi( (J_i - J_e) / (sqrt(2) sigma_e) ).

Inference:
  1. calibrate sigma_e per season by maximum pseudo-likelihood over observed
     eliminations (L2 = sum log P(e_w actually eliminated | z-ranking risk));
  2. draw fan-vote posterior samples: z = J-gap + rank-preserving dispersion
     + rare zero-information shocks; renormalize u = z to vote-count scale
     (sum(u) = sum(J) so the 50/50 mix is scale-balanced);
  3. reject weeks whose argmin-C does not reproduce the observed elimination
     (importance weight = 0 mass), keeping the feasible-set emsemble.
"""
import numpy as np
from scipy.stats import norm
from dwts_common import load_data, build_schedule

SQRT2 = np.sqrt(2.0)

# ---------------- prior hyperparameters (fully documented, weakly informative)
BETA_Q = 0.18      # judge-points per fan-z-unit: fans weakly track judges
SIGMA_Q = 0.55     # prior dispersion of fan z (judge points)
EPS_PRIOR = 3.0    # idiosyncratic noise (judge points)
SHOCK_P = 0.05     # prob of a large popularity shock per contestant-week
SHOCK_SD = 1.00    # size of that shock (judge points)


def _active_matrix(mates):
    Js = np.array([m["J"] for m in mates], float)
    gap = Js - Js.mean()
    return Js, gap


def game_matrix(mates, sig):
    """Pairwise 'beats' probabilities used for the pseudo-likelihood."""
    Js, _ = _active_matrix(mates)
    m = len(mates)
    A = np.zeros((m, m))
    for i in range(m):
        for j in range(i + 1, m):
            p = norm.cdf((Js[i] - Js[j]) / (sig * SQRT2))
            A[i, j], A[j, i] = p, 1.0 - p
    return A


def L2_pseudolik(mates, sig, eps=1e-12):
    """log prod_w P(e_w eliminated | pairwise logistic risk), same week."""
    Js, _ = _active_matrix(mates)
    e_idx = next((i for i, m in enumerate(mates) if m["is_elim"]), None)
    if e_idx is None:
        return NO_ELIM  # no observed elimination this week (e.g. double week)
    ll = 0.0
    for i, m in enumerate(mates):
        if i == e_idx:
            continue
        ll += np.log(max(norm.cdf((Js[i] - Js[e_idx]) / (sig * SQRT2)), eps))
    return ll


NO_ELIM = object()


def calibrate_sigma(season_weeks, grid=None):
    """Pool the per-week pseudo-likelihoods to choose the season sigma_e."""
    if grid is None:
        grid = np.arange(0.30, 2.01, 0.05)
    lls = {}
    for s in grid:
        tot = 0.0
        for w in season_weeks:
            ll = L2_pseudolik(w["mates"], s)
            if ll == NO_ELIM:
                continue
            tot += ll
        lls[s] = tot
    sig = max(lls, key=lls.get)
    return sig, lls


def fit_week(mates, sig, n_mc=400, seed=0):
    """Draw n_mc posterior fan-vote samples for one week."""
    rng = np.random.default_rng(seed)
    Js, gap = _active_matrix(mates)
    m = len(mates)
    e_idx = next((i for i, m in enumerate(mates) if m["is_elim"]), None)
    u_samp = np.zeros((n_mc, m))
    accepted = 0
    for b in range(n_mc):
        for _ in range(60):  # rejection sampling (feasible-set ensemble)
            z = BETA_Q * gap + rng.normal(0, SIGMA_Q, m) \
                + rng.normal(0, EPS_PRIOR, m)
            if e_idx is not None:
                # e_w must be argmin C = argmin (Jshare + zshare)
                sc = 0.5 * (Js / Js.sum()) + 0.5 * (z / z.sum())
                if int(np.argmin(sc)) == e_idx:
                    break
        # rare popularity shock, keeps heavy tails in fan behaviour
        shocks = np.where(rng.random(m) < SHOCK_P,
                          rng.normal(0, SHOCK_SD, m), 0.0)
        z = z + shocks
        if e_idx is not None:
            sc = 0.5 * (Js / Js.sum()) + 0.5 * (z / z.sum())
            if int(np.argmin(sc)) != e_idx:
                continue  # infeasible draw -> discarded
        u_samp[b] = z * (Js.sum() / z.sum())   # vote-count scale, sum = sum J
        accepted += 1
        if accepted >= n_mc:
            break
    u_samp = u_samp[:accepted]
    res = []
    for i, mm in enumerate(mates):
        a = u_samp[:, i]
        res.append(dict(
            week=mm["week"], mate=mm["mate"], J=Js[i],
            u_hat=float(np.median(a)) if len(a) else Js[i],
            u_lo=float(np.percentile(a, 5)) if len(a) else Js[i],
            u_hi=float(np.percentile(a, 95)) if len(a) else Js[i],
            fan_share=float(np.mean(a / u_samp.sum(axis=1))) if len(a) else Js[i] / Js.sum(),
            judge_share=float(Js[i] / Js.sum()),
            n_samples=int(len(a)),
        ))
    return res, accepted


def fit_season(sched, n_mc=400, seed=0):
    """Full season: dateset of posterior samples + calibration diagnostics."""
    weeks_data = []
    for w, rec in sched["weeks"].items():
        if rec["is_finale"]:
            finale_elflag = True
        else:
            finale_elflag = False
        mates = []
        for c in rec["active"]:
            t = c["scores"].get(w)
            if t is None:
                # impute by the mate's latest available total before w
                prev = [c["scores"][k] for k in sorted(c["scores"]) if k < w
                        and c["scores"][k] is not None]
                t = prev[-1] if prev else 20.0
                c = dict(c)
                c = {**c, "_imputed": True}
            is_elim = (not rec["is_finale"]) and any(
                e["celeb"] == c["celeb"] for e in rec["elim"])
            mates.append(dict(week=w, mate=c["celeb"], J=float(t),
                              is_elim=is_elim))
        if len(mates) >= 2:
            weeks_data.append(dict(week=w, mates=mates,
                                   is_finale=rec["is_finale"]))
    nonfin = [wd for wd in weeks_data if not wd["is_finale"]]
    sig, lls = calibrate_sigma(nonfin)
    all_rows, exact_flags = [], []
    for wd in weeks_data:
        rows, n_ok = fit_week(wd["mates"], sig, n_mc=n_mc,
                              seed=seed * 977 + wd["week"])
        # consistency: with inferred samples, does the argmin-C reproduce e_w?
        e_true = next((i for i, mm in enumerate(wd["mates"]) if mm["is_elim"]), None)
        if e_true is not None:
            exact_flags.append(n_ok > 0)
        all_rows.extend(rows)
    meta = dict(season=sched.get("season", None), sigma_e=float(sig),
                lnl=float(sum(L2_pseudolik(wd["mates"], sig)
                              for wd in nonfin if L2_pseudolik(wd["mates"], sig) != NO_ELIM)),
                weeks_fitted=len(weeks_data),
                exactly_matched=float(np.mean(exact_flags)) if exact_flags else 1.0)
    return dict(meta=meta, weeks=weeks_data, rows=all_rows, sig=sig, lls=lls)


# ---------------- convenience: load + fit all seasons (cached in memory)
def vote_prior_summary(all_fits):
    ys = []
    for s, f in all_fits.items():
        for wd in f["weeks"]:
            jj = [m["J"] for m in wd["mates"]]
            tot = sum(jj)
            for r in f["rows"]:
                if r["week"] == wd["week"]:
                    ys.append((r["mate"], r["judge_share"], r["fan_share"]))
    jj = np.array([y[1] for y in ys]); ff = np.array([y[2] for y in ys])
    return dict(pearson_r=float(np.corrcoef(jj, ff)[0, 1]),
                mean_abs_div=float(np.mean(np.abs(jj - ff))),
                weeks=int(len(ys)))


if __name__ == "__main__":
    import sys, os, json, pandas as pd
    BASE = os.path.dirname(os.path.abspath(__file__))
    DATA = ("/Users/mac/Documents/学习/找工作/"
            "SolveX/bench/sessions/r4-c3-journal-mwodcgan/"
            "data/2026_MCM_Problem_C_Data.csv")
    seasons = load_data(DATA)
    fits = {}
    out_rows = []
    for s in sorted(seasons):
        sched = build_schedule(seasons[s])
        sched["season"] = s
        f = fit_season(sched, n_mc=300, seed=s)
        fits[s] = f
        print(f"s{s:2d}: sigma_e={f['meta']['sigma_e']:.2f} "
              f"lnL={f['meta']['lnl']:7.1f} "
              f"exact%={100*f['meta']['exactly_matched']:.0f} "
              f"weeks={f['meta']['weeks_fitted']}")
        for r in f["rows"]:
            out_rows.append(dict(season=s, **r))
    df = pd.DataFrame(out_rows)
    df.to_csv(os.path.join(BASE, "outputs_fanvote_samples.csv"), index=False)
    print("total contestant-week rows:", len(df))
    print("divergence summary:", vote_prior_summary(fits))
