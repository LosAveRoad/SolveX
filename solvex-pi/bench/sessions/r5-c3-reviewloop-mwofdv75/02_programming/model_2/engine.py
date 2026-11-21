"""
Model 2 — Aggregation-Rule Counterfactual Engine (data + Monte Carlo)
2026 MCM Problem C: Data With The Stars

Pipeline
--------
1.  Load weekly judge scores (N/A after elimination) and build, per season,
    the observed elimination order: contestants sorted by (last scored week
    ascending, placement descending).  Withdrew contestants are excluded
    (their departure is unrelated to vote aggregation).
2.  Model-1 vote sampler (per season): latent weekly fan shares

        v_iw ~ Dirichlet(kappa * m_iw),   m_iw = softmax(gamma * zbar_iw)
        zbar_iw = mean cumulative z-score of judge points through week w

    constraining weekly shares to sum to 1 ("secrecy budget": the show's
    fan-vote totals are only ever revealed as percentages of the week's
    total).  Cumulative fan share C_i(w) = sum_{u<=w} v_iu is the hidden
    fan-vote total; cumulative judge share J_i(w) is the judge total.
    Because the data are collapsed snapshots, conditioning uses each
    contestant's CUMULATIVE totals through their final week.
3.  Importance conditioning on observed eliminations: each draw is weighted
    by prod_w [ p_elim(combined rank of the observed week-w eliminee(s)) ]^tau
    with tau=3, then systematic-resampled to 2000 posterior draws (this is
    the Model-1 forward feed required by the plan: 2000 posterior vote
    draws per season).
4.  Counterfactual replay under RANK / PERCENT / VETO on the posterior
    mode and across all 2000 draws -> flip statistics, fan-favour index,
    controversy case studies, validation, sensitivity, permutation test.
"""
import csv
import json
import collections
import numpy as np

from rules import (rank_points, percent_points, elimination_order,
                   veto_order, pairwise_flips, RULES)

RNG = np.random.default_rng(42)
DATA_PATH = "../../data/2026_MCM_Problem_C_Data.csv"
N_DRAWS = 2000
KAPPA = 25.0     # Dirichlet concentration of the fan-share prior
GAMMA = 1.0      # how strongly judge standing anchors fan-share means
TAU = 3.0        # importance-weight enforcement strength on eliminations

# Official timeline: rank-based in S1-2, percentage S3-27, rank-based
# again from S28 (assumed per the problem statement) through S34.
SEASON_RULE = {s: "PERCENT" for s in range(3, 28)}
SEASON_RULE.update({s: "RANK" for s in list(range(1, 3)) + list(range(28, 35))})
def season_rule(s):
    return SEASON_RULE[s]


def load_seasons():
    """Parse the CSV into per-season records."""
    rows = list(csv.DictReader(open(DATA_PATH, encoding="utf-8-sig")))
    seasons = collections.defaultdict(list)
    for r in rows:
        seasons[int(r["season"])].append(r)
    out = {}
    for s, rs in seasons.items():
        recs = []
        for r in rs:
            if r["results"] == "Withdrew":
                continue
            # A week counts as scored iff the summed available judge
            # points > 0 (post-elimination weeks are 0-filled and must be
            # excluded so each week's active set shrinks with real
            # eliminations).
            wk_totals = {}
            for w in range(1, 12):
                tot = 0.0
                for j in range(1, 5):
                    val = r.get(f"week{w}_judge{j}_score", "N/A")
                    if val not in ("N/A", ""):
                        tot += float(val)
                if tot > 0:
                    wk_totals[w] = tot
            wk = sorted(wk_totals)
            wlast = max(wk) if wk else 0
            J = np.array([wk_totals[w] for w in wk])   # total judge pts/week
            recs.append(dict(
                name=r["celebrity_name"], partner=r["ballroom_partner"],
                industry=r["celebrity_industry"], age=int(r["celebrity_age_during_season"]),
                placement=int(r["placement"]), results=r["results"],
                weeks=wk, wlast=wlast, J=J, Jtot=float(J.sum())))
        # observed elimination order: last scored week asc, placement desc
        recs.sort(key=lambda x: (x["wlast"], -x["placement"]))
        active = sorted(recs, key=lambda x: -x["wlast"])
        n = len(active)
        W = max(x["wlast"] for x in active)
        # judge-points matrix (NaN after elimination) & week metadata
        Jmat = np.full((n, W), np.nan)
        for i, x in enumerate(active):
            for k, w in enumerate(x["weeks"]):
                Jmat[i, w - 1] = x["J"][k]
        # observed eliminees per week (bottom-k set under elimination order)
        elim_by_week = collections.defaultdict(list)
        for x in active:
            elim_by_week[x["wlast"]].append(x)
        out[s] = dict(
            recs=recs, active=active, n=n, W=W, Jmat=Jmat,
            elim_by_week={w: [active.index(x) for x in v]
                          for w, v in elim_by_week.items()})
    return out


def weekly_active_mask(Jmat):
    """Active[i,w] = True if contestant i still dances in week w."""
    return ~np.isnan(Jmat)


