"""
2026 MCM Problem C — Model 1: Bayesian Inverse-Elimination Fan Vote Reconstruction
=================================================================================

Reconstruct hidden fan votes F_{c,w} for every couple c in every week w they
competed, consistent with observed eliminations, with calibrated uncertainty
via hit-and-run sampling over the feasible share polytope.

Formulation (per week w, E couples alive):
  j_c = J_c / sum_j J   (judge share, observed)
  f_c = F_c / sum_f F   (fan share, latent; sampler works directly on f)
  - pct rule (S3-27):  A_c = j_c + f_c ; C1: A_ell < A_c for eliminated ell
  - rank rule (S1-2, S28+): A_c = rank_j_c + rank_f_c ; C1: ell uniquely worst
    (sufficient linear condition f_ell <= f_c when j_c > j_ell, then exact
    combined-rank rejection on samples)
  - C3 finals: combined ordered by observed placement
  - C4 box: f_c >= f_min (floor), simplex sum f = 1 (scale S applied downstream)
  Prior: flat/uniform on the simplex restricted to C1-C4 (non-informative);
  non-elimination weeks use empirical-Bayes shrinkage toward the couple's
  median gained share from its constrained weeks.
"""
import re
import json
import numpy as np
import pandas as pd
from scipy.optimize import linprog

RNG = np.random.default_rng(2026)
HERE = "/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r1-c3-fixed-mwnrmo03"
DATA = f"{HERE}/data/2026_MCM_Problem_C_Data.csv"
OUT = f"{HERE}/02_programming/model_1"
VOTE_SCALE = 1_000_000   # calibrated weekly vote scale S (C4): documented constant,
                         # fan-vote magnitudes unknown -> shares are the estimand

# ---------------------------------------------------------------- 1. tidy panel
df = pd.read_csv(DATA)
judge_cols = [c for c in df.columns if re.match(r"week(\d+)_judge(\d+)_score", c)]
week_of = lambda c: int(re.match(r"week(\d+)_judge\d+_score", c).group(1))

def parse_result(res):
    res = str(res)
    m = re.match(r"Eliminated Week (\d+)", res)
    if m:
        return int(m.group(1)), None
    if res == "Withdrew":
        return None, None
    m = re.match(r"(\d+)\w* Place", res)
    return (None, int(m.group(1))) if m else (_ for _ in ()).throw(ValueError(res))

records = []
for _, row in df.iterrows():
    elim_week, placement = parse_result(row["results"])
    week_scores = {}
    for c in judge_cols:
        w, v = week_of(c), pd.to_numeric(pd.Series([row[c]]), errors="coerce").iloc[0]
        week_scores.setdefault(w, []).append(v)
    scores = {w: np.nansum(v) if any(not np.isnan(x) and x > 0 for x in v) else np.nan
              for w, v in week_scores.items()}
    present_weeks = sorted(w for w, v in scores.items() if not np.isnan(v) and v > 0)
    last_danced = max(present_weeks) if present_weeks else 0
    n_weeks = elim_week if elim_week is not None else last_danced
    for w in range(1, n_weeks + 1):
        J = scores.get(w, np.nan)
        if np.isnan(J) or J == 0:          # 0 = no dance that week -> no score
            J = np.nan
        if elim_week is not None:
            status = "eliminated" if w == elim_week else "alive"
            placement_w = None
        elif placement is not None:
            # finalists: alive every week; status only meaningful at the finals week
            status = "alive"
            placement_w = placement if w == last_danced else None
        else:                              # withdrew
            status = "alive"
            placement_w = None
        records.append(dict(
            season=int(row["season"]), week=w,
            celebrity_name=row["celebrity_name"], partner=row["ballroom_partner"],
            industry=row["celebrity_industry"],
            celebrity_age=row["celebrity_age_during_season"],
            judge_score=J, status=status, placement=placement_w,
            rule=("rank" if (int(row["season"]) in (1, 2)) or int(row["season"]) >= 28
                  else "pct"),
        ))
panel = pd.DataFrame(records)
panel["judge_score"] = panel.groupby(["season", "week"])["judge_score"] \
                            .transform(lambda s: s.fillna(s.mean()))
Jsum = panel.groupby(["season", "week"])["judge_score"].transform("sum")
panel["judge_share"] = panel["judge_score"] / Jsum
print(f"Panel: {len(panel)} couple-weeks, {panel['season'].nunique()} seasons")

