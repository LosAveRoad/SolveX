"""
Model 2: Counterfactual Rule Engine for DWTS (Rank vs. Percentage vs. Judges-Save).

Replays all 34 seasons of Dancing with the Stars under different judge/fan
vote-combination rules and quantifies which rule favors fans vs. judges, and
resolves the Rice / Cyrus / Palin / Bones controversies.

Assumption M (stated in the problem): the season's actual combination rule is
  - Rank rule              : seasons 1
  - Percentage rule        : seasons 2-27
  - Rank rule + judges-save: seasons 28-34

Fan votes v_iw are unobserved. Since Model 1 artifacts are not yet on disk, this
module re-estimates them internally with the same Bayesian-style latent model
that Model 1 uses (documented so it can be swapped for Model 1 posterior files):

    log v_iw = a_i + tau * z_iw + eps_iw,      eps_iw ~ N(0, sigma_e^2)

where a_i ~ N(0, sigma_a^2) is a contestant popularity effect (persists across
weeks), z_iw is the week-w standardized judge score of contestant i, tau is the
fan sensitivity to dance quality, and sigma_e is weekly preference noise.
The popularity vector a is fitted by coordinate ascent (two passes, coarse grid
[-4, 4] with 101 points then a refined local grid, 20 sweeps per pass) so that
the observed eliminations are (as closely as possible) reproduced under each
season's actual rule.  Posterior draws add eps noise and are repaired each week
to be consistent with the observed eliminations (importance-support repair);
a per-season-week `repair_failed` diagnostic records any week where the repair
could NOT place the eliminated couple(s) in the bottom set.

Rules implemented
-----------------
rank rule   : c_iw = rank_w(s_iw) + rank_w(v_iw)                    eliminate argmin
percent rule: c_iw = 50 * s_sh_iw + 50 * v_sh_iw, where s_sh = s / sum_w(s)
              and v_sh = v / sum_w(v)  (both sources share-normalized within the
              week, i.e. the show's 50/50 percentage blend; scale-invariant in
              the absolute magnitude of v).                        eliminate argmin
judges-save : bottom-2 by rank-rule composite; judges eliminate the one with the
              worse cumulative season judge total (their own scores only).

Outputs (all under 02_programming/model_2/)
- fan_vote_estimates.csv        : point estimates + CI95 per contestant-week
- rule_replay_flip_table.csv    : per-season flip counts between rule pairs
- fan_favor_index.csv           : kappa = corr(c, rank v) - corr(c, rank s)
- elimination_consistency.csv   : reproducibility of actual eliminations
                                  + repair_failed diagnostics per season
- repair_diagnostics.csv        : repair outcome per (season, week)
- controversy_cases.csv         : Rice/Cyrus/Palin/Bones under each method
- divergence_cases.csv          : auto-detected judge-fan divergence celebrities
- recommendation_matrix.csv     : side-by-side rule metrics
- figures/*.png
"""

import re
import json
import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(20260115)

BASE = Path("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r3-c3-review-mwntpmop")
DATA = BASE / "data" / "2026_MCM_Problem_C_Data.csv"
OUT = BASE / "02_programming" / "model_2"
FIGS = OUT / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

N_DRAWS = 300          # posterior fan-vote draws per season

# ----------------------------------------------------------------------------
# 1. Data parsing
# ----------------------------------------------------------------------------

def parse_data():
    df = pd.read_csv(DATA, encoding="utf-8-sig")
    recs = []
    for _, r in df.iterrows():
        res = str(r["results"])
        m = re.search(r"Eliminated Week (\d+)", res)
        eliminated_week = int(m.group(1)) if m else np.nan
        # weeks with positive judge scores
        week_scores = {}
        for w in range(1, 12):
            tot, npos = 0.0, 0
            for j in range(1, 5):
                val = r.get(f"week{w}_judge{j}_score")
                if val not in ("N/A",) and pd.notna(val):
                    fv = float(val)
                    if fv > 0:
                        tot += fv
                        npos += 1
            if npos:
                week_scores[w] = tot
        last_week = max(week_scores) if week_scores else 0
        # Actual exit week: eliminated contestants leave the week they are voted
        # off; FINALISTS (place results, no "Eliminated Week") exit at the finale,
        # i.e. their last competing week.
        exit_week = (eliminated_week if pd.notna(eliminated_week)
                     else float(last_week))
        recs.append({
            "season": int(r["season"]),
            "celebrity": str(r["celebrity_name"]).strip(),
            "pro": str(r["ballroom_partner"]).strip(),
            "industry": str(r["celebrity_industry"]).strip(),
            "age": pd.to_numeric(r["celebrity_age_during_season"], errors="coerce"),
            "placement": int(r["placement"]) if pd.notna(r["placement"]) else np.nan,
            "eliminated_week": eliminated_week,
            "exit_week": exit_week,
            "danced_weeks": week_scores,
            "last_week": last_week,
            "withdrew": res == "Withdrew",
            "finale": "Place" in res and not res.startswith("Eliminated"),
        })
    return pd.DataFrame(recs)


# ----------------------------------------------------------------------------
# 2. Rule engine
# ----------------------------------------------------------------------------

def rank_rule_composite(s_rank, v):
    """c_iw = rank(s) + rank(v), ascending, standard competition ranking."""
    return s_rank + _rank(v)


def _rank(x):
    n = len(x)
    order = np.argsort(x, kind="stable")
    ranks = np.empty(n)
    r = 1
    k = 0
    while k < n:
        m = k
        while m + 1 < n and x[order[m + 1]] == x[order[k]]:
            m += 1
        ranks[order[k:m + 1]] = r
        r += m - k + 1
        k = m + 1
    return ranks


