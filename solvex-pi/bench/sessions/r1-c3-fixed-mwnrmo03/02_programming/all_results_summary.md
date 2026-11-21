# All Models Results Summary

Total models implemented: 3

## Model 1

⚠ No results_summary.md

---

### Artifacts discovered by SolveX (read-only scan)

- `consistency_stats.json` (1545 B)
- `fan_votes_estimates.csv` (576472 B)
  columns=17, data_rows=2864
    header: season, week, celebrity_name, partner, industry, celebrity_age, status, rule, judge_score, judge_share, fan_share_median, fan_share_q025, fan_share_q975, fan_share_iqr
    numeric: season: n=2864 min=1 mean=18.76 max=34 | week: n=2864 min=1 mean=4.699 max=11 | celebrity_age: n=2864 min=14 mean=36.16 max=82 | judge_score: n=2864 min=8 mean=26.11 max=45 | judge_share: n=2864 min=0.03552 mean=0.1257 max=0.5046 | fan_share_median: n=2864 min=0 mean=0.1014 max=0.5944
- `model1_fan_votes.py` (16312 B)

---

## Model 2

⚠ No results_summary.md

---

### Artifacts discovered by SolveX (read-only scan)

- `model2_core.py` (15399 B)

---

## Model 3

⚠ No results_summary.md

---

### Figures

- model_3/figures/fig1_forest_plot_Eg.png
- model_3/figures/fig2_survival_by_industry.png
- model_3/figures/fig3_pro_effects.png

### Artifacts discovered by SolveX (read-only scan)

- `archetype_counterfactuals.csv` (360 B)
  columns=6, data_rows=3
    header: archetype, age, b_pro_sd, pred_log_Jshare, pred_relative_Jshare, pred_survival_hazard_mult
    numeric: b_pro_sd: n=3 min=0 mean=27.33 max=58 | pred_log_Jshare: n=3 min=-1 mean=0.7962 max=2.389 | pred_relative_Jshare: n=3 min=0.999 mean=1.926 max=2.446 | pred_survival_hazard_mult: n=3 min=0.946 mean=1.006 max=1.058
- `boot_ci_judge_channel.csv` (1404 B)
  columns=4, data_rows=13
    header: , beta, ci_lo, ci_hi
    numeric: ci_lo: n=13 min=-0.2283 mean=0.1561 max=2.328 | ci_hi: n=13 min=-0.1595 mean=0.1643 max=2.599
- `covariate_impacts.csv` (1193 B)
  columns=9, data_rows=10
    header: , beta_J, beta_F, E_g, se_E, z, p, p_adj, sig_FDR
    numeric: beta_F: n=10 min=-0.09265 mean=0.02063 max=0.3896 | E_g: n=10 min=-0.2707 mean=-0.04624 max=0.0301 | se_E: n=10 min=-0.1227 mean=0.002393 max=0.1278 | z: n=10 min=-30.43 mean=-3.166 max=0.4474 | p: n=10 min=-6.199 mean=-0.3575 max=2.603 | p_adj: n=7 min=0 mean=0.2809 max=0.9415
- `figures/fig1_forest_plot_Eg.png` (109915 B)
- `figures/fig2_survival_by_industry.png` (85779 B)
- `figures/fig3_pro_effects.png` (176239 B)
- `hazard_wald_tests.csv` (1303 B)
  columns=5, data_rows=13
    header: , coef, se, z, p
    numeric: coef: n=13 min=-2.532 mean=-0.1329 max=1.125 | se: n=13 min=0.0002049 mean=0.174 max=0.4456 | z: n=13 min=-7.354 mean=0.5953 max=17.3 | p: n=13 min=4.69e-67 mean=0.3007 max=0.9444
- `lopo_refits.csv` (480 B)
  columns=4, data_rows=5
    header: pro_excluded, b_pro_of_excluded, refit_intercept, refit_age
    numeric: b_pro_of_excluded: n=5 min=8.539 mean=8.693 max=8.844 | refit_intercept: n=5 min=2.443 mean=2.46 max=2.481 | refit_age: n=5 min=-0.002088 mean=-0.001518 max=-0.001199
- `model_3_covariate_impact.py` (22057 B)
- `panel_long.csv` (199794 B)
  columns=7, data_rows=2845
    header: celebrity_name, season, week, Jshare, fshare_mean, fshare_sd, event
    numeric: season: n=2845 min=1 mean=18.7 max=34 | week: n=2845 min=1 mean=4.603 max=11 | Jshare: n=2845 min=1 mean=7.711 max=10 | fshare_mean: n=2845 min=0.02268 mean=0.1178 max=0.4528 | fshare_sd: n=2845 min=0.005648 mean=0.02699 max=0.07744 | event: n=2845 min=0 mean=0.148 max=1
- `pro_dancer_effects.csv` (3196 B)
  columns=5, data_rows=60
    header: ballroom_partner, weeks, b_pro, bottom2_weeks, overturn_rate
    numeric: weeks: n=60 min=1 mean=47.42 max=207 | b_pro: n=60 min=3.5 mean=7.233 max=8.844 | bottom2_weeks: n=60 min=0 mean=10.03 max=74 | overturn_rate: n=60 min=0 mean=0.1445 max=0.8333

---