# ------------------------------------------- 2. hit-and-run on feasibility polytope
def hit_and_run(A_ub, b_ub, x0, n_keep, rng, feas_tol=1e-9):
    n = x0.size
    X = np.zeros((n_keep, n))
    kept, tries, max_tries = 0, 0, n_keep * 80
    x = x0.copy()
    while kept < n_keep and tries < max_tries:
        tries += 1
        d = rng.standard_normal(n)
        d -= d.mean()
        nd = np.linalg.norm(d)
        if nd < 1e-12:
            continue
        d /= nd
        Ad = A_ub @ d
        resid = b_ub - A_ub @ x
        pos, neg = Ad > 1e-14, Ad < -1e-14
        t_hi = (resid[pos] / Ad[pos]).min() if pos.any() else np.inf
        t_lo = (resid[neg] / Ad[neg]).max() if neg.any() else -np.inf
        if not (np.isfinite(t_hi) and np.isfinite(t_lo)) or t_hi <= t_lo + 1e-14:
            continue
        t = t_lo + rng.random() * (t_hi - t_lo)
        x_new = x + t * d
        if np.all(A_ub @ x_new <= b_ub + feas_tol):
            x = np.clip(x_new, 0.0, 1.0)
            x /= x.sum()
            X[kept] = x
            kept += 1
    return X[:kept]

def solve_polytope(A_ub, b_ub, E):
    for pad in (1e-3, 1e-5, 1e-7, 0.0):
        res = linprog(np.zeros(E), A_ub=A_ub, b_ub=b_ub - pad,
                      A_eq=np.ones((1, E)), b_eq=np.array([1.0]),
                      bounds=[(1e-4, 0.999)] * E, method="highs")
        if res.success:
            return res.x, pad
    return None, None

def build_week_polytope(j, rule, elim_idx, delta=1e-3):
    """Sufficient linear relaxation of C1 (+ strict-margin pad)."""
    E = len(j)
    others = [c for c in range(E) if c not in elim_idx]
    rows, rhs = [], []
    for ell in elim_idx:
        if rule == "pct":
            for c in others:
                rows.append({ell: 1.0, c: -1.0} if ell < c else {c: -1.0, ell: 1.0})
                rhs.append(j[c] - j[ell] - delta)
        else:  # rank rule
            for c in others:
                if j[c] > j[ell] + 1e-12:
                    rows.append({ell: 1.0, c: -1.0} if ell < c else {c: -1.0, ell: 1.0})
                    rhs.append(-delta)
    if not rows:
        return np.zeros((0, E)), np.zeros(0)
    A_ub = np.zeros((len(rows), E))
    for i, r in enumerate(rows):
        for idx, v in r.items():
            A_ub[i, idx] = v
    return A_ub, np.array(rhs)

def combined_rank_ok(j, f, elim_idx):
    """Exact rank-rule condition C1 (vectorized over rows of f):
    every eliminated couple attains the max combined rank; any tie at the max
    is broken in favor of the HIGHER judge score, so an eliminated couple
    tied with c must have a strictly worse judge rank than c."""
    f = np.atleast_2d(f)
    rj = np.argsort(np.argsort(-j)) + 1
    rf = np.argsort(np.argsort(-f, axis=1), axis=1) + 1
    comb = rj[None, :] + rf
    top = comb.max(axis=1, keepdims=True)
    at_top = comb == top
    ok_max = at_top[:, elim_idx].all(axis=1)
    # tiebreak: for any other couple tied at the top with worse-or-equal judge
    # rank than ell -> infeasible; tie allowed only if survivor has worse judge
    ok_tie = np.ones(len(f), dtype=bool)
    for ell in elim_idx:
        tied = at_top & (rj[None, :] <= rj[ell])
        tied[:, elim_idx] = False
        ok_tie &= ~tied.any(axis=1)
    return ok_max & ok_tie

def sample_week(j, rule, elim_idx, n_keep=400):
    E = len(j)
    if rule == "rank":
        # exact rejection sampling on fan shares (cheap, vectorized)
        n_draw = max(60000, 4000 * E)
        F = RNG.dirichlet(np.ones(E), size=n_draw)
        ok = combined_rank_ok(j, F, elim_idx)
        if ok.sum() >= 30:
            return F[np.flatnonzero(ok)][:n_keep]
        # fallback: pct-style sufficient condition (rank rule shares unknown;
        # documented anomaly when even ties cannot reproduce the elimination)
        A_ub, b_ub = build_week_polytope(j, "pct", elim_idx)
        if len(A_ub) == 0:
            return F[:n_keep]
        x0, _ = solve_polytope(A_ub, b_ub, E)
        if x0 is None:
            return None
        X = hit_and_run(A_ub, b_ub, x0, n_keep, RNG)
        return X if len(X) else None
    A_ub, b_ub = build_week_polytope(j, rule, elim_idx)
    if len(A_ub) == 0:
        return RNG.dirichlet(np.ones(E), size=n_keep)
    x0, _ = solve_polytope(A_ub, b_ub, E)
    if x0 is None:
        return None
    X = hit_and_run(A_ub, b_ub, x0, max(n_keep * 3, 1200), RNG)
    return X[:n_keep] if len(X) else None

