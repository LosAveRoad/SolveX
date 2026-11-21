I have completed my verification. The evidence is conclusive; here is the review (SolveX saves this verbatim to `01_modeling/model_3_review.md`).

---

# Review — Model 3 (round 2): Hierarchical Judge–Fan Effect Decomposition

## What I checked
Read `model_3.py` (646 lines, full), all artifact CSVs, `handoff.json`, `results_summary.md`, and compared them against the round‑1 review (`model_3_review_r1.md`), which flagged 10 issues.

## What improved since round 1 (genuine fixes)
- Fan-vote sign: code now uses survival odds `(1/to_odds)^γ` with an inverted G-estimation objective — fix 2 implemented in code.
- Risk-set count: `n_risk = int(at_risk_mask.sum())` — fix 3 implemented.
- u_i / pro_mean_score mapped train-only for the held-out back-test — fix 4 implemented.
- Weekly-share logit for the fan surface (no 10M ceiling) — fix 5 implemented.
- `elimination_agreement()` now compares predicted bottom-2 to actual eliminations — fix 1 implemented.
- Interaction `u_i:pro_mean_score` and industry dummies added — fix 8 implemented.

## Why the report still cannot be accepted

### 1. The headline coefficient table comes from stale artifacts the current code never writes (CRITICAL)
The report's fan-surface table (Intercept 5.350, u_i **−2.920**, athlete −0.666, age +0.109, pro −0.209) is quoted from `theta_estimates.csv`. But **grep finds no code in `model_3.py` that writes `theta_estimates.csv`, `asymmetry_judge_fan.csv`, or `delta_pro_bootstrap_ci.csv`** — exactly the three files carrying the report's most important numbers. Worse, the fan-surface signs in `theta_estimates.csv` (u_i = −2.920, i.e. "fans punish quality") are precisely the behavior of the **old, sign-inverted construction** that round-1 issue 3 documented. The current code (survival odds, weekly share) produces `mixedlm_coefficients.csv`, whose fan surface reads **u_i = +6.384, Intercept = −2.289** — the opposite sign. The report's central "sign inversion / fans punish technical merit" narrative is therefore an artifact of a superseded run, not a result of the current model.

Even the **judge-surface** numbers do not match the current artifact: the report claims pro_mean_score = +0.193 (p = 0.016); `mixedlm_coefficients.csv` (judge_score rows) gives +0.0704 (p = 0.157, NOT significant), and u_i = +1.636 vs the report's +1.586. Only the interaction (−0.169, p = 0.038) agrees. The report quotes a chimera of two different runs, and where they disagree it consistently quotes the (stale, more favorable) one.

### 2. Supporting artifacts are also stale — label mismatches prove it
- Code writes model name `"OLS (entry-info design)"`; `aic_comparison.csv` contains `"OLS (celebrity covariates)"`.
- Code writes `backtest` with a `split` column; `backtest_results.csv` has **no split column** (and no row matches "test").
So even `aic_comparison.csv` and `backtest_results.csv` were not produced by the current `model_3.py`. The "REML-based AIC within the same fixed-effect set is tabled in aic_comparison.csv" claim is false — the MixedLM AIC cell is empty.

### 3. The current script crashes; it demonstrably never ran to completion (CRITICAL)
Line 373: `r2_mix = ... / ss_tot` — **`ss_tot` is never defined** (grep confirms only that single use). NameError ⇒ the run dies before writing `backtest_results.csv`, `aic_comparison.csv`, figures 2–5, `sensitivity_grid.csv`, `core_results.json`, `pipeline_log.txt`. This also explains why the programmer's limitation 5 says `core_results.json`/`pipeline_log.txt` are missing: they cannot be produced by this code.

### 4. Claimed cluster bootstrap does not exist
Status says "cluster bootstrap CIs (1,000 resamples)" and `theta_estimates.csv` claims "bootstrapped 95% CI", but **the current `model_3.py` contains no bootstrap code at all** (grep: no match for bootstrap/resample). The plan's core uncertainty machinery (plan step 3) is absent.

