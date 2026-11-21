import pandas as pd

con = pd.read_csv('/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/01_modeling/shared_data/contestants.csv')
p = pd.read_csv('/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r6-c3-quality-mwojr1zz/02_programming/model_3/outputs/model3_placements.csv')
real = con[con.placement == 1].set_index('season').celebrity_name.to_dict()
best = p.loc[p.groupby(['season', 'rule']).p_win.idxmax(), ['season', 'rule', 'celebrity']]
for rule in ['r1_rank', 'r2_percent', 'r4_pct_save', 'r5_qualibrium', 'r6_pct_hi']:
    w = best[best.rule == rule].set_index('season').celebrity
    n = sum(w[s] == real[s] for s in w.index)
    print(rule, 'argmax-p_win winner == real:', n, '/', len(w))
