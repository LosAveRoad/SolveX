I have enough evidence to render the verdict. Here is the complete review (SolveX will save it verbatim to `01_modeling/model_3_review.md`).

---

# Review — Model 3 (round 3): Hierarchical Judge–Fan Effect Decomposition

## What I checked
`model_3.py` (all 732 lines, including the new fix-2 bootstrap block), all artifact CSVs, `addendum_cluster_ols.md`, `cluster_ols_judge.csv`, `cluster_ols_fan.csv`, `handoff.json`, `results_summary.md`, and the two prior review rounds. Cross-checked every headline number against the file it is claimed to come from.

## What genuinely improved
- The `ss_tot` NameError is fixed; agreement now compares predicted bottom-2 to **actual eliminations**; fan votes use **survival odds** with the inverted G-estimation objective; total SE is √Σ(SE²); withdrew → NaN; export groups by `cid`; athlete_flag removed from formulas; rare industries collapsed before fitting. All 8 review fixes are present in code.
- The `estimated_fan_votes.csv` on disk is actually the **refreshed** export (~422 rows, 10 withdrew rows correctly carrying `estimated_total = NaN, note = "withdrew"`; grep finds **no** 0.5M placeholder). The summary's claim that it is stale (409 rows with placeholders) is wrong in the *conservative* direction — but it is still a factual error.
- The status is honestly flagged NEEDS_REVISION and most stale artifacts are labeled.

## Why it still cannot be accepted

### 1. The response-surface engine never ran on the current design (core deliverable unrealized)
MixedLM still crashes (`LinAlgError: Singular matrix`) after both fixes 7 iterations. Consequences: no converged forest-plot-ready coefficient set, no variance decomposition, no VF ratio, no backtest/diagnostics refresh, no `core_results.json`, `pipeline_log.txt`, `sensitivity_grid.csv`, and the fix-2 bootstrap never executed. No bootstrap artifact exists on disk.

### 2. `cluster_ols_judge.csv` — the fallback the addendum hangs its conclusions on — does not match its own stated design (CRITICAL)
The addendum claims: u_i **orthogonalized against the 7 collapsed industry dummies** (n<10 → "Other"), design rank checked. The artifact shows:
- **~25 industry dummies** including sparse levels that the collapse was supposed to remove (`Astronaut`, `Con artist`, `Politician`, `Racing Driver`, `Conservationist`…);
- a **case-duplicate pair** `ind_Social Media Personality` / `ind_Social media personality` (both SE ≈ 0.081, p ≈ 0.055 — nearly identical columns);
- `athlete` and `ind_Athlete` are **exactly duplicated columns** (coef 0.0244, SE 0.0268 in both rows) — a rank-deficient design, contradicting the "design rank checked" claim.
- Scale impossibility: const = **5.2251** with u_i = 3.883 implies a typical celebrity (u_i ≈ 0, since u_i is centered with sd ≈ 0.73) is predicted a log judge score of **5.2, while the observed log per-judge score is ≈ 2.0–2.3** (judges score ≤ 10). Only predictions work if u_i is ≈ −0.9 for essentially everyone, which contradicts the stated construction of u_i (centered mean-z × √τ²ₐ). The orthogonalization (which cannot change a coefficient by 2.4× from 1.64 to 3.88 without a scale change) is unexplained. **These numbers cannot be traced to a valid fitted model; the "corrected" addendum conclusions (u_i = 3.88, 2.4× the leaked-design value) are verifiably built on a design that doesn't match its own documentation.**

### 3. Stale-artifact contradictions remain unresolved in the summary's own table
The summary's coefficient table quotes `theta_estimates.csv` (fan u_i = **−2.920**, athlete −0.666) — the values of the old sign-inverted construction — while the same directory's `mixedlm_coefficients.csv` (previous converged run) has fan u_i = **+6.529**, Intercept −2.6076. Both are present on disk; the report selects the stale one for its table even while flagging it "expired." The judge-surface numbers in the table (u_i 1.586, pro CI [0.046, 0.302]) differ from `mixedlm_coefficients.csv` (u_i 1.638) — a chimera of two runs again, and the quoted CI for pro_mean_score "0.071" doesn't match either file's value (0.0607 SE 0.0400, p = 0.129 in mixedlm; 0.1929 in theta). The "p = 0.157" correction quoted per fix 3 appears in **no** on-disk artifact.