### 5. The "bottom-3 fan votes" are withdrawal artifacts, not estimates (CRITICAL-adjacent)
The three bottom entries — Sara Evans (S3), Misty May-Treanor (S7), Tom DeLay (S9) — are all **celebrities who withdrew**. In the code, withdrawn couples have no score rows, so their cid never appears in `fan_tot`, and the `fillna(V0*0.05…)` fallback assigns the 0.5M placeholder. The report's claim that these are "floor/censored at the volume prior … unidentifiable vote totals" mislabels a withdrawal placeholder as an estimated unpopular contestant. They have no fan-vote estimate at all.

### 6. The fan-vote export silently drops 13 contestant-seasons
`estimated_fan_votes.csv` uses `drop_duplicates(subset=["celebrity_name"])` — with 13 two-season celebrities this keeps only the first season, so the deliverable contains 408 rows while the panel defines 421 cid's. The report describes it as "n = 408 contestant-seasons" while also claiming 421 contestant-seasons of estimates elsewhere; 13 second-season estimates are silently missing (and the file has a duplicated `season` column).

### 7. The A-interpretation is spun the wrong way
`agreement_ablation.csv`: A = 0.0057 with and without prior, Δ = 0. The report calls this "correct behavior for a latent variable." It is not: 0.0057 means the predicted bottom-2 contained the actually-eliminated couple in ~0.6% of eliminations — **the fan-vote estimates fail the problem's central consistency question**. Additionally the "prior" is implemented as `hazard_prob * exp(+γ·u_i)`, which *increases* the elimination score for higher-quality celebrities — a sign contradiction with "fan appeal helps survival"; with Δ_A = 0 the planned Model-1 loop ablation gain is null and must be reported as a failure of the loop, not neutralized by rhetoric.

### 8. Implausible uncertainties
`fan_vote_se = sqrt(votes)·(1+|u_i|)` per week, and the **total** SE is the *sum* of weekly SEs (not √ΣSE²), which overstates correlation-effected error; yet the resulting bands (SE ≈ 60,769 on 112.46M votes, relative SE ≈ 0.05%) are absurdly precise for latent "secret" data. The certainty section is not credible.

### 9. Singular fan design not actually fixed
Limitation 10 claims athlete_flag "was dropped from the final fan surface"; the code still includes both `athlete_flag` and `C(industry6)`, and `mixedlm_coefficients.csv` shows the singular result (Athlete dummy coefficient 1.7×10¹⁶, athlete_flag = −1.7×10¹⁶, several coefficients with **empty SE/p/CI**). A fit with 10¹⁶-scale coefficients and missing standard errors must not be presented through a hand-curated table.

### 10. Unverifiable hazard numbers and missing artifacts
Hazard betas (u_i = −2.535, p < 1e-4; pro = −0.007; interaction p = 0.81), the G-estimation grid (γ̂ = 0.900, wscale 0.300, obj −0.5416), and n = 3,352 are backed by **no on-disk artifact** (`pipeline_log.txt`, the only place they'd appear, is missing; no hazard CSV exists). `handoff.json` actually **exists** (contradicting the report's table, which lists it as MISSING) and is narrative, not evidence. Text defect: garbled string "is龙岗" in the summary.

## What holds
- Data handling improvements (withdrawal censoring, dedupe assert, cid per season) are real, in code.
- Judge surface from the current code is plausible (u_i dominant positive, interaction −0.169 significant), and the honest downgrade of back-test R² to 0.083 is commendable — but even that file is stale (no `split` column), so strictly it is unverified too.

## Verdict
The four most load-bearing claims of the report — the fan-channel signs (u_i = −2.920, athlete −0.666), the pro-mean-score significance (p = 0.016), the bootstrap CIs, and the "bottom-3 estimates" — are contradicted by, unbacked by, or absent from the current code and artifacts. The current script itself crashes. This is a rewritten summary over a partially stale artifact set.

VERIFICATION_RESULT: NEEDS_REVISION

