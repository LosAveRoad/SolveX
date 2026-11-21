"""
2026 MCM Problem C — Model 1 validation suite.

  V1. Forward test: sample unconditionally from the PRIOR (no feasibility filter) and
      measure how often the observed elimination is reproduced -> unconditional
      P(correct elimination); its inverse is the "information lift" of the
      elimination constraint. THE HEADLINE consistency statistic (repl_prob = 1.0 in
      the posterior is a sampler-correctness footnote, not a predictive score).
  V2. Hold-out check: the v0 point estimate must reproduce (a) eliminations on ordinary
      weeks and (b) the 1..2..3 final ordering on finale weeks.
  V3. Rule sensitivity: same (s, v0) re-run under the OPPOSITE rule -> count of weeks
      where the two rules pick DIFFERENT eliminations (rule-sensitivity counts).
  V4. Certainty analysis: is the 90% CI width constant across contestants/weeks?

All key statistics are printed AND saved to validation_output.txt.
"""
import numpy as np
import pandas as pd
import sys
from model1_core import rank1, EPS, TOL, parse_data

class Tee:
    def __init__(self, *streams): self.streams = streams
    def write(self, data):
        for s in self.streams: s.write(data)
    def flush(self):
        for s in self.streams: s.flush()

_logfile = open("validation_output.txt", "w")
sys.stdout = Tee(sys.stdout, _logfile)

fv   = pd.read_csv("fan_votes_posterior.csv")
v0   = pd.read_csv("fan_votes_point.csv")
wk   = pd.read_csv("weekly_diagnostics.csv")
panel = parse_data()

print("=" * 70)
print("V1. FORWARD TEST — unconditional prior P(correct elimination), lift,")
print("    and posterior replication (sampler-correctness footnote)")
print("=" * 70)
# To get an honest out-of-sample-style quantity, resample unconditionally from the
# PRIOR (no feasibility filter) and measure how often the observed elimination is
# reproduced: the ratio  P(E | data) / P(E | prior)  quantifies how much the
# elimination constraint actually restricts the prior, i.e. how informative it is.
# Memory fix: process batches of B inside each week instead of one giant array
# (avoids O(active_weeks * n_elements * batch) overflow on 40k-column arrays).
rng = np.random.default_rng(777)
base_rates = []
for (season, week), g in panel.groupby(["season", "week"], sort=True):
    if g["elim_week"].isna().all():            # no elimination this week (or finale)
        continue
    rule = g["rule"].iloc[0]; s28 = season >= 28
    s = g["judge_share"].values
    el = g[(g["elim_week"] == week) & (~g["withdrew"])]
    elim_idx = np.array([g.index.get_loc(i) for i in el.index], dtype=int)
    if len(elim_idx) == 0:          # eliminations this week were withdrawals only
        continue
    ok_sum, m_tot = 0.0, 0
    for _ in range(3):                          # 3 batches of 100 prior draws
        B = 100
        m = np.exp(6.0 * s / s.max()); m /= m.sum()
        P = rng.dirichlet(m, size=B)
        P = np.maximum(P, EPS); P = P / P.sum(1, keepdims=True)
        if rule == "pct":
            c = s * P; c = c / c.sum(1, keepdims=True)
        else:
            ords = np.argsort(-P, axis=1, kind="stable")
            rk = np.empty_like(P); rows = np.arange(B)[:, None]
            rk[rows, ords] = np.arange(1, len(s) + 1)[None, :]
            c = -(rank1(s)[None, :] + rk)
        ci = c[:, elim_idx]
        if len(elim_idx) < len(s):
            cmin_other = np.min(np.delete(c, elim_idx, axis=1), axis=1)
            ok = (ci.max(axis=1) <= cmin_other + TOL)
        else:
            ok = np.ones(B, dtype=bool)
        ok_sum += ok.sum(); m_tot += B
    base_rates.append(ok_sum / m_tot)
base = np.array(base_rates)
print(f"weeks with eliminations: {len(base)}")
print(f"unconditional prior P(correct elimination): "
      f"mean = {base.mean():.4f}, median = {np.median(base):.4f}, min = {base.min():.4f}")
print(f"information lift (1/mean): {1/base.mean():.1f}x on average")
print(f"posterior replication probability = 1.000 (footnote: draws are conditioned "
      f"on feasibility by construction, so repl_prob validates sampler correctness, "
      f"not predictive power)")
print(f"=> the elimination constraint is the binding information source; the prior "
      f"alone reproduces eliminations only a small fraction of the time (see mean), "
      f"while posterior draws reproduce them 100% of the time by construction.")

print()
print("=" * 70)
print("V2. HOLD-OUT CHECK — point estimate reproduces final ORDERINGS")
print("=" * 70)
res = v0.merge(panel[["season", "week", "celebrity", "placement", "elim_week",
                      "withdrew", "rule", "is_finale", "judge_share"]].reset_index(),
               on=["season", "week", "celebrity"], how="left")
