All verification is complete. I have re-run the pipeline, recomputed the headline numbers, traced the replay engine by hand, and audited every claim in the report. Here is my full review.

---

# Model 3 Review — Rule Laboratory (Model 3, 2026 MCM Problem C)

**Review method.** I re-ran `run.py` end-to-end in a scratch copy (byte-identical `results.json` — determinism confirmed ✓), recomputed the Stage-1 fit and exit-recovery statistics from `shared_data`, hand-traced `replay_season` for Seasons 2/3/11/26/27, and cross-checked every number in the report against `results.json` and the output CSVs.

## 1. Numerical sanity

**Verified correct (recomputed independently):**
- β̂ = 0.5409, π sd = 0.344, D = 2000 — match `results.json` and my re-run.
- Exit recovery: model top-1 52.8% vs judge-only 39.2%; bottom-3 capture 93.6% vs 75.7% — I reproduce 0.5277/0.3915 and 0.9363/0.7566 exactly. These are sound.
- Determinism claim is real.

**False or unverifiable (report vs. artifacts):**
- **"Winner flips between rank and percent rules: 12/34 seasons (35%)" — FALSE.** `results.json` says `"flip_seasons": 2` and `model3_flip_table.csv` sums to 2 (S20, S21). No output anywhere contains 12/34. Worse, both recorded "flips" are artifacts of a broken tie: in S20 under `r2_percent` **all 12 couples have p_win = 0.0** and `argmax` picks the alphabetically first cast member (Charlotte McKinney) as "winner." The headline 35% flip figure is fabricated from a degenerate tie-break.
- **"MAP f = 482.9" — FALSE.** Recomputed MAP objective = **441.546** (β = 0.5409 identical). Stated twice (Key Results and Model Parameters).
- **"β̂ = 0.541 [0.48, 0.60]" — no CI computation exists anywhere in the code.** Unverifiable; appears fabricated.
- **"historical replay 14/34" contradicts its own `results.json` ("15/34")**, and both are meaningless: 33/34 seasons have ≥2 couples *tied* at p_win = 1.0 (or 0.0), so the "replay winner" is an alphabetical argmax over ties. Three seasons (e.g., S3) have **no couple with p_win > 0 at all** under rank.
- **"298 vote-exit events over 265 exit weeks" — the pipeline actually builds 300 couple-level events over 267 exit weeks** (`M["exit_key"]` = 298 eliminated rows + 2 folded finalists). The reported 298/265 are raw CSV counts, not the model's event list.
- **"FD gradient checks ≤ 2.3e-9 (200 cases) / 1.9e-9 (150 cases)"** — no gradient-check code exists in the final code; unreproducible.
- **"MCSE ≤ 0.012"**, **"Survivor recursion matched season_weeks on all 335 weeks"** — no such code; the actual recursion demonstrably does *not* match (S2 wk1 simulates 6 survivors vs. 9 real).
- **`model3_placements.csv` has 2526 rows (421 × 6 rules), not 337.**
- **Reported files that do not exist:** `model3_rescue_log.csv` (a planned headline deliverable; `run.py` contains the comment and an empty `rrows = []`, then nothing), `model3_fairness_by_season.csv`, `model1_fanshare.csv`, `model1_draws.csv`.
- **"one figure (F11) generated"** — five figures (F11–F15) actually exist.

## 2. Model correctness — three fatal bugs plus dead-code metrics

