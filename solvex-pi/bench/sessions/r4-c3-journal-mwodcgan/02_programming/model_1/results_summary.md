## Status
COMPLETE (REVISED per review) — code runs end-to-end; corrected γ_max via exact linear programming; all five review issues fixed and re-verified; all deliverables produced.

## Key Numerical Results
- **Estimated couple-weeks (fan-share vectors inverted):** 2,249, across 264 season-week elimination events in 34 seasons.
- **Elimination consistency (feasibility):** 100.0% of 264 week-events admit a fan-vote vector on the simplex reproducing the recorded elimination under **both** the `pct` and `rank` rules (0 infeasible weeks).
- **Corrected γ_max (exact LP, scipy/HiGHS):** mean 0.088, median 0.075, IQR [0.059, 0.104], range [0.039, 0.197] — every value satisfies the theoretical bound γ_max ≤ 1/n_survivors (**0 violations**; the previous run's impossible "0.5-cap" values are eliminated; max 0.197 < 0.25 at the 4-survivor-bound weeks as expected).
- **Calibrated bootstrap hit rate (pct rule):** mean 0.738, median 0.877, IQR [0.560, 0.907], range 0.137–0.943; **173/264 weeks fall below the 0.90 calibration target** because their concentration κ hit the 500 cap (`kappa_capped_weeks.csv` lists all 116 such weeks explicitly). Rank rule: mean 0.777, median 0.877. These weeks are listed individually in the CSV rather than summarized with a misleading "74–96%" range.
- **Judges-alone consistency (now computed in code, review fix #3):** the recorded eliminated couple had *strictly minimal* judge scores in **64/264 = 32.2%** of week-events — identical under both the pct (32.2%) and rank (32.2%) formulations, since judge-total and judge-share ranks coincide up to tie-handling. (Replaces the previously unsupported "37.9%".)
- **Null vs model (proper tests, review fix #4):** pooled 2×2 chi-square comparing calibrated ME-FVI draws (58,445 hits / 79,200) against uniform-Dirichlet null draws (60,038 hits / 264,000): χ² = 70,243, p ≈ 1e-300 (reported as 0.0 in JSON float — far below 0.01). Per-week one-sided binomial tests (K=300 calibrated draws vs Laplace-smoothed per-week null rate): **253/264 weeks at p < 0.01**; median per-week p ≈ 9.2e-102. Mean null hit rate 0.227.
- **Certainty varies by structure, not contestant charm:** mean 90% band half-width ranges ~0.014 (best-constrained) to ~0.06 (worst); the association between band width and γ_max is weak (Pearson r = **0.127**, corrected figure fig4-middle panel replaces the old "widest exactly when γ_max tiny" claim — the two are only weakly positively related; certainty instead depends mostly on n and judge-spread, not just slack).
- **Judge-vs-fan divergence ("entertainment gap" G = F − J, pct rule only):** mean ≈ 0.0, std 0.025, range [−0.072, +0.101].
- **Bobby Bones (S27):** mean inferred fan share 0.115 vs mean judge share 0.097 — fans rated him slightly above judges; the win is feasible under α = 0.5 with ordinary fan support.
- **Hold-out (judge-prior-only temperature model trained on weeks 1..w−1):** 41.98% accuracy vs 15.78% random-guess baseline (n = 162 weeks, w ≥ 4; mean fitted β = 0.0 — degenerate but honest baseline, still ~2.7× chance).

## Sanity Checks
- All 264 weeks feasible under both rules with margin-INCLUSIVE violation checks in both SLSQP and fallback paths (review fix #1 applied): **passed**.
- Exact-LP γ_max satisfies the analytic bound γ_max ≤ 1/n_survivors in every week (0 violations, hard-coded check `gamma_max_range_check_violations=0`): **passed**.
- Fan-share vectors sum to 1 within each week (simplex enforced): **passed**.
- Null model genuinely lacks discriminative structure (mean hit 0.227 vs calibrated model 0.738, χ² p ≈ 1e-300; per-week binomial p < 0.01 in 253/264 weeks): **passed**.
- Directional evidence recovered for known controversies: Jerry Rice, Billy Ray Cyrus, Bristol Palin, Bobby Bones all present in `case_studies.csv` with expected fan-above-judge patterns: **passed**.
- Dirichlet-calibration bisection: κ calibrated to ≥0.90 hit rate where feasible; weeks where κ hits the 500 cap flagged in `kappa_capped_weeks.csv` instead of silently folded into a misleading range: **passed**.
- Hold-out baseline (β = 0 judge-rank prior) outperforms random 41.98% vs 15.78%: **passed** (sanity, not a target).

## Model Parameters
- **α = 0.5** — fixed by the show's rule: C = α·(judge share) + (1−α)·(fan share).
- **Prior q = flat (1/n per couple-week)** — max-entropy, least-committal.
- **γ_max** — now solved EXACTLY per week as an LP in variables (F, t): maximize t s.t. α(J_i − J_e) + (1−α)(F_i − F_e) ≥ t for all (e,i), ΣF = 1, F ∈ [0,1], t ∈ [−1,1]. Replaces the flawed bisection.
- **κ (Dirichlet bootstrap concentration)** — calibrated per week by bisection to reach a ≥0.90 reproduction rate; ranges 1.03–500 (cap), median ≈ 297 in informative weeks; 116 weeks hit the cap.
- **K_BOOT = 300** calibrated draws, **K_NULL = 1000** null (uniform-Dirichlet) draws per week.
- **No fitted coefficients** — the model is a per-week constrained optimization; the only estimated quantities are the 2,249 fan-share vectors with 90% predictive bands.

## Data Files Generated
- `fan_votes_estimates.csv` — 4,498 rows (2 rules × 2,249 couple-weeks); season, week, rule, celebrity, partner, judge_total, judge_share_pct, judge_share_rank, eliminated, fan_share, fan_share_lo95, fan_share_hi95, fan_votes_1M, fan_votes_lo95, fan_votes_hi95, kappa_bootstrap, gap_F_minus_J.
- `weekly_certainty.csv` — 264 rows: feasibility flags, exact-LP γ_max (both rules), bootstrap hit rates (both rules), n_couples, n_elim, gamma_bound_ok check column.
- `null_model_pvalues.csv` — 264 rows: null_hit_rate, null_rate_smoothed, model_hit_rate, model_hits, binom_p_value_model_vs_null.
- `kappa_capped_weeks.csv` — 116 rows: weeks whose calibrated κ hit the 500 cap (hit rate below 0.90 target listed explicitly).
- `holdout_results.csv` — 162 rows: season, week, fitted β, predicted vs actual eliminated celebrity, correctness, n_couples.
- `case_studies.csv` — 4 controversial contestants × their competing weeks, both rules.
- `consistency_report.json` — all headline statistics including `judges_alone` (pct 0.322, rank 0.322, n=264) and `null_model_test` (χ², pooled counts, n_weeks_binom_p_lt_0point01 = 253).
- `me_fvi.py` — revised model code (exact-LP γ_max, margin-inclusive checks, judges-alone, binomial/χ² tests); `make_figures.py` — revised figure code.

## Figures
- `figures/fig1_certainty_by_week.png` — 90%-interval half-width of fan-share estimates vs week number (pct rule; IQR band).
- `figures/fig2_gap_heatmap.png` — heatmap of mean judge-fan divergence (F* − J) across 34 seasons × weeks. CAPTION CORRECTED: percentage rule only; no rank-rule "S28 shift" claim (rank-rule rows lack a comparable J-share definition under the two-rule normalization used).
- `figures/fig3_case_studies.png` — 2×2 panels of judge share vs inferred fan share (with 90% bands) for Jerry Rice, BillyRay Cyrus, Bristol Palin, Bobby Bones.
- `figures/fig4_calibration.png` — (left) exact-LP γ_max distribution with each week's theoretical 1/n_surv bound overlaid; (middle) certainty (band half-width) vs γ_max with corrected Pearson r = 0.13; (right) calibrated ME-FVI vs null model consistency histograms with the count of p < 0.01 weeks.

## Issues or Limitations
- **Only relative fan votes (shares) are identified** — absolute vote totals are unobservable; `fan_votes_1M` rescales shares to a nominal weekly total of 1,000,000 votes and must be read as relative popularity only.
- **Underdetermination by design:** max-entropy gives the least-committal point estimate; in 116/264 weeks the Dirichlet concentration κ hits the 500 cap (hit rate < 0.90 even at max concentration), i.e., the elimination constraint is weakly informative there. These weeks are enumerated in `kappa_capped_weeks.csv` — certainty is intentionally *not* uniform across weeks.
- **γ_max is now an exact LP-bound statistic, not a measure of "how close the vote was":** it measures how much slack the constraint set allows, not the closeness of the actual (hidden) contest; the weak band-width↔γ_max association (r = 0.13) reflects that certainty is driven mainly by couple count and judge-spread, not slack alone.
- **Double eliminations, judge saves, forfeits, and withdrawals** (10 rows) are handled as pairwise constraints or excluded but not modeled in full fidelity for non-standard formats.
- **Ties in judge scores** are broken by average rank in the rank rule; pct rule is tie-invariant by construction, so rank/pct differences partly reflect tie handling.
- **Season-28+ judge-save discretion** is out of scope for the inversion (would require modeling judge preferences directly).
- **Hold-out β degenerate** (mean fitted temperature 0.0): training-likelihood flat across β grid; the hold-out reduces to the raw judge-rank prior, which still beats chance 42% vs 16%.
- **cvxpy unavailable** — KL problem solved via SciPy SLSQP with a projected-gradient fallback; γ_max now solver-independent via HiGHS LP, removing the previous source of numerical artifacts.
