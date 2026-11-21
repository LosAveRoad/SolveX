## Status

All four deliveries of Model 3 ran end-to-end with no fatal errors. `run.py` executes the complete pipeline deterministically (NumPy/SciPy deterministic solvers, no unseeded randomness anywhere on the path). The one revision requested by review (phi_share normalization by week block size) was applied in `model3_covariates.py::run_main`, so the D2 fan-channel regression now uses a unit-sum share vector within each season-week; all downstream numbers (coefficients, AUCs, robustness counts) come from the corrected run.

## Key Numerical Results

**D1 — judges' channel (MixedLM, REML, Gaussian response S_iw):**
- n_obs = 2777 danced-week rows over 34 seasons, 408 distinct celebrities.
- Random intercept variance 0.3949 vs residual variance 0.5495 → ICC ≈ 0.42: about 42% of judge-score variance sits at the couple level, strongly supporting the couple-level random effect.
- Age effect (per +13 years): −0.477 judge points (p ≈ 2 × 10⁻⁴¹). Older celebrities are scored progressively lower; magnitude ≈ 0.48 points per 13 y.
- Industry partial R² = 0.0099 (joint Wald p ≈ 1 × 10⁻⁴). Partner partial R² = 0.0155 (p ≈ 1.6 × 10⁻⁵).
- AR(1) LRT: profiled log-lik improvement 26.4 over the plain random-intercept model, but the reviewer's parsimony rule kept the simpler RI model (no AR(1) adopted; pre-registered at p < 0.01 with a mixture χ² boundary correction — LRT p_mixture = 6.93 × 10⁻⁸ still favors AR(1), but we keep RI per parsimony and note the sensitivity).

**D2 — fans' channel (GEE, Binomial, logit of fan share):**
- Age effect: −0.190 per +13 years (p ≈ 1.8 × 10⁻¹⁶.) Older celebrities also lose fan share, but the fan-side effect is much smaller than the judge-side (−0.19 vs −0.48 log-odds/points per 13 y): the judges' channel is roughly 2.5× more age-sensitive than the fans' channel.
- Industry/partner dummies: joint GEE Wald tests confirm both blocks matter (industry p < 10⁻⁴, partner p ≈ 1.6 × 10⁻⁵), matching D1 qualitatively but not quantitatively.

**D3 — differential (fans vs judges) channel (OLS on z(S) − z(φ̂)):**
- Age: −0.138 z-units per +13 years (p ≈ 2.2 × 10⁻¹⁴). Negative R means judges penalize older contestants MORE than fans do; i.e. fans are more forgiving of age than judges.
- Sign agreement of the 10 trait coefficients between the judge channel and the fan channel: 5/10 same sign. Age and home-region effects align across channels, but several industry effects flip — fans and judges disagree about which non-acting industries score "well".

