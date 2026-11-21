# Review — Model 2 (revision 2): Judge–Fan Fusion Engine

## What I verified (recomputation, not just file reading)

I re-ran the full pipeline (`python3 run.py`, ~26 s) and recomputed the headline numbers from the actual output files in `02_programming/model_2/`.

**Reproduced exactly:**
- **Determinism**: `results.json` MD5 identical (7b74e98ae0ba73a63144f8446a1b1bf3) before and after a full rerun; no wall-clock field. ✔
- **Validation**: mean per-season cut-match 0.8887; event-weighted ledger 265/299 = 88.6% (Σk = 299 vs 298 eliminated contestants; the +1 is genuinely the S18 Diana Nyad patch — I confirmed in `build_season_context` that Nyad is carried into week 2 with k=2 for {Nyad, Sean Avery} and Billy Dee Williams does not consume a slot); Jaccard 0.8811, placement MAE 0.5626, τ 0.9025. Era rates: S1–2 rank 1.000, S3–27 pct 0.9916 (event-weighted 222/224 = 0.9911), S28+ rank+dance-off 0.4896. All match `replay_validation_by_season.csv` and results.json. ✔
- **Rule divergence γ_s**: mean 0.468, median 0.444, zero-disagreement seasons S1/S25/S26 (I verified cell-by-cell in `rule_replay.csv` that in those seasons no elimination week with k>0 shows R≠P), max S9 = 0.889, S8/S11/S13 = 0.778, S7/S12 = 0.750; pooled 129/265 = 48.7%; disagreement counts in `rule_replay.csv` match `rule_disagreement_by_season.csv` for all 34 seasons. ✔
- **φ̂**: 2,780 rows; sums to 1 in all 335 season-weeks (max dev 4e-16); mean 0.1205; median relative 90% width 0.1579; absolute p10/p90 = 0.0049/0.0346; lo ≤ φ̂ ≤ hi and lo ≤ hi in every row; corr(φ̂, rel width) = −0.8 (bands genuinely wider for low-φ̂ couples); u_i extremes (Marie Osmond +2.5, Mya +1.75, …, Shannen Doherty/Redfoo −2.0, Bobby Bones +0.625; 421 rows). ✔
- **Controversies**: all 8 rows of `controversy_table.csv` match my re-simulation from the stored u_fan_appeal with θ=(1.5,0,0.05), including the S11 P-rule winner being Kyle Massey with Bristol Palin 2nd. ✔
- **Flip curves**: every number quoted in the summary matches `controversy_flip_curves.csv` (56 rows = 8 pairs × 7 multipliers): Bristol ×2→R4/P2, ×4→R2/P1 with R never winning; Bobby ×2→R4/P2, ×4→R2/P1, R stuck at 2nd through ×16; Mya ×2→P1; Jerry ×2→R2/P1; Billy Ray ×2→R5/P3(→P1 at ×4), R 3rd at ×4; Sabrina S15 ×2→R2/P4; Sabrina S5 R 7→…→3 (×8) →1 (×16), P 1st at ×4. ✔
- **S28+ decomposition**: 58/65 plain rank, 34/65 plain percentage, 33/65 rank+dance-off, 31/65 pct+dance-off — matches `s28plus_rule_overlay.csv` and the fresh rerun; dance-off overlay 2/5/4/3/5/3/5 changed weeks, 5–11 placement shifts. ✔
- **HDI-bound sensitivity is now delivered** (`hdi_bound_sensitivity.csv` + F12): 7/8 placements constant at lo/point/hi. The plan-required experiment exists and its scope limits (focal celebrity only) are honestly flagged. ✔
- **Deliverables**: 12 CSVs, 10 figures (300 dpi), results.json, handoff.json, results_summary.md; shared_data copies `model2_fanvote_estimates.csv` / `model2_rule_replay.csv` / `model2_controversy_table.csv` exist and are byte-identical to the model outputs (recreated by the rerun and equality-checked). ✔
- **Engine matches the plan's formulation**: TH^R=(r_judge+r_fan)/2 (worst = max), TH^P=(ρ̂+φ̂)/2 (worst = min), Z variant, S28+ bottom-(k+1) + lowest season-to-date mean judge score dance-off proxy, fixed elimination calendar, deterministic tie-breaking; softmax φ̂ with u_i + α·log ρ + β·log cJ; documented patches (Diana Nyad, finale-cut finalists, withdrawals). Deviations from the plan (φ̂ inversion done in-model because no Model 1 output existed; flip multipliers applied from week 1 rather than from the controversy week) are documented and justified. ✔
- **Limitations honestly flagged**: in-sample calibration (421 free u_i against the same 2,780 couple-weeks/299 cut events; 88.9% is an in-sample fit, no LOSO), (α,β) ridge (Δlog-lik 0.6), S28+ driven by the unobserved dance-off stage, HDI scope, fixed quotas. ✔