def ranks_vec(x):
    """Vectorized standard-competition (min-method) ranks over the last axis."""
    order = np.argsort(x, axis=-1, kind="stable")
    xs = np.take_along_axis(x, order, axis=-1)
    starts = np.concatenate(
        [np.ones(xs.shape[:-1] + (1,), dtype=bool), xs[..., 1:] != xs[..., :-1]],
        axis=-1)
    pos = np.arange(1, xs.shape[-1] + 1)
    ranks_sorted = np.maximum.accumulate(np.where(starts, pos, 0), axis=-1)
    ranks = np.empty_like(ranks_sorted)
    np.put_along_axis(ranks, order, ranks_sorted, axis=-1)
    return ranks.astype(float)


def percent_rule_composite(s, v):
    """Show's percentage method (Appendix of the problem): convert each source to
    its share of the week's total, then blend 50/50:
        c_i = 100 * (s_sh_i + v_sh_i) / 2 = 50*s_sh_i + 50*v_sh_i.
    Scale-invariant jointly in (s, v) magnitude; sums to 100 per week."""
    s_sh = s / s.sum()
    v_sh = v / v.sum()
    return 100.0 * (s_sh + v_sh) / 2.0


def season_actual_rule(season):
    """Assumption M: actual combination rule per season."""
    if season == 1:
        return ("rank", False)       # (composite rule, judges_save)
    if 2 <= season <= 27:
        return ("percent", False)
    return ("rank", True)


def bottom_k(composite, k, tie_break):
    """indices of the k lowest composite values; tie_break used to stagger ties."""
    return np.argsort(composite + 1e-9 * tie_break, kind="stable")[:k] if k else np.array([], dtype=int)


def replay_season(names, s_mat, v_mat, weeks_elim, finale_week, rule, judges_save,
                  judge_cum=None, tie_break=None):
    """Replay one season with given fan-vote matrix v_mat (n_wks x n_cons).

    s_mat : (n_wks x n_cons) judge totals, nan where not competing that week
    weeks_elim : dict week -> list of contestant indices actually eliminated
    finale_week : week of the finale (no composite elimination)
    Returns sim_elim_week array (nan = survived the replay's eliminations up to
    finale) and sim placement (1 = winner).
    """
    n = s_mat.shape[1]
    sim_elim_week = np.full(n, np.nan)
    remaining = np.ones(n, dtype=bool)

    for w in sorted(weeks_elim):
        act = np.where(remaining)[0]
        if len(act) <= len(weeks_elim[w]):
            continue
        s_w = s_mat[w - 1][act]  # nan if absent this week (bye) -> treat below
        v_w = v_mat[w - 1][act]
        valid = ~np.isnan(s_w)
        act_v = act[valid]
        s_w = s_w[valid]
        v_w = v_w[valid]
        tb = tie_break[act_v]
        if rule == "rank":
            s_rank = _rank(s_w)
            comp = rank_rule_composite(s_rank, v_w)
        else:
            comp = percent_rule_composite(s_w, v_w)
        k = len(weeks_elim[w])
        if judges_save and k == 1 and len(act_v) >= 2:
            # judges-save: bottom TWO by composite, judges eliminate the one with
            # the worse cumulative judge total entering this week
            idx2c = bottom_k(comp, 2, tb)
            idx2 = act_v[idx2c]
            jc = np.atleast_1d(judge_cum[w - 1][idx2])
            out = int(idx2[int(np.argmin(jc))])
            sim_elim_week[out] = w
            remaining[out] = False
        else:
            elim_idx = bottom_k(comp, k, tb)
            for idx in elim_idx:
                sim_elim_week[act_v[idx]] = w
            remaining[act_v[elim_idx]] = False

    # finale: rank remaining by composite at finale week
    act = np.where(remaining)[0]
    places = np.empty(n)
    s_w = s_mat[finale_week - 1][act]
    v_w = v_mat[finale_week - 1][act]
    valid = ~np.isnan(s_w)
    act_v = act[valid]
    comp = (rank_rule_composite(_rank(s_w[valid]), v_w[valid])
            if rule == "rank" else percent_rule_composite(s_w[valid], v_w[valid]))
    order = np.argsort(comp + 1e-9 * 0.0, kind="stable")  # ascending = best
    for rank_pos, idx in enumerate(order, start=1):
        places[act_v[idx]] = rank_pos
    # eliminated: worse placement than every finalist, in reverse elimination order
    elim_order = sorted([i for i in range(n) if not np.isnan(sim_elim_week[i])],
                        key=lambda i: -sim_elim_week[i])
    base = len(act_v) + 1
    for pos, idx in enumerate(elim_order):
        places[idx] = base + pos
    return sim_elim_week, places


# ----------------------------------------------------------------------------
# 3. Fan-vote estimation (Model 1-style latent model, fitted internally)
# ----------------------------------------------------------------------------

SIGMA_A, SIGMA_E, TAU = 0.65, 0.45, 0.30


def build_season_matrices(rec, weeks):
    names = list(rec["celebrity"])
    n = len(names)
    s_mat = np.full((len(weeks), n), np.nan)
    for i, dw in enumerate(rec["danced_weeks"]):
        for k, w in enumerate(weeks):
            if w in dw:
                s_mat[k, i] = dw[w]
    ew = rec["eliminated_week"].astype(float)
    weeks_elim = {}
    for w_k, w in enumerate(weeks):
        eliminated = np.where(ew == w)[0]
        if len(eliminated):
            weeks_elim[w] = list(eliminated)
    finale_week = weeks[-1]
    return names, s_mat, weeks_elim, finale_week


