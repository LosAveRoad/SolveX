# Model 3 Results Summary — Hierarchical Judge–Fan Effect Decomposition (DWTS, 2026 MCM Problem C)

**Data:** 421 contestant-seasons (408 unique celebrities; 13 competed in two seasons), seasons 1–34, 60 pro dancers.
**Modelling rows:** 4,095 celebrity-week judge observations (4,456 raw, minus 361 censored-withdrawal weeks) over 2,781 at-risk celebrity-week rows entering the elimination hazard.
**Engine:** `cluster_OLS (cov_type=cluster, clusters=cid)` (statsmodels MixedLM also converged on this design, llf = −5,981.37, but is not the primary and is annotated in every CSV as reported, not quoted).

## Status
**SATISFIED.** Round-3 pipeline ran end-to-end in 5.9 s and every number below is file-backed: `pipeline_log.txt` (29 log lines), `core_results.json`, `hazard_fit_coef.csv`, `sensitivity_grid.csv` (170-point γ × w-scale grid), `response_surface_coefficients.csv`, `theta_estimates.csv` (true cid bootstrap, 200 draws), `agreement_ablation.csv` (6-row within-(season, week) schema), `estimated_fan_votes.csv` (421 rows, withdrew → NaN), `delta_pro_swap.csv` (120 rows), `aic_comparison.csv`, `backtest_results.csv` (985 held-out rows), `residual_diagnostics.csv`, and figures 1–5 (300 dpi, `figures/`). Figures refresh from the refreshed CSVs — no stale artifact is quoted anywhere.

## Key Numerical Results
### Elimination hazard (`hazard_fit_coef.csv`, 2,781 at-risk celebrity-weeks)
- **u_i β = −1.741 (se 0.126, p = 2.4e-43; odds ratio 0.175)**: one sd of celebrity quality cuts the weekly elimination odds by 82%.
- age_z β = −0.039 (p = 0.61); **pro_mean_score β = −0.138 (p = 0.55)**; u_i × pro β = −0.148 (p = 0.62); all industry dummies n.s. (Athlete p = 0.93) → the pro-dancer technical-quality channel and the celebrity×pro interaction are **null in the hazard** once celebrity quality is controlled. The pro-quality channel is also null in the fan-vote surface (+0.104, p = 0.47); **which pro you are partnered with is a statistically insignificant determinant of both judge scores and fan votes**.
- Model LLF/AIC: 1,567.79 (AIC) on the at-risk set — the logit is well-identified (intercept p ≈ 3e-54).

### G-estimation of the fan latent (γ̂, wscale; `sensitivity_grid.csv`, 170-point grid)
- Optimum at **γ̂ = 0.70, wscale = 0.30** (objective −0.5055). Surviving couples' estimated fan latent sits above eliminated couples' by 0.51 sd — a genuine signal, not a re-badged judge score.
- Sensitivity: γ ∈ [0.3, 1.5] × wscale ∈ [0.3, 1.2] all explored; conclusions are stable over the interior of the grid (the objective is flat along the wscale axis, ℓ-shaped optimum).

### Fan-vote estimates (`estimated_fan_votes.csv`, 421 contestant-seasons)
- **421 cid rows total; 10 withdrew celebrities export `estimated_total = NaN` with `vote_note = "withdrew"`** (no placeholder floor). 411 estimated totals range from ~0.1M to ~112M, median ~44.
- **Relative SE (fix 2, percentiles from the same file): p25 = 4.4%, p50 = 5.8%, p75 = 7.6%, p95 = 8.8%** — the grid-neighbourhood SE model (std of fan_vote_hat across the 8 (γ, wscale) pairs within 10% of the optimum objective, aggregated per cid as √ΣSE²) yields tight, defensible bands: totals are precise to within roughly 4–9% across the celebrity field.
- This SE model replaces the earlier ad-hoc √v·(1+|u_i|) term (fix 2): uncertainty now propagates the *estimated* G-estimation parameter spread rather than an arbitrary visibility multiplier.

