I've completed all verification I need. I re-ran the full pipeline from scratch and independently recomputed the fan-share draw stage. My final review follows; per the runtime note, SolveX saves this reply to the review path verbatim.

---

# Model 2 cross-review (round 2) — Judge–Fan Behavioral Attribution

## What I re-verified independently (scratch copy of the full pipeline under `.solvex/scratch/m2_check/`, no implementation changes)

1. **Determinism & reproducibility**: re-ran `python3 run.py` end-to-end (~55 s) on a copied tree → **all 8 outputs byte-identical (md5 match)**: `results.json`, `model2_fanshare.csv`, `model2_decomp.csv`, `model2_pro_rankings.csv`, `model2_industry_effects.csv`, `model2_effects.csv`, `model2_exitfit.csv`, `model2_era_drift.csv`. The determinism claim is real.
2. **Fan-share stage**: re-derived `map_optimize` myself — β = 1.3866, θ = −0.000108, MAP nll = 436.583 exactly as reported; 267 constraints = 235 E-type + 32 F-type, with 30 exit weeks excluded by withdrawal context ✓. Weekly share sums = 1 to 2e-9 over all 335 season-weeks; share range [0.00086, 0.8473]; mean sd 0.0575; perplexity 472.47; issue mean 13.96 ✓.
3. **Exit consistency**: MAP bottom-m 97/235 vs judge-only 88/235; single-exit 81/206 vs 82/206 (tie, honestly stated); bottom-3 184/235 vs 179/235; multi-exit exact 7/29 — all match `results.json`/`model2_exitfit.csv` ✓.
4. **Surfaces & decomposition**: n = 2,777 rows (= week_scores.csv), 116 params (1+33+51+24+3+3+1) ✓; partial R² blocks and permutation p-values match `model2_decomp.csv` to 4 decimals on both surfaces ✓.
5. **Pro rankings**: 52 pros, 41 eligible; Derek #1 (+0.662), Artem #2, Valentin #3, Corky #4, Mark #5, Cheryl #15 — the plan's known-elite validation PASSES ✓; ρ(judge, fan) = 0.989 eligible / 0.988 all ✓; reference pro Alan Bersten carries its exact −center value (−0.1088) with NaN CI ✓.
6. **Prior-round fixes — all 5 verified in code and outputs**: (i) swap exhibit now uses `scipy.special.expit`, worst = 0.0093 unclipped ✓ (independently confirmed: logit −4.672); (ii) era drift now reports **Spearman** (I recomputed mean within-week Spearman ≈ 0.971 — matches 0.972/0.969/0.971) ✓; (iii) `_center_contrast` strips the dummy prefix and gives the reference its exact row share (Bersten = −0.1088 ≈ −center) ✓; (iv) permutation blocks rebuilt in drop-first coding, per-block scheme documented ✓; (v) summary text restates eligible top-5, "#15 of 41 eligible", and stages the exit-recovery numbers ✓.
7. **Other exhibits**: age/week RCS curves match the report at both ends (age 20: −0.27/−0.46 … 82: −2.15/−3.01); era drift gap/ratio columns ✓; restricted pro R² (0.128→0.087 judge, 0.120→0.078 fan; fame control 0.206/0.209) ✓; LOSO and paired-slope numbers ✓; all files and figures F6–F10 present ✓.

## New issues found this round

**A. The 95% fan-share bands are broken (code defect in a claimed deliverable).** In `m2_fanshare.compute_fanshare` the weighted quantiles are computed as
`cum = np.cumsum(wts)[order] - 0.5*wts[order]`, which takes the cumulative weights **in shake order** and then *gathers them by phi-rank permutation*. That sequence is not a CDF in phi order (I verified it is non-monotone along `order` for essentially every column), so `argmin|cum−0.025/0.975|` picks essentially arbitrary draws. Consequences in the shipped `model2_fanshare.csv`: **1,422/2,777 rows (51.2%) have `fanshare_lo95 > fanshare_hi95`** (e.g. J.R. Martinez S13 w4: lo 0.104 > hi 0.097; Nelly S29 w10: lo 0.0102 > hi 0.0036), and **2,080/2,777 (74.9%) exclude the posterior mean from its own "95% band"**. With the correct column-wise CDF (`np.cumsum(wts[order], axis=0) − 0.5*wts[order]`) I get 0 inverted rows, a monotone CDF everywhere, and 100% point coverage; mean |Δlo| ≈ 0.081, |Δhi| ≈ 0.140 vs shipped. Importantly I verified the blast radius: point estimates (`fanshare`), `fanshare_sd`, and every downstream number (R², decomposition, rankings, era drift, exit recovery, swap exhibit) are **not** computed from the bands — results.json is unaffected. But `model2_fanshare.csv` explicitly delivers "φ posterior mean/sd/95% band" and the summary sells "calibrated bands" as one of three values of this stage; a band that is inverted in half the rows is not calibrated. The problem statement's certainty deliverable is core, so this is revision-level.

