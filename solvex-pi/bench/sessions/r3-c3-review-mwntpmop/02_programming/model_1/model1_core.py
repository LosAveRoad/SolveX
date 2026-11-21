"""
2026 MCM Problem C — Model 1: Bayesian Fan-Vote Inversion (Elimination-Constraint Sampler)

Core pipeline:
  1. Parse the wide CSV into a weekly panel (couple-week rows).
  2. For each week, define the feasible region F_w of fan-vote shares v consistent with
     the observed elimination under the season's combination rule:
        - rank rule (seasons 1-2 and >=28): composite = rank(judge) + rank(fan); worst eliminated.
        - percentage rule (seasons 3-27): composite share c_i ∝ s_i * v_i; worst eliminated.
        - season >=28: eliminated couple must lie in the bottom TWO (judges' tiebreak).
        - finale weeks: final placement ordering must match composite ordering
          (imposed both in the point estimate and in the sampler).
  3. Point estimate per week: inverse optimization maximizing the elimination margin
     (max-min slack) with entropy regularization toward the judge-informed prior mean.
  4. Posterior model (ACTUAL implemented model):
        p(v | E) ∝ 1[v ∈ F_w] · Dir(v; q),   q_i ∝ exp(θ · s_iw),  Σ_i q_i = κ0,
     with FIXED θ = 6.0, κ0 = 12.0 for every week (fixed judge-informed prior; NO
     data-dependent recentering — option (a) of the revision). The proposal is frozen
     from the very first draw, so every retained draw is an exact iid sample from the
     truncated-Dirichlet posterior. Rejection sampling is exact (accept/reject on F_w).
     An optional two-phase adaptive mode (`adapt_q=True`) follows the revision protocol:
     Phase 1 collects the first `n_adapt` accepted draws ONLY for adaptation
     (q = KAPPA0 * (0.25 + 0.75 * accepted_mean/accepted_mean.max())), those draws are
     DISCARDED, then Phase 2 runs with fixed q and retains only Phase-2 accepted draws.
  5. Output v̂_iw with 90% credible intervals (Phase-2 draws only), CV, per-week
     effective retention, and diagnostics.
"""
import re
import numpy as np
import pandas as pd
from scipy.optimize import minimize

RNG_POINT = np.random.default_rng(20260122)   # dedicated stream -> point estimates
RNG_POST  = np.random.default_rng(20260123)   # dedicated stream -> posterior draws
# (splitting the streams makes fan_votes_point.csv independent of sampler internals)

EPS = 5e-4          # floor on any fan-vote share (0.05%)
TOL = 1e-9          # numeric tolerance for feasibility comparisons
THETA = 6.0         # prior log-strength of judge share (popularity ~ quality prior)
KAPPA0 = 12.0       # prior concentration (Σ_i q_i = κ0; width of popularity prior)
N_KEEP = 3000       # posterior draws retained per week (Phase 2 only)
N_ADAPT = 800       # phase-1 accepted draws used for adaptation, then DISCARDED
MAX_ATTEMPTS = 1_000_000

DATA = "../../data/2026_MCM_Problem_C_Data.csv"
OUTDIR = "."

