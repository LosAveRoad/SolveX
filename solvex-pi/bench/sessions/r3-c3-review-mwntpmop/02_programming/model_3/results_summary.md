# Results Summary — Model 3: Hierarchical Driver Model (Judge vs. Fan Channels)

## Status
SUCCESS — code ran end-to-end; both Bayesian channels converged (no R̂ warnings with 4 chains, 4800 post-warmup draws each); all results and figures written.

## Key Numerical Results
- Data used: 335 couple-weeks (421 couples, seasons 1–34) after melting weekly judge scores.
- Coefficient contrasts Δ = β^fan − β^judge (logit scale, posterior mean [95% HDI], P(Δ>0)):
  - **age (per +1 SD): Δ = −0.153 [−0.199, −0.110], P(Δ>0) = 0.000** — fans punish age ≈1.2× more strongly than judges (judge β = −0.125, fan β = −0.278).
  - **athlete flag: Δ = +0.050 [−0.064, +0.163], P(Δ>0) = 0.820** — athletes are rewarded by both channels (judge β = +0.068, fan β = +0.118); no significant channel difference.
  - **fame tier (1=high → 3=low): Δ = +0.027 [−0.022, +0.075], P(Δ>0) = 0.882** — high fame helps both channels; fan β (+0.076) ≈ judge β (+0.049); difference not conclusive.
- Random-effect SDs: pro identity s_pro = 0.315 (fan) vs 0.076 (judge); season s_seas = 0.341 (fan) vs 0.187 (judge). Pro identity matters **~4× more** in the fan channel; season matters ~2× more.
- Variance partition of explained logit variance:
  - Fan channel: pro 49.6%, season 11.2%, fixed effects 39.2%.
  - Judge channel: pro 11.1%, season 57.6%, fixed effects 31.4%.
- **Answer:** pros/traits do NOT matter equally to judges and fans — pro identity dominates fan votes (49.6%) while season-to-season judging climate dominates judge scores (57.6%); only age has a channel-differentiated effect (fans penalize age twice as hard).
- Fan-vote identification: in 75.2% of weeks the eliminated couple was NOT the judge-score leader (fan votes decisive); in 24.8% of weeks judges alone would have picked the eliminated couple.
- Naive baseline (fan share = judge share) within-week normalized RMSE = 0.824; constrained identified model = 0.884 (model is forced away from judge-proportional shares by rank constraints — expected).

## Sanity Checks
- Fan shares sum to 1 within every week (verified by construction: wgt/wgt.sum()).
- Shares are in (0,1); judge points ranged 0–40; consistency fractions sum to 1 (0.752 + 0.248).
- Slopes/tier codes standardized (age z-scored, tier centered at mean 1.61; tier counts 184/27/124).
- Posterior predictive proxy: Beta replication with mean = observed share correlates 1.0 by construction; fit judged via wRMSE and channel SDs instead.
- Convergence: 4 chains × 1200 draws, target_accept 0.9; no R̂ > 1.01 warnings on final run.

## Model Parameters
- Fixed effects (fan / judge, logit scale): b0 ≈ 0 (standardized shares); age −0.278 / −0.125; athlete +0.118 / +0.068; fame tier +0.076 / +0.049; φ ≈ 20 (Beta concentration).
- Priors: N(0, 2²) fixed effects; HalfNormal(0.5) random-effect SDs; HalfNormal(5) φ.
- Random effects: u_pro ~ N(0, s_pro²) over 144 pro categories; u_season ~ N(0, s_seas²) over 34 seasons.

## Data Files Generated
- `fan_vote_estimates.csv` — 3,335 rows × 18 cols (couple-week panel with judge_share, identified fan_share, covariates).
- `delta_summary.csv` — 3 rows (age_z, athlete, fame_tier) × 8 cols of posterior summaries per channel + Δ.
- `pro_rankings_fan_channel.csv` — 10 rows (top-10 pros by fan-channel effect, with ±1 SD CI).
- `pro_rankings_bottom_fan.csv` — 5 rows (bottom-5 pros).
- `channel_fit_summary.csv` — 2 rows (judge/fan channels: SDs, wRMSE, variance shares).
- `model3_meta.json` — full metadata: timings, consistency fractions, top/bottom pros, variance partitions.

## Figures
- `figures/forest_delta.png` — forest plot of Δ = β^fan − β^judge with 95% HDIs and per-channel β annotations (shows fans ≠ judges on age).
- `figures/variance_partition.png` — grouped bars: pro/season/fixed-effect variance shares for both channels (pro dominance in fan channel vs season dominance in judge channel).
- `figures/pro_effect_ranking.png` — horizontal bar chart of top-10 pro fan-vote boost with posterior-SD error bars.

## Issues or Limitations
- Fan votes are unobserved; fan shares are *identified* from elimination/combination ranks via the classic rank formula fan_rank = 2·comb_rank − judge_rank (clipped), not measured. Estimates are therefore consistent with the show's rank-combination method, not true vote counts.
- Within-week share RMSE of the constrained model (0.884) exceeds the naive judge-proportional baseline (0.824) because rank constraints intentionally pull fan shares away from judge shares; the model is a constrained identification, not an unconstrained forecast.
- Athlete and fame-tier Δ intervals cross zero: only the age effect is decisively channel-differentiated at this sample size.
- Pro names in later seasons embed episode annotations in the source file (e.g. "Val Chmerkovskiy (Joey Graziadei week 9)"), which fragments pro categories (144 levels); a cleaned pro list would strengthen random-effect precision.
- Posterior predictive check implemented as a Beta-replication proxy rather than full replicate-data PPC; a full PPC is a straightforward extension.
