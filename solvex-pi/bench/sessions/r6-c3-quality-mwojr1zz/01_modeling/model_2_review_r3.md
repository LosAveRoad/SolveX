I've completed my verification. All checks and recomputations were run under `.solvex/scratch/m2r3/` (no implementation changes). Here is my complete review — SolveX will save it to the review path verbatim.

---

# Model 2 cross-review (round 3) — Judge–Fan Behavioral Attribution

## What I re-verified independently (scratch copy of the full pipeline, no implementation changes)

1. **Determinism & reproducibility**: re-ran `python3 run.py` end-to-end (~57 s) on a scratch copy → `results.json` and **all 7 CSVs byte-identical (md5 match)** with the shipped workspace outputs. The determinism claim holds.
2. **Round-1 issues (all 5) verified genuinely fixed in code and output**: swap exhibit uses exact `expit` (verified independently: Koko Iwasaki logit −4.672 → 0.0093); era drift is Spearman (0.972/0.969/0.971 recomputed ≈ match); `_center_contrast` is a true row-weighted contrast (Alan Bersten = −0.1088 ≈ −center, exact); permuted pro/industry blocks rebuilt with identical drop-first coding/column order (code + module docstring); summary restages eligible top-5, "#15 of 41 eligible", and the exit-recovery stages.
3. **Round-2 issues (all 3) fixed**: fan-share bands now 0 inverted rows and 2,777/2,777 point-in-band (recomputed); Derek Hough CI in the summary **[0.447, 0.942]** matches `results.json`; swap exhibit says **~15.6 pp** (0.1656−0.0093 = 15.63) and ~2.2 judge-z (2.177) — both arithmetically correct.
4. **Headline numbers reproduce exactly**: MAP nll 436.58, β = 1.387, θ = −0.0001; exit recovery MAP 97/235 vs judge-only 88/235, post-mean bottom-3 184/235 vs 179/235, single-exit 81/206 vs 82/206, multi-exit 7/29 (all match `model2_exitfit.csv`, which I rebuilt from raw `contestants.csv` keys: 265 raw exit cells − 30 withdrawal-context weeks = 235 ✓); R² judge 0.3358 / fan 0.3924; **all 8 partial-R² blocks match `model2_decomp.csv` to 6 decimals** (I recomputed them with an independent `lstsq` solver — an apparent mismatch in my first pass was my own row-alignment bug); design = 116 params = 1+33+51+24+3+3+1 ✓; constraints = 235 E + 32 F = 267 ✓; pro rankings (Derek #1, Artem #2, Valentin #3, Corky #4, Mark #5, Cheryl #15 of 41 eligible), ρ = 0.989, restricted pro R² (0.128→0.087 / 0.120→0.078, fame control 0.206/0.209), era drift, CV/certainty stats, sign-discipline numbers, age/week curves, and the full swap exhibit (+0.672/16.6%, −0.081/6.4%, −1.505/0.9%) all verified exactly.
5. **Weekly normalization**: Σφ = 1 to 2e-9 in 335/335 season-weeks; share range [0.00086, 0.8473] matches results.json.

## The one substantive remaining issue: the fan surface is not fed by Model 1's posterior

The plan states Model 2 "consumes Model 1's posterior fan shares (ρ = E[φ])" and step 1 is "merge `week_scores.csv` with `model1_fanshare.csv`". The implementation instead built an in-house "Model-1-lite" stage, justified (in the summary and `m2_fanshare.py` docstring) by *"Model 1 ran in parallel"*. That justification no longer holds: **Model 1 is now delivered and verified SATISFIED** (`02_programming/model_1/model1_fanshare.csv`, 2,777 rows with `phi_share`).

I ran Model 2's response-surface stage unchanged, with only the fan shares swapped to Model 1's delivered posterior (same design, same code path). The fan-side results move materially — two headline claims change:

| Quantity | M2-lite φ (shipped) | Model 1 φ (recomputed by me) |
|---|---|---|
| R² fan surface | 0.392 | **0.477** |
| fan pro R² (partial) | 0.117 | 0.137 |
| fan age R² (partial) | 0.122 | 0.094 |
| fan week R² (partial) | 0.048 | **0.164** |
| **ρ(pro effect judge vs fan, eligible)** | **0.989** | **0.623** |
| fan-surface top-5 | Derek, Artem, Valentin, (Chaplin, Holker) | Derek, Daniella Karagach, Kym Johnson, Jenna Johnson, Valentin |
| exit recovery (same ½ judge + ½ φ protocol) | bottom-m 97/235; single-exit exact 81/206; bottom-3 184/235 | **198/235; 170/206 (82.5% vs 39.8% judge-only); 232/235** |

The exact comparison `corr(φ_M2, φ_M1) = 0.615` confirms the two φ surfaces differ substantially, so this is a genuine sensitivity, not rounding. Consequences:

- **F10's caption quantity (ρ = 0.989) and the "pros who lift judges lift fans" claim are artifacts of the weaker in-house φ.** With Model 1's posterior the association is 0.623 — still clearly positive, but the 0.99 figure overstates coupling and will disagree with any paper-phase number that uses Model 1's φ.
- The exit-consistency story in the summary ("not magic vote recovery… single-exit is a statistical tie with judge-only") materially **understates** what this pipeline can deliver: under Model 1's φ, single-exit exact recovery is 170/206 (82.5%) versus 39.8% judge-only — a dramatic win, not a tie.
- The judge surface — Model 2's core novel contribution (decomposition of judge scores, pro rankings validation, age/week judge curves) — is **entirely unaffected** (all judge-side numbers reproduce and stay the same).

The correctness of what shipped is not in question (everything reproduces exactly); the issue is conformance to the plan's data flow and the stability of the headline fan-side numbers that the paper phase will cite.

## Minor notes (documentation-level, fix in the same pass)

- The plan promised a **hierarchical Bayesian** fit (PyMC NUTS, R-hat/ESS gates, pro × industry interaction term θ). The delivered model is OLS with run-cluster SEs, no interaction block, and the u_c random intercept reduced to a residual-ICC diagnostic (0.450/0.434). These are defensible simplifications (fewer pros than the plan's 54; deterministic; stable), but the summary never explicitly discloses them as deviations from the plan's formulation — one sentence is needed so the paper doesn't claim MCMC diagnostics that don't exist.
- Plan sign-discipline expected f̂(age) ≥ 0 on [15, 45] on the judge surface; the fit gives −0.27 at age 20 (younger than 36 = lower). "Monotone decline, no crossing" is reported, but the plan's "flag & explain" clause was applied only to the week slope — add the same treatment for age (older celebrities retain judge favorability; the F7 curves show this cleanly).

## Completeness & honesty

All specified files and figures are present and correct (`results.json`, 7 CSVs — row counts verified: 2,777 / 12 / 52 / 25 / 94+1 / 235 / 3 — and F6–F10 at dpi 300). Known-elite validation passes. Limitation 1–7 are candid and accurate (LOSO judge target miss, identification ceiling, endogeneity bound, anonymous judges). The honesty discipline (ties stated as ties, targets missed reported as missed) is exemplary.

## Verdict

One focused revision: plumb Model 1's now-available delivered posterior as the primary fan-share input to the surfaces/consistency/era-drift/restricted/swap stages (keeping the in-house stage as a documented sensitivity), regenerate, and restate only the fan-side numbers. Judge-side results need no change.

VERIFICATION_RESULT: NEEDS_REVISION
## Issues Found:
1. **`run.py` step 2 / `yF` construction (fan surface input)** — the pipeline uses its own "Model-1-lite" φ (`m2_fanshare.py`) instead of Model 1's delivered posterior `../../../02_programming/model_1/model1_fanshare.csv` (`phi_share`), as the Master Plan requires. The substitution was justified by parallel execution, but Model 1 is now delivered and verified. I recomputed Model 2's surface stage with Model 1's φ (same design/code path) and the fan-side results move materially: R² fan 0.392 → **0.477**; fan partial R² pro/industry/age/week 0.117/0.054/0.122/0.048 → **0.137/0.056/0.094/0.164**; eligible pro-effect correlation ρ(judge, fan) 0.989 → **0.623** (the F10 caption's "ρ = 0.989 — pros who lift judges lift fans" is an artifact of the weaker φ); fan-surface top-5 becomes Derek Hough, Daniella Karagach, Kym Johnson, Jenna Johnson, Valentin Chmerkovskiy; exit recovery under the pipeline's own ½·judge + ½·φ protocol becomes bottom-m **198/235**, single-exit exact **170/206 (82.5%) vs judge-only 39.8%**, bottom-3 **232/235** (the shipped 97/235, 81/206 "statistical tie", 184/235 substantially understate the achievable result). corr(φ_M2lite, φ_M1) = 0.615 confirms the two φ surfaces genuinely differ. Judge-surface numbers (all pro judge rankings, judge decomposition, age/week judge curves, restricted judge R², judge R² = 0.3358) are unaffected and reproduce exactly.
2. **`results_summary.md` (Status/Regression-disclosure)** — the summary does not disclose as plan deviations: (a) the plan's hierarchical Bayesian design (PyMC NUTS with R-hat/ESS gates) was replaced by OLS with run-cluster SEs (R-hat/ESS validation gates are therefore vacuous as written); (b) the plan's pro × industry interaction block θ was dropped from the design; (c) u_c was reduced to a residual-ICC diagnostic (0.450/0.434). These simplifications are defensible but must be stated so the paper phase doesn't claim nonexistent MCMC diagnostics.
3. **`results_summary.md` (sign discipline)** — the plan's validation clause "f̂(age) on the judge surface should be non-negative on [15,45]" is violated (−0.27 at age 20, −0.19 at 14 on the judge curve) and is not flagged/explained the way the week-slope violation is ("flagged and explained" per the plan).

## Fix Instructions:
1. In `run.py` (step 2, after `pan, fstats = MF.compute_fanshare(...)`), add a canonical-input override with graceful fallback: read `../model_1/model1_fanshare.csv`, merge `phi_share` on (season, week, celebrity_name), and set the effective fan share `pan["fanshare"] = phi_share` as the **primary** input for the surfaces (`yF`), exit-consistency counts (`model2_exitfit.csv`, MAP/post-mean blocks), era drift, CV/certainty stats, restricted pro R², and the swap exhibit; keep the in-house stage as a sensitivity column (e.g. `fanshare_lite`) and record both in `results.json` (e.g. `R2_fan_lite`, `rho_lite`) so the determinism/self-contained property is preserved via fallback if the Model 1 file is absent. Rerun `python3 run.py`. Expected new values (from my recomputation — targets within ±1 in lowest digit are acceptable): R² fan ≈ 0.477; fan partial R² pro ≈ 0.137, industry ≈ 0.056, age ≈ 0.094, week ≈ 0.164 (with permutation p-values re-run); ρ(judge, fan | eligible) ≈ 0.623; consistency blocks ≈ [198, 235] bottom-m, [170, 206] single-exit exact, [232, 235] bottom-3 (recompute exactly); fan top-5 = Derek Hough, Daniella Karagach, Kym Johnson, Jenna Johnson, Valentin Chmerkovskiy; era-drift columns, CV stats, restricted pro R², and the swap fan-share column will all move — update them from the regenerated `results.json`. Judge-side outputs (R² judge, judge decomposition, judge pro rankings/CIs, judge curves) must come out byte-equivalent; verify this explicitly.
2. In `results_summary.md`: (a) replace the "Model-1-lite … because Model 1 ran in parallel" framing with consumption of Model 1's delivered posterior (cite the merged file), restaging the exit-recovery bullet around the much stronger result (single-exit exact 82.5% vs 39.8% judge-only) while keeping the judge-only baseline comparison; (b) add a "Deviations from the plan" note listing OLS-with-cluster-SEs in place of the PyMC hierarchical spec (hence no R-hat/ESS gates), the dropped pro × industry interaction, and u_c as residual ICC — one sentence each with justification; (c) update the F10 caption to the new ρ (≈0.62) and re-word the "pros who lift judges lift fans" claim to the moderated form (positive but far from collinear).
3. In `results_summary.md` (sign discipline): add a one-line flag for the age-curve sign-discipline deviation on the judge surface (f̂(20) ≈ −0.27 < 0 over [15,45]) with the explanation that judge favorability peaks in mid-age and declines monotonically toward older celebrities, mirroring the F7 crossing narrative already used for the week slope.