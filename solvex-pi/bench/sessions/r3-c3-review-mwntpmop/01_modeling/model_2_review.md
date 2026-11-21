I have reviewed the master plan, the code (`model_2.py`), all 7 output CSVs, the 4 figures, and the results summary. Here is my assessment.

---

# Model 2 Review — Counterfactual Rule Engine

## 1. Numerical sanity

**Internally consistent but one headline number is an artifact (see §2).**

- Probabilities are well-behaved: P(win) ∈ [0, 0.04], P(finalist) ∈ [0, 0.94] across all 12 controversy rows; per-season flip fractions ∈ [0, 1] with correct 2.5/97.5 bounds. Verified against `controversy_cases.csv`, `rule_replay_flip_table.csv`.
- Cross-checks of summary claims against the CSVs **pass on the mean-level numbers**: mean flip rank-vs-percent = mean over S2–34 of column = 0.509 ✓ (min 0.141 at S12, max 0.761 at S28 ✓); mean κ(rank) = +0.0072 and κ(percent) = −0.0551 ✓; mean observed-rule match fraction: the `elimination_consistency.csv` actual-rule match column averages ≈ 0.52 ✓; perfect seasons 7, 14, 16, 26 at 1.00 ✓ (though S29/S31 also show 1.00 under a counterfactual rule and are unmentioned — harmless).
- Domain plausibility: Jerry Rice mean z_judge = −0.64, Bobby Bones = −0.84, Cyrus = −1.01 — consistent with the known "good dancers with low judge scores" narrative. Divergence table (Sabrina Bryan S5, Steve-O S8, Marie Osmond S5, Jerry Springer S3) matches broadcast history well.
- Certainty metrics: relative CI width ~157–211% is honest for latent, only-relatively-identified quantities; the week-1 [0.27, 1.71] vs finale-scale [8.18, 45.5] examples check out against `fan_vote_estimates.csv`.

## 2. Model correctness — **one serious scale-dependence bug**

