# Master Plan — 2026 MCM Problem C: "Data With The Stars"

## Overview
Three sub-problems drive the analysis: (A) inverse-infer the secret weekly fan votes that are
consistent with every observed elimination; (B) run counterfactual What-If seasons under both
combination rules (rank-based and percentage-based) plus the judges-save rule to detect
outcome sensitivity; (C) decompose performance into celebrity-drawn and pro-dancer effects to
recommend a fairer combination mechanism.

Overall strategy — an inverse-problem formulation, deliberately "identification-first": rather
than fitting a black-box predictor, Model 1 computes the FEASIBLE SET of fan-vote vectors and
picks a maximum-entropy point estimate inside it, propagating that uncertainty forward. Model 2
consumes the feasible sets (not just point estimates) of Model 1 so counterfactual claims are
made with honest error bars. Model 3 splits judge-driven vs. fan-driven signal, feeding back into
Model 2's controversy cases and motivating the new fairness mechanism in C.3.

Data pipeline: parse data/2026_MCM_Problem_C_Data.csv → wide-to-long table indexed by
(season, week, celebrity, pro, dance, judge_score, result) → engineered features (judge rank
within week, percent-of-max, prior-week survival count, contestant demographics).

---

## Model 1: Maximum-Entropy Fan-Vote Inversion with Elimination Constraints (ME-FVI)
### Purpose
Recover weekly fan vote estimates ū_{i,w} (per contestant i, week w) that are NOT observable but
must jointly reproduce the recorded outcome: the eliminated couple is (approximately) the lowest
combined-scoring couple that week. This converts a hidden-variable problem into a constrained
optimization problem and provides calibrated certainty (plausible fan-vote intervals).

### Mathematical Formulation
Let J_{i,w} = normalized judge score share of couple i in week w (J_{i,w} = s_{i,w} / Σ_k s_{k,w}).
Normalize fan votes to shares: F_{i,w} = u_{i,w} / Σ_k u_{k,w}, so Σ_i F_{i,w} = 1.
Combined score under rule r ∈ {rank, pct}: C^r_{i,w} = α·J^r_{i,w} + (1−α)·F_{i,w}, with α = 0.5
in the show's rule. Eliminated couple e_w must satisfy:
    C^r_{e_w,w} ≤ C^r_{i,w} − γ   ∀ i ≠ e_w, i surviving    (margin γ ≥ 0, slack allowed)