def make_week_static(s_mat, weeks_elim, n, rule, save, judge_cum):
    """Precompute per-elimination-week constants used by the vectorized penalty.

    Bottom-set size n_target: n_elim normally, but n_elim + 1 for a
    single-elimination week under the judges-save (the eliminated couple must
    merely be IN the bottom two; the judges then pick from that pair)."""
    rows = []
    for w in sorted(weeks_elim):
        k = w - 1
        s_row = s_mat[k]
        act = ~np.isnan(s_row)
        elim_idx = np.array([i for i in weeks_elim[w] if act[i]], dtype=int)
        elim_set = set(elim_idx.tolist())
        surv_idx = np.array([i for i in np.where(act)[0] if i not in elim_set],
                            dtype=int)
        if len(elim_idx) == 0 or len(surv_idx) == 0:
            continue
        row = {"week": w, "k": k,
               "elim": elim_idx, "surv": surv_idx,
               "act_idx": np.where(act)[0],
               "n_elim": len(elim_idx),
               "n_target": min(len(surv_idx) + len(elim_idx),
                               len(elim_idx) + (1 if (save and len(elim_idx) == 1)
                                                else 0))}
        if rule == "rank":
            row["s_rank"] = _rank(np.nan_to_num(s_row, nan=1e9))
        else:
            s_act = s_row[act]
            row["s_sh"] = s_act / s_act.sum()
        if save and len(elim_idx) == 1:
            jc = judge_cum[k]
            # survivors whose cumulative judge total is WORSE than the actually
            # eliminated couple's: if any of them shares the bottom two with e,
            # the judges (choosing by our cumulative-judge proxy) would eliminate
            # that survivor instead of e -> the week would not be reproduced.
            row["good_partner"] = surv_idx[jc[surv_idx] > jc[elim_idx[0]]]
        else:
            row["good_partner"] = np.array([], dtype=int)
        rows.append(row)
    return rows


def comp_grid(logv, rule, week_static, s_rank_full):
    """Composite c for every grid slice of log-votes.

    logv : (G, W, n) log fan votes (grid dimension first)
    Returns (G, W, n) composite; inactive contestants get +inf so they are never
    compared.  The percentage branch is share-normalized within each week over
    ACTIVE contestants only: c = 50 * s_sh + 50 * v_sh."""
    G, W, n = logv.shape
    if rule == "rank":
        rv = ranks_vec(np.exp(logv))                     # (G, W, n)
        return rv + s_rank_full[None, :, :]
    comp = np.full((G, W, n), np.inf)
    v = np.exp(logv)
    for row in week_static:
        k, act_idx = row["k"], row["act_idx"]
        vv = v[:, k][:, act_idx]                         # (G, A)
        v_sh = vv / vv.sum(axis=1, keepdims=True)
        comp[:, k, act_idx] = 50.0 * (v_sh + row["s_sh"][None, :])
    return comp


def fit_fan_votes(rec, names, s_mat, weeks_elim, finale_week, weeks, rule, save):
    """Coordinate ascent on popularity a_i so observed eliminations reproduce.

    Two passes:
      pass 1: 20 sweeps over a coarse grid a_i in [-4, 4] (101 points);
      pass 2: 20 sweeps over a refined local grid (a_i +- 0.4, 101 points).
    Each contestant's grid is evaluated VECTORIZED (all 101 values at once),
    so the heavier fit stays fast. Consistency penalty: for each eliminated e
    and survivor j with c_e > c_j (violated order) add margin + c_e - c_j
    (margin 0.5 rank units / 0.25 percentage points) plus a 0.01 ridge on a."""
    n = s_mat.shape[1]
    z_mat = np.full_like(s_mat, np.nan)
    for k in range(s_mat.shape[0]):
        act = ~np.isnan(s_mat[k])
        if act.sum() > 1:
            std = s_mat[k][act].std()
            z_mat[k][act] = (s_mat[k][act] - s_mat[k][act].mean()) / (std if std else 1.0)
    base_lv = TAU * np.nan_to_num(z_mat)  # tau * z component

    # full-matrix judge ranks for the rank rule (constants w.r.t. a)
    s_rank_full = np.zeros_like(s_mat)
    for k in range(s_mat.shape[0]):
        s_rank_full[k] = _rank(np.nan_to_num(s_mat[k], nan=1e9))

    # cumulative judge total entering each week (judges-save proxy, constants w.r.t. a)
    cum_fit = np.zeros_like(s_mat)
    for k in range(s_mat.shape[0]):
        cum_fit[k] = np.nan_to_num(s_mat[:k + 1]).sum(axis=0)
    week_static = make_week_static(s_mat, weeks_elim, n, rule, save, cum_fit)
    margin = 0.5 if rule == "rank" else 0.25

    def penalty_grid(a, i, grid):
        """Penalty for each value of a[i] on `grid`, other entries fixed."""
        a2_full = float(a @ a)
        L = a[None, :] + base_lv                      # (W, n)
        G = len(grid)
        Lg = np.broadcast_to(L, (G, s_mat.shape[0], n)).copy()
        Lg[:, :, i] = grid[:, None]
        comp = comp_grid(Lg, rule, week_static, s_rank_full)
        pen = np.zeros(G)
        for row in week_static:
            cand = comp[:, row["k"]][:, row["act_idx"]]
            nt = min(row["n_target"], cand.shape[1] - 1)
            nt = max(nt, 1)
            # threshold = n_target-th smallest composite among active contestants
            t = np.partition(cand, nt - 1, axis=1)[:, nt - 1]     # (G,)
            ce = comp[:, row["k"]][:, row["elim"]]                # (G, E)
            # (i) eliminated couple(s) below the bottom-set cutoff
            viol = np.maximum(0.0, margin + ce - t[:, None])      # (G, E)
            pen += viol.sum(axis=1)
            # (ii) judges-save: some survivor with WORSE cumulative judge total
            # than e must also sit inside the bottom two, so that the judges'
            # pick (by cumulative-judge proxy) is e and not that survivor
            gp = row["good_partner"]
            if len(gp):
                cg = comp[:, row["k"]][:, gp]                     # (G, P)
                cmin = cg.min(axis=1)                             # best candidate
                pen += np.maximum(0.0, margin + cmin - t)
        # ridge: 0.01 * ||a||^2 with a[i] replaced by each grid value
        pen += 0.01 * (a2_full - a[i] ** 2 + grid ** 2)
        return pen

    def coord_pass(a, grid_fn, n_sweeps):
        for _ in range(n_sweeps):
            for i in range(n):
                grid = grid_fn(i)
                pen = penalty_grid(a, i, grid)
                a[i] = grid[int(np.argmin(pen))]
        return a

    a = np.zeros(n)
    # pass 1: coarse full grid [-4, 4], 101 points, 20 sweeps
    coord_pass(a, lambda i: np.linspace(-4.0, 4.0, 101), 20)
    # pass 2: refined local grid around current values, 101 points, 20 sweeps
    coord_pass(a, lambda i: np.linspace(a[i] - 0.4, a[i] + 0.4, 101), 20)

    # final penalty (diagnostic: 0 = all observed eliminations consistent)
    L = a[None, :] + base_lv
    comp = comp_grid(L[None, :, :], rule, week_static, s_rank_full)
    pen_clean = 0.0
    for row in week_static:
        cand = comp[0, row["k"]][row["act_idx"]]
        nt = max(min(row["n_target"], cand.shape[0] - 1), 1)
        t = np.partition(cand, nt - 1)[nt - 1]
        ce = comp[0, row["k"]][row["elim"]]
        pen_clean += np.maximum(0.0, margin + ce - t).sum()
        gp = row["good_partner"]
        if len(gp):
            pen_clean += max(0.0, margin + comp[0, row["k"]][gp].min() - t)
    pen_clean += 0.01 * float(a @ a)
    return a, z_mat, base_lv, pen_clean


