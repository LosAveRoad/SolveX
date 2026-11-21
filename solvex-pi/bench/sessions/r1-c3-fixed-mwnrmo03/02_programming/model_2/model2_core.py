"""
Model 2 core — 2026 MCM Problem C: Data With The Stars.

Components
----------
1. Data loading and weekly structure reconstruction:
   - judge totals per couple per week from the 4 judge-score columns
     (all-NaN / all-zero weeks = couple did not dance that week);
   - documented outcomes: 'Eliminated Week w', 'Withdrew', 'kth Place'.
2. Model-1-style posterior fan-vote sampler: for the active couples of week w,
   f^{(s)} ~ Dirichlet(KAPPA * jshare + SMOOTH) — fans partially follow judge
   quality. Draws are CONDITIONED (rejection sampling) on the documented
   elimination(s) under the as-aired rule in decision weeks and on the
   documented winner at the finals week, so the joint (judges, fans) posterior
   is consistent with the observed record.
3. Combination rules (worse-key = larger key = eliminated):
   - rank rule  : judge min-rank + fan min-rank (1 = best each); ties broken
                  AGAINST the lower judge score (judges rescue the better-danced
                  couple), replicating the documented S1-2 tie behaviour.
   - pct rule   : worse-key = -(jshare + fshare); ties broken the same way.
   - gamma rule : A = (1-lam)*jshare + lam*fshare + lam_d*|jshare - fshare|.
   Judges'-save variant: bottom (m+1) by the rule's key; the panel saves the
   best-judged of them; the rest of the bottom set is eliminated.
4. week-level diagnostics on the as-aired active set with UNconditioned
   (prior) draws:
   - FPI(R): fraction of draws where the rule eliminates a couple that is NOT
     the judge-score minimum (fans overruled judges);
   - D(k): fraction of draws where the rank rule and the pct rule eliminate a
     DIFFERENT couple (plus a permutation null: fan vectors relabelled across
     couples destroys any fan/judge alignment; D should collapse).
5. Counterfactual season replay (the main engine):
   replay a whole season under any rule. Alive couples dance every week; at
   decision week w the m_w worst-key alive couples are eliminated (judges'
   save applied if enabled); couples that the real show already eliminated but
   the rule keeps alive become "phantom" couples: they carry their last real
   judge total and persistence-resampled fan draws. Withdrew couples leave
   exogenously and keep their documented placement. At the finals week the
   survivors are ranked by the same rule.
"""
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent
SESSION = BASE.parent.parent
CSV_PATH = SESSION / 'data' / '2026_MCM_Problem_C_Data.csv'
FIG_DIR = BASE / 'figures'
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------- model parameters ------------------------------------
KAPPA = 12.0     # Dirichlet anchor on judge shares (fan quality-following strength)
SMOOTH = 0.5     # Dirichlet smoothing (fans may vote for anyone)
WMAX = 11        # maximum number of weeks in the dataset
N_DRAWS = 1000   # posterior draws per (season, week) pool
BATCH = 4000     # rejection-sampling batch size
MAX_TRIES = 60   # max rejection batches per week


# ----------------------------- data loading ----------------------------------
def load_seasons():
    df = pd.read_csv(CSV_PATH, encoding='utf-8-sig')
    seasons = {}
    for k, g in df.groupby('season'):
        g = g.reset_index(drop=True)
        n = len(g)
        J = np.full((n, WMAX), np.nan)
        for i in range(n):
            row = g.iloc[i]
            for w in range(1, WMAX + 1):
                vals = []
                for j in range(1, 5):
                    col = f'week{w}_judge{j}_score'
                    if col in g.columns and pd.notna(row[col]):
                        v = float(row[col])
                        if v > 0:
                            vals.append(v)
                if vals:
                    J[i, w - 1] = float(np.sum(vals))
        results = g['results'].tolist()
        last_real = np.array([
            int(np.max(np.where(~np.isnan(J[i]))[0])) + 1 if (~np.isnan(J[i])).any()
            else 0 for i in range(n)])
        withdrew = np.array([r == 'Withdrew' for r in results])
        elim_week = np.full(n, np.nan)
        for i in range(n):
            r = results[i]
            if isinstance(r, str) and r.startswith('Eliminated Week'):
                elim_week[i] = int(r.split()[-1])
        seasons[int(k)] = dict(
            names=g['celebrity_name'].tolist(), partners=g['ballroom_partner'].tolist(),
            J=J, results=results, placement=g['placement'].to_numpy(float),
            last_real=last_real, withdrew=withdrew, elim_week=elim_week, n=n)
    return seasons