## Issues Found:
1. `theta_estimates.csv`, `asymmetry_judge_fan.csv`, `delta_pro_bootstrap_ci.csv` are not written by the current `model_3.py`; their fan-surface values (u_i = −2.920, Intercept 5.350, athlete −0.666) match the old sign-inverted construction and contradict the current artifact `mixedlm_coefficients.csv` (fan u_i = +6.384, Intercept −2.289). The report's central "fans punish quality" conclusion is unsupported.
2. Judge-surface discrepancy: report says pro_mean_score = +0.193 (p = 0.016); current-artifact value is +0.0704 (p = 0.157, ns). u_i 1.586 vs 1.636. The report mixes two runs.
3. `r2_mix` uses undefined `ss_tot` (line 373) — the script crashes before writing `backtest_results.csv`/`aic_comparison.csv`; the current code never completed a run.
4. `aic_comparison.csv`/`backtest_results.csv` are stale: label `"OLS (celebrity covariates)"` vs code's `"OLS (entry-info design)"`; no `split` column in backtest_results.csv despite code writing it; MixedLM AIC cell empty.
5. No cluster-bootstrap code exists despite the report's "1,000 resamples" claim and `theta_estimates.csv` "bootstrapped CI" column.
6. "Bottom-3 fan-vote estimates" (Sara Evans, Misty May-Treanor, Tom DeLay) are withdrawal placeholders from `fillna`, not estimated unpopular contestants.
7. `estimated_fan_votes.csv` drops the 13 second contestant-seasons via `drop_duplicates(subset=["celebrity_name"])`; duplicated `season` column.
8. A = 0.0057 (0.6% bottom-2 hits) means the estimates do **not** reproduce eliminations — the report's "correct behavior" spin is unacceptable; the exp(+γ·u_i) prior sign is also contradictory.
9. Total fan-vote SE = linear sum of weekly SEs and relative SE ≈ 0.05% — implausible uncertainty for latent data.
10. Fan surface still singular (athlete/industry collinearity: coefficients 10¹⁶, empty SEs) contrary to limitation 10's "dropped" claim; hazard betas and γ̂ grid unbacked by any artifact; `pipeline_log.txt`/`core_results.json`/`sensitivity_grid.csv` missing; garbled "is龙岗" text.

## Fix Instructions:
1. In `model_3.py`, define `ss_tot = float(((test_df["log_judge_score"] - test_df["log_judge_score"].mean())**2).sum())` immediately after the `r2_backtest` computation (before line 373), then run the pipeline end-to-end so every CSV, `pipeline_log.txt`, `core_results.json`, and `sensitivity_grid.csv` is regenerated from the current code.
2. Delete or regenerate `theta_estimates.csv`, `asymmetry_judge_fan.csv`, `delta_pro_bootstrap_ci.csv` from the current run; either add a bootstrap celebrity-resampling block (resample ~301 train cids with replacement, refit both MixedLM surfaces, percentile CIs) or remove all bootstrap/asymmetry claims from the summary.
3. Replace the fan-channel table and "fans punish/quality sign-inversion" narrative in `results_summary.md` with values read from the regenerated `mixedlm_coefficients.csv`; fix the pro_mean_score judge-surface number (+0.0704, p = 0.157, not significant) and u_i (+1.636).
4. In the estimated-fan-votes export (line ~229): group by `cid` and drop duplicates on `cid` (not `celebrity_name`) so all 421 contestant-seasons export; rename the duplicate `season` column; for withdrew celebrities emit `estimated_total = NaN, note = "withdrew"` instead of the 0.5M fillna placeholder, and remove the "bottom-3 estimates" paragraph.
5. Change total SE to `np.sqrt((fan_vote_se**2).sum())` per cid and justify (or widen) the per-week SE model; state relative SEs explicitly.
6. Rewrite the A paragraph: state plainly that bottom-2 hits ≈ 0.6% ⇒ estimates do not yet reproduce eliminations; re-examine the prior as `hazard_prob * exp(−γ·u_i_fanAppeal)` and re-report Δ_A.
7. Resolve the fan-surface singularity: in both `FORMULAS["fan_vote"]` and the hazard design, remove `athlete_flag` (it is collinear with `C(industry6)[T.Athlete]`) or collapse industries with n<10 into "Other" **before** fitting (the stated intent of fix 2), and verify no coefficient has SE > 100.
8. Proofread the summary (remove "is龙岗" and any stale mixed-run numbers); quote only numbers present in on-disk artifacts.