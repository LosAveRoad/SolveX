import pandas as pd
import numpy as np

base = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/'
f1 = pd.read_csv(base + '02_programming/model_1/model1_fanshare.csv')

# 1) correlations phi vs judge share / judge z (within week)
f1['jz'] = f1.groupby(['season', 'week'])['judge_total'].transform(
    lambda s: (s - s.mean()) / s.std(ddof=0))
print('corr(phi_share, judge_share) overall : %.4f' % f1.phi_share.corr(f1.judge_share))
print('corr(phi_share, within-week judge z) : %.4f' % f1.phi_share.corr(f1.jz))

# 2) judge-only argmin hit on exact-regime single-exit weeks
ef = pd.read_csv(base + '02_programming/model_1/model1_exitfit.csv')
exact_single = ef[(ef.n_exits == 1) & (ef.veto_regime == 0)]
print('exact single weeks:', len(exact_single))
# find actual exit per (season,week): the celebrity whose phi_map row matches exit
# use contestants: eliminated rows keyed by last_week
con = pd.read_csv(base + '01_modeling/shared_data/contestants.csv')
ex = {}
for r in con.itertuples():
    if r.result_type == 'eliminated':
        ex.setdefault((r.season, r.last_week), []).append(r.celebrity_name)
    elif r.result_type == 'finalist' and r.last_week < r.finale_week:
        ex.setdefault((r.season, r.last_week), []).append(r.celebrity_name)
hits, n = 0, 0
for (s, w), names in ex.items():
    wk = f1[(f1.season == s) & (f1.week == w) & (~f1.result_type.isin(['finalist']))]
    if len(wk) < 3:
        continue
    # exact regime: S<=27, single exit
    if s >= 28 or len(names) != 1 or w == f1[f1.season == s].week.max():
        continue
    n += 1
    low = wk.loc[wk.judge_share.idxmin(), 'celebrity']
    hits += int(low == names[0])
print('judge-only argmin == exit (share scale, exact singles): %d/%d = %.3f' % (hits, n, hits / n))

# 3) share-scale weekly tension: sd of (phi - judge share) within week, averaged
gap = f1['phi_share'] - f1['judge_share']
sd_wk = f1.groupby(['season', 'week']).apply(lambda g: (g.phi_share - g.judge_share).std(ddof=0))
print('mean within-week sd of (phi - judge) share gap: %.4f' % sd_wk.mean())

# 4) Model 2 decomposition table
d = pd.read_csv(base + '02_programming/model_2/model2_decomp.csv')
print(d.to_string(index=False))

# 5) phi sd stats (Model 1)
print('\nphi_sd: mean %.4f median %.4f' % (f1.phi_sd.mean(), f1.phi_sd.median()))
print('phi range: %.4f - %.4f' % (f1.phi_share.min(), f1.phi_share.max()))
print('judge_share range: %.4f - %.4f' % (f1.judge_share.min(), f1.judge_share.max()))
print('age range: %d-%d, mean %.1f' % (f1.age.min(), f1.age.max(), f1.age.mean()))
print('n celebrity rows:', len(f1), 'unique celebs:', f1.celebrity.nunique(),
      'unique partners:', f1.partner.nunique())
print('industries:', f1.industry.nunique())
