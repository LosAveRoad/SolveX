# 2026 MCM Problem C — Master Plan

## Goal
Recover hidden fan votes from judge scores + elimination record (Model 1), replay seasons
under rank vs. percentage combination rules with counterfactual flips (Model 2), and
explain judge/fan divergence via celebrity covariates and survival (Model 3).

## Model 1: Bayesian Inverse-Elimination Fan Vote Reconstruction
- Likelihood: weekly survivorship is a censored ordering drawn via Plackett–Luce with
  utility u_{c,w} = log(F_{c,w}) + gamma·J_{c,w} + delta_w (week fixed effects).
- Priors: F hierarchical log-normal (industry/celebrity covariates), gamma decyzja.
- Inference: hit-and-run / Gibbs over the polytope implied by C1–C4 consistency constraints;
  output posterior medians, q025/q975, IQR per couple-week.
- Files: consistency_stats.json, fan_votes_estimates.csv, model1_fan_votes.py.

## Model 2: Rank-Combination vs. Percentage Combination Counterfactual Engine
- For each of 2000 posterior draws of F: rescore seasons under rank method and percentage
  method; record eliminated couple, bottom-two sets, podiums, flip probabilities.
- D(k) disagreement rate per season; permutation test for structure vs. noise.
- Files: model2_rule_combination_vs_pct.py, rule_disagreement_by_season.csv,
  podium_flip_probabilities.csv. PARTIALLY SATISFIED: no results_summary.md.

## Model 3: Dual-Channel Mixed Effects + Celebrity Covariate Impact
- Channel J: log(Jshare) ~ age + gender + industry + (1|pro) + (1|season).
- Channel F: logit(fshare_mean) ~ same + r_c,w gain.
- Survival: discrete-time cloglog hazard on weeks survived.
- OLS per posterior draw + bootstrap; KNN imputer for missing metadata.
- Files: covariate_impacts.csv, archetype_counterfactuals.csv, hazard_wald_tests.csv,
  pro_dancer_effects.csv, boot_ci_judge_channel.csv, panel_long.csv.
- Figures: fig1_forest_plot_Eg, fig2_survival_by_industry, fig3_pro_effects.

## Deliverable
04_paper/main.tex — 20–30 pages; memo to producers in appendix; all 3 Model 3 figures
inserted and analyzed.
