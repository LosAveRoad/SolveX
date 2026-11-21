# Review — Model 2 (Judge–Fan Fusion Engine: Rank vs Percentage)

## What I verified (recomputation, not just file reading)

I re-ran parts of the pipeline (`model2_lib simulate_season` with the stored `u_fan_appeal.csv`, θ=(1.5,0,0.05)) and recomputed every headline number from the actual output files in `02_programming/model_2/`.

**Confirmed correct (match results.json / CSVs exactly):**
- φ̂ table: 2,780 cells, mean 0.1205, median rel-90%-band 0.1579, abs p10/p90 = 0.0049/0.0346; φ̂ sums to 1 in all 335 season-weeks (max dev 4e-16). ✔
- γ_s table (mean 0.468, median 0.444; zero-disagreement seasons S1/S25/S26 with R≡P verified cell-by-cell; max S9=0.889; S8/S11/S13=0.778; S7/S12=0.750). ✔ (but see issue 2 on the pooled figure)
- Era reproduction rates from my own re-run: S1–2 rank = 1.000, S3–27 pct = 0.9916, S28+ rank+dance-off = 0.4896; pooled mean-of-season-rates 0.8887, Jaccard 0.881, MAE 0.56, τ 0.902 — all reproduce the stored values exactly. ✔
- u_i extremes (Marie Osmond +2.50, Mya +1.75, Shannen Doherty/Redfoo −2.00, Bobby Bones +0.625; 421 rows). ✔
- Controversy base placements re-simulated: Bobby Bones S27 R=5/P=3, Bristol Palin S11 R=4/P=2 (P winner is Kyle Massey), Sabrina Bryan S15 R=3/P=8, Mya S9 R=2/P=1, Donny Osmond R=1/P=2 — controversy_table.csv is correct. ✔
- Dance-off overlay (2/5/4/3/5/3/5 changed weeks; placements shifted 5–11 per season). ✔
- Quota arithmetic: Σk by season = observed eliminations in 33/34 seasons, S18 +1 (documented patch). ✔
- Determinism/deliverables: 10 CSVs, results.json (all headline numbers present), 9 figures at 300 dpi, handoff.json. ✔
- Engine design matches the plan's formulation (TH^R=(r_judge+r_fan)/2, TH^P=(ρ̂+φ̂)/2, Z variant, S28+ bottom-2 + lowest season-mean judge score dance-off proxy, fixed elimination calendar, deterministic ties). Reasonable, documented simplifications.

## Issues Found

1. **The validation headline "88.9% (266/298 cut events matched)" is not supported by any output.** The event-weighted ledger from the model's own files is **265 matched / 299 cut events = 0.886** (Σk over the 265 elimination weeks is 299, not 298; 266/298 = 0.8926 matches neither the event-weighted rate nor the 0.8887 mean-of-season-rates). The 88.9% rate itself is fine (it is the mean of per-season rates, which is what `reproduction_pooled` stores), but the "(266/298)" count pair appears fabricated by back-division and is internally inconsistent (298 is the count of eliminated contestants; Σk = 299 because of the S18 patch).

2. **"2,780-week pooled weekly disagreement: 105/240 elimination weeks (43.8%)" is wrong on all three counts.** From `rule_disagreement_by_season.csv`: **129 disagreement weeks / 265 elimination weeks = 0.487**. "2,780-week" is a typo (2,780 is couple-weeks; elimination weeks are 265). The correct value 0.487 is also *more* favorable to the model's thesis (R vs P disagree in ~half of all elimination weeks).

3. **The claim "percentage rule counterfactually applied to S28+ reproduces 99%" is false, and the conclusion built on it is unsupported.** Recomputed from the model's own engine: pct rule on S28–34 matches only **34/65 = 52%** of cut events (weekly-exact 13/56 = 23%); pct+dance-off 31/65 (48%); it is the **rank rule without** the dance-off stage that matches 58/65 = 89%. So the summary's statement "strong evidence that the dance-off layer (not fan votes) drives the divergence there" is contradicted by the outputs — under plain percentage the S28+ reproduction is barely better than the dance-off rank engine (52% vs 51%), while plain rank reproduces far more. This claim also concerns 3 different spots (Key Results, Sanity Checks, Issues).

