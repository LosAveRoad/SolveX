# Review — Model 2 (revision 2): Judge–Fan Fusion Engine

## What I verified (recomputation from code + data, not just file reading)

I re-ran `python3 run.py` (32 s, deterministic), re-derived the headline numbers from the output CSVs, and re-simulated the controversy replays independently via `model2_lib.simulate_season` with the stored `u_fan_appeal.csv` and θ=(1.5, 0.0, 0.05). All revision-1 issues are confirmed fixed.

**Reproduced exactly:**
- **Determinism**: a full rerun produced byte-identical outputs — all 12 CSVs + results.json MD5-identical before/after; results.json carries no wall-clock/random field. ✔
- **Validation**: mean per-season cut-match 0.8887; event-weighted ledger **265/299 = 88.6%** (Σk = 299 legitimately exceeds 298 eliminated contestants because of the documented S18 Diana Nyad week-2 patch); Jaccard 0.8811; placement MAE 0.5626; τ 0.9025. Era rates: S1–2 rank 1.000 (10/10 events), S3–27 pct 0.9916 (222/224), S28+ rank+dance-off 0.4896 (33/65). ✔
- **γ_s table**: recomputed R-vs-P disagreement week-by-week from my own replays — identical to `rule_disagreement_by_season.csv` for all 34 seasons (mean 0.468, median 0.444, zero-disagreement S1/S25/S26 verified cell-by-cell, max S9 = 0.889). ✔
- **Controversies**: re-simulated all 8 named cases (Jerry Rice S2, Billy Ray Cyrus S4, Bristol Palin S11, Bobby Bones S27, Mya S9, Donny Osmond S9, Sabrina Bryan S5/S15) — every R/P/Z placement matches `controversy_table.csv`; the S11 P-replay winner is Kyle Massey as stated. ✔
- **Flip curves**: all 56 cells of `controversy_flip_curves.csv` match my re-simulation (e.g. Bristol ×2 → R4/P2, ×4 → R2/P1, R never wins; Bobby ×16 → R2/P1). ✔
- **S28+ decomposition**: 58/65 plain rank, 34/65 plain pct, 33/65 rank+dance-off, 31/65 pct+dance-off — matches `s28plus_rule_overlay.csv` and supports "the dance-off stage, not rank-vs-percentage, drives the S28+ divergence". ✔
- **HDI-bound sensitivity (new in rev 2)**: `hdi_bound_sensitivity.csv` matches the summary — 7/8 placements constant at lo/point/hi; the hdi sentence now quotes the correct ledger (Bobby Bones P_base = 3rd, P_lo = 4th, P_hi = 3rd, adverse direction documented). ✔
- **Recommendation metrics**: τ/Gini/shock averages recomputed per season — match (R −0.756 / P −0.618 / Z −0.799; shock 0.038/0.003/0.050), and the summary's interpretation is now sign-correct ("P decouples outcomes most from judge quality"). ✔
- **Sanity checks**: φ̂ sums to 1 in all 335 season-weeks (max dev 4.4e-16); φ̂ ∈ [lo, hi] with zero band violations; corr(φ̂, rel width) = −0.8 (wider bands for low-φ̂ couples); u_i ∈ [−2.0, +2.5] ⊂ [−3, 3]; S18 quota arithmetic (Σk = 299 vs 298 eliminated) documented with the exact Nyad/Billy Dee mechanism (verified in `build_season_context`). ✔
- **Deliverables**: all 12 CSV data files + 10 figures (300 dpi) + results.json + handoff.json present; the three `shared_data` copies (`model2_fanvote_estimates.csv`, `model2_rule_replay.csv`, `model2_controversy_table.csv`) now exist and are byte-identical to the model outputs. Figures F5 (legend moved above the axes, no label overlap) and F6 (x-axis explicitly "τ → −1 = judge-consistent") render correctly.

All three revision-1 issues (fabricated 266/298 count, false "percentage on S28+ reproduces 99%", Bristol overclaim) plus the missing HDI experiment, missing shared copies, τ misreading, ±16% rounding, and F5 overlap have been resolved.

## Issues Found

None blocking. Two cosmetic notes, no action required:
1. `results.json` stores HDI/flip values as floats (3.0, 5.0) where placements are integers — purely cosmetic.
2. The Summary table omits `calibration_grid.csv` (105 rows, consistent with 42 stage-1 + 5 stage-2 + local refinement rows) — no inconsistency, just an undocumented file.

## Verdict

The implementation matches the plan's formulation (TH^R/TH^P/Z rules, S28+ bottom-(k+1) dance-off proxy, fixed elimination calendar), the calibration is honestly flagged as in-sample, and every quoted number reproduces from the code and data. Mathematically sound.

VERIFICATION_RESULT: SATISFIED
