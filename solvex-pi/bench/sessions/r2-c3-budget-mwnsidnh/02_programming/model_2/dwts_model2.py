"""
dwts_model2.py — Core library for Model 2: Counterfactual Rules Laboratory
2026 MCM Problem C "Data With The Stars"

Components
----------
1. Data loading / season-structure extraction from the official CSV.
2. Model 1 posterior fan-vote estimation:
   Each week, fan shares f ~ Dirichlet(alpha) with alpha_i = A*kshare_i + B,
   conditioned (rejection sampling) on the observed elimination(s) under that
   season's historical combination rule. Because conditioning on the observed
   elimination path fixes the active set at each week, the weekly posteriors
   are conditionally independent -> factorized rejection is exact per week.
3. Counterfactual weekly-elimination simulator under 4 rules:
   RANK, PCT (alpha-weighted), JUDGE-SAVE (RANK base), PROPOSED (geometric).
4. Metrics: placement distributions, flip probabilities, fan/judge power,
   Kendall tau fairness, survival entropy (excitement).
"""
import re
import numpy as np
import pandas as pd

RNG = np.random.default_rng(2026)

# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------
DATA_PATH = None  # set by run script


def load_data(path):
    df = pd.read_csv(path)
    return df


def parse_elim_week(results):
    m = re.match(r"Eliminated Week (\d+)", str(results))
    return int(m.group(1)) if m else None


def build_season(df, season):
    """Return dict describing one season's structure.

    - names: celebrity names (row order preserved)
    - S: (n, k) judge score per scored-week column (mean of available judge
         scores), NaN once the couple has exited (scores are 0 after exit in
         the raw file -> mapped to NaN).
    - week_nums: the calendar week number of each scored column
    - elim_schedule: list of (col_index, set_of_row_indices eliminated then)
    - withdrawn: dict row_index -> exit column index (leave AFTER that col)
    - n_finalists: survivors at the last scored column
    - observed_order: row indices sorted by data placement (ties preserved)
    - historical rule: 'RANK' for s1-2 & s>=28, 'PCT' for s3-27
    """
    d = df[df.season == season]
    names = d["celebrity_name"].tolist()
    n = len(d)
    scores, week_nums = [], []
    for w in range(1, 12):
        cols = [f"week{w}_judge{k}_score" for k in range(1, 5)]
        if f"week{w}_judge1_score" not in d.columns:
            break
        v = d[cols].replace("N/A", np.nan).apply(pd.to_numeric, errors="coerce")
        if v.notna().any(axis=1).sum() == 0:
            continue
        scores.append(v.mean(axis=1).to_numpy())  # mean of judges that week
        week_nums.append(w)
    S = np.array(scores).T  # (n, k)
    S[S == 0] = np.nan      # post-exit zeros -> NaN
    k = S.shape[1]

    ew = d["results"].map(parse_elim_week).to_numpy()
    withdrew = (d["results"] == "Withdrew").to_numpy()

    # Counterfactual score matrix S_cf: post-exit weeks are imputed with the
    # couple's mean observed judge score (they never danced those weeks, so
    # under alternative rules we impute an average dance). This allows
    # couples to survive FAR longer in counterfactual trajectories, which is
    # physically impossible with raw NaN.
    S_cf = S.copy()
    colmean = np.nanmean(S, axis=0)
    for i in range(S.shape[0]):
        miss = np.isnan(S_cf[i])
        if miss.any():
            own = S[i, ~miss]
            fill = float(np.mean(own)) if len(own) else float(np.nanmean(colmean))
            S_cf[i, miss] = fill

    # elimination schedule: col index -> row indices eliminated at that col
    elim_sched = {}
    for i in range(n):
        if not withdrew[i] and not np.isnan(ew[i]):
            wk = int(ew[i])
            col = week_nums.index(wk)
            elim_sched.setdefault(col, []).append(i)

    # withdrawal exit col = last scored column of that couple
    withdrawn = {}
    for i in range(n):
        if withdrew[i]:
            lastc = np.where(~np.isnan(S[i]))[0]
            if len(lastc):
                withdrawn[i] = int(lastc.max())

    n_finalists = int((~np.isnan(S[:, -1]) & (S[:, -1] > 0)).sum())
    if withdrawn:
        n_finalists = int(sum(1 for i in range(n)
                              if S[i, -1] > 0 and i not in withdrawn))

    # observed placement order among non-withdrawn survivors
    place = d["placement"].to_numpy(float)
    live = [i for i in range(n) if i not in withdrawn]
    observed_order = sorted(live, key=lambda i: place[i])

    rule = "RANK" if (season <= 2 or season >= 28) else "PCT"
    return dict(season=season, names=names, S=S, S_cf=S_cf,
                week_nums=week_nums,
                elim_sched=elim_sched, withdrawn=withdrawn,
                n_finalists=n_finalists, observed_order=observed_order,
                rule=rule, n=n, k=k)