Also, j-th-ranked judge couple shouldn't finish BELOW the eliminated couple with probability > δ_{rank}
(bounded inconsistency, gives rise to Model-1's report metric).
Objective (max-entropy / min-KL deviating from a weak prior q_{i,w} = flat or judge-proportional):
    maximize  H(F) = −Σ_i F_{i,w} log(F_{i,w} / q_{i,w})   subject to above margins, F ∈ Δ_W.
Equivalently solve min Σ_w Σ_i (F_{i,w} − q_{i,w})² or KL divergence subject to linear constraints
(→ Convex QP with a simplex per week).

### Solution Strategy
1. Build long-format table; for each week compute judge-share vector J^pct_{·,w} and its rank
   percentile J^rank_{·,w} (rank method: normalize rank to [0,1], invert orientation higher=better).
2. Solve the QP per week with cvxpy / scipy.optimize (SLSQP fallback) to get u* consistent with
   margin γ.                         3. Refine with bootstrapped / simulated annealing (e.g., a
   few hundred perturbations around u*, swapping in stochastic margins γ = μ + ε̄) to produce
   u*_k sample j → empirical distribution of F_{i,w}, giving 90% prediction intervals.
4. Certainty metric: width/2 relative to the point estimate, expected to differ by contestant
   popularity vs. judge-score gap (Model 1 reports a table ū_ik(90%)).

### Expected Outputs
- ū_{i,w} point estimates and [5%, 95%] predictive intervals per contestant-week.
- Consistency check report: fraction of weeks where the inferred fan vector's argmin_C equals the
  true elimination (target ≥95% on observed data); per-season elimination consistency matrices.
- Heatmap of fan-vote vs. judge-score divergence per celebrity-week ("entertainment gap").
- Weekly uncertainty plot: interval half-width vs. week number (should shrink toward finale,
  detectable via Gini-style dispersion of surviving couples).

### Validation
- Hold-out check: fit ū on weeks 1..w−1 only; verify that the HIGHEST-entropy solution with
  γ = 0 still predicts the single known elimination in week w with correct margin sign.
- Null-model comparison: random fan-vote vectors drawn Dirichlet-consistent with label smoothing
  must FAIL to reproduce eliminations (empirical χ² or permutation test, p < 0.01).
- Sanity check against well-documented cases (Bobby Bones, Jerry Rice, Bristol Palin) — high fan
  share, low judge share must appear under both rank and pct rules.

---

## Model 2: Counterfactual Season Re-Play under Rank / Percent / Judges-Save Rules (CSR)
### Purpose
Replay every season 3–34 under BOTH combination rules (rank-based s1–2 style and percent-based
s3+ style) plus the judges-save mechanism introduced in s28, using Model 1's fan-vote samples as
input. This measures (i) outcome flip frequency by rule, (ii) whether one rule systematically
favors fan votes, and (iii) specifically what would have happened to Jerry Rice, Billy Ray Cyrus,
Bristol Palin, and Bobby Bones under each rule / save variant.

### Mathematical Formulation
Rule RANK (used s1–2, assumed reintroduced s28): convert both judge scores and fan-vote totals
to per-week integer ranks r̂^J_{i,w}, r̂^F_{i,w}; combined score C^RANK_{i,w} = r̂^J_{i,w} + r̂^F_{i,w};
eliminate argmin_i C^RANK (ties broken by fan rank, as is documented show practice).
Rule PCT (s3+): C^PCT_{i,w} = ½ · (J_{i,w}/Σ J + F_{i,w}/Σ F); eliminate argmin C^PCT.
Judges-Save variant: identify bottom-two set B = {argmin, argmin₂} of C; outcome becomes
 e_w ∈ B chosen by a stochastic "judge-preference" draw
     P(save i | i ∈ B) = σ( κ · (J_i − J_j) + η · (〈pro effect〉_i − 〈pro effect〉_j) )
 with κ, η fitted by Maximum-Likelihood on the s28+ seasons where the save WAS used.
Flip probability per contestant i: Φ_i = P_r [ placement_R(r) ≠ placement_P(r) ] over Model-1
bootstrap samples k (an honest Monte Carlo over fan-vote uncertainty).

### Solution Strategy
1. Simulate an entire season week-by-week with eliminations applied progressively, since
   eliminating one couple changes subsequent weeks' relative ranks (a NON-separable path
   dependence — must re-run the chain, not just per-week scoring).
2. For each season s: replay under 4 variants {RANK, PCT} × {no-save, judges-save}; replicate over
   500 Model-1 fan-vote bootstrap samples to get flip-probability distributions.
3. Special-case analysis: force-reconstruct the actual s2/s4/s11/s27 trajectories, then overlay
   the alternative rule to trace the first week where the alternate rule changes the story.
4. Fit κ (judge save-tendency) on s28+ data via pooled logistic regression; report CI.
5. Aggregate metric: "fan-favor index" f_r = mean over weeks of (fan-share weight that flipped
   the elimination under rule r vs. judge-only ranking) — checks whether RANK vs. PCT systematically
   privileges fans.

### Expected Outputs
- Table of final placements per season under both rules (observed vs. counterfactual), with
  flip-probability Φ_i per notable celebrity.
- Bar chart: seasons in which switching rank↔percent changes the TOP-3 or the WINNER.
- Convergence plot: cumulative flip-probability vs. bootstrap sample size (shows result stability).
- "Divergence map": per celebrity-week, |judge percentile − fan percentile|, colored by survival.