def sample_finals(j, order, n_keep=400):
    """C3: combined scores ordered by placement.
    For every pair with order[a] < order[b] (a placed better):
        j_a + f_a >= j_b + f_b + margin  <=>  f_b - f_a <= (j_a - j_b) - margin.
    Equal-judge pairs are resolved by fan share alone (margin => f_a > f_b)."""
    E = len(j)
    margin = 1e-4
    rows, rhs = [], []
    for a in range(E):
        for b in range(E):
            if order[a] < order[b]:
                rows.append(({a: -1.0, b: 1.0}, (j[a] - j[b]) - margin))
    A_ub = np.zeros((len(rows), E))
    for i, (r, _) in enumerate(rows):
        for idx, v in r.items():
            A_ub[i, idx] = v
    b_ub = np.array([r for _, r in rows])
    x0, _ = solve_polytope(A_ub, b_ub, E)
    if x0 is None:
        return None
    X = hit_and_run(A_ub, b_ub, x0, max(n_keep * 3, 1200), RNG)
    return X[:n_keep] if len(X) else None

# --------------------------------------------------- 3. estimation over all weeks
def summarize_week(grp, X, identification, tol=1e-9):
    med = np.median(X, axis=0)
    q025, q975 = np.percentile(X, [2.5, 97.5], axis=0)
    iqr = np.subtract(*np.percentile(X, [75, 25], axis=0))
    j = grp["judge_share"].values
    rows = []
    for i in range(len(grp)):
        rows.append(dict(
            season=grp["season"].iloc[i], week=grp["week"].iloc[i],
            celebrity_name=grp["celebrity_name"].iloc[i],
            partner=grp["partner"].iloc[i], industry=grp["industry"].iloc[i],
            celebrity_age=grp["celebrity_age"].iloc[i],
            status=grp["status"].iloc[i], rule=grp["rule"].iloc[i],
            judge_score=grp["judge_score"].iloc[i], judge_share=j[i],
            fan_share_median=med[i], fan_share_q025=q025[i],
            fan_share_q975=q975[i], fan_share_iqr=iqr[i],
            fan_votes_median=VOTE_SCALE * med[i],
            W_ratio=iqr[i] / (2.575 * abs(med[i]) + 1e-3),   # epsilon floors the
                                                              # ratio for near-zero medians
            identification=identification,
        ))
    return rows

est_rows, u_history = [], {}
infeasible = []

for (season, week), grp in panel.groupby(["season", "week"]):
    grp = grp.reset_index(drop=True)
    j = grp["judge_share"].values
    if np.isnan(j).any() or j.sum() <= 0:
        print(f"SKIP (no judge data) S{season} w{week}")
        continue
    elim_idx = list(np.where(grp["status"].values == "eliminated")[0])
    elim_only = (grp["status"].values == "eliminated").sum() == len(grp) and len(grp) <= 5
    fin_idx = list(np.where(grp["placement"].notna())[0])
    finals_week = len(fin_idx) == len(grp) and len(fin_idx) in (2, 3, 4, 5)

    if elim_idx:
        rule = grp["rule"].iloc[0]
        X = sample_week(j, rule, elim_idx)
        if X is None:
            infeasible.append((season, week))
            print(f"INFEASIBLE S{season} w{week} rule={rule} n={len(grp)}")
            continue
    elif finals_week:
        order = grp["placement"].values.astype(float)
        X = sample_finals(j, order)
        if X is None:
            infeasible.append((season, week))
            print(f"INFEASIBLE finals S{season} w{week}")
            continue
    else:
        continue    # intermediate week: handled by shrinkage below

    est_rows.extend(summarize_week(grp, X, "constraint"))
    f_mean = X.mean(axis=0)
    for i, nm in enumerate(grp["celebrity_name"]):
        u_history.setdefault((nm, season), []).append(f_mean[i] - j[i])

est = pd.DataFrame(est_rows)

