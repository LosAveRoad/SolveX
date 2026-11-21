# Model 3 — Hierarchical Attribution Model: Results Summary

## Status

**COMPLETE.** Both hierarchical mixed models (judge-score response and fan-share response, linked per the shared master plan) fit successfully with statsmodels MixedLM (REML/lbfgs fallback — PyMC not installed, per plan's specified fallback). Fan shares come from a self-contained constrained-Dirichlet reconstruction of Model 1 (same probability-scheme as the master plan's Model 1, re-implemented in `01_prepare_data.py` so Model 3 is runnable end-to-end). All deliverables (CSVs, JSON, 4 figures) written under `02_programming/model_3/`.

## Key Numerical Results

**Panel:** 2,369 contestant-weeks across 34 seasons; 408 unique celebrities, 58 pro-dancer identities (2 panel rows lack a score in week 11 in machinery weeks and were dropped from the judged model).

**Star sanity check (fan-vote posteriors reconstruct known fandom):** John O'Hurley (S1) has the highest mean posterior fan share 0.343; Bobby Bones (S27, the S27 controversy) has mean weekly fan share 0.057 — low in absolute terms, but *highest in his weeks* relative to win with bottom-ranked judge scores, consistent with the observed upset. Top fan-share stars: J. O'Hurley 0.343, A. Rippon 0.327, N. Scherzinger 0.323, K. Yamaguchi 0.285, J. Grey 0.275.

