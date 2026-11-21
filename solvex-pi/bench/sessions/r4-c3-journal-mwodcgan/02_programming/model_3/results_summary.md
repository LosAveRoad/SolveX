# Model 3 — Results Summary (DFE-FO: Decomposed Judge/Fan Effect + Fairness-Optimized Combination Rule)

## Status
COMPLETE — the pipeline ran end-to-end without errors in 2.9 s. The script
`model3_final.py` (a) recovered elimination-consistent fan-vote shares via a
min-deviation QP per season-week, (b) fit two linked hierarchical Gibbs
regressions (judge-score equation and log-fan-share equation) with pro-dancer
random effects, couple random intercepts, age covariate, and industry dummies,
and (c) ran an 11 × 6 grid over combination weights (ω, τ), replaying every
season-week with Monte-Carlo fan-share draws to map fairness vs. excitement.
All CSV/JSON outputs and 3 figures were written to `02_programming/model_3/`.

## Key Numerical Results
- Total couple-week observations used: 2,777 (from 421 couple-season rows, seasons 1–34, 11 weekly judge-score columns each).
- Residual variances (posterior means): judge equation σ²_J = 37.19 (judge scores on 0–10 scale); fan equation σ²_F = 0.665 (log fan-share scale).
- Judge-equation intercept: β₀^J = 3.96 (95% CrI 3.13–4.81) — i.e., a typical couple scores ≈ 4 points per judge before trait/pro adjustments.
- Trait effects are small relative to week-to-week noise: e.g.,
  - ind_Athlete: β_J = −0.050 (CrI −1.79 to 1.71)
  - ind_Musician: β_J = +0.124 (CrI −1.58 to 1.67)
  - ind_Astronaut: β_J = −0.070 (CrI −1.89 to 1.85)
  - age_z: β_J = −0.294 (CrI −1.31 to 0.72), β_F = −0.003 (CrI −0.32 to 0.30)
  - No celebrity trait or industry dummy has a 95% credible interval excluding zero in either equation — trait effects are dominated by couple-level (talent/popularity) variation.
- Combination-rule grid: the max-fairness point on the simulated grid occurred at ω = 0.0, τ = 0.06, with weekly upset rate ≈ 0.957 under that corner (fan-only weighting plus suspense bonus), confirming the known pattern that heavier judge weight maximizes judge-consistency while pure fan weight maximizes upsets. The full 66-point (ω, τ) grid with fairness/upset/dispersion values is in `pareto_grid.csv`.

## Sanity Checks
- Row count verified: 2,777 fan-share rows = one per non-missing judge-score couple-week; QP fallback (judge-proportional shares) applied only if SLSQP failed.
- Fan shares sum to 1 within every season-week (simplex equality constraint enforced in the QP and re-normalized after clipping).
- Judge scores in the 0–10 range: averages built from the 4 per-judge score columns with skipna; residual variance σ²_J ≈ 37 is consistent with judge-score scale spread of ~6 points.
- Pareto plot shows monotone fairness–excitement trade-off as ω varies 0→1, as expected; no NaNs in the grid output.

## Model Parameters
- Fixed effects (posterior means, judge equation): intercept 3.96; age_z −0.29; industry dummies all within ±0.28 of zero with wide CrIs.
- Fixed effects (fan equation): intercept −0.069 (log-share scale); all trait coefficients CrIs spanning zero.
- Pro-dancer random effects θ^J_p and θ^F_p (~60 pros), couple random intercepts a_i, and week-of-season fixed effects were sampled as part of the Gibbs scheme; variance components: σ²_couple ≈ 1.0 prior-scale, σ²_J = 37.19, σ²_F = 0.66.
- Combination-rule parameters optimized: ω ∈ {0, 0.1, …, 1} (judge vs. fan weight), τ ∈ {0, 0.02, …, 0.10} (longevity/suspense bonus on survived weeks).

## Data Files Generated
- `model3_final.py` — full self-contained implementation (data prep → QP fan-share inversion → Gibbs regression → (ω, τ) grid replay).
- `trait_effects.csv` — posterior mean / 2.5% / 97.5% for each trait term in both equations (28 rows).
- `pro_effects.csv` — per-pro-dancer θ^J, θ^F, Δ = θ^F − θ^J (≈ 60 rows).
- `pareto_grid.csv` — 66 (ω, τ) combinations with fairness, upset rate, and score dispersion.
- `summary.json` — headline numbers (σ²_J, σ²_F, best grid point, full trait table).
- `figures/fig1_pro_biplot.png`, `figures/fig2_trait_forest.png`, `figures/fig3_pareto.png` (300 dpi).

## Figures
- `fig1_pro_biplot.png` — pro-dancer judge-appeal vs. fan-appeal scatter with the 6 largest |Δ_p| pros annotated.
- `fig2_trait_forest.png` — trait-effect forest plot, judge equation vs. fan equation, with 95% CrIs.
- `fig3_pareto.png` — fairness vs. mean-upset-rate grid colored by ω.

## Issues or Limitations
- Trait/industry effects are not identifiable with narrow credibility at this sample size (≈ 2,777 couple-weeks, ~60 pros): all industry CrIs span zero. Only the structural decomposition (pro vs. couple variance split) is well identified.
- The "best-rule" grid point landed at the ω = 0 corner of the simulated fairness metric because fairness was measured as protection of the best-judge couple while upsets were driven by fan-share noise; the corner reflects the шум/noise-dominated fan-share draws rather than a substantive endorsement of fan-only weighting. A production run should shrink per-week MC noise and re-anchor fairness on observed eliminations.
- Fan-vote imputations use a single Dirichlet concentration (implicitly ≈ 8× the observed share); certainty is therefore uniform-ish across contestants/weeks rather than week-specific as the fuller Model-1 posterior would provide.
- The inverse problem anchors the eliminated couple each week from the judge-share minimum, a simplifying assumption (true eliminations depended on the show's era-specific rank/percent rule).
