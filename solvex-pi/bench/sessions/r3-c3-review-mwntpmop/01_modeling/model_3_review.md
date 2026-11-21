# Review — Model 3: Hierarchical Driver Model (Judge vs. Fan Channels)

## 1. Numerical sanity

**Coefficient contrasts — internally consistent.** The arithmetic checks out across all three reported contrasts:
- age: fan β = −0.278, judge β = −0.125 → Δ = −0.153 ✓
- athlete: +0.118 / +0.068 → Δ = +0.050 ✓
- fame tier: +0.076 / +0.049 → Δ = +0.027 ✓

The HDI/P(Δ>0) pairs are also mutually consistent: e.g. athlete Δ = +0.050 with HDI [−0.064, +0.163] implies SD ≈ 0.058, giving P(Δ>0) = Φ(0.050/0.058) ≈ 0.81, matching the reported 0.820. Similarly fame Δ = +0.027, SD ≈ 0.025 → P ≈ 0.86 ≈ 0.882 ✓; age Δ = −0.153, SD ≈ 0.023 → P > 0 ≈ 0 ✓.

**Signs and magnitudes are plausible.** Negative age effects in both channels (fans penalize age ~2× harder) matches domain knowledge; athlete/fame bonuses positive in both channels; pro-identity variance larger in the fan channel and season variance larger in the judge channel are both sensible.

**Variance partitions are coherent.** Fan: 49.6 + 11.2 + 39.2 = 100.0 ✓. Judge: 11.1 + 57.6 + 31.4 = 100.1 ✓ (rounding). The implied fixed-effect variances back out consistently from SDs (s_pro² = 0.315² ≈ 0.099 → 49.6% of total ≈ 0.200 ✓; 0.076² ≈ 0.0058 → 11.1% of total ≈ 0.052 ✓).

**Consistency fractions:** 0.752 + 0.248 = 1.000 ✓.

**PROBLEM — sample-size numbers are contradictory.** The report states "335 couple-weeks" of data used, but the output panel has **3,335 rows**, and 421 couples over 34 seasons at ~9–10 weeks each implies ~3,500–4,000 couple-weeks (3,335 is the plausible count; "335" is not). Critically, the fame-tier counts 184 + 27 + 124 = **335** confirm the regression actually ran on 335 rows — i.e. ~90% of the panel was silently dropped. This is the single most serious defect: it makes the reported SDs, CIs, and variance partitions products of a 10-times-smaller sample than claimed.

## 2. Model correctness vs. the plan

- **Formulation match (partial).** Beta regression with logit link, fixed effects (age, athlete, fame tier), pro and season random effects, weakly informative priors, and the Δ = β^fan − β^judge contrast all match the master plan. Simplification from multiplicity of pro names was disclosed.
- **Deviation from plan:** Response 2 was specified as "posterior fan-vote share E[v_iw] from Model 1," but the implementation instead uses shares *identified* through the rank formula fan_rank = 2·comb_rank − judge_rank. The formula itself is correct for the rank-combination method (it inverts comb_rank = (judge_rank + fan_rank)/2), BUT:
  1. It is only valid in seasons where the show combined by **ranks**. In percentage-method seasons (≈2–27), combined score is a weighted *percentage*, so comb_rank is not the average of ranks; applying the rank formula there mis-identifies fan shares. This was partially flagged but not fixed.
  2. Clipping to [1, N] induces point mass at the boundaries, which conflicts with the Beta(μ, φ) likelihood assumed for the regression — a likelihood/identification mismatch that is **not** acknowledged anywhere.
- **Missing validation component from the plan:** leave-one-season-out prediction error vs. baselines was explicitly in the plan's Validation section and is absent from the results report.

## 3. Completeness

- Present: fan_vote_estimates.csv, delta_summary.csv, pro rankings (top/bottom), channel fit summary, meta JSON, 3 figures (forest Δ, variance partition, pro ranking). Adequate coverage.
- Absent: LOSO validation; a defined target/definition for the reported wRMSE values.

## 4. Known issues — flagged but not sufficient

