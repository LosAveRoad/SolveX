I've reviewed the code (`me_fvi.py`), outputs (`consistency_report.json`, `weekly_certainty.csv`, `fan_votes_estimates.csv`, `case_studies.csv`, `null_model_pvalues.csv`, figures), and cross-checked the programmer's claims. Here is my review.

---

# Model 1 Review — ME-FVI (Maximum-Entropy Fan-Vote Inversion, Elimination Constraints)

## What checks out

- **Core inversion is faithfully implemented.** Per-week min-KL-to-flat-prior on the simplex with combined score C = 0.5·J + 0.5·F and non-strict pairwise margin constraints for the eliminated couple matches the plan's formulation. SLSQP with a projected-gradient `soft_repair` fallback (cvxpy unavailable, disclosed). Spot check confirms correctness of the exponential-family structure: e.g. S1W2 (6 couples, eliminated Trista Sutter not judge-last) gives exactly 1/6 for the four uninvolved couples and shifts only the eliminated (0.1167) and the judge-minimum couple Holyfield (0.2167) — exactly what a single-constraint KL projection must do.
- **Headline counts consistent.** `consistency_report.json` matches the report: 2,249 couple-weeks, 264 week-events, 34 seasons; feasibility 1.0/1.0; null hit rate 0.2266 (≈22.7%, = 264×1000 pooled draws); bootstrap hit-rate mean 0.738 (pct) / 0.777 (rank); hold-out n=162, accuracy 0.4198, baseline 0.1578, mean β = 0.0. All present in the actual JSON.
- **Local numbers verify.** Bobby Bones S27W8: fan share 0.216667, band [0.180192, 0.257952] → half-width 0.039 (report: "≈0.039" ✓); κ = 297.28 ("median κ ≈ 297" ✓). Bobby Bones per-week mean fan share over his 7 pct-rule weeks = 0.115 vs mean judge share 0.097 — both verified from `case_studies.csv`. "110/264 weeks at γ_max = 0.5" — the *count* of rows matches (110 rows with 0.4999999995…), but the *value* is impossible (see Issue 1). Fan shares sum to 1 within weeks (spot-checked S1W2). All 7 listed output files + 4 figures exist.
- **Known controversies recovered directionally**: Jerry Rice (fan≥judge, growing late-season), Billy Ray Cyrus (positive gap up to +0.094), Bristol Palin (rising fan share with low judge rank), Bobby Bones (fan 0.115 > judge 0.097) — all present and consistent.

## Critical problem: γ_max is mathematically impossible for ~110 weeks

The report claims **"110/264 weeks (41.7%) have maximum feasible elimination margin γ_max ≥ 0.5"**. This is provably false. With n_s survivors, summing the margin constraints C_i − C_e ≥ γ over all survivors gives

  Σ_{i≠e}(C_i − C_e) = ½·[2 − (n_s+1)(J_e + F_e)] ≤ 1  ⇒  **γ_max ≤ 1/n_s**.

For a 5-couple week (S1W3, reported γ_max = 0.4999999995) the true bound is γ_max ≤ 1/4 = 0.25; for a 7-couple week (S2W4, also reported 0.5) it is ≤ 1/6 ≈ 0.167. The reported 0.5 cap is impossible in **every** week where it appears (all have n ≥ 3, so γ ≤ 1/2… and n ≥ 4 in all flagged rows).

**Root cause found in `me_fvi.py`.** The feasibility check ignores the required margin γ in *both* solver paths:
- SLSQP success path: `viol = max(0, max(C_e − C_i))` — no `−γ`.
- `soft_repair` fallback: `ok = viol <= 1e-6` where `viol` is again the pure ordering violation `C_e − C_i`, not `C_e − C_i + γ`.

So whenever SLSQP fails at an infeasible γ (which it must, since the true constraint set is empty), the fallback still returns ok=True as long as the elimination ordering holds — which it does in ~all weeks. The bisection in `gamma_max()` then marches `lo` to the hard-coded upper bracket 0.5, producing the impossible 0.4999999995 values (identical to ~1e-10 across all 110 rows and both rules — the signature of converging to the bracket, not a solution). This corrupts: the "110/264 = 41.7% at cap" claim, the "25% of weeks have γ_max ≤ 0.0054" quartile statistic (small values are also unreliable — they mark where soft_repair *failed to converge*, not true infeasibility), fig4 (left panel), and the narrative "bands widest exactly in weeks with tiny γ_max".

## Other issues

- **"Judges alone would have eliminated the eventual eliminated couple in only 37.9% of the 264 weeks" has no provenance.** This number appears nowhere in `me_fvi.py`, `consistency_report.json`, or any output CSV (the 0.379 hit in `null_model_pvalues.csv` line 177 is a coincidental per-week null hit rate). It cannot be accepted as reported.
- **`null_p_value` is not a p-value.** In the code it is literally `max(null_hit_rate, 1/1000)` — the null hit rate itself. The plan's required "empirical χ² or permutation test, p < 0.01" was never implemented; no test statistic compares model vs. null properly (the pooled 0.74 vs 0.23 contrast is qualitative, not a test).
- **Minor mislabeling**: fig2 caption claims it "reveals … the S28+ rank-rule shift", but `gap_F_minus_J` is computed only for pct-rule rows; the heatmap cannot show a rank-rule shift. Also the report's "74–96% hit rate" phrasing conflicts with its own numbers (mean 0.738, range 0.133–0.943) — min 0.133 is well below 0.90 despite "calibrated to ≥0.90 where kappa allows"; the min-hit-rate weeks should be individually listed.
- **Acceptable disclosed limitations**: relative-share-only identification, fan_votes_1M as pseudo-scaling, S27 judge-save not modeled, tie-handling asymmetry between rules, degenerate β = 0 hold-out (honestly flagged), no cvxpy. These are fine.

