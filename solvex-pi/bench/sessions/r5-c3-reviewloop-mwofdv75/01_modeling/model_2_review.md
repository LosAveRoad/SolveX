I have now verified the report against `rules.py`, `engine.py`, `run_model2.py`, all four output CSVs, `run_stats.json`, the hand-off files, and three figures. Here is my review.

---

# Model 2 Review — Aggregation-Rule Counterfactual Engine

## 1. Numerical sanity — VERIFIED

Every headline number in the report matches the regenerated artifacts exactly:

| Report claim | Artifact check | Status |
|---|---|---|
| Hit rate 0.362 (mode) / 0.349 (draws) | `run_stats.json`: 0.3618 / 0.3485; `rule_flip_stats.csv` consistent | ✓ |
| Mean weekly flip prob 0.1289; veto flip 0.1227; 0/34 zero-flip seasons | `run_stats.json` + CSV (min Σ flip = 0.0635, S27) | ✓ |
| Highest-risk seasons S21 0.262, S5 0.257, S32 0.224, S4 0.223, S30 0.211, S25 0.207 | CSV: 0.2624, 0.2571, 0.2235, 0.2227, 0.2107, 0.2069 | ✓ |
| Σ_w Pr(flip) ≤ n−2 (max 2.571, S5, n=12) | CSV max Σ = 2.5715; bound trivially satisfied (2.571 ≪ 10) | ✓ |
| Fan-favour 0.978 (RANK) vs 0.965 (PERCENT), PERCENT higher in 11/34 | `fan_favor_index.csv` + fig3 caption "11/34" | ✓ |
| Controversy Pr(bottom-1) ≈ 1.00 (Bones 0.997 RANK / 0.999 PERCENT), veto saves = 0, fan/judge gaps −0.118 to −0.170 | `controversy_case_studies.csv` + fig2 | ✓ |
| Permutation 0.362 vs 0.217 | `validation_permutation.csv`; shuffled values 0.08–0.30, plausible | ✓ |

Probability quantities are all in [0,1] and Σ_w Pr(flip) is far below the sanity bound. The Bobby Bones case is internally coherent: S27 hit rate 0.0 (his win is never reproduced) yet flip risk 0.0079 (RANK and PERCENT agree with *each other*) — a subtle but correct pairing, and the report explains it correctly.

**One narrative inaccuracy (minor):** the report lists "Weakest reproduction: S1 (0.00), S9 (0.20)" but omits that **S27 also has hit_mode = 0.00** (and S30 = 0.111, S33 = 0.143 are below S9's 0.20). The omission is arguably an oversight since the S27 = 0 fact is stated honestly in the controversy section, but the "weakest" sentence should read S1/S27 (both 0.00), then S30 (0.11), S33 (0.14), S9 (0.20).

## 2. Model correctness vs. the plan

- **Rule functions** (`rules.py`) match the plan's formulation: RANK = sum of judge-rank and fan-rank points with (n+1−r) scoring, equal weight; PERCENT = 0.5·judge share + 0.5·fan share (β=0.5); VETO = bottom-two of base rule, judges keep the higher-scored member. The Appendix self-test is genuinely hand-computed (C/D tied at 3 points under RANK, C eliminated under PERCENT, D eliminated under veto) and the dense-rank tie cases in the report verify correctly.
- **Season rule map** RANK S1–2/S28–34, PERCENT S3–27 implemented (`SEASON_RULE`) and visible in the CSV `rule` column — this was the round-1 fix and it is correctly applied.
- **Fan-favour index**: the retraction of the round-1 "PERCENT always more fan-favouring" claim is legitimate — the old computation mixed standing vectors. The corrected index is computed on a single consistent standing vector and gives 11/34, matching fig3. Honest and correct handling.
- **Deviation (acceptable but under-flagged):** the plan says "for each week w with estimated shares v̂_w and judge ranks/scores", but the engine evaluates every week with **cumulative** judge points and **cumulative** fan shares (`Jcum`, `Vcum[:, w-1]`), not that week's shares. This is self-consistent across rules (so the RANK-vs-PERCENT comparison remains a fair apples-to-apples contrast, which is this model's purpose), but it is not the literal weekly-combination rule, and it is only indirectly covered by Limitation 3 ("collapsed snapshot"). It should have been stated explicitly.
- **Related subtlety:** for S28–34 the hit rate requires the *base* rule's bottom pick to equal the observed eliminee, even though in those seasons the real show used the judges' veto (eliminee may legitimately be 2nd-worst). This mildly understates S28–34 hit rates. There is also dead/conflicting comment logic in `sample_posterior` ("worst-or-second-worst" for VETO seasons is not implemented). Both are minor and directionally conservative.

## 3. Completeness — VERIFIED

All seven data products, three figures, and three code modules exist and are internally consistent (CSV row counts, `run_stats.json`, figures match). `posterior_fan_shares_sample.csv` has 134 rows (S2: 10 contestants over 8 weeks depleted, S27: 13), matching the report. `handoff.json` documents the Model-1 swap-in point. Figure 2 numerical bars match the CSV to the third decimal; figure 3's corrected caption is visible.

## 4. Known issues — ADEQUATELY FLAGGED

Five limitations are disclosed, including the S1 Kelly Monaco failure mode (honest — the model misses exactly the high-leverage fan case), the non-external Model-1 posterior, and the finale-only controversy counterfactual. The reasoning that controversies arise from a persistent −12 to −17 pp fan/judge cumulative-share gap that *both* rules convert identically, with the veto saving nobody (bottom-picked contestants also had the worst judges' scores of the bottom pair), is a sound and defensible basis for the producers' recommendation.

## Verdict

The quantitative results are reproducible from the shipped code and artifacts, the probabilities are sane and properly validated (discriminating permutation test, weekly active-set logic verified against the raw CSV where eliminated contestants are 0-filled, budget constraint |Σv−1| < 1e-9, Appendix hand-tests pass), and the round-1 errors (mixed standing vector, undiscriminating permutation test, wrong season-rule map) were genuinely fixed rather than cosmetically patched. The residual issues — cumulative-instead-of-weekly combination not explicitly disclosed, the "weakest reproduction" list omitting S27's 0.00 hit rate, and the S28–34 base-rule hit-rate subtlety — affect narrative framing and calibration interpretation, not the correctness of any reported number.

VERIFICATION_RESULT: SATISFIED