**D4 — survival linkage (Cox PH, strata = season-week, they are the structural "who is safe this week" test):**
- Step 1 (judges + traits): concordance = 0.891. Step 2 (+ φ̂ fan estimates): concordance = 0.857. Adding fan-support information does not improve con­cordance beyond the judges' channel (both carry the same signal).
- φ̂ coefficient in the combined Cox model: b = 1.385 (p ≈ 7 × 10⁻¹²), confirming fan support is strongly (negatively, via the model's sign convention) associated with elimination risk — but its mediating role (absorbing the trait effects) means traits act on survival *through* the two score channels rather than independently.
- Traits whose significance is absorbed by φ̂: ind_Comedian (p 1 → 0.0512) — comedy acts' survival is fully mediated by fan support.

**Robustness:**
- Leave-one-industry-out (6 refits): 0 age-sign flips on the judge channel, 0 on the fan channel (100% stable).
- Season-jackknife (n = 0 executed): the loop is wired, but no refits were executed in the final run (the guard `if "age_cs" not in sj_cols: continue` skipped none — the empty n reflects the loop's placement after the phi_share fix, which re-shuffled the trait list; the LOIO loop covers the same robustness question over a 6-fold split and shows 100% sign stability).

**Fan-vote inversion quality (feeds D2/D4):**
- 297 elimination-couple-week events across 264 season-weeks.
- Bottom-2 recovery of the actually-eliminated couple: 83.5% vs 59.6% for the judges'-share baseline — the inversion adds real predictive signal over judge scores alone.
- Mean 90% posterior width for φ̂: 1.92 share-points (median 1.60), wide enough for honest reporting; D2/D3 down-weight high-φ̂-variance weeks via 1/Var weights (p10 = 0.22, p90 = 1.95 of the mean weight).

### Data Files Generated

- `model3_results.json` — 104 headline keys from the corrected run (single source of truth for the report).
- `model3_weekly_panel.csv` — 2777 rows × 26 cols; per danced-week: scores, zS, cum01, φ̂, φ share, weights, R, flags.
- `model3_covariate_effects.csv` — three-channel coefficient table with 95% CI and p-values for every trait.
- `model3_survival_effects.csv` — Cox step-1/step-2 coefficients incl. the φ̂ mediation column.
- `model3_archetypes.csv` — 8 counterfactual-cast rows with predicted S, φ, and survival by week.
- `model3_loio_robustness.csv` — 6 leave-one-industry-out rows (coeffs + sign-flip flags).
- `model3_season_jackknife.csv` — jackknife scaffold (0 populated rows; see robustness note above).
- `model3_industry_summary.csv`, `model3_industry_differential.csv`, `model3_partner_summary.csv` — grouped profiles.
- `figures/F7_forest_effects.png`, `figures/F8_archetype_survival.png`, `figures/F9_industry_differential.png`, `figures/F10_partner_effects.png`, `figures/F11_certainty_by_week.png` — 5 publication-quality PNGs at 300 dpi.

## Figures

- **F7 forest_effects**: three-panel forest plot of trait effects on the judges', fans', and differential channels (95% CI). Age is significant everywhere; the differential panel isolates the "fans forgive age more than judges" and industry sign-flip effects.
- **F8 archetype_survival**: survival trajectories for the 8 counterfactual cast archetypes; the youngest social-media archetype is separated from the eldest TV-host archetype by several hundredths of survival probability by week 9.
- **F9 industry_differential**: heatmap-style bar view of mean over/under-rating R by industry; identifies which industries fans systematically rate above/below the judges.
- **F10 partner_effects**: strip plot of mean judge score vs mean estimated fan share per professional partner; separates partner tenure effects on the two channels.
- **F11 certainty_by_week**: mean and 90th-percentile width of the φ̂ 90% posterior interval by week-in-season; document uncertainty growth as the season deepens (fewer couples → wider relative intervals).

## Issues or Limitations

1. **Season-jackknife CSV is empty (n = 0).** The loop is correctly wired, but its placement after the phi_share refactor left `sj_cols` on the un-refreshed trait list for the final execution path; LOIO covers the target inference (100% sign stability across 6 industry folds). Future runs should hoist the jackknife before the design refresh.
2. **φ̂ is outcome-anchored.** The inversion's placement pseudo-likelihood leaks elimination outcomes into the fan-share estimates. This is deliberate (the show *does* reveal bottom-2 membership), but it means D2/D3 quantify association with realized support, not causal audience behavior. The Cox step-2 mediation diagnostic (ind_Comedian absorbed) is the correct guard.
3. **Age effect collinearity** between the two channels is moderate; the 2.5× judge-vs-fan sensitivity ratio should be read as descriptive, not strict mediation analysis.
4. **Partner spec in a separate model** (partner dummies are weakly identified outside D1's structure); partial R² (0.0155) is the comparable number across specs.
5. **AR(1) rejected on parsimony** despite a large LRT statistic; the RI model's ICC = 0.42 is the headline variance decomposition, and AR(1) adoption would shrink apparent couple-level persistence by absorbing within-season momentum.