## Severity assessment

The **primary deliverable — the 2,249 fan-share point estimates and their calibrated intervals — is largely unaffected** (point estimates are computed at γ=0, where the check is valid; bootstrap calibration uses F*, not γ_max). But γ_max is one of the model's headline certainty metrics per the plan, and the reported γ_max values — including the specific "110/264 at ≥0.5 cap" and "bottom quartile ≤ 0.0054" claims, both quoted as key numerical results — are provably wrong, plus two auxiliary statistics (37.9% judges-alone; null p-values) are unverifiable/invalid as implemented. This requires revision of the γ_max machinery and the affected claims.

---

VERIFICATION_RESULT: NEEDS_REVISION

## Issues Found:

1. **γ_max values impossible (critical).** 110/264 weeks report γ_max = 0.4999999995 (cap), but for n_s survivors γ_max ≤ 1/n_s mathematically (≤ 0.25 for a 5-couple week, ≤ 0.167 for a 7-couple week). Cause: in `me_fvi.py`, `solve_week()` (both the SLSQP post-check and the `soft_repair` fallback return path) computes `viol` as the pure ordering violation `max(C_e − C_i)` **without** adding back the requested margin γ, and `gamma_max()`'s bisection treats that as feasibility, so `lo` always converges to the 0.5 bracket whenever the elimination ordering is achievable.
2. **"Judges alone eliminated the recorded couple in 37.9% of 264 weeks" is not computed anywhere** in `me_fvi.py` or in any output file; it cannot be checked and must be either produced by code or removed.
3. **`null_model_pvalues.csv` "null_p_value" column is not a p-value** — code sets it to `max(null_hit_rate, 1/1000)`. The plan's null-model test (permutation/χ², p < 0.01) is not implemented; no formal model-vs-null inference exists.
4. **Fig2 caption/claim overreach**: `gap_F_minus_J` exists only for pct-rule rows, so the heatmap cannot support the claimed "S28+ rank-rule shift" signal; and the report's "74–96%" hit-rate phrasing contradicts its own reported range (0.133–0.943).

## Fix Instructions:

1. **Fix the margin check in `me_fvi.py`, function `solve_week`**: report violation *inclusive of the margin* in both paths:
   - SLSQP success path: `viol = max(0.0, max(combined(F,J)[e] - combined(F,J)[i] + gamma for e in elim_idx for i in surv))`; `ok = viol <= 1e-6` **and** additionally confirm `res.success`.
   - `soft_repair` fallback: change the returned-check to `viol = max(0.0, max(A[e] - A[i] + gamma ...))`; `ok = viol <= 1e-6` (keep the internal loop as is — it already uses gamma-inclusive violations).
   **Preferred alternative (exact, solver-free)**: compute γ_max with a linear program instead of bisection. Variables F (n) and t; maximize t, i.e. `scipy.optimize.linprog` with objective c = [0,…,0, −1]; constraints: for each survivor i, `0.5*(F_i − F_e) − t ≥ −0.5*(J_i − J_e)`; `sum(F) = 1`, `F ≥ 0`, `t` unbounded below (set loose bounds, e.g. [−1, 1] for t). The LP optimum is the exact γ_max; with `linprog` this also removes reliance on SLSQP/soft_repair convergence entirely.
2. **Recompute and rewrite all γ_max-derived claims** after the fix: the "110/264 weeks (41.7%) at γ_max ≥ 0.5" statement (expect every γ_max ≤ 1/n_s, i.e., ≤ ~0.14–0.25), the "25% of weeks have γ_max ≤ 0.0054" quartile, regenerating `figures/fig4_calibration.png` (left panel) and `weekly_certainty.csv` (`gamma_max_pct`, `gamma_max_rank`), and the fig4/Report narrative linking band width to γ_max. Verify the band-width-vs-γ_max correlation claim against the corrected values; keep the restated numbers consistent with the "mean 0.738, range 0.133–0.943" hit-rate statistics.
3. **Add the judges-alone statistic to the code** (in the section computing consistency metrics): count over the 264 week-events, under the pct rule, the fraction of weeks where the recorded eliminated couple has strictly minimal `judge_total` (and, separately, minimal `judge_share_rank`); store both in `consistency_report.json` as e.g. `judges_alone_consistency_pct`; then cite the computed number in `results_summary.md` (replacing the unsupported 37.9%).
4. **Replace the null p-value**: keep `null_hit_rate` and add a proper test, e.g. per-week binomial p-value `p = 1 − stats.binom.cdf(K*hit_rate_model − 1, K, null_hit_rate)` (vectorized, K = 300 calibrated draws), or a pooled permutation test comparing pooled model hits vs. pooled null hits; report the number of weeks with p < 0.01 in `consistency_report.json` and in the summary. Alternatively rename the column `null_hit_rate_capped` if no test is added — but then drop the implied "p < 0.01" language.
5. **Fix figure/summary labeling**: restrict the fig2 caption to pct-rule gap; either compute the rank-rule gap additionally or remove the "S28+ rank-rule shift" claim; in `results_summary.md`, list the weeks whose calibrated hit rate falls below 0.90 (kappa-capped) instead of the inconsistent "74–96%" phrasing.