def season_plan(sd):
    """Weekly elimination schedule and the as-aired active couple sets."""
    n = sd['n']
    non_wd = [i for i in range(n) if not sd['withdrew'][i]]
    W = int(max(sd['last_real'][i] for i in non_wd))     # finals week
    decision = {w: [i for i in non_wd if sd['elim_week'][i] == w] for w in range(1, W)}
    winner = [i for i in non_wd if sd['results'][i] == '1st Place']
    active = {w: [i for i in non_wd
                  if sd['last_real'][i] >= w
                  and (np.isnan(sd['elim_week'][i]) or sd['elim_week'][i] >= w)]
              for w in range(1, W + 1)}
    return dict(non_wd=non_wd, W=W, decision=decision,
                winner=winner, active=active)


def as_aired_rule(season):
    """(rule, judges_save) documented as-aired by era."""
    if season <= 2:
        return 'rank', False
    if season >= 28:
        return 'rank', True
    return 'pct', False


# ------------------------- combination rules ---------------------------------
def rank_key(jt, f):
    """jt (n,), f (S,n) -> (S,n) worse-key. Combined min-rank (1=best) sum;
    tie -> the couple with the WORSE judge score is eliminated."""
    n = len(jt)
    jr = 1 + (jt[None, :] < jt[:, None]).sum(0).astype(float)     # 1 = best judge
    fr = 1 + (f[:, :, None] > f[:, None, :]).sum(-1).astype(float)  # 1 = most fan votes
    return jr[None, :] + fr + jr[None, :] / (2 * n + 1.0)


def pct_key(jt, jsh, f, lam=1.0, lam_d=0.0):
    """worse-key = -A, A = (1-lam)*jshare + lam*fshare + lam_d*|jshare-fshare|."""
    A = (1.0 - lam) * jsh[None, :] + lam * f
    if lam_d > 0:
        A = A + lam_d * np.abs(jsh[None, :] - f)
    return -A - jt[None, :] * 1e-9      # tie -> lower judge total eliminated


def key_for(rule, jt, jsh, f, lam=1.0, lam_d=0.0):
    return rank_key(jt, f) if rule == 'rank' else pct_key(jt, jsh, f, lam, lam_d)


def week_elim(key, m, jt, save=False):
    """(S,n) worse-key -> (S,m) column indices eliminated (worst first)."""
    S, n = key.shape
    if m == 0:
        return np.zeros((S, 0), dtype=int)
    order = np.argsort(-key, axis=1, kind='stable')
    if not save:
        return order[:, :m]
    bottom = order[:, :m + 1]
    keep_local = np.argmax(jt[bottom], axis=1)       # judges save best-judged
    mask = np.ones((S, m + 1), dtype=bool)
    mask[np.arange(S), keep_local] = False
    return np.sort(bottom[mask].reshape(S, m), axis=1)[:, ::-1]


def elim_matches(elim, doc_local):
    if elim.shape[1] != len(doc_local):
        return np.zeros(elim.shape[0], dtype=bool)
    return np.all(np.sort(elim, axis=1) == np.array(sorted(doc_local))[None, :], axis=1)