4. **Bristol Palin verdict overclaimed:** summary says "under P she would have WON (P=2nd→1st after finale)". The stored table and my re-run give **P = 2nd (runner-up; Kyle Massey 1st)** at the base estimate. Likewise "×2 → R 4th, P 1st; ×4 → both 1st" contradicts `controversy_flip_curves.csv` (×2 → R 4, P 2; ×4 → R 2, P 1; R never reaches 1st at any multiplier, so "Bobby ×8 → both 1st" is also wrong — R stays 2nd at ×8 and ×16).

5. **Planned HDI bound sensitivity was not delivered.** The plan's Validation section requires re-running with φ̂ at its 90% HDI bounds and labeling controversy verdicts robust/fragile; the summary asserts "controversy verdicts are robust" without that experiment (only the multiplier grid exists, which is a different probe). Also exactly 2 of the 3 promised `shared_data` copies (fanvote_estimates.csv, controversy_table.csv) are absent — only rule_replay.csv was copied — while the summary lists all three.

6. **In-sample nature of the calibration is under-flagged:** 421 free u_i parameters against 2,780 couple-weeks / 298 Bernoulli events; a quick probe (U fit on S5 alone makes S5's composite log-lik ≈ −0.19 vs −142 with U fit on S27) shows u_i absorb nearly all signal; no leave-one-season-out validation was run. The summary flags the (α,β) ridge but not this.

7. Cosmetic: F5 (placement flow) has overlapping labels/arrows making several controversies unreadable; the summary's flip-curve row count note ("56 = 7 pairs × 8") is garbled (8 pairs × 7 multipliers; multiplier 1.0 skipped).

## Fix Instructions

1. In `results_summary.md`, replace "(266/298 cut events matched)" with the exact ledger: 265 matched of 299 cut events (event-weighted 88.6%), or state clearly that 88.9% is the mean of per-season rates and that Σk=299 (S18 +1 quota patch). 
2. Replace "105/240 elimination weeks (43.8%)" with **129/265 = 48.7%** (from `rule_disagreement_by_season.csv`).
3. Delete or correct the "percentage rule applied to S28+ reproduces 99%" claim (three places) and the derived conclusion; the correct statement is: on S28+ the engine's rank+dance-off proxy reproduces 51% of cut events, plain rank without dance-off 89%, plain percentage only 52% — the S28+ divergence is driven by judge-deliberation choices not in the data, and φ̂ itself reproduces observed cuts well when the dance-off stage is dropped.
4. Correct the Bristol Palin and Bobby Bones sentences to match `controversy_flip_curves.csv`: Bristol base P = 2nd (not 1st); ×2 → R 4/P 2; ×4 → R 2/P 1; R stays 2nd even at ×16 ("both 1st" → "P 1st, R 2nd").
5. Either run the planned HDI-bound sensitivity (re-run Steps D–E with φ_lo90/φ_hi90 in place of φ̂, e.g. a small loop in `run.py` around `analyze_controversies`) or soften the robustness sentence to "robust on the multiplier grid; HDI-bound check not performed".
6. Actually write the promised `01_modeling/shared_data/` copies (the code already wraps this in try/except that failed silently — check permissions) or correct the file list.
7. Add one paragraph flagging the in-sample calibration (421 u_i parameters; no cross-season holdout), and re-render F5 with non-overlapping layout.

The core engine, results.json, and nearly all CSV numbers are sound and reproduce; the revision needed is confined to incorrect summary claims and the one missing planned validation.


## Issues Found:
(numbered issues above)
## Fix Instructions:
(numbered fixes above)

VERIFICATION_RESULT: NEEDS_REVISION