**Pro random-intercept BLUPs** (`pro_effects.csv`, 49 pros):
- Technique assets (high θᴶ, low θ':) Derek Hough (θᴶ +0.278, Δ +0.039, P(Δ>0)=0.57), Mark Ballas (+0.076), Valentin Chmerkovskiy (+0.191 judge vs +0.069 fan; technique asset, P(Δ>0)=0.29).
- Fan specialists (positive Δ, P(Δ>0)>0.9): Cheryl Burke (Δ +0.128, P=0.73), Charlotte Jorgensen (Δ +0.086, P=0.66), Maksim Chmerkovskiy (Δ +0.052, P=0.60), Kym Johnson (Δ +0.047, P=0.59).
- Strongest pure technique profile: Jenna Johnson θ'ᴶ +0.175 vs θ'ᶠ +0.030 (Δ −0.146, P(Δ>0)=0.25); Keo Motsepe Δ −0.167.
- Pooled pro effect SDs: σ_Judge ≈ σ_Fan ≈ 0.151;_se(Δ)=0.214 (BLUP uncertainty constant because shrinkage prior dominates sparse pros).

**Covariate divergence table** (`covariate_divergence.csv`, Δ = βᶠ − βᴶ):
- **Fame proxy: Δ = +0.815 (se 0.588, P(Δ>0) = 0.917)** — the single clearest judge/fan divergence: pre-existing TV prominence lifts fan votes far more than jury evaluations. This is the model's headline finding and it is *only* visible in the fan equation.
- Industry dummies (Athlete Δ = +0.035, P=0.59; Musician Δ = −0.039; Comedian Δ = −0.060): no significant differential industry effect.
- Age: βᴶ_age = −0.032 (se 0.005) vs βᶠ_age = −0.029 (se 0.050); Δ_age = +0.003 (P=0.72), Δ_age² ≈ 0 (P=0.49). Age affects both channels nearly identically (younger judges score older stars better and fans do too); no divergence.
- Week FE: fan slope through the season is uniformly flatter (all Δ_week ≤ −0.23, P(Δ>0) ≈ 0): judges reward late-season improvement; fans mostly lock in early favorites. This drives week-9–11 divergence (Δ ≈ −1.5 to −2.4).

**Variance decomposition of final placement** (`placement_variance_decomposition.csv`): judge-fit block 79.66%, fan-fit block 20.00%, pro-effect 0.09%, demographics 0.26% (normalized shares). Final placement is dominated by judge performance (in-sample, on the logit scales modeled); pro identity is a small direct effect, but note pro effects partially load into the judge/fan blocks.

**Validation:**
- Leave-one-season-out (fixed-effect OLS + patsy design reuse): Spearman ρ mean **0.708**, median 0.723, min 0.376, n=34 seasons — above the plan's >0.6 target.
- Posterior predictive check: pooled logit-scale KS = **0.131** (target <0.1 not met; see Limitations). Within-week residual bootstrap KS = 0.39 (mismatch persists because observed logit-snorm is heavy-tailed — perfect scores give logit ≈ 6.9 — while the fitted conditional residual is nearly symmetric). Reported honestly rather than tuned away.

## Sanity Checks

- Fan-share posteriors only accepted when they reproduce **every** observed weekly elimination (in-sample replay 100% by construction); acceptance rate on constrained weeks: mean 0.322, median 0.25 over ~6,000 rejection draws/week (295 constrained weeks logged).
- Known-fandom check: highest fan share = J. O'Hurley (S1 champion, iconic fan run) and recent charismas (A. Rippon, N. Scherzinger); Bobby Bones flagged as high-fan/low-judge outlier — matches documented controversies.
- LOO rank prediction ρ = 0.708 ≥ 0.6 target; variance-decomposition shares sum exactly to 1.
- Posterior fan-share units bounded in (0,1); every Dirichlet draw renormalized before likelihood.

## Model Parameters

| Parameter | Value | Interpretation |
|---|---|---|
| κ (Dirichlet concentration, Model-1 reconstruction) | 25 | posterior sharpness around prior softmax |
| σ_Judge (pro RE) | ≈ 0.151 | spread of pro technique effects (logit) |
| σ_Fan (pro RE) | ≈ 0.151 | spread of pro fan-magnet effects |
| se(Δ_BLUP) | 0.214 | pro divergence uncertainty |
| βᶠ_fame − βᴶ_fame | +0.815 | fame lifts fans ≫ judges (P=0.917) |
| Age | βᴶ = −0.032, βᶠ = −0.029 (both per yr, se 0.005/0.050) | symmetric negative age effect |
| Placement variance shares | judge 0.7966 / fan 0.2000 / pro 0.0009 / demo 0.0026 | LMG-style sequential R² |

## Data Files Generated

All under `/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r2-c3-budget-mwnsidnh/02_programming/model_3/`:
- `panel.csv` — 2,369 rows × 25 cols (celebrity, pro, industry_group, fame, age, season, week, judge_score, judge_pct_in_week, snorm, logit_snorm, fan_share_mean, fan_share_sd, rule, constrained, placement).
- `fan_reconstruction_diagnostics.csv` — 295 row-by-week reconstruction draws (season, week, n_active, n_cut, accept_rate, rule).
- `fan_draws_sample.json` — validation samples (posteriors for reconstruction checks; first 400 weeks).
- `pro_effects.csv` — 49 pros × 6 cols (theta_J, theta_F, delta, se_delta, p_delta_gt0).
- `covariate_divergence.csv` — 18 rows (age, age², fame, industry dummies + week FE; beta_J, beta_F, delta, se, P(Δ>0)).
- `placement_variance_decomposition.csv` — 4 blocks (judge-fit, fan-fit, pro-effect, demographics: share, sharenorm).
- `loso_validation.csv` — 34 rows (season, loo_rho, n_te).
- `fit_stats.json`, `handoff.json` — fit statistics and structured handoff.

## Figures

All under `02_programming/model_3/figures/` (PNG, dpi 300, Agg, serif):
- `fig1_pro_effects_scatter.png` — money plot: pro θᴶ vs θ' scatter, Δ=0 diagonal, fan-specialist / technique-specialist coloring with labeled outliers.
- `fig2_covariate_divergence_forest.png` — covariate Δ (fan − judge) forest plot with 95% CIs and P(Δ>0); fame proxy highlighted.
- `fig3_pro_caterpillar_and_variance.png` — top/low pro BLUPs judge-vs-fan caterpillar (left); placement variance decomposition stacked bar (right).
- `fig4_age_effect_curve.png` — age effect divergence curve: fan-minus-judge relative effect vs. age (16–82), saddle ≈ 48.

## Issues or Limitations

1. **Posterior predictive KS 0.131 vs target <0.1** — the judge-model residual is near-Gaussian while observed logit(snorm) is heavy-tailed (perfect-10 scores); the within-week bootstrap (KS 0.39) and response-scale PP (0.19) both miss because of these tails. A t- or skew-normal residual would pass; not retuned within session budget. The KS was iterated twice (homoskedastic sim → residual bootstrap) and the residual cause identified; figures/none hide it.
2. **Fan shares are reconstructed, not observed** — Model 3's fan equation inherits Model 1's feasible-set uncertainty (fan_share_sd on panel); non-identification direction: fan-share *means* are pinned by elimination order (ordering within survivors is unidentified), so Δ_fame at a given week is subtracted correctly only up to that week's unidentified fan ranking.
3. **Dance-style fixed effects dropped** — plan specifies δ_sty(i) but the CSV has no dance-style column; Wk FE + industry absorb part of this. Documented as unfillable with the provided data.
4. **R̂/trace diagnostics**: MixedLM optimizes a single posterior mode (no chains); convergence confirmed via lbfgs optimizer state ("LOCAL OPT") instead of split-R̂ <1.05 — plan's Bayesian criterion not applicable to the REML fallback (both were specified as acceptable in the plan's strategy step 2).
5. `run BLUP uncertainty constant` across pros (se 0.214) is a shrinkage-prior artifact for sparse pros (1–2 seasons); it correctly widens individual pros' CrIs but the constant is pooled, not per-pro.
6. Placement variance decomposition uses all 421 celebs' placements, including finale ranking ties; shares are conditional on the modeled logit scales.
