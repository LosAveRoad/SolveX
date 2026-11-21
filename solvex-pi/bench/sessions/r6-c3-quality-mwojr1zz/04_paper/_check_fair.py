import pandas as pd
import numpy as np

base = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/'
ws = pd.read_csv(base + '01_modeling/shared_data/week_scores.csv')
con = pd.read_csv(base + '01_modeling/shared_data/contestants.csv')
p = pd.read_csv(base + '02_programming/model_3/outputs/model3_placements.csv')

# non-finale weeks per season (elimination-relevant ranks)
sw = pd.read_csv(base + '01_modeling/shared_data/season_weeks.csv')
fin_week = sw[sw.is_finale_week == 1].groupby('season').week.max()

# mean judge rank per celeb-run (rank 1 = best judge share within week)
ws = ws.merge(sw[['season', 'week', 'is_finale_week']], on=['season', 'week'],
              how='left', suffixes=('', '_sw'))
wsnf = ws[ws.is_finale_week_sw == 0]
jr = []
for (s, w), g in wsnf.groupby(['season', 'week']):
    sh = g.weekly_total / g.weekly_total.sum()
    r = sh.rank(ascending=False, method='first')  # 1 = best
    for name, rr in zip(g.celebrity_name.values, r.values):
        jr.append((s, name, w, rr))
jrf = pd.DataFrame(jr, columns=['season', 'name', 'week', 'jrank'])
mjr = jrf.groupby(['season', 'name']).jrank.mean().reset_index()
mjr.columns = ['season', 'celebrity', 'mean_jrank']

# winners per rule = argmax p_win
pw = p.sort_values('p_win', ascending=False).groupby(['season', 'rule']).head(1)
winners = pw[['season', 'rule', 'celebrity']]

piv = p.pivot_table(index=['season', 'celebrity'], columns='rule', values='p_win',
                    aggfunc='first').reset_index()
mg = piv.merge(mjr, on=['season', 'celebrity'])

RULES = ['r1_rank', 'r2_percent', 'r3_rank_save', 'r4_pct_save', 'r5_qualibrium',
         'r6_pct_hi']
rows = []
for rule in RULES:
    idx = mg.groupby('season').apply(
        lambda g: g.loc[g.mean_jrank.idxmin(), rule])
    ax1 = idx.mean()
    # worst quartile by mean judge rank
    fc = []
    for s, g in mg.groupby('season'):
        nq = max(1, int(np.ceil(len(g) / 4.0)))  # match run.py nq = len//4
        nq = max(1, len(g) // 4)
        worst = g.nlargest(nq, 'mean_jrank')
        fc.append(worst[rule].mean())
    rows.append((rule, ax1, float(np.mean(fc))))
print('CORRECTED fair. axioms (recomputed from placements + judge ranks):')
print(pd.DataFrame(rows, columns=['rule', 'ax1_condorcet_meanPwin',
                                  'ax2_fan_ceiling_meanPwin']).round(4).to_string(index=False))

# mixed historical rule replay: winner identity vs real
real = con[con.placement == 1].set_index('season').celebrity_name.to_dict()
混 = 0
for (s, rule), celebs in winners.groupby('season'):
    hist_rule = 'r1_rank' if (s <= 2 or s >= 28) else 'r2_percent'
    got = celebs[celebs.rule == hist_rule].celebrity.iloc[0]
    if got == real[s]:
        混 += 1
print('mixed historical-rule replay (argmax p_win):', 混, '/34')
# also strict per-season argmax recomputed
for rule in ['r1_rank', 'r2_percent']:
    w = winners[winners.rule == rule].set_index('season').celebrity
    n = sum(w[s] == real[s] for s in w.index)
    print(f'{rule} modal-winner == real: {n}/{len(w)}')