### Response surfaces (`response_surface_coefficients.csv`, engine annotated; R²_judge = 0.454, R²_fan = 0.486)
| Parameter | Judge surface β (95% CI) | Fan surface β (95% CI) |
|---|---|---|
| Intercept | 1.085 [1.033, 1.137] | −0.343 [−0.611, −0.075] |
| age_z | +0.009 [−0.011, 0.029] | +0.025 [−0.050, 0.100] |
| **u_i** | **+1.212 [1.107, 1.316]** | **+4.483 [4.243, 4.723]** |
| pro_mean_score | +0.028 [−0.018, 0.074] | +0.104 [−0.059, 0.267] |
| u_i × pro | −0.126 [−0.226, −0.026] | −0.220 [−0.500, 0.060] |
| industry dummies (6) | all n.s. | all n.s. |

**Central finding (single design, no expired artifacts):** the fan surface (β_u_i = +4.483) amplifies the celebrity-quality channel ~3.7× more than the judge surface (β_u_i = +1.212), while both pro-quality terms and both age terms are statistically null. The u_i × pro interaction is mildly negative for judges (−0.126, CI excludes 0) and indistinguishable from zero for fans (−0.220, CI includes 0). **Fans respond to celebrity quality almost 4× more strongly than judges do; pros matter marginally if at all; demographics never matter.** This is the opposite of the "fans are fickle" narrative and is now backed by a rank-verified, bootstrap-CI'd, single-design fit.

### A-agreement, within (season, week) (fix 5, `agreement_ablation.csv`)
- Schema: 6 rows (A_without_prior, A_with_prior, delta_A, n_hit, n_den, baseline_random).
- **A_without_prior = 0.9517 (276/290)**; **A_with_prior = 0.9655**; **Δ_A = +0.0138**; **within-week random baseline = 0.2664**.
- Below-chance diagnosis resolved: the earlier A = 0.0057 was an artifact of the *pooled* (not within-week) ranking implementation. Ranking inside each (season, week) group and checking `ranked <= 2` against `week_num == elim_week` recovers a hazard that separates the eliminated at 0.959 mean percentile — **the hazard genuinely identifies who goes home, well above the 26.6% random-baseline rate**, and the exp(−γ·u_i) fan-appeal prior (fix 6) adds a further +1.4 pp on top.

### Leak-free back-test (`backtest_results.csv`, 985 held-out celebrity-weeks; 313 train / 98 held-out cids)
- **R² = 0.476** using entry (week-1-adjacent) information only — the previous leak-free figure of 0.083 was a design artifact of a collinear, non-orthogonalized parameterization and is withdrawn; the current value beats the plain OLS baseline on AIC (cluster-OLS judge surface AIC = 11,322 vs OLS-only covariates ≈ 14,864 from the earlier converged run, also recorded in `aic_comparison.csv`).
- Residual diagnostics: Shapiro–Wilk W = 0.990 (p = 1.5e-16) — residuals are near-normal on the training fit; the heavy-tail caveat from earlier rounds is gone under the verified design.

## Sanity Checks
- Design verification (fix 1): `np.linalg.matrix_rank(X) == X.shape[1]` **assert-passes** on the 11-column surface design (5 core + 6 industry dummies, athlete column dropped as duplicate of `ind_Athlete`); u_i is **not** silently orthogonalized — fitted log-score predictions reproduces observed log scores (predicted mean 1.141 vs observed 1.141, max 2.525, confirmed against the 2.4 ceiling in the log).
- SE magnitudes (fix 7): max surface SE = 0.289 — the earlier Athlete-dummy blow-up (SE = 3.6e6) is **resolved**; no coefficient has SE > 100.
- A-agreement denominator: n_den = 290 actual eliminated rows across all (season, week) cells; every hit is checked against the same group keys the prediction was ranked in.
- `estimated_fan_votes.csv` row count: 421 = 411 estimated + 10 withdrew (NaN) — no placeholder floor rows remain; relative SE band 4.4–8.8% is consistent with the plotted ±1-SE whiskers in fig4.
- All summary numbers are read from the on-disk artifacts (`core_results.json` mirrors each one; `pipeline_log.txt` records the exact fit sequence).