**Critical: the percentage-rule composite is implemented on raw scales, not shares.** The plan (following Model 1's own formulation, where s_iw is the judge *share*) specifies `c = 100·(s+v)/(Σs+Σv)` with s, v as shares, which reduces to the show's actual 50/50 percentage blend. The code instead feeds **raw judge totals** (s ≈ 13–30) and **latent v̂ with mean 3.77, max 19.8** into `percent_rule_composite`. Since the normalization is order-preserving, the composite ranking is the ranking of (s+v) with **judge weight ≈ 6–8× fan weight** — purely an artifact of the arbitrary absolute scale of the lognormal latent v̂, which the programmer's own Limitation 1 admits is *"only relatively identified … should not be read as real counts."* The show's actual percentage method (per the problem's Appendix) converts judges' scores to a percentage of total judge points AND fan votes to a percentage of total votes before combining.

Consequences:
- **κ(percent) = −0.0551 and the conclusion "the percentage rule favors judges, not fans" is scale-dependent** — with share normalization (50/50 by construction) the percent composite is provably scale-invariant and would not inherit this judge tilt. This also contradicts the well-documented historical motivation (the percent rule was adopted precisely because the rank rule let Rice survive on fan votes; the model's own result — Rice P(finalist) 0.94 under rank vs 0.82 under percent, in the right direction — coexists confusingly with the κ claim).
- The rank-vs-percent flip fraction 0.509 is inflated by the same artifact.

**Secondary correctness issues:**
- The repair/procedure story is internally inconsistent: the code claims v̂ points are "repaired each week to be consistent with the observed eliminations," and `repair_week` is applied, yet observed-rule replication is only **0.523** with floors of 0.111 (S8, S17) and 0.128–0.143 (S10, S18, S20, S27, S28). Model 1's own validation target was ≥ 0.85 posterior reproducibility. A latent model whose point estimates are fit-by-design to reproduce eliminations should not miss over 45% of them; this indicates the coordinate ascent (45-point grid on a_i ∈ [−2.2, 2.2], 6 sweeps) plus a timid repair step (0.04-relative, ≤40 iters) is not converging. All downstream counterfactuals are conditioned on these under-constrained v̂.
- Plan's flip metric Φ was defined per contestant `(i,w): rule A eliminates i, rule B eliminates j ≠ i`; the implementation counts weeks where the eliminated *sets* differ. Acceptable simplification, but undocumented and it changes the metric's meaning.
- The survival-curve figure marks "(actual wk **nan**)" for all four celebrities — the `Eliminated Week (\d+)` regex returns NaN for finalists, so `axvline` renders nothing, contradicting the summary's "actual elimination week marked."

## 3. Completeness

Good: 7 CSVs (row counts verified: 102, 102, 34, 12, 14, 2,738, 3), 4 figures present and legible (survival curves show sensible ordering: rank+save suppresses low-judge/high-fan profiles earliest), reproducible seed, runtime 7 min. Conclusion/memo grounded in produced files.

## 4. Known issues

Well-flagged (latent scale, fixed τ, judges-save proxy, MC-only CIs). The flagged "absolute magnitudes are unidentified" limitation directly implies the percent-rule scale bug was foreseeable and should have been neutralized by share normalization — the one place the programmer *failed to apply* their own caveat. Also, a garbled character ("τ... approximation.妣 A hierarchical…") in Limitation 3.

---

## VERIFICATION_RESULT: NEEDS_REVISION

## Issues Found:
1. **Scale-dependence of the percentage rule (critical).** `percent_rule_composite` in `model_2.py` uses raw judge totals (s ≈ 13–30) with latent v̂ (mean 3.77). Because the composite ordering equals the ordering of s+v, judges get ≈ 6–8× the fan weight, opposed to the show's 50/50 share-normalized method. This invalidates the headline claims κ(percent) = −0.0551 ("percent favors judges"), the recommendation's point 1, and inflates the rank-vs-percent flip fraction 0.509 (which depends on the same artifact).
2. **Consistency target substantially missed.** Observed-rule point-estimate replication is 0.523 (floors 0.111 at S8/S17), far below the plan's ≥ 0.85 validation target, despite a "repair" mechanism designed to enforce it; the coordinate-ascent fit (grid 45 points, a_i ∈ [−2.2, 2.2], 6 sweeps, repair step 0.04, ≤40 iters) is under-converged and contaminates all MC counterfactuals.
3. **Survival-curve figure bug.** All four panels read "(actual wk nan)" and draw no actual-elimination marker, because finalist rows have no "Eliminated Week" match; the summary claims the week is marked.
4. **Minor:** Φ implemented as per-week eliminated-set inequality, not the plan's per-contestant definition; garbled character in results_summary.md Limitation 3; dead variable `spont`.

## Fix Instructions:
1. In `model_2.py`, change `percent_rule_composite` (and every inline percent-composite computation in `repair_week`, `fan_favor_index`, and `replay_season`) to share-normalize within each week: `s_sh = s / s.sum(); v_sh = v / v.sum(); comp = 100 * (s_sh + v_sh) / 2` (equivalently 50·s_sh + 50·v_sh). Then re-run with seed 20260115 and regenerate `fan_favor_index.csv`, `rule_replay_flip_table.csv`, `controversy_cases.csv`, `recommendation_matrix.csv`, and figures 1–3. Update the summary text wherever "percent favors judges" appears — the corrected direction must be reported honestly, even if it reverses the memo's conclusion.
2. Strengthen the consistency fit: widen the a_i grid to [−4, 4] with ≥ 101 points (two passes), raise sweeps to ≥ 20, and in `repair_week` increase the step to `0.15 * (comp[e] - comp[j] + 0.1)` with `n_iter = 200`. Add an explicit diagnostic column `repair_failed` (per season-week) to `elimination_consistency.csv`; recompute matches (target ≥ 0.85 on seasons without double-elimination irregularities) and re-propagate to all MC outputs.
3. In `parse_data` / the figure-3 block, compute actual exit week for finalists as `last_week` (or from placement: finalists exit at the finale), so `axvline` marks the true week; regenerate `survival_curves_controversies.png`.
4. Either reimplement Φ per the plan per-contestant definition or add one sentence to the summary noting the per-week set-difference simplification; fix the garbled character in results_summary.md; remove `spont`.