# ------------------- posterior fan-vote sampler (Model 1 feed) ---------------
class SeasonDraws:
    """Conditioned (real_pool) and unconditioned (prior_pool) weekly fan draws."""

    def __init__(self, season, sd, plan, seed=0):
        self.season, self.sd, self.plan = season, sd, plan
        self.rng = np.random.default_rng(1_000_000 * season + seed)
        self.real_pool, self.prior_pool, self.acceptance = {}, {}, {}

    def _dirichlet(self, jsh, B):
        alpha = KAPPA * jsh + SMOOTH
        g = self.rng.gamma(shape=alpha, scale=1.0, size=(B, len(jsh)))
        return g / g.sum(axis=1, keepdims=True)

    def sample(self):
        rule0, save0 = as_aired_rule(self.season)
        W, act_w = self.plan['W'], self.plan['active']
        lastfk = {}                                   # couple -> last pool ref
        for w in range(1, W + 1):
            act = act_w[w]
            jt = self.sd['J'][act, w - 1]
            jt = np.where(np.isnan(jt),
                          np.nanmean(np.where(self.sd['J'][act] > 0,
                                              self.sd['J'][act], np.nan), axis=1), jt)
            jsh = jt / jt.sum()
            Fp = self._dirichlet(jsh, N_DRAWS)
            self.prior_pool[w] = (np.array(act), Fp)
            F, acc = Fp, 1.0

            def condition(pred):
                got, tot, hit, tries = [], 0, 0, 0
                while sum(a.shape[0] for a in got) < N_DRAWS and tries < MAX_TRIES:
                    tries += 1
                    fb = self._dirichlet(jsh, BATCH)
                    key = key_for(rule0, jt, jsh, fb)
                    ok = pred(key, fb)
                    tot += BATCH
                    hit += int(ok.sum())
                    if ok.any():
                        got.append(fb[ok])
                if got:
                    Fa = np.vstack(got)[:N_DRAWS]
                    return Fa, hit / max(tot, 1)
                return None, 0.0

            if w in self.plan['decision'] and self.plan['decision'][w]:
                doc_local = [act.index(i) for i in self.plan['decision'][w]]
                m = len(doc_local)
                F, acc = condition(lambda key, fb: elim_matches(
                    week_elim(key, m, jt, save0), doc_local))
            elif w == self.plan['W'] and self.plan['winner']:
                wloc = act.index(self.plan['winner'][0])
                F, acc = condition(lambda key, fb: np.argmin(key, axis=1) == wloc)
            if F is None:
                F, acc = Fp, 0.0
            self.real_pool[w] = (np.array(act), F)
            self.acceptance[w] = acc
            for i, c in enumerate(act):
                lastfk[c] = w
        self.last_pool_week = lastfk
        return self


def fan_cols(sdraws, cands, w):
    """Return (F_used, idx_map) — for each candidate couple, a column of fan
    shares from week-w real pool if the couple danced that week, else from the
    couple's most recent conditioned pool (persistence for phantom couples)."""
    SD = sdraws.sd
    cols_all, keep_idx, keep_pool = [], [], []
    for c in cands:
        w0 = w
        if not (np.isnan(SD['elim_week'][c]) or SD['elim_week'][c] >= w):
            w0 = int(SD['last_real'][c])           # phantom: last real week
        pool = sdraws.real_pool.get(w0, sdraws.prior_pool.get(w0))
        cols, F = pool
        keep_idx.append(int(np.where(cols == c)[0][0]))
        keep_pool.append(F)
    Smin = min(F.shape[0] for F in keep_pool)
    out = np.empty((Smin, len(cands)))
    for jj, F in enumerate(keep_pool):
        out[:, jj] = F[:Smin, keep_idx[jj]]
    return out


def judge_totals(sdraws, cands, w):
    """Judge totals at week w; phantom couples carry their last real total."""
    SD = sdraws.sd
    return np.array([SD['J'][c, w - 1] if not np.isnan(SD['J'][c, w - 1])
                     else SD['J'][c, int(SD['last_real'][c]) - 1] for c in cands])