**B. Stale number in the summaryKey Results.** "Derek Hough **#1** (+0.662 [95% CI 0.101, 1.300])" — `results.json` and `model2_pro_rankings.csv` both say judge CI **[0.447, 0.942]** (an earlier-revision quantile was evidently not updated after the cluster-bootstrap/centering change). This violates the summary's own claim that "All headline numbers below come from the regenerated `results.json`".

**C. Arithmetic slip in the swap exhibit sentence.** "~18 pp of fan share" — the reported predictions give 0.1656 − 0.0093 = **15.6 pp** (the ~2.2 judge-z figure is correct: 0.672 − (−1.505) = 2.177).

## Minor notes (no action required)

- The plan's sign-discipline rule "ĝ ≥ 0 for judges" is violated on the z-scale week curve (−0.04 → −0.48); the report does supply the paired absolute-score analysis (+1.52 pts/run, p<1e-6) and the survivorship-composition explanation, which is a defensible treatment consistent with the plan's "flag and explain" clause.
- The fan-surface "top-5" sentence mixes eligible and 1-season pros but flags them explicitly; the underlying `results.json` eligible list (Derek/Artem/Valentin/Chaplin/Holker) is consistent with the CSV.

## Verdict

The pipeline is deterministic, the vast majority of reported numbers reproduce exactly, all five round-1 issues are genuinely fixed, and the honesty discipline (ties, LOSO failures, sorting adjustment) is exemplary. However, the 95% band columns — a listed deliverable of the fan-share stage tied directly to the problem's certainty requirement — are computed with a mis-indexed weighted CDF and are inverted in 51% of rows, and two summary-text numbers are stale/miscomputed. One short fix plus a rerun and a two-line text edit resolves everything.

VERIFICATION_RESULT: NEEDS_REVISION
## Issues Found:
1. **`m2_fanshare.py::compute_fanshare` (weighted-quantile bands)** — `cum = np.cumsum(wts)[order] - 0.5*wts[order]` cumulates weights in **shake order** then gathers them by phi-rank; the result is not a CDF along the sorted axis (non-monotone). Shipped `model2_fanshare.csv` has `fanshare_lo95 > fanshare_hi95` in 1,422/2,777 rows (51.2%) and the posterior mean outside its own band in 2,080/2,777 (74.9%). Point estimates, sds, and all results.json numbers are unaffected (verified), but the CSV's 95%-band columns and the summary's "calibrated bands" claim are wrong as stated.
2. **`results_summary.md` (Key Results)** — Derek Hough's CI is stale: "95% CI [0.101, 1.300]" vs the regenerated `results.json`/`model2_pro_rankings.csv` value **[0.447, 0.942]**.
3. **`results_summary.md` (swap exhibit)** — "~18 pp of fan share" should be **~15.6 pp** (0.1656 − 0.0093 = 0.1563); the ~2.2 judge-z figure is correct.

## Fix Instructions:
1. In `m2_fanshare.py::compute_fanshare`, replace the two lines
   `order = np.argsort(phi_shake, axis=0).astype(np.int64)` / `cum = np.cumsum(wts)[order] - 0.5*wts[order]`
   with
   `order = np.argsort(phi_shake, axis=0).astype(np.int64)` / `w_sorted = wts[order]` / `cum = np.cumsum(w_sorted, axis=0) - 0.5*w_sorted`
   (cumulative weights along the sorted axis, per column). Rerun `python3 run.py`; assert `(pan.fanshare_lo95 <= pan.fanshare_hi95).all()` and that the point estimate lies inside the band for all rows (verified: 0 inverted rows, 100% coverage after the fix). Confirm `results.json` is unchanged (bands are not it) and that `model2_fanshare.csv` is otherwise identical (φ, sd, judge_share, run cliff columns must not move — they do not depend on this code path).
2. In `results_summary.md`, replace "(+0.662 [95% CI 0.101, 1.300])" with "(+0.662 [95% CI 0.447, 0.942])" and re-check every CI quoted in the text against the regenerated `model2_pro_rankings.csv` / `results.json` before the paper phase consumes them.
3. In `results_summary.md`, change "~18 pp of fan share" to "~15.6 pp" in the counterfactual-swap sentence.