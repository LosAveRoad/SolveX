import pandas as pd

base = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/02_programming/'
p = pd.read_csv(base + 'model_3/outputs/model3_placements.csv')

# winner under each rule by different criteria
w_pwin = p[p.p_win > 0].groupby(['season', 'rule']).apply(
    lambda g: g.loc[g.p_win.idxmax(), 'celebrity']).unstack()
w_pt3 = p.groupby(['season', 'rule']).apply(
    lambda g: g.loc[g.p_top3.idxmax(), 'celebrity']).unstack()
med = p.pivot_table(index=['season', 'celebrity'], columns='rule',
                    values='med_place', aggfunc='first')
n_runs = med.groupby(level=0).size()

def flips(w1, w2):
    w1s, w2s = w1.reindex(w2.index), w2
    n = int((w1s != w2s).sum())
    return n

print('flip argmax p_win            :', flips(w_pwin['r1_rank'], w_pwin['r2_percent']))
print('flip argmax p_top3           :', flips(w_pt3['r1_rank'], w_pt3['r2_percent']))
# argmin med_place winner
w_med = med.stack().groupby(['season', 'rule']).idxmin().reset_index()
w_med['celeb'] = w_med[0].apply(lambda t: t[1])
wm = w_med.pivot(index='season', columns='rule', values='celeb')
print('flip argmin med_place        :', flips(wm['r1_rank'], wm['r2_percent']))
# argmax p_win using only winners of draws strictly
w_pwin_q = p.groupby(['season', 'rule']).apply(
    lambda g: g.loc[g.p_win.idxmax(), 'celebrity']).unstack()
print('flip argmax p_win (with 0s)  :', flips(w_pwin_q['r1_rank'], w_pwin_q['r2_percent']))

q = pd.read_csv(base + 'model_3/outputs/model3_qualibrium_effect.csv')
print('\nqualibrium deltas: mean %.4f median %.2f  |d|>=1: %d  |d|>=2: %d  |d|>=3: %d'
      % (q.delta.mean(), q.delta.median(), (q.delta.abs() >= 1).sum(),
         (q.delta.abs() >= 2).sum(), (q.delta.abs() >= 3).sum()))

fs = pd.read_csv(base + 'model_3/outputs/model3_fairness_by_season.csv')
print('\nfairness_by_season columns:', list(fs.columns))
print('rows:', len(fs))
print(fs.head(4).to_string(index=False))
print(fs.describe().round(3).to_string())

c = pd.read_csv(base + 'model_3/outputs/model3_controversies.csv')
sep = c.pivot(index=['season', 'celebrity'], columns='rule_label', values='p_win')
print('\np_win by rule for the four named controversies:')
print(sep.to_string())

# Model 1: Jerry Rice exact rows (fanshare col names use `celebrity`)
f1 = pd.read_csv(base + 'model_1/model1_fanshare.csv')
jr = f1[(f1.season == 2) & (f1.celebrity == 'Jerry Rice')]
print('\nJerry Rice M1 rows:', len(jr))
print(jr[['week', 'judge_share', 'phi_share', 'phi_sd', 'phi_lo95', 'phi_hi95', 'phi_cv']].round(4).to_string(index=False))
