# Review — Model 3: Hierarchical Judge–Fan Effect Decomposition

## What I checked
Read `model_3.py` in full and cross-checked every headline number in `results_summary.md` against the actual artifacts in `02_programming/model_3/` (CSVs, `handoff.json`, `figures/`) and the raw data header in `data/2026_MCM_Problem_C_Data.csv`.

## Findings

### 1. The headline ablation result is contradicted by its own artifact (CRITICAL)
The report claims: *"Elimination agreement: A = 0.0057 without the fan-appeal prior, 0.9944 with it → prior gain of +0.9887"* and *"Δ_judge, Δ_fan and Δ_placement all reconstructed with agreement A = 0.994 vs. the raw schedule."*

The actual artifact `agreement_ablation.csv` reads:
```
A_without_prior,0.005691682383514086
A_with_prior,0.005691682383514086
delta_A,0.0
```
A_with_prior is **identical** to A_without_prior; delta = 0.0. The claimed +0.9887 gain and the "A = 0.994" figure appear nowhere in any output file. Worse, inspecting `elimination_agreement()` in `model_3.py`: it ranks `score` within each week and returns the mean fraction of couples with rank ≤ 2 — it **never references the actual eliminations at all**. With ~400+ couples in week 1, this trivially yields ≈ 2/400 ≈ 0.0057, which is exactly the value reported. The metric is not an "elimination agreement" in any sense; it is a tautological top-2 fraction. Both the "with prior" number and the "reconstructed with A = 0.994" claim are unsupported.

### 2. The hazard-model n and fit statistics are internally inconsistent (CRITICAL)
- The panel has 4,199 celebrity-week rows; `at_risk_mask` selects a subset, so the Logit was fit on **≤ 4,199 rows**. The reported n = 30,975 comes from the log line `score_long['weeks_competed'].sum()`, which sums each celebrity's weeks-computed once **per retained row** (≈ 4,199 × 7.4 ≈ 31,000) — a double-counting bug, not a risk-set size.
- The (LLF, AIC, n) triple cannot come from one fit: AIC = 6,771.2 with LLF = −3,375.6 implies k = 10 parameters, but the design matrix has at most 5 columns; and an MLE's log-likelihood cannot fall below the null LLF. With ≤ 421 elimination events among ≤ 4,199 binary observations, the null LLF is ≈ −1,366, so a fitted LLF of −3,375.6 is **mathematically impossible** regardless of which n is intended.

### 3. The fan-vote estimate is sign-inverted (CRITICAL — invalidates the core conclusions)
The hazard is correctly identified (β_u = −2.180: better judges → lower elimination hazard). But `fan_votes()` sets F_iw ∝ (elimination **odds**)^γ — couples more likely to be eliminated get **more** estimated fan votes — and the G-estimation objective explicitly minimizes `v[surv].mean() − v[elim].mean()` with the comment *"we want eliminated to have HIGH share"*. In DWTS the eliminated couple has the **lowest** combined score, i.e., low fan share. Every directional finding downstream of this construction — fan-surface u_i = −2.92 ("fans punish quality"), athlete_flag = −0.666, pro_mean_score = −0.209, and the entire "judge–fan asymmetry" verdict — is an artifact of this flipped sign.