# --------------------- counterfactual season replay --------------------------
def replay_season(sdraws, rule='pct', save=False, lam=1.0, lam_d=0.0, n_replay=200):
    """Replay the season under a rule for n_replay posterior draws.

    Returns placements (n_replay, n): 1 = winner ... higher = eliminated earlier;
    withdrew couples keep their documented placement in every row.
    """
    sd, plan = sdraws.sd, sdraws.plan
    n, W = sd['n'], plan['W']
    S = n_replay
    n_replay = S
    placements = np.full((S, n), np.nan)
    for c in range(n):
        if sd['withdrew'][c]:
            placements[:, c] = sd['placement'][c]
    alive = list(plan['non_wd'])
    for w in range(1, W):
        alive = [c for c in alive
                 if not (sd['withdrew'][c] and sd['last_real'][c] <= w)]
        m = len(plan['decision'].get(w, []))
        cand = list(alive)
        if m == 0 or len(cand) <= m:
            continue
        jt = judge_totals(sdraws, cand, w)
        F = fan_cols(sdraws, cand, w)              # (S', n_cand) shares
        jsh = jt / jt.sum()
        F = F[:S]                                   # align pool rows with S
        key = key_for(rule, jt, jsh, F, lam, lam_d)
        elim = week_elim(key, m, jt, save)         # (S, m) worst key first
        # all still-alive couples outrank the eliminated ones so far; the e-th
        # worst eliminated couple takes the current worst placement this week
        cur_worst = len(alive)
        for e in range(m):
            placements[np.arange(S),
                       [cand[i] for i in elim[:, e]]] = cur_worst - e
        gone = set(cand[i] for i in elim.ravel())
        alive = [c for c in alive if c not in gone]
    # finals: rank survivors, best key first (placement 1 upward)
    if alive:
        jt = judge_totals(sdraws, alive, W)
        F = fan_cols(sdraws, alive, W)[:S]
        jsh = jt / jt.sum()
        key = key_for(rule, jt, jsh, F, lam, lam_d)
        order = np.argsort(key, axis=1)            # best first
        for pos in range(len(alive)):
            placements[np.arange(S), [alive[i] for i in order[:, pos]]] = pos + 1
    # fill any NaNs (e.g. single-candidate weeks) with worst remaining spots
    for r in range(S):
        miss = [c for c in range(n) if placements[r, c] != placements[r, c]]
        if miss:
            nxt = int(np.nanmax(placements[r])) + 1
            for c in sorted(miss, key=lambda c: -judge_totals(sdraws, [c], W)[0]):
                placements[r, c] = nxt
                nxt += 1
    return placements


# ------------------------- week-level diagnostics ----------------------------
def week_diagnostic(sdraws, w, lam=1.0, lam_d=0.0):
    """On the as-aired active set with prior draws:
    returns dict with FPI for rank/pct rules, disagreement D, and drama flag."""
    cols, F = sdraws.prior_pool[w]
    jt = judge_totals(sdraws, list(cols), w)
    jsh = jt / jt.sum()
    m = len(sdraws.plan['decision'].get(w, []))
    if m == 0:
        return None
    key_r = rank_key(jt, F)
    key_p = pct_key(jt, jsh, F, lam, lam_d)
    elim_r, elim_p = week_elim(key_r, m, jt), week_elim(key_p, m, jt)
    jmin = set(np.argsort(jt)[:m].tolist())
    fpi_r = float(np.mean([len(set(row) & jmin) < m for row in elim_r]))
    fpi_p = float(np.mean([len(set(row) & jmin) < m for row in elim_p]))
    dis = float(np.mean(np.any(np.sort(elim_r, 1) != np.sort(elim_p, 1), axis=1)))
    drama = bool(np.argsort(jt)[-1] != np.argmax(F.mean(axis=0)))
    return dict(week=w, FPI_rank=fpi_r, FPI_pct=fpi_p, D=dis, drama=drama)


def permutation_test_D(sdraws, w, nperm=200):
    """Null distribution of D under exchangeable relabelling of fan columns."""
    cols, F = sdraws.prior_pool[w]
    jt = judge_totals(sdraws, list(cols), w)
    jsh = jt / jt.sum()
    m = len(sdraws.plan['decision'].get(w, []))
    if m == 0:
        return None
    rng = np.random.default_rng(777 + w)
    null = []
    for _ in range(nperm):
        perm = rng.permutation(F.shape[1])
        Fp = F[:, perm]
        elim_r = week_elim(rank_key(jt, Fp), m, jt)
        elim_p = week_elim(pct_key(jt, jsh, Fp), m, jt)
        null.append(np.mean(np.any(np.sort(elim_r, 1) != np.sort(elim_p, 1), axis=1)))
    return np.array(null)