### Validation
- Reproduce observed outcomes: under each season's TRUE historical rule (rank for s1–2 & s28+,
  pct for s3–27), the simulated season must match the recorded eliminations in ≥95% of bootstrap
  replicates (upper-bounded by Model 1's inferential uncertainty).
- Cross-check s28+ seasons: with judges-save ON, Model 2's e_w must equal the actual saved-vs-
  eliminated pair (validates κ, η).
- Sensitivity to α (the 50/50 mix): sweep α ∈ [0,1] and record flip probability — guards against a
  knife-edge artifact of the 50% weighting.

---

## Model 3: Decomposed Judge/Fan Effect Model + Fairness-Optimized Combination Rule (DFE-FO)
### Purpose
(A) Explain how pro-dancer identity and celebrity attributes (age, industry, gender, prior fame,
dance experience proxy) drive judge scores vs. fan votes — testing whether pros and traits bias
the two audiences differently. (B) Use the decomposition to propose a NEW combination rule that
maximizes a fair-and-exciting objective (trade-off: merit fidelity vs. sustained viewer interest),
and benchmark it against rank/percent.

### Mathematical Formulation
Hierarchical Bayesian regression with separate equations for judge scores and log-fan-votes.
Let y^J_{i,w} and y^F_{i,w} = log ū_{i,w} be responses for couple i in week w. Model:
    y^J_{i,w} = μ^J + β^J·x_i + θ^J_{pro(i)} + ν^J_{dance(i,w)} + a_i + ε^J_{i,w}
    y^F_{i,w} = μ^F + β^F·x_i + θ^F_{pro(i)} + ν^F_{dance(i,w)} + b_i + ε^F_{i,w}
with:
  x_i  = celebrity covariates (age, gender, industry one-hot, prior-fame proxy, dance-experience)
  θ^J_p, θ^F_p = pro-dancer random effects (partially pooled: θ ∼ N(0, σ_θ²))
  ν_dance  = dance-style fixed effects (e.g., samba vs. waltz difficulty)
  a_i, b_i = couple random intercepts (talent/popularity quality)
  ε ∼ N(0, σ²_w) with week-level variance allowed (heteroskedasticity).
Key comparison metric: Δ_p = θ^F_p − θ^J_p (pro's fan-appeal vs. judge-appeal) and analogously
Δ_β = β^F − β^β per celebrity trait — a "who-values-what" decomposition.
New rule (C.3): choose combination weights ω = (ω_J, ω_F) and a "suspense bonus" τ for
survived-couples to optimize
   max_ω,τ   λ·Fairness(ω,τ) + (1−λ)·Excitement(ω,τ)
   Fairness = 1 − P(best-judge couple eliminated before top-3)  (from Model 2 sim)
   Excitement = normalized Gini-dispersion of weekly combined scores ∪ longevity variance
   subject to ω_J + ω_F = 1, τ ∈ [0, 0.15].

### Solution Strategy
1. Fit hierarchical model via PyMC (MCMC, NUTS) with priors on σ_θ, σ_β; use Model 1's ū_{i,w}
   posterior samples as multiple imputations (stacked imputation → accounts for fan-vote noise).
2. Report posterior credible intervals on θ^J_p, θ^F_p, andΔ_p; plot pro-dancer fan-appeal vs.
   judge-appeal biplot (identifies "charisma" pros like Derek Hough-types vs. "technical" pros).
3. Trait effect forest plot with 95% CrIs for age / industry / gender on both audiences.
4. Solve the (ω, τ) optimization by grid / Bayesian optimization (scikit-optimize) coupled with
   Model 2's season-replay simulator as the objective map ω,τ → (Fairness, Excitement).
5. Benchmark proposed rule against rank and percent on: winner match with best-judge causet,
   average surviving-couple score gap, top-3 composition entropy.

### Expected Outputs
- Pro-dancer effect biplot (θ^J vs θ^F with CrI ellipses) and celebrity-trait forest plot.
- Pareto frontier: Fairness vs. Excitement over (ω, τ); recommended operating point highlighted.
- Headline regression table: effect sizes + uncertainty for each attribute, separately for judges
  and fans, with a "Δ column" answering "do they impact judges and fans the same way?"
- Final recommendation memo paragraph: which rule + whether to add judges-save.

### Validation
- Posterior predictive checks (PPC): distribution of y^J/y^F residuals per season must match noise.
- LOO / WAIC cross-validation: hierarchical model must beat pooled OLS and a no-pro null model
  (Δelpd > 0 with SE) for both judge and fan equations — otherwise trait claims are retracted.
- Sensitivity analysis: re-fit on the 90% upper / lower bound of fan votes from Model 1 to confirm
  sign-stability of all reported trait and pro effects.
- Rule validation: optimization result must be an INTERIOR Pareto point (not edge-dominated by
  existing rank/percent rules), confirmed via stochastic dominance of simulated outcome vectors.

---

## Integration
Model 1 → supplies posterior samples of ū_{i,w} (the hidden fan votes) to Models 2 & 3 with
calibrated uncertainty. Model 2 → consumes samples, replays counterfactuals, identifies flip
cases (Jersey-Rice/Bristol/Bobby), and supplies the Fairness/Excitement simulator returning to
Model 3's (ω, τ) optimization. Model 3 → feeds the fitted judge-save propensity κ, η back into
Model 2 for the s28+ validation, and its Fairness/Excitement Pareto optimal (ω*, τ*) is the final
recommended rule set, cross-validated on the same simulator. Final deliverables: elimination-
consistency report, certainty intervals, rule-comparison tables, controversy counterfactuals,
pro/celebrity effect atlas, and the fairness-optimized recommended mechanism with full
uncertainty quantification at every step.
