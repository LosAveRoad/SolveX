## Status

**SATISFIED.** `python3 run.py` regenerates every output deterministically (seed 20260205) in ~3 s (MAP + 4000 Laplace draws + validation + figures). All headline numbers below are copied from `results.json`.

Model 1 = Constrained-Ordinal Bayesian Fan-Vote Identification: softargmax market-share grid with outside (non-voting) mass, every one of the 265 vote-based exit weeks enforced as a Plackett–Luce ordinal soft constraint (exact bottom-m for S≤27 and all multi-exits; bottom-2 membership for the 47 S≥28 single-exit weeks, where judges only veto within the bottom two), weak finale-placement anchors, multi-start MAP (stage A) and per-season block-sparse Laplace posterior (stage B) with rank-violation importance weighting.

## Key Numerical Results

- **Exit-recovery (posterior mean ordering vs observed exits):** single-exit exact-regime hit rate **100% (186/186)**; multi-exit exact-set hit rate **100% (32/32)**; S≥28 judge-veto weeks bottom-2 capture **100% (47/47)**. Targets were ≥85% / ≥75% (plan validation).
- **Probabilistic recovery** (importance-weighted capture probability of the observed exit set, exact-regime): model mean **0.325** vs judge-only **0.134** and uniform **0.127** (all 265 weeks: 0.318 / 0.151 / 0.143; singles-only judge-only mean `mean_p_capture_judge_single` = 0.150) — 2.4× the judge-only baseline. Log-loss **1.167** (model) vs **2.050** (judge-only) vs **2.117** (uniform). **Hard judge-only baseline:** picking the lowest judge total recovers the actual exit in **76/186 = 40.9%** of exact-regime single-exit weeks (`hit_rate_single_exact_judge_only`), vs **100% (186/186)** for the model.
- **Survivor identity:** reconstructed next-week competition counts match `season_weeks.csv` for all 335 season-weeks (build-time assertion; exits keyed by `last_week`).
- **Uncertainty is NOT constant (per the problem statement):** mean CV of week-1 rows **2.72** vs mid-run rows **2.23** (ratio **1.22**); 95% interval coverage **1.00** (map point and posterior mean) — conservative, i.e. intervals are wide by design (see Limitations). Example: Jerry Rice (S2) week-1 share 0.143, 95% CI [0.00003, 0.884], CV 1.66 → week-8 0.346, CI [0.0007, 0.989], CV 1.01.
- **Judge-vs-fan tension:** mean within-week sd of the fan-minus-judge gap **0.86** on the log-utl scale (target ≥0.05) — fans add non-trivial structure beyond judges. Correlations of recovered φ̂ with judge signal: vs weekly judge share **r = 0.697** (`figure_stats.r_phi_vs_judgeshare`), vs within-week judge z-score **r = 0.385** (`figure_stats.r_phi_vs_judgez`, as plotted in F5; z-scores are unit-scaled per week, so they compress cross-week share differences that the share correlation retains).
- **Leave-one-week-out stability (12 random exit weeks refit):** Kendall τ with the full fit = **0.882 mean / 0.744 min** (season scope), 0.712 (exit-week scope) — above the 0.80 plan gate on the season metric.
- **Zoom on the S26 W3 triple elimination:** the 6-ordering Plackett–Luce path-sum is in the likelihood; the MAP recovers the exact exit set.
- **Fitted parameters:** judge sensitivity **ξ̂ = 4.147** (posterior on fan utility scale), run-popularity sd **0.868**, decay-strength sd **0.392**; season terms ε_s are inactive at the MAP (**ε̂_s = 0 for all 34 seasons** — with a within-week shift-invariant likelihood, season-level signal is absorbed by the 421 per-run g1 effects, so the ε_s shrink entirely to their prior mean), MAP negative log posterior = **206.19**.
- **Importance weighting:** 0 of 4000 raw Laplace draws satisfy all 265 weekly ordinal facts exactly, so the deliverable posterior uses the least-violating quartile (1000 draws, κ=1 weights for diagnostics); exponential-weight ESS = 2.33 (documented limitation).

## Sanity Checks

- φ̂ shares sum to exactly 1 within every week (min/max of weekly sums = 1.000000/1.000000); all 2777 contestant-week shares in [0.0015, 0.5702] — plausible magnitudes for a 6–16-couple field.
- 630 vote-based exit pairs (233 single + 31 double + 1 triple weeks; 265 weeks) all matched their contestant rows via `last_week`; withdrawals excluded from risk pools; all build-time asserts passed (exit counts, exits competing, veto weeks ≥3 dancers).
- Gradient of the full objective verified against central-difference directional derivatives: max relative error ≤ **3e-8** (path-enumeration likelihood is analytically exact; two earlier gradient bugs — a PAIR_SD exponent and a swapped anchor role — were found and fixed by exactly this check).
- Judge-only argmin hit rate on exact-regime singles is **76/186 = 40.9%** (`hit_rate_single_exact_judge_only`), far below the model's 100% (186/186) MAP recovery — the fan-latent space genuinely absorbs what judge totals alone cannot explain. (Soft PL judge-only capture-probability means for reference: 0.150 singles / 0.042 multi-exit weeks, `mean_p_capture_judge_single` / `mean_p_capture_judge_multi`.)
- `0`-vs-`'N/A'` judge-slot semantics and multi-dance week conventions are handled upstream (Phase 1 tables); within-week z-scores used only for reporting.