# ----------------------------------------------------------------------------
# 1. Parsing
# ----------------------------------------------------------------------------
def parse_data():
    df = pd.read_csv(DATA)
    jcols = [c for c in df.columns if "_judge" in c]
    wkof = {c: int(re.match(r"week(\d+)_", c).group(1)) for c in jcols}
    df["elim_week"] = df["results"].str.extract(r"Eliminated Week (\d+)").astype(float)

    def last_active(r):
        ms = [wkof[c] for c in jcols
              if pd.notna(r[c]) and str(r[c]) != "N/A" and float(r[c]) > 0]
        return max(ms) if ms else 0

    df["last_active"] = df.apply(last_active, axis=1)
    df["withdrew"] = (df["results"] == "Withdrew")

    rows = []
    for _, r in df.iterrows():
        season = int(r["season"])
        for w in range(1, int(r["last_active"]) + 1):
            cs = [c for c in jcols if wkof[c] == w]
            pts = np.array([float(r[c]) if pd.notna(r[c]) else np.nan for c in cs])
            if np.all(np.isnan(pts)):
                continue
            pts = np.nan_to_num(pts)
            tot = pts.sum()
            if tot <= 0:
                continue
            rows.append(dict(
                season=season, week=w,
                celebrity=r["celebrity_name"], partner=r["ballroom_partner"],
                industry=r["celebrity_industry"], age=r["celebrity_age_during_season"],
                judge_points=tot,
                placement=pd.to_numeric(r["placement"], errors="coerce"),
                elim_week=r["elim_week"], withdrew=bool(r["withdrew"]),
                results=r["results"],
            ))
    panel = pd.DataFrame(rows)
    # judge share normalized within season-week
    g = panel.groupby(["season", "week"])["judge_points"].transform("sum")
    panel["judge_share"] = panel["judge_points"] / g
    # season finale week = max active week in that season
    fin = panel.groupby("season")["week"].transform("max")
    panel["is_finale"] = (panel["week"] == fin)
    # number of couples eliminated this week (withdrawals removed from constraint set)
    elim_counts = (panel[panel["elim_week"].notna()]
                   .groupby(["season", "week"]).size())
    panel["n_elim"] = panel.set_index(["season", "week"]).index.map(elim_counts).fillna(0)
    panel["n_active"] = panel.groupby(["season", "week"])["celebrity"].transform("count")
    # combination rule: rank method seasons 1-2 and >=28, percentage otherwise
    panel["rule"] = np.where(panel["season"].isin([1, 2]) | (panel["season"] >= 28),
                             "rank", "pct")
    return panel

# ----------------------------------------------------------------------------
# 2. Composite scores and feasibility
# ----------------------------------------------------------------------------
def rank1(x):
    """dense rank, 1 = best (largest x best)."""
    order = np.argsort(-x, kind="stable")
    rk = np.empty(len(x), dtype=float)
    rk[order] = np.arange(1, len(x) + 1)
    # handle ties: same value -> same rank
    sx = x[order]
    for k in range(1, len(sx)):
        if sx[k] == sx[k - 1]:
            rk[order[k]] = rk[order[k - 1]]
    return rk

def composite(s, v, rule):
    if rule == "pct":
        c = s * v
        tot = c.sum()
        return c / tot if tot > 0 else c
    else:  # rank rule
        return rank1(s) + rank1(v)   # larger = worse

def feasible(s, v, elim_idx, n_elim, rule, s28, order_pairs=None, is_finale=False):
    """Vectorized feasibility for a batch of proposals v (B, n).
    Returns boolean mask of length B. Includes the finale ordering constraint so the
    sampler sees the SAME feasible region as the point-estimate optimizer."""
    B, n = v.shape
    v = np.maximum(v, EPS); v = v / v.sum(1, keepdims=True)
    if rule == "pct":
        c = s * v
        c = c / np.maximum(c.sum(1, keepdims=True), 1e-300)  # larger = better
    else:
        # rank1 is element-wise; vectorize ranks over batch
        ords = np.argsort(-v, axis=1, kind="stable")
        rk = np.empty_like(v)
        rows = np.arange(B)[:, None]
        rk[rows, ords] = np.arange(1, n + 1)[None, :]
        # (ties in v from Dirichlet are measure-zero; skip tie correction in batch path)
        rs = rank1(s)[None, :]
        c = rs + rk            # larger = worse
        c = -c                 # flip so larger = better (uniform treatment)
    mask = np.ones(B, dtype=bool)
    if n_elim >= 1:
        ci = c[:, elim_idx]                     # (B, m) composites of eliminated couples
        # condition: max eliminated composite <= min non-eliminated composite + TOL
        if len(elim_idx) < n:
            cmin_other = np.min(np.delete(c, elim_idx, axis=1), axis=1)
            mask &= (ci.max(axis=1) <= cmin_other + TOL)
        # season >= 28: eliminated couple must be within bottom TWO (judges' choice from B2)
        if s28:
            for j in range(n_elim):
                worse_cnt = (c < ci[:, [j]] - TOL).sum(axis=1)  # strictly worse others
                mask &= (worse_cnt <= (1 if n_elim == 1 else 2))
    if is_finale and order_pairs:
        # better placement must have composite at least as good, for every batch row
        for (i, j) in order_pairs:  # i = better placement
            mask &= (c[:, i] >= c[:, j] - TOL)
    return mask