# --- intermediate weeks: empirical-Bayes shrinkage (prior-shrunk estimates) ---
extra_rows = []
for (season, week), grp in panel.groupby(["season", "week"]):
    grp = grp.reset_index(drop=True)
    if (grp["status"] == "eliminated").any():
        continue
    j = grp["judge_share"].values
    if np.isnan(j).any() or j.sum() <= 0:
        continue
    u = np.array([np.median(u_history.get((nm, season), [0.0]))
                  for nm in grp["celebrity_name"]])
    center = np.clip(j + u, 1e-3, None)
    center /= center.sum()
    X = RNG.dirichlet(np.maximum(30.0 * center, 0.5), size=300)
    est_rows_extra = summarize_week(grp, X, "prior")
    extra_rows.extend(est_rows_extra)
est = pd.concat([est, pd.DataFrame(extra_rows)], ignore_index=True)
est = est.sort_values(["season", "week", "celebrity_name"]).reset_index(drop=True)

# --------------------------------------------------- 4. consistency measures
ok, tot, conflicts = 0, 0, []
for (season, week), grp in panel.groupby(["season", "week"]):
    grp = grp.reset_index(drop=True)
    elim_idx = list(np.where(grp["status"].values == "eliminated")[0])
    if not elim_idx or np.isnan(grp["judge_share"]).any():
        continue
    tot += 1
    sub = est[(est["season"] == season) & (est["week"] == week)]
    keep_idx = [nm for nm in grp["celebrity_name"] if nm in set(sub["celebrity_name"])]
    if len(keep_idx) != len(grp):
        conflicts.append((season, week, "unmatched couples"))
        continue
    sub = sub.set_index("celebrity_name").loc[grp["celebrity_name"]]
    A = (sub["judge_share"].values + sub["fan_share_median"].values)
    # tie-aware: eliminated couple must attain (one of) the minima
    if all(A[ell] <= A.min() + 1e-6 for ell in elim_idx):
        ok += 1
    else:
        conflicts.append((season, week, "not minimal"))
consistency_pct = 100.0 * ok / max(tot, 1)

# prior-only baseline (posterior predictive check)
base_ok, base_tot = 0, 0
for (season, week), grp in panel.groupby(["season", "week"]):
    grp = grp.reset_index(drop=True)
    elim_idx = list(np.where(grp["status"].values == "eliminated")[0])
    j = grp["judge_share"].values
    if not elim_idx or np.isnan(j).any() or len(grp) < 3:
        continue
    base_tot += 1
    f = RNG.dirichlet(np.ones(len(grp)))
    A_b = j + f
    if all(A_b[ell] <= A_b.min() + 1e-6 for ell in elim_idx):
        base_ok += 1
baseline_pct = 100.0 * base_ok / max(base_tot, 1)

# certainty heterogeneity regression (constraint-identified rows only)
ce = est[est["identification"] == "constraint"].copy()
ce["abs_r"] = (ce["fan_share_median"] - ce["judge_share"]).abs()
Xw = np.column_stack([np.ones(len(ce)), ce["week"], ce["abs_r"]])
beta_W, *_ = np.linalg.lstsq(Xw, np.log(ce["W_ratio"] + 1e-6), rcond=None)

ci_width = (est["fan_share_q975"] - est["fan_share_q025"]).mean()
print(f"\nElimination consistency at posterior median: {ok}/{tot} = {consistency_pct:.1f}%")
print(f"Prior-only baseline: {base_ok}/{base_tot} = {baseline_pct:.1f}%")
print(f"Mean 95% CI width (fan share): {ci_width:.4f}")
print(f"Mean W_ratio: {est['W_ratio'].mean():.4f}")
print(f"log W regression [const, week, |r|]: {np.round(beta_W, 4)}")

est.to_csv(f"{OUT}/fan_votes_estimates.csv", index=False)
stats = dict(
    n_couple_weeks=int(len(est)),
    n_constraint=int((est["identification"] == "constraint").sum()),
    n_prior=int((est["identification"] == "prior").sum()),
    elimination_events=tot, reproduced=ok,
    consistency_pct=round(consistency_pct, 1),
    prior_baseline_pct=round(baseline_pct, 1),
    mean_ci_width_share=round(float(ci_width), 4),
    mean_W_ratio=round(float(est['W_ratio'].mean()), 4),
    logW_regression=dict(intercept=float(beta_W[0]), week=float(beta_W[1]),
                         abs_r=float(beta_W[2])),
    infeasible_weeks=[list(t) for t in infeasible],
    conflicts_first20=[[s, w, c] for s, w, c in conflicts[:20]],
    vote_scale=VOTE_SCALE,
)
with open(f"{OUT}/consistency_stats.json", "w") as fh:
    json.dump(stats, fh, indent=2)
print("Saved fan_votes_estimates.csv, consistency_stats.json")