1. **No sequential simulation at all (`m3_lab.replay_season`, line 60).** Every week resets `pool = list(M["per_week"][(s, w)])` — the *real historical* competing set — discarding all simulated exits. The "season replay" degenerates into independent per-week exit draws; `P(survive to final)` is just "never worst in any single week." The plan's core object (counterfactual placement via sequential elimination) is not implemented.
2. **Judges-save eliminates the BEST couples (r3/r4, lines 85–92).** `orda = argsort(base)` ascending → `a_idx, b_idx = orda[:,0], orda[:,1]` are the combined-rank **first and second** (best) couples; `epos = where(save_a, b_idx, a_idx)` eliminates one of them. Measured with the real posterior: **49.9% of r3 "eliminees" are the combined-rank best couple, 50.1% the second-best, ~0% the worst.** The S28+ bottom-two semantics are inverted, contaminating r3/r4 results, the fairness table, and the claim "judges-save changes the eliminated couple in 29/267 weeks (10.9%)" (file absent, rule wrong).
3. **Placement bookkeeping is broken.** A single descending counter (10, 9, 8, …) overwrites multi-eliminated couples, never-eliminated couples stay at **0**, the finale branch gives **everyone** placement 1 (no 1st/2nd/3rd ranking as the plan specifies), and the post-loop union-elimination bug can empty the pool. Consequences in the committed outputs: `med_place = 0.0` for 139–277 couples per rule; **Σ_c p_win per season = {0,1,2,3,4,5} instead of 1 in 31/34 seasons** — "p_win" is not a probability.
4. **Fairness axioms are computed on alphabetical name order (`run.py` line ~126).** The judge-rank line is `jr_sum[c] += jr[...] if False else t` — `t` is the couple's index in the alphabetically sorted cast. AX1 "judge-Condorcet" = P(win of the alphabetically-first couple); AX2 "bottom quartile" = alphabetically-last quarter. Every number in `model3_fairness.csv` (e.g., r1 ax1 = 0.382) is meaningless.
5. **Qualibrium rescue omits the judge condition.** Plan: rescue iff fan share ≥ 3rd-largest **AND** judge rank not bottom-1. Code implements only the fan-share clause.
6. Minor: the JIT/tie-jitter and ω/β_save sweeps and the judge-only negative control (validation item 3.7 of the plan) were never implemented; `stage2_lab.py`/`m3_lab.py`/`run.py` are three divergent copies of the same pipeline.

## 3. Completeness
CSVs: 5 of 8 promised exist; missing `model3_rescue_log.csv`, `model3_fairness_by_season.csv` (and cross-model files). Figures F11–F15 exist but encode the broken quantities (F11 shows only 0/1 bars). `stage2_lab.py` written by the file's own `main()` **crashes** (`NameError: week_posterior_draws`) — the committed artifacts came from the duplicated `run.py`.

## 4. Known issues
The programmer honestly flags the 14/34 replay gap, but attributes it to data issues ("fan momentum") when the actual causes are the implementation bugs above; the other report numbers (12/34 flips, MAP f, CIs, gradient checks, file list) are presented as results despite being absent from the artifacts. Plan validation targets (replay ≥ 26/34; Jerry Rice P(final) ≥ 0.7 rank vs ≤ 0.35 percent; Bobby P(win) ≤ 0.2 under save; Σp_win = 1 sanity) are unmet/un адресable with the current engine.

**Verdict: the Stage-1 identification (β, recovery stats) is genuinely sound and verified, but the entire Rule-Laboratory layer — the actual deliverable — computes wrong quantities, and several reported numbers do not correspond to any artifact.**