def feasible_single(s, v, elim_idx, n_elim, rule, s28, order_pairs=None, is_finale=False):
    """Scalar feasibility used by the inverse optimizer (also checks finale order)."""
    v = np.maximum(v, EPS); v = v / v.sum()
    if rule == "pct":
        c = s * v; c = c / max(c.sum(), 1e-300)
    else:
        c = rank1(s) + rank1(v)
        c = -c
    if n_elim >= 1:
        if len(elim_idx) < len(c):
            if c[elim_idx].max() > np.min(np.delete(c, elim_idx)) + TOL:
                return False
        if s28:
            for j in elim_idx:
                if (c < c[j] - TOL).sum() > (1 if n_elim == 1 else 2):
                    return False
    if is_finale and order_pairs:
        # better placement must have strictly-or-equal better composite
        for (i, j) in order_pairs:  # i = better placement
            if c[i] < c[j] - TOL:
                return False
    return True

# ----------------------------------------------------------------------------
# 3. Inverse optimization: max-margin point estimate
# ----------------------------------------------------------------------------
def margin(s, v, elim_idx, n_elim, rule, s28):
    v = np.maximum(v, EPS); v = v / v.sum()
    if rule == "pct":
        c = s * v; c = c / max(c.sum(), 1e-300)
    else:
        c = rank1(s) + rank1(v); c = -c
    if n_elim == 0 or len(elim_idx) == len(c):
        return 0.0
    return np.min(np.delete(c, elim_idx)) - np.max(c[elim_idx])

def goodness(s, v, rule):
    """Composite 'goodness' c (larger = better), same convention as margin()."""
    v = np.maximum(v, EPS); v = v / v.sum()
    if rule == "pct":
        c = s * v; return c / max(c.sum(), 1e-300)
    return -(rank1(s) + rank1(v))

def point_estimate(s, elim_idx, n_elim, rule, s28, order_pairs, is_finale, rng):
    n = len(s)
    # judge-informed prior mean: q_i ∝ exp(θ·s_i)  (FIXED, no feasibility information)
    m_prior = np.exp(THETA * (s - s.max())); m_prior /= m_prior.sum()

    def unpack(z):
        z = z - z.max(); e = np.exp(z); return e / e.sum()

    def neg_obj(z):
        v = unpack(z)
        pen = 0.15 * np.sum(v * np.log(np.maximum(v, 1e-12) / m_prior))  # KL to prior
        # finale ordering penalty: any violation of c_i >= c_j is heavily penalized
        # (margin is identically 0 on finale weeks, so this drives the search)
        ord_pen = 0.0
        if is_finale and order_pairs:
            c = goodness(s, v, rule)
            for (i, j) in order_pairs:
                ord_pen += max(0.0, c[j] - c[i])
        return -(margin(s, v, elim_idx, n_elim, rule, s28)) \
               - 25.0 * ord_pen + pen

    best_v, best_margin = None, -np.inf
    for t in range(14):
        z0 = np.log(m_prior) + (0.0 if t == 0 else rng.normal(0, 1.2, n))
        if t >= 7:  # biased starts: push eliminated couples down
            z0 = z0 - 2.5 * np.isin(np.arange(n), elim_idx)
        res = minimize(neg_obj, z0, method="Nelder-Mead",
                       options=dict(maxiter=1500, xatol=1e-3, fatol=1e-6))
        v = unpack(res.x)
        if feasible_single(s, v, elim_idx, n_elim, rule, s28, order_pairs, is_finale):
            mg = margin(s, v, elim_idx, n_elim, rule, s28)
            if mg > best_margin:
                best_margin, best_v = mg, v
    if best_v is None:  # fallback: deterministic construction
        if is_finale and order_pairs:
            # enforce the observed final placement ordering directly: swap along
            # ordering pairs (bubble sort) until the prior mean is ordered by placement
            v = m_prior.copy()
            for _ in range(n):
                done = True
                for (i, j) in order_pairs:
                    if v[i] < v[j]:
                        v[[i, j]] = v[[j, i]]
                        done = False
                if done:
                    break
            best_v = np.maximum(v, EPS); best_v = best_v / best_v.sum()
        else:
            v = np.full(n, (1 - n_elim * EPS) / max(n - n_elim, 1))
            if n_elim:
                v[elim_idx] = EPS
            best_v = v / v.sum()
        best_margin = margin(s, best_v, elim_idx, n_elim, rule, s28)
    return best_v, best_margin