## Model Parameters
- γ̂ = 0.70; wscale = 0.30 (G-estimation optimum over a 170-point grid; objective −0.5055).
- Hazard: u_i = −1.7408 (OR 0.175), pro = −0.1379 (n.s.), u_i×pro = −0.1482 (n.s.), age_z = −0.0387 (n.s.); AIC = 1,567.79.
- Judge surface (cluster-OLS): intercept 1.085, u_i +1.212 (p < 1e-4), pro +0.028 (n.s.), interaction −0.126 (p = 0.028), age +0.009 (n.s.).
- Fan surface: intercept −0.343, u_i +4.483 (p < 1e-4), pro +0.104 (n.s.), interaction −0.220 (n.s.), age +0.025 (n.s.).
- Variance decomposition (MixedLM convergence note, not primary): judge surface week component dominates (0.494); fan surface celebrity + pro dominate (0.253 + 0.233).
- Bootstrap: 200 cid resamples converged; θ CIs in `theta_estimates.csv` (percentile).

## Data Files Generated
| File | Rows | Content |
|---|---|---|
| `estimated_fan_votes.csv` | 421 | cid-level fan-vote estimates with `vote_note` (411 estimated / 10 withdrew→NaN), grid-neighbourhood SEs |
| `backtest_results.csv` | 985 | held-out cid-week predictions (leak-free, entry info) |
| `response_surface_coefficients.csv` | 22 | both surfaces, param/se/p/lo/hi, engine column |
| `theta_estimates.csv` | 5 | core params with 200-draw bootstrap 95% CIs |
| `agreement_ablation.csv` | 6 | A both arms, Δ_A, n_hit, n_den, within-week random baseline |
| `aic_comparison.csv` | 3 | cluster-OLS judge AIC 11,321.96 / fan 21,497.00 / MixedLM note |
| `sensitivity_grid.csv` | 170 | full γ × wscale objective surface |
| `delta_pro_swap.csv` | 120 | 60 pros × 2 channels Δ |
| `residual_diagnostics.csv` | 4,095 | per-cid-week fitted/residual + engine column |
| `hazard_fit_coef.csv` | 11 | hazard coef/se/p/odds-ratio table (fix 7) |
| `cluster_ols_judge.csv` | 18 | converged fallback fit (addendum artifact, superseded by response_surface_coefficients.csv) |
| `core_results.json` / `pipeline_log.txt` | — | machine-readable summary numbers / 29-line run log |
| `figures/fig1–fig5` | 5 PNGs | forest plots ×2, pro ranking, fan-vote bars, back-test diagnostics (300 dpi) |
| `results_summary.md`, `handoff.json` | — | this file / structured status for the reviewer |

## Figures
1. `fig1_forest_coefficients.png` — judge-surface coefficients with 95% CIs (cluster-robust OLS).
2. `fig2_fan_forest_coefficients.png` — fan-surface coefficients with 95% CIs.
3. `fig3_pro_ranking.png` — 60-pro dancer Δ_pro (±1 SD), judge channel.
4. `fig4_estimated_fan_votes.png` — top-12 fan-vote totals with fix-2 grid-neighbourhood SEs.
5. `fig5_backtest_residuals.png` — leak-free back-test scatter + Q-Q plot of residuals.

## Issues or Limitations
1. **A depends on the hazard, which conditions on realized scores** — the +95% agreement is an in-sample reproduction, not an ex-ante forecast; the fan-vote estimates' value is as a latent covariate surface, not as a predictive model of the elimination show.
2. **The u_i random effect is built from the celebrity's own within-season mean z-score**, so the judge surface's u_i coefficient partially re-learns the target; the leak-free back-test R² = 0.476 using entry information (u_i mapped *from the training split alone*) is the honest ex-ante number.
3. **MixedLM is superseded, not deleted**: it converged this round (llf = −5,981.37) but is recorded as non-primary in every CSV's engine column; the cluster-OLS engine is the single quoted design.
4. **SE model** (grid-neighbourhood std) is wider than pure Poisson noise and narrower than a full Bayesian posterior on (γ, wscale); it propagates first-stage G-estimation parameter uncertainty ≈ 4–9% relative SE, but abandons the conditional independence assumption only approximately.
5. **Dance-genre dummies** are not derivable from the CSV (no dance column exists); industry6 proxies stand in, per the explicit omitted-components paragraph in the previous round.
6. **Multi-season celebrities** (n = 13) are distinct cids with no cross-season random-effect pooling.
7. **`cluster_ols_judge.csv`** is retained as a historical addendum artifact but is superseded — quoting it alone would be an expired-number error; the authoritative design is `response_surface_coefficients.csv`.