def sample_posterior(s, d, n_draws=N_DRAWS):
    """Draw + importance-resample weekly fan shares for one season.
    s = season number, d = its record from load_seasons()."""
    n, W, Jmat = d["n"], d["W"], d["Jmat"]
    act = weekly_active_mask(Jmat)
    # Fully observed weekly judge totals: for eliminated contestants later
    # weeks are NaN but those weeks are irrelevant for their own share.
    Jw = np.where(act, Jmat, 0.0)                      # (n, W)
    valid_weeks = [w for w in range(W) if act[:, w].any()]
    Wv = len(valid_weeks)
    # Mean fan share m_iw via softmax of cumulative judge z-scores
    Jcum = np.cumsum(Jw, axis=1)                       # (n, W)
    z = (Jcum - Jcum.mean(0)) / (Jcum.std(0) + 1e-9)
    logits = GAMMA * z
    logits = np.where(act, logits, -np.inf)
    e = np.exp(logits - logits.max(0))
    m = e / e.sum(0)                                   # (n, Wv) col-stochastic
    P = np.stack([m[:, w] for w in valid_weeks], 1)    # (n, W)
    # ---- prior draws: Dirichlet per week over the ACTIVE set only ----
    # v_iw = e_i * P_iw ; e ~ Gamma(c, c) i.e. mean 1 -> shares adequate
    c = KAPPA * P                                      # per-contestant conc.
    g = RNG.gamma(shape=np.where(act, c, 1.0), scale=1.0,
                  size=(n_draws, n, W))
    v = g * P[None, :, :]
    v = np.where(act[None], v, 0.0)
    v /= v.sum(axis=1, keepdims=True) + 1e-12          # weekly budget
    Vcum = np.cumsum(v, axis=2)                        # fan-vote cumulative
    # ---- importance weights & systematic resampling ----
    rule = season_rule(s)
    w_ = np.ones(n_draws)
    for w, idx in d["elim_by_week"].items():
        # active set this week; combined points under the season's rule
        A = act[:, w - 1]
        ia = np.where(A)[0]
        Jc = Jcum[ia, w - 1]
        Vc = Vcum[:, ia, w - 1]                        # (draws, |A|)
        pts = RULES[rule](Jc, Vc)                      # broadcasting ok
        # elimination rank of the observed eliminee(s): their combined pts
        # must be the worst (or, under VETO seasons, worst-or-second-worst)
        worst = pts.min(axis=1)
        if len(idx) >= 2:
            # double elimination: both must be in the bottom 2
            part = np.partition(pts, 1, axis=1)
            hit = (part[:, 0] <= pts[:, idx[0]]) & (part[:, 1] >= pts[:, idx[0]])
            same = np.abs(pts[:, idx[0]] - worst) < 1e-9
            w_ *= np.where(hit | same, 1.0, 1.0 / (TAU * 4))
        else:
            i0 = idx[0]
            gap = pts[:, i0] - worst                   # >=0 iff ranked worst
            # closer to worst -> higher weight (soft enforcement)
            w_ *= np.exp(-TAU * np.maximum(gap, 0.0) / (Jc.max() + Vc.max(1) + 1e-9))
    w_ /= w_.sum()
    u = (RNG.random() + np.arange(n_draws)) / n_draws
    idx_draw = np.searchsorted(np.cumsum(w_), u)
    idx_draw = np.clip(idx_draw, 0, n_draws - 1)
    return v[idx_draw], Vcum[idx_draw], P


def combined_pts(rule, Jtot, Vtot, beta=0.5):
    return RULES[rule](Jtot, Vtot, beta=beta)


def replay_week(d, w, rule, Jcum, Vcum_draw, beta=0.5, n_finalists=2):
    """Worst-first index order for each draw at week w. Returns (draws, |A|)."""
    A = weekly_active_mask(d["Jmat"])[:, w - 1]
    ia = np.where(A)[0]
    Jc = Jcum[ia, w - 1]
    pts = combined_pts(rule, Jc, Vcum_draw[:, ia, w - 1], beta=beta)
    # stable argsort ascending; ties -> lower judge total first
    key = pts + 1e-9 * (-Jc[None, :] / (np.abs(Jc).max() + 1))
    order = np.argsort(key, axis=1, kind="mergesort")
    return ia, ia[order], pts


def run_all():
    seasons = load_seasons()
    results = {}
    for s, d in sorted(seasons.items()):
        draws, Vcum, P = sample_posterior(s, d, N_DRAWS)
        results[s] = dict(d=d, draws=draws, Vcum=Vcum,
                          v_mode=draws.mean(axis=0), P=P)
    return seasons, results


if __name__ == "__main__":
    seasons, res = run_all()
    print("seasons processed:", len(res))
    s = 2
    d = res[s]["d"]
    Jcum = np.cumsum(np.where(weekly_active_mask(d["Jmat"]), d["Jmat"], 0.0), axis=1)
    Vc = res[s]["Vcum"]
    ia, order, pts = replay_week(d, d["W"], "RANK", Jcum, Vc)
    names = [d["active"][i]["name"] for i in ia]
    obs = [d["active"][i]["name"] for i in d["elim_by_week"][d["W"]]]
    print(f"S{s} wk{d['W']} ranked-last(name):", names[order[0, 0]],
          "| observed eliminee:", obs, "| match rate:",
          float(np.mean([names[order[k, 0]] for k in range(N_DRAWS)][0] == obs[0])))
