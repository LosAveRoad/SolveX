I've reviewed the code (`model1_core.py`, `model1_validation.py`), the diagnostics CSVs, and figure outputs against the Master Plan formulation. Here is my assessment.

---

# Model 1 Review — Bayesian Fan-Vote Inversion (Elimination-Constraint Sampler)

## 1. Numerical Sensibility Check

**Plausible and internally consistent:**
- 335 season-weeks over 34 seasons (~10 weeks/season), 2,777 contestant-weeks (~8.3 active couples/week) — consistent with DWTS history.
- Additivity Σᵢ v̂ᵢw = 1 to machine precision, boundedness, and CI ordering checks pass — the outputs form valid probability vectors.
- Pooled fan-share mean 0.1206 / median 0.1047 vs. expected 1/n_active ≈ 0.10–0.15 — consistent.
- Judge↔fan correlation r = 0.833 is the right ballpark for DWTS (fans substantially track judges, with popularity deviations) — domain-plausible.
- Extreme estimates are domain-plausible: Kelly Monaco S1 W6 ≈ 0.52 at a 2-couple finale; Macy Gray S9 W1 ≈ 0.02 eliminated first with bottom judge score. Emmitt/Mario S3 W10 near 50/50 toss-up is historically correct.
- Acceptance rates quantized at 0.75, 0.375, 0.1875, 0.09375 = 3000/(4000·k) — explained by the batched rejection loop (keep 3,000 of 4,000 per batch), not a bug per se.

**What does NOT hold up:**
- `repl_prob = 1.000` for all 335 weeks is **tautological**. Draws are *defined* as feasible, so "posterior replication probability" measures nothing. The programmer flags this, which is honest, but the summary simultaneously claims it "validates sampler correctness against the ≥0.85 target." The honest out-of-sample quantity is the validation script's prior-based lift (`P(correct elimination)` under the unconditional prior ≈ 1/lift), reported in `model1_validation.py` but absent from the results summary. Only the lift, not repl_prob, should be headlined.
- Several extreme "posterior" values (e.g., Kelly Monaco 0.5207, S1 W6) come from weeks with `n_elim = 0` (finale weeks) where the feasible set is **unconstrained**. There, the reported `fan_share_mean` is essentially the *prior mean* (Dirichlet recentered on the judge-share prior exp(6·s)) — not an estimate informed by anything. Presenting prior means as posterior fan-vote estimates for finale weeks is a numerical-soundness problem for downstream models.

## 2. Model Correctness vs. the Plan Formulation — Major Deviations

This is the core problem. Three substantive mismatches between the plan's mathematics and the implementation:

**(a) The hierarchical model was never implemented.** The plan specifies z_iw = logit(v_iw) ~ N(μᵢ + δ_w + θ·s_iw, σ²), μᵢ ~ N(0, τ²), sampled by Metropolis-within-Gibbs. The code implements **rejection sampling from a truncated Dirichlet** with fixed constants θ = 6.0, κ₀ = 12.0. No μᵢ, δ_w, σ, τ appear anywhere; no celebrity-level or week-level shrinkage exists. The summary's "Model Parameters" section — claiming these hierarchical logit parameters "were sampled (Metropolis-within-Gibbs with mirror/projection moves)" — **misdescribes the code**. A truncated-Dirichlet rejection sampler is a legitimate choice in its own right, but the summary must say so.

**(b) The adaptive phase corrupts the posterior.** In `posterior_week`, accepted draws are appended to `kept` from the *very first* batch, while `q` is still being adapted (recentered toward the accepted mean) until `n_accepted_total ≥ n_adapt = 800`. The retendered sample is therefore a **mixture of truncated Dirichlets with different concentration vectors q**, not an iid sample from any single distribution. The docstring's claim ("phase 2 freezes q and produces genuine iid posterior samples –> ESS = N") is false as coded. The 90% credible intervals — the deliverable that answers "how much certainty" — are computed from an ill-defined mixture, so the central uncertainty claim of Model 1 is not statistically valid as implemented.

**(c) The prior is recentered on v0, which was itself built from the same feasibility constraint** (`kappa = KAPPA0 * (0.25 + 0.75 * v0/v0.max())`). This double-uses the elimination constraint (once to find v0, again to reshape the prior) and systematically narrows the CIs toward the max-margin point. Combined with (b), the reported CI widths (mean 0.117) are likely **too narrow** and not interpretable as 90% credible intervals under any stated model.

**(d) Finale ordering constraints dropped from the sampler.** `point_estimate(…, order_pairs, is_finale)` enforces final-placement ordering, but `posterior_week(s, elim_idx, n_elim, rule, s28, v0, rng)` does not even accept those arguments. The plan's F_w explicitly included finale ordering (`better placement must have composite ≥`). Result: on final weeks the sampler ignores the one piece of extra ordering information, while the point estimate uses it — an inconsistency between `fan_votes_point.csv` and `fan_votes_posterior.csv`.

**Justified simplifications that are acceptable:** rank-tie handling as measure-zero in the batch path; withdrawal rows excluded from the elimination constraint; ε = 5e-4 floor on shares. The `if False else np.nan` dead expression and the `lam = 0.0`, `kappa * (1 + 0.0)` dead lines in `parse_data`/`posterior_week` are sloppy but harmless (the share is recomputed by groupby afterward).