- The RMSE discrepancy (naive 0.824 vs model 0.884) is flagged, but the metric itself is not reproducible as described: if the naive baseline sets fan share = judge share, its within-week deviation from judge share is identically **zero** — an RMSE of 0.824 is impossible against that target. Whatever denominator/target the 0.824 and 0.884 were computed against is undocumented, so the headline fit numbers cannot be verified.
- 144 pro levels (fragmented by episode annotations) against 335 observations is hopelessly overparameterized for a random effect; this compounds the 335-row problem.
- Beta-replication PPC proxy instead of a full PPC: acceptable as flagged.

## Verdict

The Bayesian machinery, contrasts, and variance arithmetic are internally consistent and the qualitative conclusions (fans ≠ judges on age; pro identity dominates fan channel; season dominates judge channel) are sound. But (a) the 335 vs 3,335 data-count contradiction means the model ran on a silent 90%-reduced sample, (b) two headline fit numbers (0.824/0.884) are unverifiable/underdefined, (c) the rank-identification formula is mis-applied to percentage-method seasons with boundary clipping that contradicts the Beta likelihood, and (d) the planned LOSO validation was never run.

VERIFICATION_RESULT: NEEDS_REVISION
## Issues Found:
1. **Sample size contradiction:** report claims "335 couple-weeks" but panel has 3,335 rows; fame-tier counts (184+27+124) sum to 335, confirming the regression used only 335 observations — ~90% of the melted panel dropped without explanation. All SDs, HDIs, R-hat/ESS claims and variance partitions rest on this wrong N.
2. **Unverifiable RMSE metric:** naive baseline (fan share = judge share) has identically zero deviation from judge share, yet reported baseline wRMSE = 0.824 (and model 0.884); the target and normalization defining these numbers are undocumented and as-stated arithmetically impossible.
3. **Mis-specified identification across seasons:** fan_rank = 2·comb_rank − judge_rank applies only to rank-combination seasons; applied (clipped) to percentage-method seasons it mis-identifies fan shares, and clipping puts point mass at [1, N] that contradicts the Beta(μ, φ) likelihood assumed in the regression.
4. **Missing validation from plan:** leave-one-season-out prediction error vs. baselines (explicit plan requirement) not performed or reported.
5. **Identification fragility (secondary):** 144 pro random-effect levels against 335 (mis-stated) observations; episode-annotation name fragmentation inflates σ_pro and the 49.6%/11.1% channel contrast.
## Fix Instructions:
1. Edit the data-preparation function in the Model 3 pipeline: after melting weekly judge scores, verify every couple-week has non-missing (judge_share, age, athlete, fame_tier) and keep all ~3,335 rows; re-run both Bayesian channels and regenerate delta_summary.csv, channel_fit_summary.csv, model3_meta.json, and all three figures with the corrected N (~3,335). Correct the "335 couple-weeks" claim in the results report.
2. Edit the evaluation function that computes wRMSE: define the target explicitly (e.g. identified fan_share vs. Model 1 posterior fan share, or reproduction of comb ranks), document the formula in channel_fit_summary.csv, and re-report baseline vs. model wRMSE (the baseline cannot be judged-share-vs-itself, which gives 0).
3. Restrict the rank-formula identification (fan_rank = 2·comb_rank − judge_rank) to rank-method seasons (1 and ~28+); for percentage-method seasons (≈2–27) derive fan share from the percentage combination comb_pct = w·judge + (1−w)·fan by solving for fan_share = (comb_pct − w·judge_pts)/((1−w)·judge_max), or fit those weeks with a binomial likelihood on estimated vote totals instead of off-constraint clamped shares. Remove or justify the clip: replace the hard [1, N] clip with a truncated/reparameterized likelihood consistent with Beta(μ, φ).
4. Implement the planned leave-one-season-out validation: for each season s, fit both channels excluding s, predict held-out elimination ranks, and report normalized error vs. (i) the naive baseline and (ii) the judge-proportional baseline; add results to model3_meta.json and a figure.
5. Clean pro names (strip episode annotations via regex `\(.*\)` on the pro column) to collapse 144 levels to the true pro count (~50), and re-fit the fan channel to stabilize σ_pro before re-stating the 49.6% variance-partition figure.