def repair_week(eps_row, s_row, z_row, eliminated, rule, a_slice,
                save=False, judge_cum_row=None, n_iter=200):
    """Repair the weekly eps noise so the eliminated set is rule-consistent.

    Dual-sided coordinate repair: the eliminated couple's log-vote is pushed
    DOWN toward the bottom-set cutoff by step = 0.15 * (comp[e] - cutoff + 0.1),
    and the surviving 'occupant' of the bottom set with the highest composite
    is pushed UP by the same amount.  This two-sided move is essential under
    the share-normalized percentage rule (where lowering one vote raises every
    other share, so a one-sided descent can stall) and under the rank rule
    (where a blocking survivor must rise in the fan-vote ranking).  eps_iw is
    free per (contestant, week), so each week can be repaired independently.

    Percentage composite is share-normalized within the week (50*s_sh+50*v_sh
    over active cast).  For a single-elimination week under the judges-save,
    the eliminated couple only needs to be IN the bottom two and the other
    bottom-two member must have a worse cumulative judge total than e so the
    judges' pick lands on e; otherwise a 'good partner' (worse cumulative
    judge total sitting just outside the bottom two) is nudged down to swap in."""
    n = len(s_row)
    act = ~np.isnan(s_row)
    tau_z = TAU * np.nan_to_num(z_row)
    for _ in range(n_iter):
        v = np.exp(a_slice + tau_z + eps_row)
        if rule == "rank":
            comp = _rank(np.nan_to_num(s_row, nan=1e9)) + _rank(v)
            comp[~act] = np.inf
        else:
            ss, vv = np.nan_to_num(s_row), v
            comp = np.full(n, np.inf)
            comp[act] = percent_rule_composite(ss[act], vv[act])
        act_idx = np.where(act)[0]
        elim_set = set(eliminated)
        n_target = len(eliminated) + (1 if (save and len(eliminated) == 1
                                            and len(act) > len(eliminated) + 1)
                                      else 0)
        order = act_idx[np.argsort(comp[act_idx], kind="stable")]
        n_target = min(n_target, len(order))
        bottom = order[:n_target]
        cutoff = comp[bottom[-1]]
        violated = False
        infeasible = False
        for e in eliminated:
            if not act[e]:
                continue
            if e not in set(bottom.tolist()):
                # membership: couple must enter the bottom n_target
                step = 0.15 * (comp[e] - cutoff + 0.1)
                eps_row[e] -= step
                occ = [j for j in bottom.tolist() if j not in elim_set]
                if occ:
                    jmax = max(occ, key=lambda j: comp[j])
                    eps_row[jmax] += 0.15 * (comp[e] - cutoff + 0.1)
                violated = True
            elif (save and len(eliminated) == 1 and judge_cum_row is not None
                  and n_target == 2 and len(order) > 2):
                # judges-save partner condition
                o = int(next(j for j in bottom if j != e))
                if judge_cum_row[o] <= judge_cum_row[e]:
                    good = [j for j in order[n_target:]
                            if judge_cum_row[j] > judge_cum_row[e]]
                    if good:
                        p = max(good, key=lambda j: (comp[j]
                                                     if np.isfinite(comp[j])
                                                     else -np.inf))
                        eps_row[p] -= 0.15 * (comp[p] - comp[o] + 0.1)
                        violated = True
                    else:
                        # e has the worst judges' total of all actives: under the
                        # cumulative-judge proxy the save cannot pick e -> honest
                        # repair failure for this season-week
                        infeasible = True
        if infeasible or not violated:
            break
    return eps_row


