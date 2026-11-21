VERIFICATION REVIEW — Model 2 (Aggregation-Rule Counterfactual Engine)

Code reviewed: `02_programming/model_2/{rules.py, engine.py, run_model2.py}`, plus all CSVs, `run_stats.json`, `handoff.json`, and the three figures, cross-checked against `data/2026_MCM_Problem_C_Data.csv` (read-only session; no code executed).

## 1. Numerical sanity

The headline Monte-Carlo numbers are internally consistent with the artifacts: `run_stats.json` (mean_flip_prob = 0.0751, mean_veto_flip = 0.0593, perm_true = perm_shuffled = 1.0) matches the report, `rule_flip_stats.csv` matches the per-season values (S33 0.5435, S9 0.506, S6 0.3785, S26 0.3465, S10 0.241, S12 0.151), the sum-flip bound holds, and fig1 renders the same values. However, several **reported numbers contradict the model's own output files**:

- **Fan-favour index means are wrong.** Report claims "mean 0.982 (RANK) vs 1.000 (PERCENT)" and "PERCENT ≥ RANK in 33/33 computable seasons." Averaging the actual `fan_favor_index.csv` columns gives ≈ 0.867 (RANK) vs ≈ 0.896 (PERCENT), and PERCENT < RANK in **S9 (0.713 vs 0.929), S24 (−0.449 vs −0.072), S32 (−0.31 vs −0.241)** — three counterexamples, not zero. Figure 3's caption claim ("all points on/below identity line") is also false for those seasons.
- **"14 of 34 seasons have zero flip risk" — the CSV shows 15** (S1,2,3,5,13,14,15,18,19,22,25,27,29,30,34).
- **`posterior_fan_shares_sample.csv` is reported as "427 rows"; the file on disk has ~198 data rows** (S2: 80, S27: 117 + header). The delivered hand-off product does not match its description.

## 2. Model correctness — the central defect

Tracing `engine.load_seasons()` against the raw CSV reveals a **zero-score-week bug that invalidates the replay layer**. Many eliminated contestants have `"0,0,0"` in post-elimination weeks (e.g., S2 Tatum O'Neal weeks 3+, S27 Jamie Anderson weeks 2+, Billy Ray Cyrus weeks 9–10). The scoring filter `r[f"week{w}_judge1_score"] not in ("N/A", "")` counts `0` as a scored week, so:

- Every eliminated contestant is treated as **active through the season's final scored week** with zero judge points. The S27 sample CSV confirms all 13 contestants (including week-1 eliminee Nikki Glaser) appear as "active" at week 9; S2 lists all 10 at week 8.
- Consequently `elim_by_week[final week]` = **all n contestants**, so the "hit" test `set(order[:k]) == set(elims)` with k = n is **trivially true for any votes**: the 34/34 hit rate = 1.00 and the permutation test collapse are artifacts of this bug, not of importance conditioning as the report claims (the conditioning machinery is in fact inert here — for these degenerate eliminee sets the soft penalties apply uniformly and cancel).
- The reported "weekly flip probability" is the argmin-flip of cumulative combined points **over the full cast including long-eliminated couples**, not over the truly active set that faced the week's decision. The actual weekly elimination decisions in the plan (weeks 1…W, active sets shrinking) were never replayed at all — `n_elim_weeks = 1` in every season is a symptom of the bug, not a property of the data (the CSV does contain weekly score columns; only post-elimination entries are 0-filled, which the code could easily distinguish).
- The controversy case studies inherit this flaw: "position 7.03 of 13" for Bobby Bones ranks him against couples eliminated weeks earlier on cumulative totals, and Pr(bottom-2) = 0 for all four celebrities is an artifact, not a finding. The cleanly implemented pure-rule functions in `rules.py` (which do match the Appendix, self-tests are correct) are never applied to a faithful weekly decision problem.
- Minor: `SEASON_RULE` treats seasons 28–34 as PERCENT, whereas the plan (and problem statement) say ranks were reinstated from S28; the counterfactuals still cover both rules, but the base-rule label/validation for 28–34 is wrong.

## 3. Completeness

All promised code files, CSVs, figures, `run_stats.json` and `handoff.json` exist and figures render their described content. Note the programmer built an internal Model-1 substitute despite `02_programming/model_1/fan_votes.csv` existing — defensible as documented, but the deliverable then duplicates rather than consumes the pipeline's Model 1.

## 4. Known issues

The programmer honestly flagged the permutation-test collapse, the internal posterior, and the snapshot limitation — but **mis-diagnosed their cause** (attributing hit-rate = 1.00 to conditioning rather than to the zero-week bug), and reported several numbers that disagree with the produced CSVs (Sections 1 above). Combined with the vacuous elimination-consistency measure (the problem's first required deliverable), this needs revision before the numbers feed the paper.

VERIFICATION_RESULT: NEEDS_REVISION
## Issues Found:
1. `engine.load_seasons()` treats `"0"` judge scores as scored weeks, so eliminated contestants are "active" at the season's final week; the observed-eliminee set at the replay week = the whole cast, making hit rate = 1.00, the permutation test collapse, and Pr(bottom-2)=0 controversy results all trivial artifacts (see S27: all 13 celebrities listed active in week 9 of `posterior_fan_shares_sample.csv`).
2. Report misstates its own outputs: fan-favour means "0.982 vs 1.000" vs actual ≈0.867 vs ≈0.896; "PERCENT ≥ RANK in 33/33" false (S9, S24, S32 violate it); "14 of 34 zero-flip seasons" vs actual 15; sample CSV "427 rows" vs ~198 on disk.
3. Weekly flip probabilities computed over the wrong (full-cast) active set; no true weekly elimination decision was ever replayed, so the required "consistency with who was eliminated each week" measure was never validly computed.
4. `SEASON_RULE` labels seasons 28–34 as PERCENT contrary to the plan/problem statement (S28+ = rank rule).
## Fix Instructions:
1. In `engine.py: load_seasons()`, count a week as scored only if the summed available judge scores > 0 (filter the 0-filled post-elimination weeks); rebuild `weeks`, `wlast`, `Jmat`, and per-week active masks accordingly, so each week's active set shrinks with real eliminations and `elim_by_week` maps each real elimination week to only that week's eliminee(s).
2. Re-run `run_model2.py` after the fix; recompute hit rate as P(observed week-w eliminee is the bottom pick among the truly active couples) — this should become a genuine (non-degenerate) consistency measure, and the permutation test should become discriminating; if it still equals 1.00/1.00, state the degeneracy honestly in `results_summary.md`.
3. In `engine.py`, set `SEASON_RULE = {1:"RANK", 2:"RANK", 28..34:"RANK"}` (or justify PERCENT-for-28+) and rerun so the `rule` column in `rule_flip_stats.csv` is correct.
4. Correct the misstated numbers in `results_summary.md` (fan-favour means and the 33/33 claim, zero-flip season count, sample-CSV row count) by recomputing them from the regenerated CSVs, and fix fig3's caption claim; optionally re-express the fan-favour index using the plan's definition (−corr(judge rank, placement under rule A) computed on a consistent standing vector, not a mixture of observed placements and final-week orderings).