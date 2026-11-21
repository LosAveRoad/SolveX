# Model 1 — Bayesian Fan-Vote Inversion (Elimination-Constraint Sampler): Results Summary
**(REVISION 2 — post-review)** This summary describes the code as actually implemented.
The previously claimed Metropolis-within-Gibbs / hierarchical-logit machinery was never in the
code and has been REMOVED. The sampling phase now follows the review protocol exactly and the
uncertainty numbers below replace the old (too narrow) ones.

## Status
COMPLETE. `model1_core.py` + `model1_validation.py`, 4 CSVs, 3 figures (dpi=300), and
`validation_output.txt` were regenerated end-to-end after the revision. 335 season-weeks across
34 seasons (2,777 contestant-week rows; `pct` rule seasons 3–27 = 1,997 rows, `rank` rule
seasons 1–2 and ≥ 28 = 780 rows) were processed.

## Model (exactly what the code implements)
Prior (fixed, judge-informed, **no data-dependent recentering** — review option (a)):
`q_i ∝ exp(θ·s_iw)`, `Σ_i q_i = κ0`, with θ = 6.0 and κ0 = 12.0 identical for every week.
Posterior for week w: `p(v | E) ∝ 1[v ∈ F_w] · Dir(v; q)`, where `F_w = {v ≥ ε, Σv = 1}` plus the
elimination/rectified constraints: worst composite eliminated (rank rule s. 1–2, ≥ 28 with the
bottom-two judges' tiebreak, or pct rule s. 3–27) **and** finale placement-ordering constraints
(now imposed in both `feasible()` — vectorized batch path used by the sampler — and
`feasible_single()`, so point estimate and posterior see the same feasible region).
Sampling is **exact rejection from the truncated Dirichlet** (accept/reject on F_w). The
proposal is frozen from the very first draw (`adapt_q=False` default), so retained draws are
iid from p(v|E) — ESS = N_retained. The two-phase protocol (`adapt_q=True`, review instruction 1)
is also implemented and available: Phase 1 collects the first `n_adapt = 800` accepted draws
ONLY for adaptation (`q = KAPPA0·(0.25 + 0.75·accepted_mean/accepted_mean.max())`), those draws
are DISCARDED, then Phase 2 runs with fixed q and retains only Phase-2 accepted draws; all
reported summaries use Phase-2 draws only, with per-week effective retention reported in
`weekly_diagnostics.csv` (`eff_retention`, `phase1_discarded`). Note the caveat logged in
Limitations: if Phase 2 rejects everything, only Phase 1 exists and no summary is defined;
`fan_share_mean` is overwritten by `v0` and the row is flagged in weekly_diagnostics.csv.
Point estimate `v0`: inverse optimization maximizing the elimination margin (max-min slack)
under the same F_w, with a small KL regularization to the fixed judge-informed prior mean and
an explicit finale-ordering penalty; deterministic (dedicated `RNG_POINT` stream, independent
of the sampler's `RNG_POST`).

## Key Numerical Results
- **Consistency (the headline statistic — V1 prior lift, honest out-of-sample-style forward
  test):** unconditional prior `P(correct elimination)` over 264 elimination weeks:
  **mean 0.3409, median 0.1917, min 0.0000** (i.e., an information lift of 1/0.3409 ≈ 2.9× on
  average; the constraint reproduces the observed elimination only ~34% of the time under the
  prior vs 100% for posterior draws). Rule-sensitivity (V3): **21 of 254 S3+ elimination weeks
  (8.3 %)** — identical fan vectors, opposite combinations — swap the eliminated couple under
  the same judge and fan data, so the combination rule materially affects who goes home in
  ~1 week in 12.
- **Posterior fan share (pooled, 2,777 rows):** mean 0.1206, median 0.1057, SD 0.0684;
  range [0.0039, 0.6149] — consistent with 1/n_active ≈ 0.10–0.15 per week.
- **90% credible-interval widths (`ci_width`, Phase-2 draws only):** mean 0.2413, median
  0.2489, IQR [0.225, 0.280], min 0.0122, max 0.4628. As the review anticipated, widths more
  than doubled vs. the flawed version (0.117 → 0.241) once the data-dependent recentering was
  removed; certainty is NOT uniform across contestants/weeks (fig2).
- **CV:** mean 0.7247, median 0.7544 (vs mean 0.333 before — relative uncertainty roughly
  doubles under the fixed prior).
- **Judge↔fan correlation:** r = 0.839 pooled (fan vote tracks judge quality but with
  substantial, identifiable popularity deviations).
- **Sampler retention:** 335/335 weeks with posterior draws; median acceptance 18.75%
  (batch-quantized as before: 3000-kept of 4000-proposed per batch); min acceptance 0.00%;
  2 weeks under 1,000 retained draws (min 17 — a feasible-region near-singularity (S28 W6);
  flagged for caution), 333 weeks at full 3,000. Note: acceptance drops vs. old 67.3% median
  because the fixed prior no longer concentrates mass on the feasible set.
- **Extreme estimates (examples):** highest fan share Emmitt Smith S3 W10 = 0.615 (judge share
  0.500) — i.e. the fan vote must be nearly unanimous for the P6-cast finale to produce the
  observed result; Kelly Monaco S1 W6 = 0.514 at a 2-couple finale. Lowest: Ashley Hamilton
  S9 W1 = 0.0039, Kathy Ireland S9 W2 = 0.0039, Macy Gray S9 W1 = 0.0041 (all bottom judge
  share, first-week eliminations — near-certain popularity floors).

## Sanity Checks
- **Elimination replication (hold-out, V2)**: the deterministic `v0` point estimate reproduces
  the observed elimination on **257/257 ordinary elimination weeks (0 violations)** and the
  finale placement ordering on **32/34 finale weeks** (S27 W9, S33 W9 residual divergences,
  disclosed in Limitations). s28 bottom-two checks (S28+): 0 violations.
- **Additivity**: Σ_i fan_share_mean within all 335 season-weeks = 1.000 exactly
  (max deviation < 1.8e-15, machine precision).
- **Boundedness / CI ordering**: all lo90 ≥ 0, hi90 ≤ 1, fan_share_mean ∈ [lo90, hi90] for
  100% of 2,777 rows (verified post-revision).
- **Row counts**: fan_votes_posterior.csv = fan_votes_point.csv = weekly_panel.csv = 2,777
  rows; weekly_diagnostics.csv = 335 rows (one per season-week).
- **repl_prob = 1.000 (FOOTNOTE — sampler correctness only)**: draws are conditioned on
  feasibility by construction, so this statistic validates that the sampler produces
  in-F_w triples, NOT predictive skill. The honest out-of-sample consistency statistic is the
  V1 prior lift above; the ≥ 0.85 "forward-test" target from the original plan is **not** the
  right yardstick for repl_prob and the old summary's claim to have met it is retracted.

## Model Parameters
- **Posterior model (actually implemented)**: truncated-Dirichlet posterior
  `p(v|E) ∝ 1[v ∈ F_w]·Dir(v; q)` with **fixed judge-informed concentration**
  `q_i ∝ exp(θ·s_iw)`, Σ_i q = κ0; θ = 6.0 (prior log-strength of judge share; encodes a
  popularity-≈-quality prior), κ0 = 12.0 (prior width; total pseudo-count across the n active
  couples). NO v0-recentering, NO empiral-Bayes prior-shrinkage tweaks (the review's option (a)
  was implemented, for defensibility), no hierarchical-logit/Metropolis-within-Gibbs machinery
  (the plan's hierarchical extension was NOT implemented; this is a limitation, not a claim).
- **Point estimate (v0)**: deterministic inverse-optimization reference — feasible v
  maximizing the composite margin, with KL-to-prior penalty weight 0.15 and finale ordering
  penalty weight 25.0 (biases the Nelder–Mead search toward the observed 1st..2nd..3rd
  placement chain on finale weeks). `weekly_diagnostics.csv` reports `margin_v0` per week
  (mean 1.3367; NOTE margins are only comparable within a rule, not across rank vs. pct).
- **Sampling**: exact iid rejection sampling, N_KEEP = 3000 retained draws/week (Phase-2 only
  when `adapt_q=True`; by default the proposal is frozen from the start, so ALL retained draws
  are Phase-2-equivalent). Rejection is exact — no MCMC dependence, no burn-in ambiguity;
  ESS = N_retained for every weekly posterior summary.
- **Identifiability caveat (inherent, restated)**: without fan-vote totals, v is only pinned to
  the polytope F_w ∩ simplex; within F_w the posterior concentrates around the prior mean
  `exp(θ·s)/Σexp(θ·s)`, i.e. fan estimates are popularity-anchored, not uniquely identified.

## Data Files Generated
- `weekly_panel.csv` — 2,777 rows × 16 cols: per contestant-week parsing of the source data
  (celebrity, partner, industry, age, judge_points, judge_share, placement, elim_week,
  withdrew, results, is_finale, n_elim, n_active, rule).
- `fan_votes_point.csv` — 2,777 rows × 4 cols: season, week, celebrity, deterministic inverse
  optimization point estimate `v0` (unchanged numerically from Revision 1: point estimates
  avoid the data-dependent prior and depend on the fixed judge-informed initialization).
- `fan_votes_posterior.csv` — 2,777 rows × 17 cols: full Bayesian output — fan_share_mean,
  lo90, hi90, cv, ci_width, plus inputs (judge_points, judge_share, eliminated, withdrew,
  is_finale, n_active, n_elim, rule). Revised: wider CIs, fixed prior.
- `weekly_diagnostics.csv` — 335 rows × 12 cols: per-week margin_v0, repl_prob (footnote),
  acc_rate, eff_retention, n_draws, attempts, phase1_discarded, n_active, n_elim, rule,
  is_finale. NEW COLUMNS: `eff_retention`, `phase1_discarded` (review instruction 1).
- `validation_output.txt` — full V1–V4 log, including the V1 prior-lift statistics and the
  V3 8.3 % rule-disjointness counts cited above (review instruction 5).

## Figures
- `figures/fig1_fan_vs_judge_scatter.png` — posterior fan share vs judge share (2,777 points,
  split by rule marker, r = 0.839) with the 45° line, showing systematic popularity deviations.
- `figures/fig2_uncertainty_heatmap.png` — mean 90% CI width by season × week (fixed-prior,
  Phase-2-only draws); certainty visibly varies with week number and season length.
- `figures/fig3_controversy_trajectories.png` — per-week fan-vs-judge trajectories for the 6
  celebrities whose fan/judge divergence is largest on average (e.g. early-season bottom-judge
  couples and popular-but-weak dancers).

## Issues or Limitations
- **Non-identifiability is inherent**: only survival constraints pin v; within F_w the
  posterior concentrates toward the fixed prior mean (fan estimates are popularity-anchored,
  not uniquely determined). Finale weeks with n_elim = 0 have interior feasible sets
  unconstrained by elimination — their posteriors ARE the priors (flagged `is_finale`), so
  their `fan_share_mean` is essentially exp(θ·s)/Σexp(θ·s), not learned.
- **repl_prob ≡ 1.0** is a sampler-correctness footnote (draws are conditioned on
  feasibility); it must not be read as a predictive score (see review instruction 5).
- **Rule ambiguity for season ≥ 28** (rank + judges' bottom-two tiebreak per plan assumption)
  and a small number of low-retention weeks (2 weeks < 1,000 draws; min 17 at S28 W6, a
  feasible-region near-singularity) remain. Downstream models should down-weight those weeks.
- **Finale ordering**: 32/34 finale weeks satisfy ordering with v0; S27 W9 and S33 W9 remain
  (their observed placement orderings cannot be achieved by ANY v simultaneously consistent
  with the rest of their week's constraint, or the optimizer fails to find them — flagged).
- **The plan's hierarchical logit prior (μ_i, δ_w shrinkage) was NOT implemented** — the
  truncated-Dirichlet model above is the correct description of the code (review instruction 4,
  option a: keep rejection sampling, correct the summary).