def repair_check(s_row, v_row, eliminated, rule, save=False, judge_cum_row=None):
    """True if, under the exact replay semantics, the eliminated set is the one
    the rules would remove: bottom-n_elim by composite (or, for a save week,
    e in the bottom two AND the judges' cumulative-judge pick equals e)."""
    act = ~np.isnan(s_row)
    v = np.asarray(v_row, dtype=float)
    if rule == "rank":
        comp = _rank(np.nan_to_num(s_row, nan=1e9)) + _rank(v)
    else:
        comp = np.full(len(s_row), np.inf)
        comp[act] = percent_rule_composite(
            np.nan_to_num(s_row)[act], v[act])
    act_idx = np.where(act)[0]
    k = sum(1 for e in eliminated if act[e])
    if k == 0:
        return True
    order = act_idx[np.argsort(comp[act_idx], kind="stable")]
    if save and k == 1 and len(order) > 2 and judge_cum_row is not None:
        bottom2 = set(order[:2].tolist())
        e = int(eliminated[0])
        if e not in bottom2:
            return False
        o = [j for j in bottom2 if j != e][0]
        return judge_cum_row[o] > judge_cum_row[e]
    bottom = set(order[:k].tolist())
    return bottom == set(int(e) for e in eliminated if act[e])


# ----------------------------------------------------------------------------
# 4. Metrics
# ----------------------------------------------------------------------------

def kendall_tau(x, y):
    n = len(x)
    c = d = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = np.sign((x[i] - x[j]) * (y[i] - y[j]))
            c += s > 0
            d += s < 0
    return (c - d) / (c + d) if (c + d) else np.nan


def fan_favor_index(s_mat, v_mat, rule):
    """kappa = corr(composite, rank(v)) - corr(composite, rank(s)) over active (week,i)."""
    cs, crs, crv, cv = [], [], [], []
    for k in range(s_mat.shape[0]):
        act = ~np.isnan(s_mat[k])
        if act.sum() < 3:
            continue
        s, v = s_mat[k][act], v_mat[k][act]
        if rule == "rank":
            comp = _rank(np.nan_to_num(s, nan=1e9)) + _rank(v)
        else:
            comp = percent_rule_composite(s, v)   # share-normalized 50/50 blend
        cs += list(comp)
        crs += list(_rank(s))
        crv += list(_rank(v))
        cv += list(v)
    cs, crs, crv, cv = map(np.array, (cs, crs, crv, cv))
    def corr(a, b):
        if a.std() == 0 or b.std() == 0:
            return np.nan
        return np.corrcoef(a, b)[0, 1]
    return corr(cs, crv) - corr(cs, crs)


# ----------------------------------------------------------------------------
# 5. Main pipeline
# ----------------------------------------------------------------------------