# ----------------------------------------------------------------------------
# Weekly posterior fan-share sampling (Model 1 conditioning)
# ----------------------------------------------------------------------------
def _ranks_desc(x, axis=1):
    """rank 1 = largest value."""
    order = np.argsort(-x, axis=axis, kind="stable")
    r = np.empty_like(order)
    if axis == 1:
        rows = np.arange(x.shape[0])[:, None]
        r[rows, order] = np.arange(1, x.shape[1] + 1)[None, :]
    else:
        cols = np.arange(x.shape[0])[:, None]
        r[order, cols] = np.arange(1, x.shape[0] + 1)[:, None]
    return r


def rule_elim_index(combined_ranks, judge_scores_active, m, rng, rule):
    """Return (M, m) indices (into active set) eliminated under given rule
    given combined rank matrix (M, a) and judge scores (a,)."""
    M, a = combined_ranks.shape
    if rule == "RANK":
        key = combined_ranks + rng.random((M, a)) * 1e-9
        return np.argsort(-key, axis=1)[:, :m]
    if rule == "PCT":
        raise ValueError("use rule_elim_pct")
    raise ValueError(rule)


def weekly_constraint_draws(sj, n_active, m_elim, rule, save_judge=None,
                            n_draw=2000, n_max=60000, A=4.0, B=0.6,
                            alpha_pct=0.5, rng=None, seed=None):
    """Sample fan shares (Dirichlet prior centred on judge shares) until we
    have n_draw draws whose rule-eliminee(s) match the observed set.

    sj: (a,) judge shares (sum to 1) of active couples, order = row order.
    m_elim: number eliminated this week (1, 2 or 3 for S26 finale).
    rule: 'PCT' or 'RANK' or 'RANK_SAVE'.
    save_judge: (a,) judge scores used by the modeled panel tie-save
                (only for RANK_SAVE: bottom-two member with the LOWER judge
                score is eliminated).
    Returns (draws (n_draw, a) fan shares, acceptance_rate, relaxed:bool)
    """
    rng = rng or np.random.default_rng(seed or 0)
    a = n_active
    alpha = A * sj + B
    alpha = alpha / alpha.sum() * max(2.0, a * 1.0)  # keep informative scale

    # observed-eliminee is fixed: accept when rule picks exactly those m
    # We don't know which active indices were eliminated here — the caller
    # passes the TARGET elimination index (-positions in active list).
    raise RuntimeError("replaced by weekly_posterior()")


