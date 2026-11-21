import pandas as pd

base = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/02_programming/'

# --- Model 3 checks ---
p = pd.read_csv(base + 'model_3/outputs/model3_placements.csv')
med = p.pivot_table(index=['season', 'celebrity'], columns='rule',
                    values='med_place', aggfunc='first')
diff = (med['r2_percent'] - med   

 ['r1_rank']).abs()

print('placements rows:', len(p))
print('runs with |med diff| >= 1 (rank vs pct):', int((diff >= 1).sum()), '/', len(diff))
seas = diff.groupby(level=0).max()
print('seasons with any med diff >= 1:', int((seas >= 1).sum()), '/ 34')

fl = pd.read_csv(base + 'model_3'
                 '/outputs/model3_flip_table.csv')
print('flip seasons (median-over posterior):', int(fl.flipped.sum()))
print('flipped season rows:')
print(fl[fl.flipped == 1].to_string(index=False))

# p_win disagreement between rank and percent
pw = p.pivot_table(index=['season', 'celebrity'], columns='rule',
                   values='p_win', aggfunc='first')
argediff = (pw['r1_rank'] - pw['r2_percent']).abs()
print('runs with |P(win) rank - P(win) pct| >= 0.2:',
      int((argediff >= 0.2).sum()))

qe = pd.read_csv(base + 'model_3/outputs/model3_qualibrium_effect.csv')
print('qualibrium effect: mean delta %.3f, sd %.3f' % (qe.delta.mean(), qe.delta.std()))
print('runs |delta| >= 1:', int((qe.delta.abs() >=

                                1).sum()), '/', len(qe))

# fairness
fair = pd.read_csv(base + 'model_3/outputs/model3_fairness.csv')
print(fair.to_string(index=False))

# controversies: heroes
con = pd.read_csv(base + 'model_3/outputs/model3_controversies.csv')
print(con.to_string(index=False))

# --- Model 1 spot checks ---
f1 = pd.read_csv(base + 'model_1/model1_fanshare.csv')
print('fanshare rows:', len(f1), 'cols:', list(f1.columns))
jerry = f1[(f1.season == 2) & 

 (f1.celebrity == 'Jerry  Rice')]
print('Jerry rows found:', len(jerry))
sub = f1[(f1.season == 2) & (f1.week == 1)]
print('S2 W1 n coupled:', len(sub))
wsum = f1.groupby(['season', 'week'])['phi_share'].sum()
print('weekly sums min/max: %.6f / %.6f' % (wsum.min(), wmax() if False else wsum
                                             .max()))

ef = pd.read_csv(base + 'model_1/model1_exitfit.csv')
print('exitfit rows:', len(ef), ' veto weeks:', int(ef.veto_regime.sum()))
print('exact single:', int(((ef.n_exits == 1) & (ef.veto_regime == 0)).sum()))
print('exact multi:', int(((ef.n_exits > 1) & (ef.veto_regime == 0)).sum()))