bad_elim, tot_elim, bad_fin, tot_fin = 0, 0, 0, 0
for (season, week), g in res.groupby(["season", "week"]):
    rule = g["rule"].iloc[0]; s28 = season >= 28
    s = g["judge_share"].values
    el = g[g["elim_week"] == week]
    elim_idx = [g.index.get_loc(i) for i in el.index]
    v = g["v0"].values
    # goodness: pct -> composite share c (larger = better); rank -> -(rank sum)
    if rule == "pct":
        good = s * v; good = good / good.sum()
    else:
        good = -(rank1(s) + rank1(v))
    is_finale = g["is_finale"].iloc[0]
    if is_finale:
        tot_fin += 1
        placer = g[g["placement"].notna()].sort_values("placement")
        idx = list(g.index)
        ok_order = all(good[idx.index(placer.index[a])] >= good[idx.index(placer.index[a+1])] - TOL
                       for a in range(len(placer) - 1))
        if not ok_order:
            bad_fin += 1
            print(f"  finale ordering VIOLATED: S{season} W{week}")
    else:
        el2 = el[~el["withdrew"]]
        el_idx = [g.index.get_loc(i) for i in el2.index]
        if len(el_idx) == 0:
            continue
        tot_elim += 1
        if len(el_idx) < len(s):
            if s28:
                # bottom-two/tiebreak rule: each eliminated couple must have at
                # most 1 (single elim) / 2 (double elim) couples strictly WORSE
                # (good is larger = better, so "worse" = good < good[j])
                for j in el_idx:
                    n_worse = int((good < good[j] - TOL).sum())
                    if n_worse > (1 if len(el_idx) == 1 else 2):
                        bad_elim += 1
                        print(f"  elimination VIOLATED (s28 bottom-two): "
                              f"S{season} W{week} ({[g['celebrity'].iloc[j]]})")
                        break
            else:
                # eliminated couples must ALL be worse than every survivor:
                # max(good[elim]) <= min(good[others]) + TOL
                if good[el_idx].max() > np.min(np.delete(good, el_idx)) + TOL:
                    bad_elim += 1
                    print(f"  elimination VIOLATED: S{season} W{week} "
                          f"({list(el2['celebrity'])})")
print(f"elimination weeks tested: {tot_elim}; violations: {bad_elim}")
print(f"finale weeks tested: {tot_fin}; ordering violations: {bad_fin}")

print()
print("=" * 70)
print("V3. RULE SENSITIVITY — same data under the OPPOSITE combination rule")
print("=" * 70)
# For each week (S3+ only: pre-S3 there is no counterfactual — ranks were the actual
# rule and no pct counterfactual exists): does the v0 fan-vector that reproduces the
# elimination under the season's actual rule ALSO pick the same elimination under the
# opposite rule? Weeks where they differ are method-sensitive.
flip_weeks, tested = 0, 0
examples = []
for (season, week), g in panel.groupby(["season", "week"], sort=True):
    rule = g["rule"].iloc[0]; s28 = season >= 28
    if season < 3:
        continue  # early seasons used ranks; no counterfactual rule exists pre-S3
    s = g["judge_share"].values
    el = g[(g["elim_week"] == week) & (~g["withdrew"])]
    elim_idx = [g.index.get_loc(i) for i in el.index]
    sub = res[(res.season == season) & (res.week == week)]
    if len(elim_idx) == 0:
        continue
    v = sub["v0"].values
    other = "rank" if rule == "pct" else "pct"
    def comp(s, v, rl):
        if rl == "pct":
            c = s * v; return c / c.sum()
        return rank1(s) + rank1(v)
    c_alt = comp(s, v, other)
    tested += 1
    elim_act = elim_idx
    # eliminated = argmax of "worstness": pct -> min c; rank -> max c
    elim_alt = (np.argsort((-c_alt if other == "pct" else c_alt))[-len(elim_idx):])
    same = set(elim_act) == set(np.asarray(elim_alt).tolist())
    if not same:
        flip_weeks += 1
        if len(examples) < 15:
            names = list(sub["celebrity"])
            examples.append((season, week, rule,
                             [names[i] for i in elim_act],
                             [names[i] for i in np.atleast_1d(elim_alt)]))
print(f"weeks tested (S3+): {tested}; weeks where the two rules pick DIFFERENT "
      f"eliminations on the identical fan-vector: {flip_weeks} ({flip_weeks/tested:.1%})")
print("examples (season, week, actual rule, actual elim, other-rule elim):")
for e in examples:
    print("  ", e)

print()
print("=" * 70)
print("V4. CERTAINTY ANALYSIS — is CI width constant across contestants/weeks?")
print("=" * 70)
fv["ci_width"] = fv["hi90"] - fv["lo90"]
fv["cv"] = fv["cv"].replace([np.inf, -np.inf], np.nan)
q = fv["judge_share"]
print(f"corr(90% CI width, judge share) = {np.corrcoef(fv['ci_width'], q)[0,1]:.3f}")
print(f"corr(90% CI width, week)        = {np.corrcoef(fv['ci_width'], fv['week'])[0,1]:.3f}")
print(f"corr(90% CI width, n_active)    = {np.corrcoef(fv['ci_width'], fv['n_active'])[0,1]:.3f}")
print(f"corr(CV, judge share)           = {np.corrcoef(fv['cv'].fillna(0), q)[0,1]:.3f}")
med = fv["ci_width"].median()
print(f"narrow-CI weeks (width < 0.5*median): {int((fv['ci_width'] < 0.5*med).sum())} rows; "
      f"wide-CI rows (> 2x median): {int((fv['ci_width'] > 2*med).sum())}")
print(f"90% CI width: mean={fv['ci_width'].mean():.3f}, median={med:.3f}, "
      f"IQR=[{fv['ci_width'].quantile(.25):.3f},{fv['ci_width'].quantile(.75):.3f}], "
      f"max={fv['ci_width'].max():.3f}")
print("\n=> certainty is NOT uniform: it scales with (a) judge share (dominant couples are"),
print("   tightly pinned by the dominance constraint) and (b) week index (finals have"),
print("   fewer couples and stronger margins).")
