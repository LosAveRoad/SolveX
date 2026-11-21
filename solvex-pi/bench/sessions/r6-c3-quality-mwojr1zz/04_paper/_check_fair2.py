import pandas as pd
import numpy as np

base = '/Users/mac/Documents/StudyDocs/SolveX/run/'
base = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/'
ws = pd.read_csv(base + '01_modeling/shared_data/week_scores.csv')
sw = pd.read_csv(base + '01_modeling/shared_data/season_weeks.csv')
p = pd.read_csv(base + '02_programming/model_3/outputs/model3_placements.csv')

ws = ws.merge(sw[['season', 'week', 'is_finale_week']].rename(
    columns={'is_finale_week': 'fin_sw'}), on=['season', 'week'], how='left')
wsnf = ws[ws.fin_sw == 0]

jr = []
for (s, w), g in wsnf.groupby(['season', 'week']):
    sh = g.weekly_total / g.weekly_total.sum()
    r = sh.rank(ascending=False, method='first')
    for name, rr in zip(g.celebrity_name.values, r.values):
        jr.append((s, name, w, rr))
jrf = pd.DataFrame(jr, columns=['season', 'celebrity', 'week', 'jrank'])
mjr = jrf.groupby(['season', 'celebrity']).agg(
    mean_jrank=('jrank', 'mean'), n_weeks=('jrank', 'size')).reset_index()

piv = p.pivot_table(index=['season', 'celebrity'], columns='rule',
                    values='p_win', aggfunc='first').reset_index()
mg = piv.merge(mjr, on=['season', 'celebrity'], how='left')
print('merged rows:', len(mg), 'NaN mean_jrank:', int(mg.mean_jrank.isna().sum()))

RULES = ['r1_rank', 'r2_percent', 'r3_rank_save', 'r4_pct_save', 'r5_qualibrium',
         'r6_pct_hi']
rows = []
for rule in RULES:
    sel = mg.loc[mg.groupby('season').mean_jrank.idxmin()]
    rows.append((rule, sel[rule].mean()))
    if rule in ('r1_rank', 'r3_rank_save'):
        print('judge-best picks', rule,
              [(int(a), b, round(float(c), 2)) for a, b, c in
               zip(sel.season, sel.celebrity, sel[rule])][:8])
ax1 = pd.DataFrame(rows, columns=['rule', 'ax1'])
print(ax1.round(4).to_string(index=False))

# fan ceiling: worst quartile by mean_jrank, mean p_win
rows = []
for rule in RULES:
    fc = []
    for s, g in mg.groupby('season'):
        nq = max(1, len(g) // 4)
        worst = g.nlargest(nq, 'mean_jrank')
        fc.append(worst[rule].mean())
    rows.append((rule, float(np.mean(fc))))
print(pd.DataFrame(rows, columns=['rule', 'ax2_fan_ceiling']).round(4).to_string(index=False))