# ----------------------------------------------------------------------------
# 4. Exact rejection sampler from the truncated-Dirichlet posterior
#    p(v|E) ∝ 1[v ∈ F_w] · Dir(v; q),   q_i ∝ exp(θ·s_iw),  Σ q = κ0.
#    Default  (adapt_q=False): the proposal is FROZEN from the first draw; every
#    retained draw is an exact iid posterior sample (Phase 2 only, no warm-up).
#    Optional  (adapt_q=True) : two-phase protocol — Phase 1 collects the first
#    `n_adapt` accepted draws ONLY to recenter q, DISCARDS them, then Phase 2 runs
#    with fixed q and retains only Phase-2 accepted draws. Summaries (mean, lo90,
#    hi90, cv) are computed from Phase-2 draws only in BOTH modes.
# ----------------------------------------------------------------------------
def prior_q(s, theta=THETA, kappa0=KAPPA0):
    """Fixed judge-informed Dirichlet concentration: q_i = κ0 · exp(θ·s_i)/Σ exp(θ·s_j)."""
    w = np.exp(theta * (s - s.max()))
    w /= w.sum()
    return kappa0 * w

def posterior_week(s, elim_idx, n_elim, rule, s28, order_pairs, is_finale, rng,
                   n_keep=N_KEEP, n_adapt=N_ADAPT, max_attempts=MAX_ATTEMPTS,
                   adapt_q=False):
    n = len(s)
    q_fixed = prior_q(s)                       # frozen judge-informed proposal
    q = q_fixed.copy()
    kept, attempts = [], 0
    phase1_discarded, n_accepted_total = 0, 0
    while len(kept) < n_keep and attempts < max_attempts:
        batch = min(8000, max_attempts - attempts)
        V = rng.dirichlet(q, size=batch)
        V = np.maximum(V, EPS); V = V / V.sum(1, keepdims=True)
        ok = feasible(s, V, elim_idx, n_elim, rule, s28, order_pairs, is_finale)
        attempts += batch
        acc = V[ok]
        if not len(acc):
            continue
        if adapt_q and len(kept) == 0 and n_accepted_total < n_adapt:
            # ---- Phase 1 (adaptation only): recenter q toward the accepted mean,
            #      DISCARD these draws; they are never retained.
            if n_accepted_total == 0:
                accepted_mean = acc.mean(axis=0)
            else:
                accepted_mean = 0.9 * accepted_mean + 0.1 * acc.mean(axis=0)
            q = KAPPA0 * np.maximum(0.25 + 0.75 * accepted_mean / accepted_mean.max(), 0.05)
            n_accepted_total += len(acc)
            if n_accepted_total >= n_adapt:
                q = KAPPA0 * np.maximum(
                    0.25 + 0.75 * accepted_mean / accepted_mean.max(), 0.05)
                phase1_discarded = min(n_accepted_total, n_adapt)
            continue
        # ---- Phase 2: fixed q (either the judge-informed prior or the frozen
        #      adapted q); retain only these draws.
        keep_now = min(len(acc), n_keep - len(kept))
        kept.extend(list(acc[:keep_now]))
    V = np.array(kept) if kept else np.empty((0, n))
    n_accepted_total = phase1_discarded + len(V)
    acc_rate = n_accepted_total / max(attempts, 1)        # overall acceptance ratio
    eff_retention = len(V) / max(attempts, 1)             # effective retention per week
    if len(V) == 0:
        return V, dict(repl_prob=np.nan, acc_rate=0.0, n_draws=0,
                       eff_retention=0.0, attempts=attempts,
                       phase1_discarded=phase1_discarded)
    # summaries from PHASE-2 (retained) draws only
    mean = V.mean(axis=0)
    lo, hi = np.percentile(V, [5, 95], axis=0)
    cv = V.std(axis=0) / np.maximum(mean, 1e-12)
    return V, dict(repl_prob=1.0, acc_rate=acc_rate, n_draws=len(V),
                   eff_retention=eff_retention, attempts=attempts,
                   phase1_discarded=phase1_discarded,
                   mean=mean, lo=lo, hi=hi, cv=cv)