def weekly_posterior(sj, judge_scores, m_elim, target_positions, rule,
                     n_draw=2000, batch=20000, max_batches=40, A=4.0, B=0.6,
                     alpha_pct=0.5, rng=None):
    """(doc)"""
    kept = []
    """Exact-per-week rejection sampling of fan shares.

    sj            : (a,) judge shares of the ACTIVE couples.
    judge_scores  : (a,) raw judge scores of active couples.
    target_positions: list of positions (into active array) eliminated that
                      week under the historical rule.
    rule          : 'PCT' | 'RANK' | 'RANK_SAVE' (S28+ style).
    Returns (draws, accept_rate, n_target_drawn).
    """
    rng = rng or np.random.default_rng(0)
    a = len(sj)
    target = np.sort(np.asarray(target_positions))
    if rule == "RANK_SAVE" and a - m_elim >= 2:
        # after removing the observed eliminee, must still be able to form B2
        pass
    alpha = (A * sj + B)
    alpha = alpha / alpha.sum() * 3.0  # moderate concentration

    kept = list(kept)
    n_kept = 0
    n_tried = 0
    for _ in range(max_batches):
        f = rng.dirichlet(alpha, size=batch)          # (batch, a)
        n_tried += batch
        if rule == "PCT":
            C = alpha_pct * sj[None, :] + (1 - alpha_pct) * f
            elimset = np.argsort(C, axis=1)[:, :m_elim]
        else:
            rJ = _ranks_desc(sj[None, :]) - 1         # 0-based best=0
            rF = _ranks_desc(f) - 1
            comb = rJ + rF + rng.random(f.shape) * 1e-9
            elimset = np.argsort(-comb, axis=1)[:, :m_elim]
        if rule == "RANK_SAVE" and m_elim == 1:
            # bottom two by combined rank (worst two); judges save the one
            # with the higher judge score -> eliminate the other (lower js)
            worst2 = np.argsort(-comb, axis=1)[:, :2]
            js = judge_scores[worst2]                  # (batch, 2)
            eliminate = worst2[np.arange(batch), np.argmin(js, axis=1)]
            ok = (eliminate[:, None] == target[None, :]).any(axis=1)
        else:
            ok = np.array([np.array_equal(np.sort(e), target)
                           for e in elimset]) if m_elim > 1 else \
                 (elimset[:, 0] == target[0])
        acc = f[ok]
        if len(acc):
            kept.append(acc)
            n_kept += len(acc)
        if n_kept >= n_draw:
            break
    draws = np.concatenate(kept, axis=0)[:n_draw] if kept else np.zeros((0, a))
    return draws, n_kept / max(n_tried, 1), n_kept