All of the revision-1 issues (fabricated 266/298 count, 105/240 pooled disagreement, the false "percentage on S28+ reproduces 99%" claim, Bristol "would have WON" overclaim, missing HDI experiment, missing shared copies, in-sample flag, F5 overlap) are fixed and the corrected numbers now match my recomputation.

## Issues Found

1. **Bobby Bones HDI sentence misquotes the model's own output.** `results_summary.md` (HDI paragraph, mirrored in the Sanity Checks bullet) states "**Bobby Bones P base = 3rd, P_lo (φ̂ at its lower 90% edge) = 2nd**". The actual output — `hdi_bound_sensitivity.csv`, results.json, and a fresh run.py rerun — gives **P_base = 3, P_lo = 4, P_hi = 3**. The lower band edge *worsens* his P projection from 3rd to 4th; it does not move him up to 2nd. The "fragile" verdict survives, but the quoted number and its implied direction are wrong (and inconsistent with the same paragraph's claim that the fragile case is the only shift).

2. **The judge-consistency interpretation of the recommendation metrics is inverted.** In `rule_metrics_by_season.csv` / results.json, τ is Kendall τ between final placement (1 = best) and mean weekly judge percentile (1 = best), so a judge-consistent rule approaches **τ ≈ −1**. I verified the convention empirically: the S1 rank replay (the honest-era rule, judge-favored finale) yields τ = −0.6 exactly as stored. Therefore **Z (−0.799) is the most judge-consistent, R (−0.756) next, and P (−0.618) is the LEAST judge-consistent / most fan-weighted rule** — which is consistent with everything else in the report (Bristol/Mya/Bobby/Jerry/Billy Ray all do better under P; P has by far the lowest top-3-φ̂ shock rate). Yet the summary's closing sentence reads: "**the percentage rule maximizes judge-consistency (|τ| smallest)**". That states the opposite of what the numbers show: P has the smallest |τ|, i.e., final placements are least coupled to judge quality (fan voice counts most under P). If this sentence propagates to the paper's recommendation memo, the headline rationale for recommending P would be wrong.

3. **Minor numeric/cosmetic nits** (do not change any verdict):
   - "band edges move φ̂ by only ±16% relative": the median *full* 90% width is 15.8%, so one band edge moves φ̂ by ≈ ±8% relative (focal celebrities' full widths 14.6–16.8%);
   - "event-weighted equivalents are 100% and 99.2%": the S3–27 event-weighted rate is 222/224 = **99.1%** (99.2% is the mean-of-per-season-rates figure);
   - Figure F5: the bottom-left legend still overlaps the "obs 8" label of the Sabrina Bryan (S15) row.

## Fix Instructions

1. In `02_programming/model_2/results_summary.md`, HDI paragraph (and the matching Sanity Checks bullet): replace "P_lo = **2nd**" with the correct ledger from `hdi_bound_sensitivity.csv`: Bobby Bones P_base = 3rd, **P_lo = 4th**, P_hi = 3rd, i.e., the lower band edge drops his P projection one podium place (fragile in the adverse direction); keep the unchanged headline verdict ("P does not reproduce the win").
2. In `results_summary.md`, recommendation-metrics paragraph: replace "the percentage rule maximizes judge-consistency (|τ| smallest)" with the correct reading, e.g., "the percentage rule is the **least** judge-consistent (smallest |τ|: outcomes are least coupled to judge quality — fan voice carries the most weight under P) and it nearly eliminates shock eliminations of fan favorites (0.3% vs 3.8% rank / 5.0% z); the z-score rule is the most judge-consistent (τ = −0.799)". Optionally relabel the F6 x-axis to make the sign convention explicit ("τ → −1 = judge-consistent").
3. In `results_summary.md`: change "±16% relative" to "≈±8% relative (median full 90% width 15.8%)", and change "event-weighted equivalents are 100% and 99.2%" to "100% and 99.1% (222/224)". Cosmetic: nudge the F5 legend (e.g., place it above the axes via bbox_to_anchor) so it does not collide with the Sabrina Bryan (S15) row.

No code changes are required — `run.py`, `model2_lib.py`, all CSVs, figures and results.json reproduce exactly and are mathematically sound; the required fixes are confined to two misquoted/misread numbers and rounding in the summary text.

VERIFICATION_RESULT: NEEDS_REVISION
