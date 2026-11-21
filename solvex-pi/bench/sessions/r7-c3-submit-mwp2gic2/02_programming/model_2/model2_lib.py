"""
model2_lib.py — Model 2 core: season contexts, combination rules, replay engine,
composite pseudo-likelihood, and calibration machinery.

Fan-vote model (the inversion the whole engine rests on):

    log phi_iw = u_i + alpha * log(rho_iw) + beta * log(cJ_iw)   (softmax-normalized)

    phi_iw : latent weekly fan-vote share of couple i in season-week w
    rho_iw : judge score share that week (percentage-rule input)
    cJ_iw  : career-to-date mean judge share (judged-quality persistence)
    u_i    : idiosyncratic fan appeal (couple-level; identified from survival)

Vote-noise model for calibration and bands: lognormal share fluctuations
phi~_i ∝ phi_i * exp(sigma*eps_i), eps~N(0,1) — Dirichlet(kappa*phi) with
kappa ≈ 1/sigma^2.
"""

import numpy as np
import pandas as pd
from scipy.stats import rankdata

SEED = 42
M_NOISE = 400          # common-random-number noise draws per week
U_BOUNDS = 3.0         # |u_i| cap (e^6 odds cap of fan appeal vs judge evidence)
GRID_ALPHA = [0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]
GRID_BETA = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]
GRID_SIGMA = [0.05, 0.10, 0.15, 0.25, 0.40]


# =====================================================================================
# Season contexts
# =====================================================================================
def build_season_context(ws, cont, season):
    """Observed-history context with documented patches:
    P1 'Eliminated Week k' couples with no week-k scores re-enter week k with the
       last observed judge score carried forward (marking elim_here);
    P2 finale-cut finalists with no finale scores re-enter the last week likewise;
    P3 withdrawals dance their final observed week, non-eliminable there.
    Quota k_w = competition eliminations leaving after week w (cast arithmetic)."""
    cw = cont[cont.season == season].copy()
    sw = ws[ws.season == season]
    weeks = sorted(sw.week.unique().tolist())
    season_last = max(weeks)
    score_of = dict(zip(sw.row_id, sw.week_score_mean))
    names = dict(zip(cw.row_id, cw.celebrity_name))
    status_of = dict(zip(cw.row_id, cw.status))
    elim_of = dict(zip(cw.row_id, cw.elim_week))
    partner_of = dict(zip(cw.row_id, cw.ballroom_partner))
    mean_score_of = dict(zip(cw.row_id, cw.mean_week_score))
    ids_by_week = {w: sw.loc[sw.week == w, "row_id"].tolist() for w in weeks}

    week_ctx = []
    for w in weeks:
        ids = list(ids_by_week[w])
        carried = {}
        miss_elim = [r for r in cw.loc[(cw.status == "eliminated") & (cw.elim_week == w) &
                                       (~cw.row_id.isin(ids)), "row_id"]]
        miss_fin = []
        if w == season_last:
            miss_fin = [r for r in cw.loc[(cw.status == "finalist") &
                                          (~cw.row_id.isin(ids)) &
                                          (cw.row_id.isin(score_of)), "row_id"]]
        for rid in miss_elim + miss_fin:
            hist = sw[(sw.row_id == rid) & (sw.week < w)]
            if len(hist):
                carried[rid] = float(hist.iloc[-1]["week_score_mean"])
                ids.append(rid)
        wd_here = set(cw.loc[(cw.status == "withdrew") & (cw.last_danced_week == w),
                             "row_id"])
        S = np.array([score_of.get(i, carried.get(i, np.nan)) for i in ids], float)
        rho = S / S.sum()
        week_ctx.append({
            "week": int(w), "row_ids": list(ids), "names": [names[i] for i in ids],
            "S": S, "rho": rho,
            "ineligible": np.array([i in wd_here for i in ids]),
            "elim_here": np.array([(status_of[i] == "eliminated") and
                                   (elim_of[i] == w) for i in ids]),
            "mean_score": np.array([mean_score_of[i] for i in ids]),
            "eps": np.random.default_rng([SEED, int(season), int(w)]).standard_normal(
                (M_NOISE, len(ids))),
        })

    kvec = []
    for wi, w in enumerate(weeks):
        if w < season_last:
            nxt = set(ids_by_week[weeks[wi + 1]])
            kvec.append(int(sum(1 for r in week_ctx[wi]["row_ids"]
                                if r not in nxt and status_of[r] == "eliminated")))
        else:
            kvec.append(int(((cw.status == "eliminated") & (cw.elim_week == w)).sum()))

    return {"season": int(season), "weeks": weeks, "week_ctx": week_ctx, "kvec": kvec,
            "roster": cw, "season_last": int(season_last), "names": names,
            "status_of": status_of, "names_rev": {v: k for k, v in names.items()}}


