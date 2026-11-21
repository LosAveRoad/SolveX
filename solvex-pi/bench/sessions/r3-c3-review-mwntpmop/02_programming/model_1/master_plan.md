# Master Plan — Model 1: Bayesian Fan-Vote Inversion (Elimination-Constraint Sampler)
(Placed here because 01_modeling/ is read-only for this parallel task; content identical to the plan's Model 1 section.)

## Purpose
Estimate the hidden weekly fan-vote share v_iw for every contestant i in week w, with
certainty measures, using the only hard signal available: who survived each week.

## Mathematical Formulation
- Known: judge score share s_iw = j_iw / Σ_k j_kw (judge points j normalized within week),
  elimination status E_iw, combination rule R(season):
    * rank method (seasons 1–2 and assumed ≥28): composite = rank(s) + rank(v), lowest eliminated;
    * percentage method (seasons 3–27): composite share ∝ s·v normalized, lowest eliminated.
- Latent feasible region: F_w = { v_w : Σ_i v_iw = 1, v_iw ≥ ε, R(season) applied to
  (s_w, v_w) reproduces observed elimination E_w }. For season ≥ 28 the bottom-two set and
  judges' tiebreak are encoded in F_w.
- Prior: z_iw = logit(v_iw) ~ N(μ_i + δ_w + θ·s_iw, σ²), hierarchical celebrity-mean
  μ_i ~ N(0, τ²); popularity prior mixes technical quality s_iw with celebrity appeal.
- Posterior: p(v|E,s) ∝ Π_w 1[v_w ∈ F_w] Π_i N(z_iw; μ_i + δ_w + θ·s_iw, σ²).

## Solution Strategy
1. Parse CSV → per-week panel (couple, judge points, judge rank, eliminated flag, season).
2. Build per-week composite under the season's rule; identify feasible polytope F_w.
3. Constrained MCMC: Metropolis-within-Gibbs over logit-space popularity parameters with
   mirror/projection moves inside F_w; ~200k draws with thinning; numpy vectorized,
   scipy only for auxiliary checks.
4. Inverse-optimization cross-check: per week, point estimate v̂ maximizing closeness of
   composite scores (max-margin slack subject to feasibility) — provides a deterministic
   reference map.
5. Posterior summaries: v̂_iw mean, 90% credible interval, coefficient of variation,
   effective sample size, per-week elimination-replication probability p(match|v^(m)).

## Validation
- Forward test: each retained posterior draw re-run through R(season); consistency metric =
  fraction of weeks where replicated elimination matches history (target ≥ 0.85 overall;
  1.00 by construction inside feasible sets, reported as check of sampler correctness).
- Hold-out: double-elimination weeks handled explicitly; log-odds width of CIs compared
  across weeks to answer "is certainty constant?" (expected: no — small weeks/strong judge
  margins → tighter; large fields → wider).
- Diagnostics: compare rank-based vs percentage-based feasible regions per week; flag
  weeks where the two rules admit disjoint regions (method-sensitivity warning).

## Expected Outputs
- contestant_week_fan_votes.csv: v̂_iw, 90% CI bounds, CV, season, week, judge share.
- weekly_diagnostics.csv: replication probability, CI width, feasibility status.
- Figures: fan-vote vs judge-share scatter, CV-by-week heatmap, CI width distribution.