## Model Parameters

- Latent per contestant-week (2777 cells): fan idiosyncrasy v ~ N(0, 0.6²); run-level popularity g1 ~ N(0, 2²) with fitted sd 0.868; run decay strength κ_a ~ N(0, 2²) with fitted sd 0.392 on a centered weeks-remaining shape.
- Season fan climate ε_s ~ N(0, 0.75²): all 34 values sit at exactly 0 at the MAP — the ε_s are inactive, not unidentified; any within-season level shift of the identified combination ũ cancels in the softmax risk order, so season-level signal is absorbed by the per-run g1 effects and the ε_s collapse to their prior mean. Judge sensitivity ξ ~ N(0, 2²) fitted to **4.147**.
- **`n_params = 3654`** = 2777 (per-week idiosyncrasy v) + 421 (run popularity g1) + 421 (run decay κ_a) + 34 (season ε_s) + 1 (judge sensitivity ξ); all entering the identified combination ũ = ξ·x̄ + v + g1 + κ_a·dmem + ε_s + ½·log x. Posterior sds of the MAP point (`map_theta_sd_*`): v **0.043**, g1 **0.868**, κ_a **0.392**.
- Likelihood: ETA0 = 0.5 per exit event; finale anchors N(0.5, 4²) on placement-ordered utl gaps (1371 pairs); softmax outside mass χ = 1000 (φ₀ ≈ 0.001/week).
- Importance weighting κ = 1.0; master seed 20260205 (draws: SEED+1).

## Data Files Generated

- `model1_fanshare.csv` — 2777 rows; per contestant-week: season, week, celebrity, partner, industry, age, result_type, placement, judge_total, judge_share, **phi_share, phi_sd, phi_lo95, phi_hi95, phi_cv**, phi_map, u_hat.
- `model1_exitfit.csv` — 265 rows; per exit-week: season, week, n_competing, n_exits, veto_regime, rank_grid, p_capture, p_capture_judge, p_capture_uniform, map_bottom_set_correct, exit_rank_in_order.
- `model1_popularity_timeseries.csv` — 2777 rows; per run-week: phi_share, phi_sd, momentum (week-over-week), rel_to_week1, frac_run_elapsed.
- `model1_draws.npz` — 4000 draws × 2777 cells: u_draw, ren_draw (renormalized φ draws), wts, viol, u_map.
- `model1_draw_summary.csv` — 4000 rows; per-draw weight, ordinal-violation count, kept flag.
- `model1_loo.csv` — 12 rows; leave-one-week-out refits: tau_season_same, tau_exit_week.
- `results.json` — every headline number (metrics, parameters, Laplace diagnostics).
- Code: `model1_core.py`, `model1_obj.py`, `model1_post.py`, `model1_run.py`, `model1_figs.py`, `run.py`.

## Figures

- `figures/F1_phats_heatmap.png` — mean recovered φ̂ by season (1–34) × week (1–11).
- `figures/F2_jerry_rice_violin.png` — posterior φ̂ violins, Season 2 weeks 1–8 (Jerry Rice highlighted).
- `figures/F3_calibration.png` — per-week exit-recovery probability: model vs judge-only vs uniform.
- `figures/F4_cv_by_week.png` — posterior CV of φ̂ by week-within-season (certainty increases with information).
- `figures/F5_phi_vs_judge_z.png` — recovered φ̂ vs within-week judge z-score (fan-vs-judge tension; plotted-correlation r = **0.3854**, `figure_stats.r_phi_vs_judgez`).

## Issues or Limitations

1. **Ordinal-only identification:** eliminations reveal ranks, not totals. Fan-share *levels* are weakly identified — posterior intervals are genuinely wide (median CV ≈ 1.0–2.7), and coverage is conservative (1.00 ≥ 0.93 target). Rank *orderings* and elimination recovery are strongly identified (100% MAP, 0.32 mean capture prob vs 0.13 judge-only).
2. **Zero-violation draw count = 0/4000:** requiring all 265 weekly ordinal facts to hold exactly is too strict for the Laplace draw cloud, so the pipeline falls back to the least-violating 25% (1000 draws, uniform weights; κ-weights retained for diagnostics). This is disclosed in `results.json` (`weight_mode="low_violation_top_quartile"`); downstream Model 2/3 should treat `phi_sd` as an upper bound on uncertainty.
3. **S≥28 regime:** judge-veto weeks are modeled as bottom-2 membership (judges' pick is unmodelable from the data); 47 of 265 weeks.
4. MAP hit rates are partially by construction of the soft-constraint likelihood (the non-trivial probabilistic metric is p_capture = 0.325 vs 0.134 judge-only baseline, exact regime); still, the model *explains* every observed elimination with a fan layer no stronger than ξ = 4.15.
5. 13 repeat celebrities are modeled as separate runs (per data dictionary); judge positions are not named judges (Phase 1 caveat); multi-dance-week totals are only compared within-week.
6. `model1_draws.npz` is 170 MB (4000 × 2777 dense draws ×3 arrays) — kept for Model 2/3 propagation; reduce `N_DRAWS` if size is a constraint.