def precompute_career(week_ctx):
    """Career-to-date mean judge share strictly BEFORE each week (fallback: the
    current week's own share for first-week dancers); aligned with row_ids."""
    hist, out = {}, []
    for wc in week_ctx:
        out.append(np.array([np.mean(hist[r]) if r in hist else wc["rho"][j]
                             for j, r in enumerate(wc["row_ids"])]))
        for j, r in enumerate(wc["row_ids"]):
            hist.setdefault(r, []).append(wc["rho"][j])
    return out


# =====================================================================================
# Combination rules
# =====================================================================================
def phi_point(u, log_rho, log_cJ, alpha, beta):
    """Softmax point phi for one week's active set."""
    logits = u + alpha * log_rho + beta * log_cJ
    logits -= logits.max()
    p = np.exp(logits)
    return p / p.sum()


def _zvec(v):
    sd = v.std()
    return np.zeros_like(v) if sd < 1e-12 else (v - v.mean()) / sd


def point_th(phi, rho, judge_rank, rule):
    """Combined-score table on point phi. Returns (th, worst).
    rank : TH=(judge_rank+fan_rank)/2       worst = MAX TH
    pct  : TH=(judge_share+fan_share)/2     worst = MIN TH
    z    : TH=(z_judge+z_fan)/2             worst = MIN TH"""
    if rule == "rank":
        rf = rankdata(-phi, method="average")
        return (judge_rank + rf) / 2.0, "max"
    fan = phi / phi.sum()
    if rule == "pct":
        return (rho + fan) / 2.0, "min"
    if rule == "z":
        return (_zvec(rho) + _zvec(fan)) / 2.0, "min"
    raise ValueError(rule)


def rule_key(d_fan, rho, judge_rank, rule):
    """Worst-first selection key for a (M,n) matrix of noisy fan draws: HIGH key =
    more likely to be cut (so argpartition top-k picks the worst)."""
    if rule == "rank":
        n = d_fan.shape[1]
        order = np.argsort(-d_fan, axis=1, kind="stable")
        fan_rank = np.empty_like(order)
        rows = np.arange(d_fan.shape[0])[:, None]
        fan_rank[rows, order] = np.arange(1, n + 1)[None, :]
        th = (judge_rank[None, :] + fan_rank) / 2.0
        return th                              # highest combined rank = worst
    if rule == "pct":
        th = (rho[None, :] + d_fan) / 2.0
        return -th                             # lowest combined share = worst
    if rule == "z":
        def zmat(v):
            mu = v.mean(axis=1, keepdims=True)
            sd = v.std(axis=1, keepdims=True)
            sd = np.where(sd < 1e-12, 1.0, sd)
            return (v - mu) / sd
        rho_b = np.broadcast_to(np.asarray(rho)[None, :], d_fan.shape).copy()
        th = (zmat(rho_b) + zmat(d_fan)) / 2.0
        return -th
    raise ValueError(rule)


def rule_cut_probs(phi, eps, sigma, rho, judge_rank, rule, ineligible, k):
    """Cut-membership probabilities under lognormal vote noise (common random
    numbers). Returns p_cut aligned with phi."""
    M, n = eps.shape
    if k <= 0:
        return np.zeros(n)
    if k >= n:
        return np.where(ineligible, 0.0, 1.0)
    d = phi[None, :] * np.exp(sigma * eps)
    d = d / d.sum(axis=1, keepdims=True)
    key = rule_key(d, rho, judge_rank, rule)
    key = np.where(ineligible[None, :], -np.inf, key)
    part = np.argpartition(-key, k - 1, axis=1)[:, :k]
    counts = np.bincount(part.ravel(), minlength=n) / M
    return np.where(ineligible, 0.0, counts)