## 3. Completeness

All artifacts are present and verified on disk: `model1_core.py`, `model1_validation.py`, `weekly_panel.csv` (spot-checked: S1 W1 has 6 active, rank rule, plausible margins), `fan_votes_point.csv`, `fan_votes_posterior.csv`, `weekly_diagnostics.csv`, and the three figures. Checks V1–V4 in the validation script are appropriately designed (the prior-lift forward test is a genuinely good idea). The validation script *does* print the lift and rule-disjointness diagnostics, but none of those lift numbers or disjointness fractions are reported in `results_summary.md`.

## 4. Known Issues

The summary flags non-identifiability, season-28 rule ambiguity, low-acceptance weeks, and the tautological repl_prob — all correctly identified. What it fails to flag are the four substantive deviations above, and in one case it actively misreports the method (Metropolis-within-Gibbs/hierarchical claim).

---

## VERDICT

The pipeline is exactly reproducible laterally (point estimate, feasibility logic is sound and delta-checked), and *stated* sanity checks mostly pass, but the uncertainty quantification — the core question this model exists to answer ("how much certainty, and is it uniform?") — rests on an ill-defined mixture posterior with a data-dependent prior and an incomplete constraint set on finale weeks, and the summary misdescribes the implemented method relative to both the plan and the code. These are fixable without redesigning the model: repair the sampler mechanics and correct the description, or honestly implement the plan's hierarchical sampler.

## Issues Found:
1. **Posterior is an undefined mixture**: `posterior_week` in `model1_core.py` retains draws accepted during the adaptive phase (while `q` is still being recentered up to draw 800), so the 3,000 retained draws are not iid from any single distribution; the reported `lo90/hi90/cv/ci_width` are not valid 90% credible summaries of a stated model.
2. **Data-dependent prior double-uses the constraint**: `kappa = KAPPA0 * (0.25 + 0.75 * v0/v0.max())` reshapes the Dirichlet prior using `v0`, which was obtained by maximizing the elimination margin under the same feasibility constraint — inflating apparent certainty (mean CI width 0.117 likely understates true uncertainty).
3. **Plan-model not implemented but claimed**: no hierarchical prior z_iw = logit(v_iw) ~ N(μᵢ + δ_w + θ·s_iw, σ²) with μᵢ ~ N(0, τ²), and no Metropolis-within-Gibbs; the code is a truncated-Dirichlet rejection sampler with fixed θ = 6.0, κ₀ = 12.0. The Summary's "Model Parameters" section is inaccurate.
4. **Finale ordering constraint missing from the sampler** while present (correctly) in the point estimate — point estimate and posterior are inconsistent on final weeks.
5. **`repl_prob = 1.0` headlined as hitting the ≥ 0.85 target** is tautological; the informative prior-lift statistic computed in `model1_validation.py` (V1) is omitted from the summary.
6. Dead/non-functional code lines in `parse_data` (the `... if False else np.nan` judge-share expression) and `posterior_week` (first `kappa` assignment, `lam`, `kappa*(1+0.0)`) — harmless to output but should be removed to guarantee the reviewed code is the operative code.

## Fix Instructions:
1. In `model1_core.py` / `posterior_week`: freeze the proposal *before* retention — collect the first `n_adapt` accepted draws only for adaptation, `q = KAPPA0 * (0.25 + 0.75 * accepted_mean/accepted_mean.max())`, **discard those draws**, then run Phase 2 with fixed `q` and retain only Phase-2 accepted draws; recompute `lo90, hi90, mean, cv` from Phase 2 only. Report per-week effective retention.
2. Either (a) remove the `v0`-recentering and use the fixed judge-informed prior `q_i ∝ exp(θ·s_i)` with κ₀ = 12 for all weeks (re-run everything; CI widths will grow), or (b) keep the recentering but explicitly declare it an empirical-Bayes shrinkage prior in the summary and add the shrinkage to the uncertainty discussion. Prefer (a) for defensibility.
3. Pass `order_pairs` and `is_finale` into `posterior_week` and include the finale ordering test in the vectorized `feasible()` (for each batch row, require c[i] ≥ c[j] − TOL for all ordering pairs), matching `feasible_single`.
4. Rewrite the "Model Parameters" section of `results_summary.md` to describe the actual implemented model (truncated Dirichlet posterior p(v|E) ∝ 1[v ∈ F_w]·Dir(v; q), q_i ∝ exp(θ·s_iw)) and delete the Metropolis-within-Gibbs / hierarchical-logit claims; OR implement the planned hierarchical sampler in a follow-up variant. Either path makes report = code.
5. Add the V1 prior-lift statistics (mean, median, min of unconditional P(correct elimination)) and the V3 rule-disjointness week counts to `results_summary.md`; demote `repl_prob` to a sampler-correctness footnote there as well (it is already correctly footnoted in Limitations).
6. Delete the dead lines noted in Issue 6 from `model1_core.py` and re-run to confirm identical outputs (diff the four CSVs).

VERIFICATION_RESULT: NEEDS_REVISION