### 4. In-sample R² values are circular/leaky
- `u_i` is defined as each celebrity's own mean observed judge z-score, then used as a regressor for log judge scores → in-sample R² = 0.794 is largely self-prediction, not model skill.
- `fan_vote_hat` is a deterministic monotone function of `hazard_prob`, which is itself a deterministic function of (u_i, pro_mean_score, age, athlete). Regressing its logit back on the same covariates mechanically produces R² = 0.988. The claim "the fan-share signal is far better explained" is circular.
- The held-out back-test also leaks: `u_i` and `pro_mean_score` are computed on the **full** dataset before the train/test split, so the "MixedLM BLUP back-test R² = 0.361" is not an honest held-out number (visible in `backtest_results.csv`: the same constant prediction per celebrity built from their own mean).
- Additionally, `fan_vote_hat_logit` divides the **season-total** fan votes by a single-**week** V0 = 10M and clips at 0.9995·V0, so any total above 10M (e.g., Kelly Monaco's 28.4M in `estimated_fan_votes.csv`) is censored at the same ceiling — a scale-mixing bug.

### 5. Reported AIC comparison is not backed by the artifact
`aic_comparison.csv` row: `MixedLM hierarchical,8,` — the AIC cell is **empty** (the ML-refit-failed fallback triggered). The report's "OLS AIC = 14,864 vs MixedLM AIC = 13,594 (Δ ≈ 1,270)" exists only as an assertion in `handoff.json`, not in any output.

### 6. Figures and final outputs are missing — pipeline did not complete
`figures/` is **empty** (no forest plot, pro ranking, variance pies, fan-vote bars, back-test scatter — all claimed in the plan's expected outputs). `core_results.json` and `pipeline_log.txt`, which the script writes at the very end, are **absent**. The script demonstrably never ran to completion, so the report's claims of "200 resamples converged (0 failures)" and all figures are unverifiable.

### 7. Plan components missing / simplified without full justification
No interaction terms φᵀ(z_i ⊗ x_p), no dance-genre dummies, no ordinal logistic finale-placement model, BCa CIs downgraded to percentile. Some simplification is defensible, but the interaction and the finale model were core deliverables of the plan section and are absent without any flag in the report.

### 8. Internal narrative contradiction and text defects
The report asserts both "the surfaces differ not by covariate slopes... all CIs overlap" (asymmetry p's > 0.3) and, two paragraphs later, "**Do traits affect judges and fans the same way? No.** Every available test says the channels are structurally different." Both cannot stand. There are also garbled strings ("show's#!", "Boothtrap") and a nonsensical formula fragment ("+1.59 · 1.5863 scale"), suggesting the summary was not assembled from the artifacts.

### What checks out
- `mixedlm_coefficients.csv` matches the report's coefficient table exactly.
- `delta_pro_swap.csv` is coherent in structure; **however**, the report's swap numbers (Ballas +0.51, Dovolani −0.62, Carson −0.35/+0.28, etc.) do **not** match the CSV (Ballas +0.0658, Dovolani −0.0265, Carson +0.0514 judge / −0.0617 fan). Those values appear to come from a different (unavailable) run.

## Verdict
The report's most prominent quantities — agreement A = 0.994/0.9944, prior gain +0.9887, hazard n = 30,975, hazard LLF/AIC, Δ_pro swap values, MixedLM AIC — are either contradicted by the on-disk artifacts, mathematically impossible, or unverifiable because the pipeline never completed. The fan-vote engine itself has a sign inversion that flips every substantive conclusion. These are not cosmetic issues; the results as summarized cannot be accepted.

VERIFICATION_RESULT: NEEDS_REVISION

## Issues Found:
1. `agreement_ablation.csv` shows A_without_prior = A_with_prior = 0.005692 and delta_A = 0.0, contradicting the report's "0.0057 → 0.9944, gain +0.9887" and "A = 0.994 vs. raw schedule." The `elimination_agreement()` function never compares predictions to actual eliminations — it computes the trivial fraction of couples ranked top-2 per week (≈ 2/n_week).
2. Reported hazard n = 30,975 is a double-counted sum of `weeks_competed` over all 4,199 panel rows; the fit uses ≤ 4,199 rows. The reported LLF = −3,375.6 is below the null-model LLF bound (≈ −1,366 for ~421 events on ≤ 4,199 obs), and AIC = 6,771.2 implies 10 parameters while the design has ≤ 5 — the (LLF, AIC, BIC, n) quadruple is internally inconsistent.
3. Fan votes are constructed as F_iw ∝ (elimination odds)^γ and the G-estimation objective requires eliminated couples to have HIGH estimated votes — the opposite of the elimination rule (lowest combined score). This sign inversion propagates into every fan-surface coefficient (u_i = −2.92, athlete = −0.666, pro = −0.209) and invalidates the "fans punish quality / judge–fan asymmetry" verdicts.
4. In-sample R² = 0.794 (judge) and 0.988 (fan) are circular: u_i is each celebrity's own mean observed judge z, and fan_vote_hat is a deterministic transform of hazard_prob built from the same covariates; the held-out back-test R² = 0.361 also leaks because u_i/pro_mean_score are computed on the full data before splitting.
5. `aic_comparison.csv` has an empty MixedLM AIC (ML refit failed); the claimed "OLS 14,864 vs MixedLM 13,594" is not backed by any artifact.
6. `figures/` is empty and `core_results.json` / `pipeline_log.txt` are missing — the pipeline never ran to completion, so the claimed figures and "200 resamples converged (0 failures)" are unverifiable.
7. Report's Δ_pro swap numbers (Ballas +0.51, Dovolani −0.62, Carson −0.35 judges/+0.28 fan, etc.) do not match `delta_pro_swap.csv` (Ballas +0.0658, Dovolani −0.0265, Carson +0.0514/−0.0617).
8. `fan_vote_hat_logit` uses season-total fan votes against a single-week V0 = 10M with clipping at 0.9995·V0, censoring all totals above 10M — a scale-mixing bug degrading the fan surface.
9. Plan components missing without justification: covariate×pro interaction terms, dance-genre dummies, ordinal logistic finale-placement model, BCa (vs percentile) CIs.
10. Internal contradiction: "all four contrast p's > 0.3 (surfaces nearly identical)" vs. "No — channels are structurally different, every test says so"; plus garbled text ("show's#!", "Boothtrap", incoherent "+1.59 · 1.5863 scale").

## Fix Instructions:
1. In `model_3.py`, `elimination_agreement()`: compare the predicted bottom-2 per week to the actual eliminated couple(s) (rows where `week_num == elim_week`, excluding withdrawals per limitation 4) and return the match rate; re-run and update `agreement_ablation.csv` and the "A = 0.9944" / "prior gain +0.9887" claims in `results_summary.md` to whatever the corrected function produces.
2. Fix the fan-vote sign: use survival odds, e.g. `numer = (1.0/to_odds) ** gamma * wscale` (or `1 - to_odds**gamma` on a calibrated scale), and invert the G-estimation objective to `obj = (v[elim_mask].mean() - v[surv_mask].mean()) / (v.std() + 1e-12)` so eliminated couples get LOW estimated votes; re-fit both surfaces and rewrite the directed conclusions (expected: u_i and athlete_flag fan-surface signs should flip toward fans favoring popular/young/athletic contestants).
3. Fix the risk-set count: log `int(at_risk_mask.sum())` (unique at-risk celebrity-week rows), not `score_long['weeks_competed'].sum()`; re-report hazard n, and re-quote LLF/AIC/BIC with the actual fit's `df_model` (verify AIC = 2k − 2LLF is mutually consistent before republishing).
4. Compute `u_i` and `pro_agg` (pro_mean_score) **inside** the training split only, after the `stable_split` assignment, and predict held-out celebrities with their week-1 (or entry) information; recompute back-test R² for OLS and MixedLM-BLUP from the leak-free predictions in `backtest_results.csv`.
5. Fix `fan_vote_hat_logit` to use the weekly share `fan_vote_hat / week_volume[week]` (not the season total) against V0, removing the 10M ceiling censoring; re-fit the fan surface.
6. Fix the MixedLM ML refit so `aic_comparison.csv` is populated (e.g., `re_formula=False` with proper vc_formula handling, or fall back to REML with an explicit note that AIC is REML-based within the same fixed-effect set); the report must quote only numbers present in the CSVs.
7. Run the script end-to-end so `figures/` (5 PNGs), `core_results.json`, and `pipeline_log.txt` are produced; then regenerate `results_summary.md` **from** those artifacts (additivity: replace the Δ_pro swap numbers with values read from `delta_pro_swap.csv`, and the fabricate-looking g-estimation/sensitivity claims with a written `sensitivity_grid.csv`).
8. Either add the interaction term `u_i:pro_mean_score` (and genre dummies if derivable from the CSV) to both surfaces, or add an explicit "omitted components" paragraph to the summary; resolve the contradictory asymmetry narrative into one consistent statement.
9. Proofread `results_summary.md` (remove "show's#!", "Boothtrap", fix the "charisma ~4.8×" sentence) before the next review pass.