### 4. Specific numeric claim contradicted by its own artifact: fan-vote SEs
The summary claims relative SEs of "~2–8% for popular celebrities and ~150%+ for early exits." The actual export gives, e.g., Kelly Monaco S1: 48.78M votes, SE 10,450 → **relative SE 0.021%**; Tatum O'Neal (2-week exit): 5.17M, SE 3,842 → **0.074%**. Every file value is orders of magnitude below the claimed 150% band, and the SE model `√votes·(1+|u_i|)` on 50M vote counts yields implausibly tiny uncertainty for "closely guarded secret" data. The rescaling arithmetic in the summary ("√(10)·√(10·v)/√(10) ≈ 3.16×") is internally garbage — the √10 factors cancel.

### 5. A = 0.0057 is **below chance**, and the artifact is stale
Random bottom-2 selection in a pooled week group (~30+ couples across seasons sharing `week_num`) yields expected hit ≈ 2/30 ≈ 6.7%. Observed 0.57% is ~10× **below** the coin-flip baseline — the model is *anti*-predicting eliminations, which needs explanation, not just the honest label "does not reproduce eliminations." Moreover `agreement_ablation.csv` still has only the 3 old metric rows; the current code writes 5 rows (including `n_actual_eliminated`, `n_bottom2_hits`) — so even this "✅ valid" artifact predates the current code, and the hit/denominator counts backing A are unverifiable.

### 6. Hazard and G-estimation numbers remain artifact-unbacked
u_i = −2.583, γ̂ = 0.750, week-scale 0.300, objective −0.532 appear nowhere in any CSV (no `pipeline_log.txt`, no `core_results.json`); they are only restated in the summary and handoff. Round-2's demand for artifact-backed hazard numbers is still unmet.

### 7. `aic_comparison.csv` is stale too
Code writes columns `model,k,aic,basis` ("OLS (entry-info design)"); the CSV has `model,k,aic` only, OLS k = 3, MixedLM AIC cell empty. Neither the current labels nor a populated MixedLM AIC.

## What holds
- Fan-vote engine sign logic, withdrawal censoring, cid-keyed export: correct in code and now reflected in the export file.
- The honest overall status, the explicit expired/stale labeling, and the withdrawal of the previously overclaimed "pros matter for judges" narrative are credible improvements in report discipline.

## Verdict
The pipeline still has no converged response-surface fit for the current design; the one converged fallback artifact contradicts its own documentation and contains a rank-deficient design with impossible prediction scale; the summary's SE claims and stale-artifact descriptions are factually wrong against the files on disk; and the below-chance agreement result is unexplained.

VERIFICATION_RESULT: NEEDS_REVISION