def main():
    print("Parsing data ...")
    cast = parse_data()
    cast = cast[~cast["withdrew"]].reset_index(drop=True)
    results = []

    season_state = {}
    repair_diag_rows = []
    for season, rec in cast[cast.season > 0].groupby("season"):
        rec = rec.sort_values("last_week", ascending=True)
        weeks = list(range(1, rec["last_week"].max() + 1))
        names, s_mat, weeks_elim, finale_week = build_season_matrices(rec, weeks)
        rule, save = season_actual_rule(season)
        # cumulative judge total entering each week (for judges-save)
        cum = np.zeros_like(s_mat)
        for k in range(s_mat.shape[0]):
            cum[k] = np.nan_to_num(s_mat[:k + 1]).sum(axis=0)
        a, z_mat, base_lv, resid = fit_fan_votes(rec, names, s_mat, weeks_elim,
                                                 finale_week, weeks, rule, save)

        # point-estimate eps repaired under the actual rule + repair diagnostic
        eps0 = np.zeros_like(base_lv)
        for w, eliminated in weeks_elim.items():
            eps0[w - 1] = repair_week(eps0[w - 1].copy(), s_mat[w - 1],
                                      z_mat[w - 1], eliminated, rule, a,
                                      save=save, judge_cum_row=cum[w - 1])
        v_point = np.exp(base_lv + a[None, :] + eps0)
        for w in sorted(weeks_elim):
            eliminated = weeks_elim[w]
            ok = repair_check(s_mat[w - 1], v_point[w - 1], eliminated, rule,
                              save=save, judge_cum_row=cum[w - 1])
            repair_diag_rows.append({
                "season": season, "week": w,
                "n_eliminated": len(eliminated),
                "repair_ok": bool(ok),
            })

        season_state[season] = dict(names=names, s_mat=s_mat, z_mat=z_mat,
                                    weeks_elim=weeks_elim, finale_week=finale_week,
                                    weeks=weeks, rule=rule, save=save, a=a,
                                    cum=cum, base_lv=base_lv, resid=resid,
                                    v_point=v_point)
        print(f"  season {season:2d}: rule={rule:8s} save={save} "
              f"consistency-penalty={resid:9.3f} cast={len(names)} "
              f"elim-weeks={sorted(weeks_elim)}")

    repair_diag = pd.DataFrame(repair_diag_rows)
    repair_diag.to_csv(OUT / "repair_diagnostics.csv", index=False)

    # ---- posterior draws + replays -----------------------------------------
    flip_records, fanfav_records, cons_records = [], [], []
    draw_v = {}
    controversy_names = {
        2: ["Jerry Rice"], 4: ["Billy Ray Cyrus"],
        11: ["Bristol Palin"], 27: ["Bobby Bones"],
    }
    surv_records = {s: {} for s in controversy_names}
    place_draws = {s: {} for s in controversy_names}

    rules_c = [("rank", False), ("percent", False), ("rank", True)]

    for season, st in season_state.items():
        names, s_mat, weeks_elim = st["names"], st["s_mat"], st["weeks_elim"]
        rule_a, save_a = st["rule"], st["save"]
        n = len(names)
        weeks = st["weeks"]
        z_mat, base_lv, a = st["z_mat"], st["base_lv"], st["a"]
        v_point = st["v_point"]

        # point-estimate replay metrics
        cons = {"season": season, "actual_rule": rule_a + ("+save" if save_a else "")}
        for rp, sv in rules_c:
            tag = rp + ("+save" if sv else "")
            sim_ew, sim_pl = replay_season(names, s_mat, v_point, weeks_elim,
                                           st["finale_week"], rp, sv,
                                           judge_cum=st["cum"],
                                           tie_break=np.arange(n, dtype=float))
            match = np.mean([set(np.where(sim_ew == w)[0]) == set(idx)
                             for w, idx in weeks_elim.items()])
            tau = kendall_tau(np.nan_to_num(sim_pl), np.nan_to_num(
                [dict((c, p) for c, p in zip(names,
                     cast[cast.season == season].sort_values("last_week")["placement"]))[nm]
                 for nm in names]))
            cons[f"match_{tag}"] = match
            cons[f"tau_{tag}"] = tau

        # repair-failure diagnostics (per season-week, summarized per season)
        sub = repair_diag[repair_diag.season == season]
        failed = sub[~sub.repair_ok]
        cons["n_weeks"] = len(sub)
        cons["repair_failed"] = int(len(failed))          # count of failed season-weeks
        cons["repair_failed_frac"] = (len(failed) / len(sub)) if len(sub) else 0.0
        cons["repair_failed_weeks"] = ";".join(str(x) for x in failed.week)
        cons["n_double_elim_weeks"] = int((sub.n_eliminated > 1).sum())
        cons_records.append(cons)

        # Monte Carlo draws
        M = N_DRAWS
        v_draws = np.empty((M, s_mat.shape[0], n))
        for m in range(M):
            eps = RNG.normal(0, SIGMA_E, size=v_point.shape)
            for w, eliminated in weeks_elim.items():
                eps[w - 1] = repair_week(eps[w - 1], s_mat[w - 1], z_mat[w - 1],
                                         eliminated, rule_a, a, save=save_a,
                                         judge_cum_row=st["cum"][w - 1])
            v_draws[m] = np.exp(base_lv + a[None, :] + eps)
        draw_v[season] = v_draws

        # flip counts between each rule pair (same draws -> paired comparison)
        pairs = [(("rank", False), ("percent", False)),
                 (("rank", False), ("rank", True)),
                 (("percent", False), ("rank", True))]
        sim_store = {}
        for rp, sv in rules_c:
            sim_store[(rp, sv)] = []
            for m in range(M):
                sim_ew, sim_pl = replay_season(names, s_mat, v_draws[m], weeks_elim,
                                               st["finale_week"], rp, sv,
                                               judge_cum=st["cum"],
                                               tie_break=RNG.random(n))
                sim_store[(rp, sv)].append((sim_ew, sim_pl))
        for (rA, sA), (rB, sB) in pairs:
            tagA, tagB = rA + ("+save" if sA else ""), rB + ("+save" if sB else "")
            flips = []
            for m in range(M):
                ewA, _ = sim_store[(rA, sA)][m]
                ewB, _ = sim_store[(rB, sB)][m]
                f = 0
                for w, idx in weeks_elim.items():
                    setA = set(np.where(ewA == w)[0])
                    setB = set(np.where(ewB == w)[0])
                    if setA != setB:
                        f += 1
                flips.append(f / len(weeks_elim))
            flips = np.array(flips)
            flip_records.append({
                "season": season, "rule_A": tagA, "rule_B": tagB,
                "flip_fraction_mean": flips.mean(),
                "flip_fraction_ci_lo": np.percentile(flips, 2.5),
                "flip_fraction_ci_hi": np.percentile(flips, 97.5),
            })

        # fan-favor index per rule (point estimates)
        for rp, sv in rules_c:
            tag = rp + ("+save" if sv else "")
            fanfav_records.append({"season": season, "rule": tag,
                                   "kappa": fan_favor_index(s_mat, v_point, rp),
                                   "era": ("S1 rank" if season == 1 else
                                           "S2-27 percent" if season <= 27 else "S28+ rank+save"),
                                   "actual": (rp == rule_a and sv == save_a)})

        # controversy survival across draws
        if season in controversy_names:
            for nm in controversy_names[season]:
                if nm not in names:
                    continue
                i = names.index(nm)
                for rp, sv in rules_c:
                    tag = rp + ("+save" if sv else "")
                    surv = []
                    for m in range(M):
                        ew, pl = sim_store[(rp, sv)][m]
                        surv.append(1.0 if np.isnan(ew[i]) else
                                    (ew[i] - 0.5))  # survival to week w = ew >= w
                    surv_records[season][nm + "|" + tag] = np.array(surv)
                    place_draws[season][nm + "|" + tag] = np.array(
                        [sim_store[(rp, sv)][m][1][i] for m in range(M)])

    flip_df = pd.DataFrame(flip_records)
    fanfav_df = pd.DataFrame(fanfav_records)
    cons_df = pd.DataFrame(cons_records)
    flip_df.to_csv(OUT / "rule_replay_flip_table.csv", index=False)
    fanfav_df.to_csv(OUT / "fan_favor_index.csv", index=False)
    cons_df.to_csv(OUT / "elimination_consistency.csv", index=False)

    # ---- fan vote estimates file (point + CI) -------------------------------
    est_rows = []
    for season, st in season_state.items():
        names = st["names"]
        v_draws = draw_v[season]
        v_point = st["v_point"]
        for i, nm in enumerate(names):
            for k, w in enumerate(st["weeks"]):
                if np.isnan(st["s_mat"][k, i]):
                    continue
                draws = v_draws[:, k, i]
                q = np.percentile(draws, [2.5, 97.5])
                est_rows.append({
                    "season": season, "celebrity": nm, "week": w,
                    "judge_score": st["s_mat"][k, i],
                    "fan_vote_point": v_point[k, i],
                    "fan_vote_mean": draws.mean(),
                    "fan_vote_ci_lo": q[0], "fan_vote_ci_hi": q[1],
                    "rel_ci_width_pct": 100 * (q[1] - q[0]) / max(draws.mean(), 1e-9),
                })
    est_df = pd.DataFrame(est_rows)
    est_df.to_csv(OUT / "fan_vote_estimates.csv", index=False)

    # ---- controversy case study --------------------------------------------
    case_rows = []
    season_of = {2: "Jerry Rice", 4: "Billy Ray Cyrus", 11: "Bristol Palin",
                 27: "Bobby Bones"}
    for season, nm in season_of.items():
        st = season_state[season]
        if nm not in st["names"]:
            continue
        i = st["names"].index(nm)
        rec = cast[(cast.season == season) & (cast.celebrity == nm)].iloc[0]
        z_scores = [st["z_mat"][k, i] for k in range(len(st["weeks"]))
                    if not np.isnan(st["s_mat"][k, i])]
        for rp, sv in rules_c:
            tag = rp + ("+save" if sv else "")
            pl = place_draws[season].get(nm + "|" + tag)
            if pl is None:
                continue
            case_rows.append({
                "season": season, "celebrity": nm, "rule": tag,
                "actual_placement": rec["placement"],
                "actual_exit_week": rec["exit_week"],
                "mean_sim_placement": pl.mean(),
                "p_win": float(np.mean(pl <= 1.0 + 1e-9)),
                "p_finalist": float(np.mean(pl <= 3.0)),
                "p_beats_actual": float(np.mean(pl < rec["placement"])),
                "mean_z_judge": float(np.mean(z_scores)),
            })
    case_df = pd.DataFrame(case_rows)
    case_df.to_csv(OUT / "controversy_cases.csv", index=False)

    # ---- auto-detected judge/fan divergence cases --------------------------
    div_rows = []
    for season, st in season_state.items():
        for i, nm in enumerate(st["names"]):
            zs, zvs = [], []
            for k, w in enumerate(st["weeks"]):
                if np.isnan(st["s_mat"][k, i]):
                    continue
                zs.append(st["z_mat"][k, i])
                vwk = draw_v[season][:, k, ~np.isnan(st["s_mat"][k])].mean(axis=0)
                mu, sd = vwk.mean(), vwk.std()
                zvs.append((draw_v[season][:, k, i].mean() - mu) / (sd if sd else 1))
            if len(zs) >= 2 and (abs(np.mean(zs) - np.mean(zvs)) > 2):
                div_rows.append({"season": season, "celebrity": nm,
                                 "mean_z_judge": float(np.mean(zs)),
                                 "mean_z_fan": float(np.mean(zvs)),
                                 "gap": float(np.mean(zvs) - np.mean(zs))})
    div_df = pd.DataFrame(div_rows).sort_values("gap")
    div_df.to_csv(OUT / "divergence_cases.csv", index=False)

    # ---- recommendation matrix --------------------------------------------
    era_of = {"rank": "S1-era rule", "percent": "S2-27-era rule",
              "rank+save": "S28+-era rule"}
    rec_rows = []
    for rp, sv in rules_c:
        tag = rp + ("+save" if sv else "")
        ff = fanfav_df[fanfav_df.rule == tag]["kappa"]
        sub = flip_df[flip_df.season.between(2, 34)]
        flips_vs_other = np.nanmean([r["flip_fraction_mean"]
                                     for _, r in sub.iterrows()
                                     if r["rule_A"] == tag or r["rule_B"] == tag])
        rec_rows.append({
            "rule": tag, "era_label": era_of[tag],
            "mean_kappa_fan_favor": ff.mean(),
            "kappa_ci_lo": np.percentile(ff, 2.5), "kappa_ci_hi": np.percentile(ff, 97.5),
            "mean_weekly_flip_vs_other_rules": flips_vs_other,
            "mean_P_finalist_controversy_cases": np.nanmean(
                case_df[case_df.rule == tag]["p_finalist"]) if len(case_df) else np.nan,
        })
    recm = pd.DataFrame(rec_rows)
    recm.to_csv(OUT / "recommendation_matrix.csv", index=False)

    # ---- Figures ------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "serif"

    # Fig 1: fan-favor index by era
    fig, ax = plt.subplots(figsize=(8, 6))
    order = ["S1 rank", "S2-27 percent", "S28+ rank+save"]
    rules_show = ["rank", "percent", "rank+save"]
    width = 0.26
    xs = np.arange(3)
    cols = ["#4c72b0", "#dd8452", "#55a868"]
    for ri, (rule_tag, col) in enumerate(zip(rules_show, cols)):
        means, los, his = [], [], []
        for era in order:
            sub = fanfav_df[(fanfav_df.rule == rule_tag) & (fanfav_df.era == era)]["kappa"]
            means.append(sub.mean() if len(sub) else np.nan)
            los.append(np.percentile(sub, 2.5) if len(sub) else np.nan)
            his.append(np.percentile(sub, 97.5) if len(sub) else np.nan)
        ax.bar(xs + (ri - 1) * width, means, width, yerr=[np.array(means) - np.array(los),
                                                          np.array(his) - np.array(means)],
               capsize=3, label=rule_tag, color=col, alpha=0.85)
    ax.set_xticks(xs, ["Season 1 (rank era)", "Seasons 2-27\n(percentage era)",
                       "Seasons 28-34\n(rank + judges-save)"])
    ax.set_ylabel(r"Fan-favor index  $\kappa = \mathrm{corr}(c,\mathrm{rank}(v)) - \mathrm{corr}(c,\mathrm{rank}(s))$")
    ax.set_title("Fan-favor index by combination rule and era\n(2.5-97.5% Monte Carlo band)")
    ax.legend(title="counterfactual rule")
    ax.axhline(0, color="k", lw=0.8)
    fig.savefig(FIGS / "fan_favor_by_era.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # clip negative half-widths (tight quantized flip distributions can put the
    # 2.5th percentile at/above the mean)
    def _clip_err(sub):
        lo = np.maximum(0.0, (sub.flip_fraction_mean - sub.flip_fraction_ci_lo).values) * 100
        hi = np.maximum(0.0, (sub.flip_fraction_ci_hi - sub.flip_fraction_mean).values) * 100
        return [lo, hi]

    # Fig 2: per-season weekly flip fraction between percentage and rank rules
    fig, ax = plt.subplots(figsize=(8, 6))
    sub = flip_df[(flip_df.rule_A == "rank") & (flip_df.rule_B == "percent")].sort_values("season")
    ax.errorbar(sub.season, sub.flip_fraction_mean * 100,
                yerr=_clip_err(sub),
                fmt="o-", capsize=3, color="#4c72b0",
                label="rank vs. percentage (paired draws)")
    sub2 = flip_df[(flip_df.rule_B == "rank+save") & (flip_df.rule_A == "percent")].sort_values("season")
    ax.errorbar(sub2.season, sub2.flip_fraction_mean * 100,
                yerr=_clip_err(sub2),
                fmt="s--", capsize=3, color="#dd8452",
                label="percentage vs. rank+judges-save")
    ax.axvline(27.5, color="gray", ls=":", lw=1)
    ax.text(27.6, ax.get_ylim()[1] * 0.95, "S28+ actual:\nrank+save", fontsize=8, color="gray")
    ax.set_xlabel("season")
    ax.set_ylabel("weekly flip fraction (%)")
    ax.set_title("Weekly eliminations that change hands between combination rules\n(Monte Carlo mean, 95% band)")
    ax.legend()
    fig.savefig(FIGS / "flip_counts_by_season.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Fig 3: survival curves for controversies under each method
    # actual exit week = eliminated week, or last competed week for finalists
    fig, axes = plt.subplots(2, 2, figsize=(9, 7), sharex=False)
    for ax, (season, nm) in zip(axes.ravel(),
                                {2: "Jerry Rice", 4: "Billy Ray Cyrus",
                                 11: "Bristol Palin", 27: "Bobby Bones"}.items()):
        rec = cast[(cast.season == season) & (cast.celebrity == nm)].iloc[0]
        exit_week = (float(rec.eliminated_week)
                     if pd.notna(rec.eliminated_week) else float(rec.last_week))
        tag_lbl = "finale" if pd.isna(rec.eliminated_week) else f"eliminated wk {int(exit_week)}"
        st = season_state[season]
        wk = np.array(st["weeks"], dtype=float)
        for rp, sv in rules_c:
            tag = rp + ("+save" if sv else "")
            key = nm + "|" + tag
            if key not in surv_records[season]:
                continue
            raw = surv_records[season][key]
            surv = [(raw >= w).mean() for w in wk]
            ax.plot(wk, surv, marker="o", ms=3, label=tag,
                    color={"rank": "#4c72b0", "percent": "#dd8452",
                           "rank+save": "#55a868"}[tag])
        ax.axvline(exit_week, color="k", ls=":", lw=1)
        ax.set_title(f"S{season}: {nm} (actual exit: {tag_lbl}, wk {int(exit_week)})",
                     fontsize=10)
        ax.set_xlabel("week")
        ax.set_ylabel("P(still in competition)")
        ax.set_ylim(-0.05, 1.05)
        ax.legend(fontsize=7)
    fig.suptitle("Survival curves for the four 'controversial' celebrities under each combining rule")
    fig.tight_layout()
    fig.savefig(FIGS / "survival_curves_controversies.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Fig 4: certainty of fan-vote estimates by week (relative CI width)
    fig, ax = plt.subplots(figsize=(8, 6))
    for season in [2, 11, 27, 34]:
        sub = est_df[est_df.season == season].groupby("week")["rel_ci_width_pct"].mean()
        ax.plot(sub.index, sub.values, marker="o", ms=4, label=f"season {season}")
    ax.set_xlabel("week within season")
    ax.set_ylabel("relative 95% CI width of fan-vote estimate (%)")
    ax.set_title("Estimate certainty vs. week\n(early weeks are less identified: wider posterior intervals)")
    ax.legend()
    fig.savefig(FIGS / "certainty_by_week.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # ---- console summary -----------------------------------------------------
    print("\n=== elimination consistency (point estimates) ===")
    print(cons_df.to_string(index=False))
    print("\n=== fan favor index per rule (mean over seasons) ===")
    print(fanfav_df.groupby(["rule", "era"])["kappa"].agg(["mean", "count"]).to_string())
    print("\n=== controversy cases ===")
    print(case_df.to_string(index=False))
    print("\n=== recommendation matrix ===")
    print(recm.to_string(index=False))

    return dict(cast=cast, season_state=season_state, draw_v=draw_v,
                flip_df=flip_df, fanfav_df=fanfav_df, cons_df=cons_df,
                est_df=est_df, case_df=case_df, div_df=div_df, recm=recm,
                repair_diag=repair_diag)


if __name__ == "__main__":
    results = main()