def worst_order(th, worst, judge_rank, rho, ineligible):
    """Indices ordered worst-first (ineligible pushed last; ties: worse judge
    first, then row order — fully deterministic)."""
    key = -th if worst == "max" else th
    key = np.where(ineligible, np.inf, key)
    sec = -judge_rank if worst == "max" else rho
    sec = np.where(ineligible, np.inf, sec)
    return np.lexsort((np.arange(len(key)), sec, key))


def dance_off_cut(std_mean, bottom_idx, th, k):
    """Judge dance-off proxy: cut the k with the LOWEST season-to-date mean judge
    score among the nominated bottom set; ties by worse week TH, then order."""
    order = sorted(bottom_idx, key=lambda i: (std_mean[i], th[i], i))
    return np.array(order[:k], int)


# =====================================================================================
# Replay engine
# =====================================================================================
def simulate_season(ctx, theta, U, rule, dance_off=False,
                    phi_mult=None, mult_from_week=1, judge_jitter=None,
                    phi_mult_weekly=None):
    """Replay one season under (rule, dance_off) with the SAME fitted fan votes
    (theta=(alpha,beta), U=appeal). Preserves elimination calendar (kvec);
    counterfactuals differ only in WHO is cut. Survivors past their real career
    carry the last observed judge score forward (share recomputed on active set).

    phi_mult     : {row_id: m} multiply phi from mult_from_week onward (renormalized)
    judge_jitter : {row_id: j} shifts the dance-off proxy's season-to-date mean

    Deterministic. Returns records, placements, eliminated_week, survivors."""
    alpha, beta = theta[0], theta[1]
    weeks, kvec, wlast = ctx["weeks"], ctx["kvec"], ctx["season_last"]
    hist_score, hist_share, hist_phi = {}, {}, {}
    eliminated_week, retired_week = {}, {}
    active = None
    records = []

    for wi, w in enumerate(weeks):
        tab = ctx["week_ctx"][wi]
        if active is None:
            active = set(tab["row_ids"])
        else:
            active = active | set(tab["row_ids"])
        rows = [r for r in tab["row_ids"] if r not in retired_week]
        extra = [r for r in sorted(active) if r not in rows]
        if extra:
            rows = rows + extra                       # carried forward (appended)

        S_obs = tab["S"]
        tot_S = S_obs.sum()
        S_arr = np.empty(len(rows))
        for j, r in enumerate(rows):
            if r in tab["row_ids"]:
                S_arr[j] = S_obs[tab["row_ids"].index(r)]
            else:
                S_arr[j] = hist_score[r][-1]          # carried-forward score
        rho = S_arr / S_arr.sum()
        judge_rank = rankdata(-S_arr, method="average")
        inelig = np.array([bool(tab["ineligible"][tab["row_ids"].index(r)])
                           if r in tab["row_ids"] else False for r in rows])
        k = int(kvec[wi])

        u = np.array([U.get(r, 0.0) for r in rows])
        cJ = np.array([np.mean(hist_share[r]) if r in hist_share else rho[j]
                       for j, r in enumerate(rows)])
        phi = phi_point(u, np.log(rho), np.log(np.maximum(cJ, 1e-9)), alpha, beta)

        if phi_mult:
            for rid, m in phi_mult.items():
                if rid in rows and w >= mult_from_week:
                    phi[rows.index(rid)] *= m
            phi = phi / phi.sum()
        if phi_mult_weekly:
            # per-week multipliers (HDI-bound sensitivity): {rid: [m per week index]}
            for rid, ml in phi_mult_weekly.items():
                if rid in rows:
                    phi[rows.index(rid)] *= ml[wi] if wi < len(ml) else 1.0
            phi = phi / phi.sum()

        std_mean = np.array([np.mean(hist_score.get(r, []) + [S_arr[j]])
                             for j, r in enumerate(rows)])
        std_mean_do = std_mean + (np.array([judge_jitter.get(r, 0.0) for r in rows])
                                  if judge_jitter else 0.0)

        th, worst = point_th(phi, rho, judge_rank, rule)
        order = worst_order(th, worst, judge_rank, rho, inelig)
        if k == 0:
            bottom_idx, cut_idx = [], []
        else:
            nb = k + 1 if dance_off else k
            bottom_idx = list(order[:nb])
            cut_idx = (list(dance_off_cut(std_mean_do, bottom_idx, th, k))
                       if dance_off else list(order[:k]))

        cut_ids = [rows[i] for i in cut_idx]
        bottom_ids = [rows[i] for i in bottom_idx]

        for j, r in enumerate(rows):
            hist_score.setdefault(r, []).append(S_arr[j])
            hist_share.setdefault(r, []).append(rho[j])
            hist_phi.setdefault(r, []).append(phi[j])
        for rid in cut_ids:
            eliminated_week[rid] = w
            retired_week[rid] = w
            active.discard(rid)
        for j, r in enumerate(rows):
            if inelig[j] and r not in retired_week:
                retired_week[r] = w
                active.discard(r)

        records.append({
            "week": int(w), "k": k, "rows": list(rows), "S": S_arr, "rho": rho,
            "judge_rank": judge_rank, "phi": phi.copy(), "th": th, "worst": worst,
            "bottom_ids": bottom_ids, "cut_ids": cut_ids, "std_mean": std_mean,
            "names": [ctx["names"].get(r, "carry") for r in rows],
        })

    # ---- placements ---------------------------------------------------------------------
    last = records[-1]
    finale_rows = last["rows"]
    survivors = [r for r in finale_rows if r not in eliminated_week]
    survivors = [r for r in survivors
                 if ctx["status_of"].get(r) != "withdrew"]
    # best-first ordering of the finale by the chosen rule's TH
    best_first = (np.argsort(last["th"], kind="stable") if last["worst"] == "max"
                  else np.argsort(-last["th"], kind="stable"))
    finale_rank = {finale_rows[i]: pos + 1 for pos, i in enumerate(best_first)}

    # withdrawals leave at their observed last-danced week if the sim never cut them
    roster_idx = ctx["roster"].set_index("row_id")
    for rid in roster_idx.index:
        if roster_idx.loc[rid, "status"] == "withdrew" and rid not in retired_week:
            retired_week[rid] = int(roster_idx.loc[rid, "last_danced_week"])

    n_fin = len(survivors)
    placements = {}
    for rid in roster_idx.index:
        if rid in survivors:
            placements[rid] = float(finale_rank[rid])
        elif rid in retired_week:
            rw = retired_week[rid]
            later = sum(1 for r2, w2 in retired_week.items() if w2 > rw)
            placements[rid] = float(later + n_fin + 1)
    return {"records": records, "placements": placements,
            "eliminated_week": eliminated_week, "survivors": survivors,
            "retired_week": retired_week}