# ----------------------------------------------------------------------------
# 5. Main loop over all season-weeks
# ----------------------------------------------------------------------------
def main():
    panel = parse_data()
    panel.to_csv(f"{OUTDIR}/weekly_panel.csv", index=False)
    print(f"panel rows: {len(panel)}, weeks: "
          f"{panel.groupby(['season','week']).ngroups}")

    post_rows, wk_rows, v0_rows = [], [], []
    rng_point, rng_post = RNG_POINT, RNG_POST
    for (season, week), g in panel.groupby(["season", "week"], sort=True):
        rule = g["rule"].iloc[0]
        s28 = (season >= 28)
        s = g["judge_share"].values.copy()
        n = len(s)
        is_finale = bool(g["is_finale"].iloc[0])
        # constraint index set = non-withdrawn couples eliminated this week
        el = g[(g["elim_week"] == week) & (~g["withdrew"])]
        elim_idx = np.array([g.index.get_loc(i) for i in el.index], dtype=int)
        n_elim = len(elim_idx)

        # finale ordering pairs: better placement must not composite-worse
        order_pairs = []
        if is_finale and g["placement"].notna().sum() >= 2:
            placer = g[g["placement"].notna()].sort_values("placement")
            names = list(g.index)
            for a in range(len(placer) - 1):
                i, j = placer.index[a], placer.index[a + 1]
                order_pairs.append((names.index(i), names.index(j)))

        # NOTE: point estimates use their own RNG stream -> deterministic, independent
        # of how many draws the posterior sampler consumed.
        v0, mg = point_estimate(s, elim_idx, n_elim, rule, s28, order_pairs,
                                is_finale, rng_point)
        V, info = posterior_week(s, elim_idx, n_elim, rule, s28, order_pairs,
                                 is_finale, rng_post)

        if info["n_draws"] > 0:
            for k, (_, row) in enumerate(g.iterrows()):
                post_rows.append(dict(
                    season=season, week=week, celebrity=row["celebrity"],
                    partner=row["partner"], judge_points=row["judge_points"],
                    judge_share=row["judge_share"], eliminated=(row["elim_week"] == week),
                    withdrew=row["withdrew"], is_finale=is_finale,
                    fan_share_mean=info["mean"][k], lo90=info["lo"][k], hi90=info["hi"][k],
                    cv=info["cv"][k], ci_width=info["hi"][k] - info["lo"][k],
                    n_active=n, n_elim=n_elim, rule=rule,
                ))
        wk_rows.append(dict(
            season=season, week=week, n_active=n, n_elim=n_elim, rule=rule,
            is_finale=is_finale, margin_v0=mg,
            repl_prob=info["repl_prob"], acc_rate=info["acc_rate"],
            eff_retention=info["eff_retention"], n_draws=info["n_draws"],
            attempts=info["attempts"], phase1_discarded=info["phase1_discarded"],
        ))
        for k, (_, row) in enumerate(g.iterrows()):
            v0_rows.append(dict(season=season, week=week,
                                celebrity=row["celebrity"], v0=v0[k]))
        if (season, week) in [(1, 1), (11, 5), (27, 4), (34, 11)] or week == 1:
            print(f"S{season} W{week}: n={n} m={n_elim} margin={mg:.4f} "
                  f"acc={info['acc_rate']:.2%} retained={info['n_draws']}")

    pd.DataFrame(post_rows).to_csv(f"{OUTDIR}/fan_votes_posterior.csv", index=False)
    pd.DataFrame(wk_rows).to_csv(f"{OUTDIR}/weekly_diagnostics.csv", index=False)
    pd.DataFrame(v0_rows).to_csv(f"{OUTDIR}/fan_votes_point.csv", index=False)

    wd = pd.DataFrame(wk_rows)
    ok = wd[wd["n_draws"] > 0]
    print("\n=== WEEK-LEVEL DIAGNOSTICS ===")
    print(f"weeks processed: {len(wd)}; weeks with posterior: {len(ok)}")
    print(f"median acceptance rate: {ok['acc_rate'].median():.2%}; "
          f"min: {ok['acc_rate'].min():.2%}")
    print(f"median effective retention: {ok['eff_retention'].median():.2%}; "
          f"min: {ok['eff_retention'].min():.2%}")
    print(f"weeks with < 1000 retained draws: {(ok['n_draws'] < 1000).sum()}")
    print(f"weeks with 0 retained draws: {(ok['n_draws'] == 0).sum()}")
    print(f"mean elimination margin (v0): {ok['margin_v0'].mean():.4f}")
    print("(repl_prob = 1.0 by construction: draws are conditioned on feasibility; "
          "it is a sampler-correctness footnote, not a predictive score)")

if __name__ == "__main__":
    main()