## Issues Found:
1. `cluster_ols_judge.csv` (the addendum's only converged evidence) contradicts its stated design: ~25 industry dummies instead of the claimed 7 collapsed levels (`Astronaut`, `Con artist`, `Politician` etc. present; case-duplicate `Social Media Personality`/`Social media personality`), and `athlete` ≡ `ind_Athlete` as exactly duplicated columns (identical coef 0.0244/SE 0.0268 ⇒ rank-deficient design, "design rank checked" claim false).
2. Scale impossibility in `cluster_ols_judge.csv`: const 5.2251 + 3.8827·u_i predicts log score ≈ 5.2 for a mean celebrity, but observed log per-judge scores are ≈ 2.0–2.3 (scores ≤ 10); u_i=3.88 vs 1.64 in the MixedLM run is unexplained by orthogonalization — the "u_i = 3.88 (2.4×)" headline is not credible.
3. Summary fan-vote SE claims (~2–8% relative SE popular, ~150%+ early exits) are contradicted by `estimated_fan_votes.csv` (0.021%, 0.074%, … ≤ ~0.15% everywhere); the quoted "≈3.16× the naive linear sum" arithmetic is self-cancelling nonsense.
4. Summary wrongly describes `estimated_fan_votes.csv` as 409 stale rows containing 0.5M placeholders; the on-disk file is the refreshed ~422-row export with `NaN`/"withdrew" notes (error is in the report text, in the conservative direction).
5. The coefficient table still quotes the sign-inverted stale `theta_estimates.csv` (fan u_i = −2.920) alongside/instead of `mixedlm_coefficients.csv` (fan u_i = +6.529); judge-surface numbers mix runs (u_i 1.586 vs 1.638 vs 3.88; pro CI doesn't match either file), and the quoted "p = 0.157" correction appears in no artifact.
6. Hazard/G-estimation numbers (u_i = −2.583, γ̂ = 0.75, obj −0.532, n = 2,781) remain backed by no on-disk artifact (`pipeline_log.txt`, `core_results.json` absent).
7. `agreement_ablation.csv` (3 rows) predates the current code (which writes 5 rows incl. hit/denominator counts) — A = 0.0057 has no verifiable n_hit/n_den — and the value is ~10× below the pooled-week coin-flip baseline (~6–7%), i.e., anti-predictive, which is unexplained; agreement should be computed within season.
8. MixedLM still singular: forest plot, variance decomposition, VF ratio, cluster bootstrap (fix 2), backtest/diagnostics, `sensitivity_grid.csv`, `core_results.json`, `pipeline_log.txt` all unregenerated — the plan's core hierarchical deliverables remain missing.

## Fix Instructions:
1. In `model_3.py`, replace the cluster-OLS fallback with a verified design: rebuild `Xt` from `pd.get_dummies(C(industry6_col), drop_first=True)` **after** applying the same n≥10 collapse used in the main pipeline; drop the separate `athlete` column (it duplicates `ind_Athlete`); verify `np.linalg.matrix_rank(X) == X.shape[1]` and assert it; do **not** orthogonalize u_i silently — if u_i is orthogonalized, log the before/after scales and confirm predictions `X @ beta` reproduce observed log scores (mean ≈ 2, max ≤ 2.4); re-export `cluster_ols_judge.csv` and rewrite `addendum_cluster_ols.md` from the new fit.
2. Fix the SE reporting: in the summary, replace the relative-SE paragraph with values computed from `estimated_fan_votes.csv` (e.g., `fan_vote_se/estimated_total_fan_votes` percentiles), and replace the per-week SE model `√v·(1+|u_i|)` in `model_3.py` (line ~224) with a defensible uncertainty model (e.g., bootstrap the γ̂/wscale grid, or inflate the Poisson sqrt by an overdispersion factor from the elimination-mismatch rate), re-export.
3. Correct the `estimated_fan_votes.csv` row/placeholder description in `results_summary.md` to match the refreshed file (≈422 rows, NaN/withdrew), and remove the 0.5M-placeholder sentence.
4. Delete `theta_estimates.csv` (sign-inverted design) or regenerate it as the true bootstrap output; rebuild the summary's coefficient table solely from the converged response-surface artifact, quoting one design only.
5. Regenerate `agreement_ablation.csv` with the 5-row schema and compute agreement **within (season, week)**: group by `(season, week_num)` before ranking; report n_hit, n_den, and the within-week random baseline; investigate why A is below chance (check `ranked <= 2` vs ties pruning, and that `actual` uses the same group keys).
6. Run the pipeline end-to-end to produce `pipeline_log.txt`, `core_results.json`, `sensitivity_grid.csv`, refreshed `aic_comparison.csv`/`backtest_results.csv`/`residual_diagnostics.csv` and figures 1–5; if MixedLM remains singular, keep the fixed cluster-OLS as primary but annotate every CSV and the summary with the engine used so no expired/stale artifact is quoted anywhere.
7. Reproduce the hazard and G-estimation numbers into an artifact (append the hazard coefficient table and γ̂/wscale grid to `pipeline_log.txt` or a `hazard_fit.csv`) so every number in the summary is file-backed.