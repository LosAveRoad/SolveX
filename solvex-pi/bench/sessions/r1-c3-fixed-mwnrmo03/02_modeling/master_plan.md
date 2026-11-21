# 2026 MCM Problem C — Master Plan

## Goal
Recover hidden fan votes from judge scores + elimination record (Model 1), replay seasons
under rank vs. percentage combination rules with counterfactual flips (Model 2), and
explain judge/fan divergence via celebrity covariates and survival (Model 3).

## Model 1: Bayesian Inverse-Elimination Fan Vote Reconstruction
- Likelihood: weekly survivorship is a censored ordering drawn via Plackett–Luce with
  utility u_{c,w} = log(F) + gamma·Jshare + delta_w (week fixed effects).
- Priors: hierarchical log-normal F (industry/celebrity covariates), gamma decision shift.
- Inference: hit-and-run / Gibbs over the polytope implied by constraints C1–C4;
  output posterior medians, q025, q975, IQR per couple-week.
- Artifacts: consistency_stats.json, fan_votes_estimates.csv, model1_fan_votes.py.

## Model 2: Rank vs. Percentage Counterfactual Engine
- For each of 2000 posterior draws of F: rescore seasons under the rank method and the
  percentage method; record eliminated couple, bottom-two sets, podium flips, D(k).
- Artifacts from execution: model2_rule_combination_vs_pct.py,
  rule_disagreement_by_season.csv, podium_flip_probabilities.csv.
- PARTIALLY SATISFIED: no results_summary.md; hypothesis tests of D(k) against noise
  baseline not completed.

## Model 3: Dual-Channel Mixed Effects + Celebrity Covariate Impact + Survival
- Channel J: log(Jshare) ~ age + gender + industry + (1|pro) + (1|season), OLS per draw.
- Channel F: logit(fshare_mean) ~ same + r gains; seemingly-unrelated coupling via draws.
- Survival: discrete-time complementary log-log hazard on weeks survived.
- KNNImputer for metadata; cluster-robust sandwich SEs at couple level.
- Artifacts: covariate_impacts.csv, archetype_counterfactuals.csv (3 archetypes),
  hazard_wald_tests.csv, pro_dancer_effects.csv, boot_ci_judge_channel.csv, panel_long.csv.
- Figures: fig1_forest_plot_Eg.png, fig2_survival_by_industry.png, fig3_pro_effects.png.

## Deliverable
04_paper/main.tex (20–30 pp., abstract written last, memo to producers as appendix,
all 3 available figures inserted and analyzed).