# =====================================================================================
# Composite pseudo-likelihood + calibration (Corpus)
# =====================================================================================
class Corpus:
    """All seasons with cached per-week log-likelihood evaluation."""

    def __init__(self, ws, cont, seasons=None):
        seasons = sorted(ws.season.unique()) if seasons is None else sorted(seasons)
        self.ctxs = {int(s): build_season_context(ws, cont, s) for s in seasons}
        self.careers = {s: precompute_career(c["week_ctx"]) for s, c in self.ctxs.items()}
        self.rule_of = {s: (rank_pct_rule(s)) for s in self.ctxs}
        self.all_names = dict(zip(cont.row_id, cont.celebrity_name))
        self.weeks_of = {}
        for s, ctx in self.ctxs.items():
            for wi, wc in enumerate(ctx["week_ctx"]):
                for r in wc["row_ids"]:
                    self.weeks_of.setdefault(r, []).append((s, wi))

    def week_ll(self, s, wi, theta, sigma, U):
        ctx = self.ctxs[s]
        wc = ctx["week_ctx"][wi]
        k = ctx["kvec"][wi]
        alpha, beta = theta[0], theta[1]
        if len(theta) > 2:            # theta may carry sigma as its 3rd element
            sigma = theta[2]
        u = np.array([U.get(r, 0.0) for r in wc["row_ids"]])
        phi = phi_point(u, np.log(wc["rho"]),
                        np.log(np.maximum(self.careers[s][wi], 1e-9)), alpha, beta)
        if k == 0:
            return 0.0
        p_cut = rule_cut_probs(phi, wc["eps"], sigma, wc["rho"],
                               rankdata(-wc["S"], method="average"),
                               self.rule_of[s][0], wc["ineligible"], k)
        obs = wc["elim_here"]
        p = np.clip(p_cut, 1e-6, 1 - 1e-6)
        return float(np.sum(obs * np.log(p) + (~obs) * np.log(1 - p)))

    def total_ll(self, theta, sigma, U):
        return sum(self.week_ll(s, wi, theta, sigma, U)
                   for s, ctx in self.ctxs.items()
                   for wi in range(len(ctx["week_ctx"])))

    def coord_ascent_U(self, theta, sigma, u_init=None, sweeps=4, u_step=0.5,
                       verbose=True, log=print):
        """Cached coordinate ascent on u_i (only the celebrity's own weeks are
        recomputed when its u changes). Deterministic (sorted order, fixed probes)."""
        U = dict(u_init) if u_init else {}
        cache = {(s, wi): self.week_ll(s, wi, theta, sigma, U)
                 for s, ctx in self.ctxs.items()
                 for wi in range(len(ctx["week_ctx"]))}
        all_ids = sorted(self.weeks_of)
        trace = [sum(cache.values())]
        for sw in range(sweeps):
            step = u_step / (2 ** sw)
            for rid in all_ids:
                affected = self.weeks_of[rid]
                cur = U.get(rid, 0.0)
                best_v, best_local = cur, sum(cache[kk] for kk in affected)
                for off in (step, -step, step / 2, -step / 2, step * 2, -step * 2):
                    v = float(np.clip(cur + off, -U_BOUNDS, U_BOUNDS))
                    if v == cur:
                        continue
                    U[rid] = v
                    loc = sum(self.week_ll(s, wj, theta, sigma, U)
                              for s, wj in affected)
                    if loc > best_local + 1e-9:
                        best_v, best_local = v, loc
                U[rid] = best_v
                for kk in affected:
                    cache[kk] = self.week_ll(kk[0], kk[1], theta, sigma, U)
            trace.append(sum(cache.values()))
            if verbose:
                log(f"    U-sweep {sw+1}: composite loglik = {trace[-1]:.2f}")
        return U, trace

    def grid_theta(self, U, verbose=True):
        """Stage-1 (alpha,beta) grid at sigma=0.15; stage-2 sigma at the winner."""
        rows = [{"alpha": a, "beta": b, "sigma": 0.15,
                 "loglik": sum(self.week_ll(s, wi, (a, b), 0.15, U)
                               for s, ctx in self.ctxs.items()
                               for wi in range(len(ctx["week_ctx"])))}
                for a in GRID_ALPHA for b in GRID_BETA]
        g1 = pd.DataFrame(rows).sort_values("loglik", ascending=False).reset_index(drop=True)
        a0, b0 = float(g1.iloc[0].alpha), float(g1.iloc[0].beta)
        rows2 = [{"alpha": a0, "beta": b0, "sigma": sg,
                  "loglik": sum(self.week_ll(s, wi, (a0, b0), sg, U)
                                for s, ctx in self.ctxs.items()
                                for wi in range(len(ctx["week_ctx"])))}
                 for sg in GRID_SIGMA]
        g2 = pd.DataFrame(rows2).sort_values("loglik", ascending=False).reset_index(drop=True)
        if verbose:
            print("  stage-1 best:", g1.iloc[0].to_dict())
            print("  stage-2 best:", g2.iloc[0].to_dict())
        return (a0, b0, float(g2.iloc[0].sigma)), pd.concat([g1, g2], ignore_index=True)

    def theta_posterior_samples(self, theta_hat, U, n_samples=100, half_width=0.5):
        """Profile-grid posterior around (alpha,beta,sigma): exponential weights on
        the composite loglik; returns drawn thetas + the full local grid."""
        a0, b0, s0 = theta_hat
        alphas = sorted({max(0.02, round(a0 + dx, 4))
                         for dx in np.linspace(-half_width, half_width, 7)})
        betas = sorted({max(0.0, round(b0 + dx, 4))
                        for dx in np.linspace(-half_width, half_width, 5)})
        sigmas = sorted({round(min(0.6, max(0.02, s0 + dx)), 4)
                         for dx in np.linspace(-half_width, half_width, 7)})
        rows = []
        for a in alphas:
            for b in betas:
                for sg in sigmas:
                    rows.append((a, b, sg,
                                 sum(self.week_ll(s, wi, (a, b), sg, U)
                                     for s, ctx in self.ctxs.items()
                                     for wi in range(len(ctx["week_ctx"])))))
        df = pd.DataFrame(rows, columns=["alpha", "beta", "sigma", "loglik"])
        w = np.exp(df.loglik - df.loglik.max())
        w = w / w.sum()
        rng = np.random.default_rng(SEED + 1)
        idx = rng.choice(len(df), size=min(n_samples, len(df)), p=w.to_numpy())
        return df.iloc[idx].reset_index(drop=True), df