def finale_posterior(sj, m_active, rule, observed_order_positions, alpha_pct=0.5,
                     n_draw=2000, batch=20000, max_batches=60, A=4.0, B=0.6,
                     rng=None):
    """Finale-week fan shares conditioned on the observed FINAL ranking of the
    survivors (graded relaxation: exact ordering, else winner-only)."""
    rng = rng or np.random.default_rng(1)
    a = m_active
    alpha = (A * sj + B)
    alpha = alpha / alpha.sum() * 3.0
    obs = np.asarray(observed_order_positions)   # best -> worst in active coords
    pos_of = np.empty(a, int)
    for rank, p in enumerate(obs):
        pos_of[p] = rank

    kept_exact, kept_loose = [], []
    n_tried = 0
    for _ in range(max_batches):
        f = rng.dirichlet(alpha, size=batch)
        n_tried += batch
        if rule == "PCT":
            C = alpha_pct * sj[None, :] + (1 - alpha_pct) * f
            ranking = np.argsort(-C, axis=1)     # best first
        else:
            rJ = _ranks_desc(sj[None, :]) - 1
            rF = _ranks_desc(f) - 1
            comb = -(rJ + rF + rng.random(f.shape) * 1e-9)  # higher=better
            ranking = np.argsort(-comb, axis=1)
        # ranking rows give active-positions best->worst; convert to observed
        # rank of each active position
        rank_of_pos = np.empty_like(ranking)
        rows = np.arange(batch)[:, None]
        rank_of_pos[rows, ranking] = np.arange(a)[None, :]
        got = rank_of_pos[:, obs]               # observed ranks in obs order
        strict_ok = np.all(np.diff(got, axis=1) > 0, axis=1)
        loose_ok = got[:, 0] == 0                # winner matches
        if strict_ok.any():
            kept_exact.append(f[strict_ok])
        if loose_ok.any():
            kept_loose.append(f[loose_ok])
        ne = sum(len(x) for x in kept_exact)
        if ne >= n_draw:
            break
    exact = np.concatenate(kept_exact) if kept_exact else np.zeros((0, a))
    loose = np.concatenate(kept_loose) if kept_loose else np.zeros((0, a))
    rate_exact = len(exact) / n_tried
    if len(exact) >= n_draw:
        return exact[:n_draw], rate_exact, 0
    need = n_draw - len(exact)
    pool = loose if len(loose) >= need else np.repeat(loose, need // max(len(loose), 1) + 1, axis=0)
    relaxed = len(exact) < n_draw * 0.5
    out = np.concatenate([exact, pool[:need]], axis=0)
    return out, (len(exact) + min(len(loose), need)) / n_tried, (1 if relaxed else 0)


# ----------------------------------------------------------------------------
# Season-level posterior assembly
# ----------------------------------------------------------------------------
def season_posterior(season_data, n_draw=2000, A=4.0, B=0.6, alpha_pct=0.5,
                     uniform_prior=False, seed=7):
    """Return dict with per-scored-week posterior fan-share draws on the FULL
    couple index (zeros for inactive), plus diagnostics.

    draws_by_col[t]: (n_draw, n) fan shares of week column t (0 if inactive)
    accept[t]: acceptance rate; finale relaxed flag...
    """
    sd = season_data
    n, k = sd["n"], sd["k"]
    S = sd["S_cf"]
    wd = sd["withdrawn"]
    rng = np.random.default_rng(seed + sd["season"])

    draws_by_col = []
    accept = []
    relaxed_finale = 0

    for t in range(k):
        S_w = sd["S_cf"][:, t]
        active = np.array([i for i in range(n)
                           if not (i in wd and wd[i] <= t)])
        a = len(active)
        sj = np.maximum(S_w[active], 1e-6)
        sj = sj / sj.sum()
        pos_in_active = {name: i for i, name in enumerate(active)}

        is_last = (t == k - 1)
        is_elim_week = t in sd["elim_sched"]
        A_use, B_use = (0.0, 1.0) if uniform_prior else (A, B)
        if uniform_prior:
            alpha_eff = np.ones(a)
        else:
            alpha_eff = (A_use * sj + B_use)
            alpha_eff = alpha_eff / alpha_eff.sum() * 3.0

        if is_elim_week:
            targets = [pos_in_active[i] for i in sd["elim_sched"][t]
                       if i in pos_in_active]
            m_elim = len(targets)
            rule_hist = sd["rule"]
            if sd["season"] >= 28 and rule_hist == "RANK":
                rule_hist = "RANK_SAVE"    # bottom-two + judge save
            draws, rate, _ = weekly_posterior(
                sj, np.maximum(S_w[active], 1e-6), m_elim, targets, rule_hist,
                n_draw=n_draw, A=A_use if not uniform_prior else 0.0,
                B=B_use if not uniform_prior else 1.0, alpha_pct=alpha_pct,
                rng=rng)
            if len(draws) < n_draw:  # top-up by bootstrap if short
                if len(draws):
                    idx = rng.integers(0, len(draws), n_draw - len(draws))
                    draws = np.concatenate([draws, draws[idx]], axis=0)
                else:
                    draws = rng.dirichlet(alpha_eff, size=n_draw)
            full = np.zeros((len(draws), n))
            full[:, active] = draws
            draws_by_col.append(full)
            accept.append(rate)
        elif is_last:
            obs_pos = [pos_in_active[i] for i in sd["observed_order"]
                       if i in pos_in_active]
            fd, rate, rl = finale_posterior(
                sj, a, sd["rule"], obs_pos, alpha_pct=alpha_pct,
                A=0.0 if uniform_prior else A, B=1.0 if uniform_prior else B,
                rng=rng)
            if len(fd) < n_draw:
                if len(fd):
                    idx = rng.integers(0, len(fd), n_draw - len(fd))
                    fd = np.concatenate([fd, fd[idx]], axis=0)
                else:
                    fd = rng.dirichlet(alpha_eff, size=n_draw)
            relaxed_finale = max(relaxed_finale, rl)
            full = np.zeros((len(fd), n))
            full[:, active] = fd
            draws_by_col.append(full)
            accept.append(rate)
        else:
            # performance-only week: unconstrained prior draws
            if uniform_prior:
                fd = rng.dirichlet(np.ones(a), size=n_draw)
            else:
                fd = rng.dirichlet(alpha_eff, size=n_draw)
            full = np.zeros((n_draw, n))
            full[:, active] = fd
            draws_by_col.append(full)
            accept.append(np.nan)

    return dict(draws_by_col=draws_by_col, accept=accept,
                relaxed_finale=relaxed_finale)


# ----------------------------------------------------------------------------
# Counterfactual simulator
# ----------------------------------------------------------------------------
def simulate_season(season_data, post, rule, n_draw=None, alpha_pct=0.5):
    """Simulate the season under rule ∈ {RANK, PCT, JUDGE_SAVE, PROPOSED}.

    Returns placements (n_draw, n): 1 = winner ... NaN = never competed? (all
    competed; eliminated later => smaller placement number = better).
    Also returns per-week eliminee info for fan/judge-power metrics.
    """
    sd = season_data
    n, k = sd["n"], sd["k"]
    S = sd["S_cf"]
    wd = sd["withdrawn"]
    M = n_draw or None
    if M is None:
        M = min(len(d) for d in post["draws_by_col"] if len(d))
    rng = np.random.default_rng(99)
    eps = 1e-9

    placements = np.full((M, n), np.nan)
    elim_by_col = []      # per column: (M,) list of eliminated indices (first)
    fan_alone_hit = []    # per elim week: P(rule eliminee == fan-worst)
    judge_alone_hit = []
    survivor_entropy = []

    # post["draws_by_col"] has length k columns (some unconstrained)
    full_draws = []
    for t in range(k):
        dmat = post["draws_by_col"][t]
        if len(dmat) < M:
            reps = int(np.ceil(M / len(dmat)))
            dmat = np.concatenate([dmat] * reps, axis=0)[:M]
        full_draws.append(dmat[:M])

    active_mask = np.ones((M, n), bool)
    trace = []

    for t in range(k):
        S_w = S[:, t]
        active0 = ~np.isnan(S_w)
        # withdrawals leave exogenously (before elimination decision)
        leaving = [i for i, c in wd.items() if c == t]
        for i in leaving:
            active_mask[:, i] = False
        active = np.where(active_mask[0])[0]
        a = len(active)
        if a == 0:
            continue
        js = np.maximum(S_w[active], 1e-6)                     # (a,)
        f = full_draws[t][:, active]                           # (M, a)

        sjnp = js / js.sum()
        fj = f / (f.sum(axis=1, keepdims=True) + eps)

        # ---------- rule-specific weekly score ----------
        if rule in ("RANK", "JUDGE_SAVE"):
            rJ = (_ranks_desc(js[None, :]) - 1)[0]             # 0=best judge
            rF = _ranks_desc(f) - 1                            # (M, a) 0=best
            comb = rJ[None, :] + rF + rng.random((M, a)) * 1e-9
            worst = comb                                       # larger = worse
        elif rule == "PCT":
            C = alpha_pct * sjnp[None, :] + (1 - alpha_pct) * fj
            worst = -C                                          # smaller C worse
        elif rule == "PROPOSED":
            s_hat = js / js.max()                               # in (0,1]
            g = np.minimum(fj, 0.9 * s_hat[None, :] /
                           max(s_hat.max(), 1e-9) * 1.0)
            g = np.minimum(fj, 0.9 * s_hat[None, :])
            Cgeo = np.sqrt(s_hat[None, :] * g)
            worst = -Cgeo
        else:
            raise ValueError(rule)

        # ---------- elimination decision ----------
        if t in sd["elim_sched"]:
            m_elim = len(sd["elim_sched"][t])
            order = np.argsort(-worst, axis=1)                  # worst first
            elim_idx = order[:, :m_elim]                        # (M, m)
            elim_names0 = active[elim_idx]                      # couple index
            # metrics: fan-alone vs judge-alone eliminee (m=1 weeks only)
            if m_elim == 1:
                fan_worst = np.argsort(-fj, axis=1)[:, 0]
                judge_worst = np.argsort(-sjnp)[0]
                fan_alone_hit.append(np.mean(fan_worst == elim_idx[:, 0]))
                judge_alone_hit.append(np.mean(judge_worst == elim_idx[:, 0]))
            if rule == "JUDGE_SAVE" and m_elim == 1 and a >= 2:
                # bottom two by combined; panel saves higher judge score
                b2 = order[:, :2]                               # (M,2)
                jsb = js[b2]                                    # (M,2)
                save_pos = np.argmax(jsb, axis=1)
                elim = b2[np.arange(M), 1 - save_pos]
                elim_names0 = active[elim]
                if t in sd["elim_sched"]:
                    # one-time-per-season PROPOSED redemption not applied here
                    pass
            elim_by_col.append((t, elim_names0))
            # placement: worst-first order gets placements a, a-1, ... where
            # a = number of couples still active before this elimination
            if m_elim == 1:
                placements[np.arange(M), elim_names0] = a
            else:
                placements[np.arange(M)[:, None], elim_names0] = \
                    a - np.arange(m_elim)[None, :]
            active_mask[np.arange(M)[:, None], elim_names0] = False
        else:
            elim_by_col.append((t, None))

        # survival entropy of renormalized fan shares among survivors
        surv_mask = active_mask[:, active]                     # (M, a) post-elim
        mean_surv = (fj * surv_mask).sum(axis=0) / max((surv_mask).sum(), 1)
        q = mean_surv / (mean_surv.sum() + eps)
        q = q[q > 0]
        H = -(q * np.log(q)).sum() / np.log(max(len(q), 2)) if len(q) > 1 else 0.0
        survivor_entropy.append(H)

    # ---------- finale ranking ----------
    t = k - 1
    S_w = S[:, t]
    active = np.where(~np.isnan(S_w))[0]
    act = [i for i in active if i not in wd]
    a = len(act)
    js = np.maximum(S_w[act], 1e-6)
    f = full_draws[t][:, act]
    sjnp = js / js.sum()
    fj = f / (f.sum(axis=1, keepdims=True) + eps)
    if rule in ("RANK", "JUDGE_SAVE"):
        rJ = (_ranks_desc(js[None, :]) - 1)[0]
        rF = _ranks_desc(f) - 1
        comb = rJ[None, :] + rF
        final_score = -comb                                     # higher better
    elif rule == "PCT":
        final_score = alpha_pct * sjnp[None, :] + (1 - alpha_pct) * fj
    else:
        s_hat = js / js.max()
        g = np.minimum(fj, 0.9 * s_hat[None, :])
        final_score = np.sqrt(s_hat[None, :] * g)
    for m in range(M):
        order = np.argsort(-final_score[m], kind="stable")
        for rank, pos in enumerate(order):
            if pos < len(act):
                placements[m, act[pos]] = rank + 1
    # any couple never placed (withdrawals) keeps NaN -> filled with data
    # placement by the run script; here fill with n+1 as fallback
    for i in range(n):
        col = placements[:, i]
        col[np.isnan(col)] = n + 1
    return dict(placements=placements, elim_by_col=elim_by_col,
                fan_alone_hit=fan_alone_hit, judge_alone_hit=judge_alone_hit,
                survivor_entropy=survivor_entropy)