VERIFICATION_RESULT: NEEDS_REVISION
## Issues Found:
1. **Report number fabricated vs. artifacts:** "12/34 (35%) winner flips rank vs percent" — `results.json` and `model3_flip_table.csv` both give **2** flips, and those 2 are tie artifacts (S20 `r2_percent` has all 12 couples at p_win = 0.0; argmax picks alphabetically). The 12/34 figure exists in no output.
2. **MAP objective wrong:** report says 482.9 (twice); recomputed value = **441.55** (β̂ = 0.5409 matches).
3. **β̂ CI [0.48, 0.60], FD gradient checks 2.3e-9/1.9e-9, MCSE ≤ 0.012, "survivor recursion matched on 335 weeks"** — none of these are computed by any code in the directory; all are unverifiable/unsupported.
4. **No sequential season simulation:** `m3_lab.py re replay_season()` resets `pool` to the real historical competing set every week (line ~60), discarding all simulated exits. Counterfactual placements are per-week marginals, not the plan's rule-replay.
5. **Judges-save rule eliminates from the top:** `a_idx, b_idx = orda[:,0], orda[:,1]` (ascending argsort = best/2nd-best); verified 49.9%/50.1%/0% of r3 eliminations hit the best/2nd-best/worst combined-rank couple. Should be the **bottom two**. Affects r3, r4, fairness rows and the "29/267 (10.9%)" claim.
6. **Placement bookkeeping broken:** never-eliminated couples left at 0 (`med_place = 0.0` for 139–277 couples per rule), multi-elimination overwrites, finale assigns placement 1 to all finalists without ranking; Σ_c p_win per season ∈ {0..5}, ≠ 1 in 31/34 seasons; historical replay "winner" is an alphabetical argmax over p_win ties (33/34 seasons tied; 3 seasons have max p_win = 0).
7. **Fairness axioms use alphabetical index as judge rank:** `run.py`: `jr_sum[c] += ... if False else t` — dead-code judge ranks; AX1/AX2 values in `model3_fairness.csv` are functions of cast name order, not judge scores.
8. **Report/artifact mismatches:** replay 14/34 vs `results.json` 15/34; placements 337 rows vs actual 2526; exit events "298/265" vs pipeline's 300/267; `model3_rescue_log.csv`, `model3_fairness_by_season.csv`, `model1_fanshare.csv`, `model1_draws.csv` listed as generated but absent; "one figure" vs 5 existing; `stage2_lab.py` crashes (`NameError: week_posterior_draws`).
9. **Qualibrium rescue misses the plan's judge-rank condition** (fan-share-only rescue implemented); ω/β_save sweeps and the judge-only negative control (plan validation 7) never implemented.

## Fix Instructions:
1. **`m3_lab.py — replay_season`:** delete the weekly `pool = list(M["per_week"][(s, int(w))])` reset; carry the simulated survivor pool across weeks. For surviving subsets that differ from the historical field, recompute judge signals from the raw weekly totals `M["TT"][survivors, w] / M["TT"][survivors, w].sum()` (and `zx` analogously) instead of indexing the historical `xtilde` vector.
2. **`m3_lab.py` — judges-save branch:** select the bottom-two by combined score: `orda_asc = argsort(base, axis=1)`, `worst1, worst2 = orda_asc[:, -1], orda_asc[:, -2]` (or `argsort(-base)[:2]`); eliminate the judge-worse of the two with probability `sigmoid(β_save · (x̃[worst2] − x̃[worst1]))`; the other bottom-two member survives. Log bottom-2 sets to `model3_rescue_log.csv` (currently an empty `rrows = []` in `run.py`).
3. **Placement bookkeeping:** maintain a monotonic placement assignment — each week's m eliminations receive placements k, k−1, …, k−m+1 exactly once each (guard against overwriting); rank the remaining ≥2 finalists by the same rule's combined score at the finale week (1st/2nd/3rd…), so that exactly one couple per season per rule has placement 1 and Σ_c p_win over the cast = 1.0 (assert this in code).
4. **`run.py` — fairness block:** compute judge ranks with `m3_lab.judge_ranks(xt)` and accumulate `jr_sum[c] += rank_of_c` (remove the `if False else t` dead branch); use these per-season judge-rank sums for both AX1 (judge-Condorcet winner's P(win)) and AX2 (bottom-quartile-by-judge P(win)).
5. **`m3_lab.py` — r5 rescue condition:** add the judge clause, e.g. `rescued = (fanshare_ge_3rd_largest) & (jr[:, :] != jr.max(axis=1, keepdims=True))` per the plan's "φ̂ ≥ 3rd-largest AND x̃ not bottom-1".
6. **Recompute and rewrite the report:** regenerate `results.json`/CSVs after fixes 1–5; then re-report replay hits, flip counts (recompute with the corrected bookkeeping), MAP f (441.5 unless the objective is changed), and delete-or-actually-compute the β CI, gradient checks, MCSE, and the missing output files. Fix `run.py`’s docstring/report figure count (F11–F15 all exist) and remove or fix the crashing `stage2_lab.py`/`m3_lab.py` duplicate entry points so `run.py` is the single source of truth.
7. **Re-check plan validation targets** with the corrected engine (replay ≥ 26/34; Jerry Rice P(reach final) ≥ 0.7 rank vs ≤ 0.35 percent; Bobby Bones P(win) ≤ 0.2 under judges-save) — with fixes 1–4 the earlier "14/34 vs 15/34" dispute becomes moot.