# =====================================================================================
# Metrics
# =====================================================================================
def gini(v):
    v = np.sort(np.asarray(v, float))
    n = len(v)
    if n == 0 or v.sum() == 0:
        return np.nan
    cum = np.cumsum(v)
    return float((n + 1 - 2 * np.sum(cum) / cum[-1]) / n)


def season_reproduction(res, ctx):
    """Cut-match rate, bottom-set Jaccard vs observed, placement MAE + Kendall tau."""
    obs_by_week = {wc["week"]: set(np.array(wc["row_ids"])[wc["elim_here"]])
                   for wc in ctx["week_ctx"]}
    n_match = n_tot = 0
    jac_sum = n_jac = 0
    for rec in res["records"]:
        obs = obs_by_week.get(rec["week"], set())
        if rec["k"] > 0:
            sim = set(rec["cut_ids"])
            n_match += len(sim & obs)
            n_tot += rec["k"]
            if obs or sim:
                jac_sum += len(sim & obs) / len(sim | obs)
                n_jac += 1
    obs_place = dict(zip(ctx["roster"].row_id, ctx["roster"].placement))
    mae = float(np.nanmean([abs(res["placements"].get(r, np.nan) - p)
                            for r, p in obs_place.items()]))
    rids = list(obs_place)
    tau = kendall_tau([obs_place[r] for r in rids],
                      [res["placements"].get(r, np.nan) for r in rids])
    return {"cut_match_rate": n_match / max(n_tot, 1),
            "matched_events": int(n_match),
            "total_cut_events": int(n_tot),
            "bottom_jaccard_mean": jac_sum / max(n_jac, 1),
            "placement_mae": mae,
            "placement_tau": tau}


def kendall_tau(x, y):
    from scipy.stats import kendalltau as kt
    r = kt(x, y)
    return float(r.statistic) if np.isfinite(r.statistic) else np.nan


def rank_pct_rule(season):
    """Era-correct rule: S1-2 rank; S3-27 percentage; S28+ rank + judges pick."""
    if season <= 2:
        return "rank", False
    if season <= 27:
        return "pct", False
    return "rank", True


# backwards-compat alias
era_rule = rank_pct_rule


# =====================================================================================
# Data loading
# =====================================================================================
def load_data():
    """Load the shared Phase-1 tables (weekly_scores.csv, contestants.csv)."""
    ws = pd.read_csv(SHARED_PATH + "weekly_scores.csv")
    cont = pd.read_csv(SHARED_PATH + "contestants.csv")
    return ws, cont


SHARED_PATH = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
               "r7-c3-submit-mwp2gic2/01_modeling/shared_data/")
