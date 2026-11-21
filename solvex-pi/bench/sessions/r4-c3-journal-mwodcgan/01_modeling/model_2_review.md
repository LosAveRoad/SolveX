I've completed my review. Based on my verification of the workspace (read-only), here is my review of Model 2:

---

# Model 2 Review — Counterfactual Season Re-Play (CSR)

## Verification of the Programmer's Claims

**1. Output artifacts — confirmed missing.** `02_programming/model_2/outputs/` and `02_programming/model_2/figures/` are both empty (0 files). The only Model-2 artifact on disk is `outputs_fanvote_samples.csv`, which is a Model-1 module byproduct, not a Model-2 result. The "FAILURE" status is honest and correctly reported. No Model-2 numbers exist to sanity-check, so criteria 1 (numerical sanity) is vacuously unfulfillable.

**2. The reported root cause is inconsistent with the code on disk.** The report claims the crash was `KeyError: 'Jgap'` because the key "was never attached" to `wk_pairs` records. However, the current `run_model2.py` lines 186–187 **do** attach `Jgap=float(D)` to every pair record. Either the file was edited after the crash without re-running, or the diagnosis was wrong. Either way, the report's stated validation of the code does not match the code state, which undermines confidence.

**3. A second, blocking bug exists that the report did not find.** In `replay_season()` (lines ~133–144), `C = combined_vec(...)` is defined only inside the `if len(mates) <= 3` branch, but line 142 (`sorted(elim, key=lambda i: -C[i])`) references `C` in the main elimination path, where it is undefined. This is a guaranteed `NameError` on the very first replayed week of the very first season. **The fix instruction in the report ("attach Jgap … and re-run") is insufficient — the code will crash again immediately after the Jgap fix.** This strongly suggests the replay path was never executed even once before delivery.

**4. Supporting modules are real and coherent.** `dwts_common.py` correctly parses season/results/weekly judge columns, excludes 10 "Withdrew" rows (verified against the CSV — 10 rows match), handles 0.0 sentinel weeks, and the historical-rule mapping (s1–2 & s28+: RANK+SAVE; s3–27: PCT) matches the plan and the problem statement. `fanvote_model1.py` implements the feasible-set rejection sampler as documented. The input-verification claims in the report (34 seasons parsed, controversy celebrities present — e.g., Bobby Bones row 320 confirmed) are consistent with the raw CSV.

**5. Minor code-quality issues that would contaminate results if run as-is:**
- The κ log-likelihood expression (line ~195) is a dead-code construct (`expit(k*D)*0 + ... if False else ...`) — it computes the right thing by accident but is not the documented formulation and should be written cleanly.
- After the fix, `let place` for double-elimination weeks (`s9/s18/s21`) relies on the undefined `C` (issue 3 above); the plan's requirement to eliminate "exactly the recorded number of bottom couples" needs an explicit test.
- `zip(wins, base_win)` in the α-sweep compares each α against α=1.0 — this is the intended "agreement with judge-only baseline," fine, but `base_win` is only populated when α=1.0 is iterated last (it is), so OK.

## Criteria Assessment

1. **Numerical sanity:** N/A — no numbers produced.
2. **Model correctness:** Formulation in code matches the plan's RANK/PCT/save rules and the progressive week-by-week replay design; however the replay path has a blocking bug (issue 3) so correctness is unproven, not merely unvalidated.
3. **Completeness:** FAIL — 0 of the required Model-2 outputs exist (no season replay table, no celebrity flip probabilities, no fan-favor index, no κ estimate, no figures, no α-sensitivity sweep, no key-results JSON).
4. **Known issues:** The programmer honestly flagged the failure and the Model-1 identifiability limits (good), but misdiagnosed the root cause and missed the second fatal bug — so even their "Fix instruction" would not produce a working run.

## Conclusion

The report is transparent about failure, and the input-parsing layer is solid, but **Model 2 produced zero deliverables and the provided fix is incomplete**. This cannot be accepted as a completed model. It needs re-implementation of the crash fixes and a successful end-to-end run before any quantitative claim can be reviewed.

VERIFICATION_RESULT: NEEDS_REVISION

## Issues Found:
1. No Model-2 outputs exist: `outputs/` (0 CSV/JSON) and `figures/` (0 PNG) are empty; κ was never estimated; winner-flip probabilities, top-3 flip rates, fan-favor index, and all four controversy-celebrity counterfactuals are missing.
2. The reported root cause (KeyError `'Jgap'` due to missing key) contradicts the code on disk — `run_model2.py` lines 186–187 do attach `Jgap`; the diagnosis is stale or wrong.
3. Blocking second bug the report missed: `run_model2.py` line 142 (`sorted(elim, key=lambda i: -C[i])`) references `C`, which is only defined inside the `if len(mates) <= 3` branch of `replay_season()` — guaranteed `NameError` on the first replayed week. The programmer's fix instruction would not produce a working run.
4. The κ log-likelihood (line ~195) is an obfuscated dead-code expression rather than the documented `Σ log(1 − σ(κD))` formulation; not wrong in effect but unverifiable as written.

## Fix Instructions:
1. In `run_model2.py`, `replay_season()`: move `C = combined_vec(mates, fans, rule, alpha)` **before** the `if len(mates) <= 3` block so it is in scope at line 142.
2. Clean up the κ likelihood to explicitly compute `ll = np.sum(np.log(1 - expit(k * D)))` per grid point (remove the `* 0 + ... if False else` construct).
3. Confirm the `replay_week(..., return_bottom2=True)` path correctly handles double-elimination weeks (s9/s18/s21) where the actual eliminated set has 2 members — currently only `matches[0]` is checked in the κ-fitting loop.
4. Re-run `python3 run_model2.py`; verify `outputs/` contains all seven expected files (`season_replay_summary.csv`, `celebrity_flip_probabilities.csv`, `fan_favor_index.csv`, `model1_fanvote_estimates.csv`, `judges_save_bottom2_pairs.csv`, `judges_save_fit.csv`, `model2_key_results.json`, plus `alpha_sensitivity.csv`) and 5 figures.
5. Update `results_summary.md` with the actual numbers (κ, winner-flip probabilities, controversy-celebrity medians, `pct_exact`) once the run succeeds.