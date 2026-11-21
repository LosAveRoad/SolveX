# Master Plan — 2026 MCM Problem C: Data With The Stars

## Overview
DWTS combines normalized judge scores and (hidden) fan votes weekly to eliminate couples. The core inversion problem: judge scores and elimination outcomes are observed, fan vote shares are not. We exploit the fact that eliminations constrain the *rank order* of combined scores, and that combined scores can be bounded given the aggregation rule in force each week (rank-based seasons 1–2 and 28+; percentage-based seasons 3–27). The plan uses three specialized, chained models:

- **Model 1 (Feasibility–Inversion Engine):** recovers per-contestant-per-week fan vote *intervals* (not point guesses) from judge scores + elimination outcomes, season by season, under the known combination rule. Uncertainty is native to the formulation (polyhedral feasible set + maximum-entropy centering).
- **Model 2 (Counterfactual Aggregation Comparator):** replays every season under rank vs. percentage combination (plus a proposed third rule), quantifying outcome flips and which rule is more fan-sensitive.
- **Model 3 (Attribution & Recommendation Model):** hierarchical regression decomposing judge scores and estimated fan appeal into celebrity traits (age, industry, gender, prior fame proxy) and pro-dancer effects; feeds a fairness/excitement criterion that selects a recommended voting system.

Model 1's intervals are the uncertainty input to Model 2's counterfactuals and Model 3's outcome regressions, so certainty statements propagate consistently end-to-end.

---

## Model 1: Fan-Vote Inversion via Constrained Rank/Share Feasibility (FENCE)

### Purpose
Estimate hidden fan vote totals/shares f_{i,w} for contestant i in week w, with honest uncertainty, from observed judge scores s_{i,w} and the elimination record. Uncertainty varies by contestant/week (large when outcome constraints are slack — e.g., a contestant safely in the middle of the pack; small near the bottom two).

### Mathematical Formulation
Notation: in week w, contestants i = 1..n_w with judge scores s_{i,w} (sum over dances), placement r_{i,w} in combined ranking, eliminated set E_w. Fan vote share p_{i,w} >= 0, sum_i p_{i,w} = 1 (rank or percentage share; min(s, f)-normalization is a monotone transform per season, so order-based feasibility is invariant — we state and use this).

- **Rank rule (S1–2, S28+):** combined rank given by first sorting on judge rank, then on fan rank; equivalently outcome constraints: if i eliminated over j, then at least one of rank(s_i) > rank(s_j) or rank(p_i) > rank(p_j) holds; for survivors, combined-rank inequalities link judge and fan ranks.
- **Percentage rule (S3–27):** combined share c_i = (s_i/S + p_i)/2 with S = sum of s. If i eliminated and j survives: c_i < c_j; if i survives among bottom-two-eligible, c_i >= c_{n-th}.
- Together these define a **polyhedral feasible set** P_w (percentage case) or a permutahedron-anchored set (rank case, mapped to linear ordering constraints on p ranks). Uncertainty for p_{i,w} = width of projection of P_w onto coordinate i:
  p̂_{i,w}^lo = min P_w(p_{i,w}), p̂_{i,w}^hi = max P_w(p_{i,w}).
- **Point estimate:** maximum-entropy center of P_w: maximize sum_i −p log p subject to P_w (unique interior "least-committal" estimate; avoids corner artifacts of LP vertices). Consecutive-week links (fandom persistence φ) tie weeks via a Kalman-like/particle filter across the season.
- **Consistency metric:** constraint-violation count under the entropy point estimate = 0 by construction; report slack σ_w = min distance of surviving contestants from the cut boundary.
- **Certainty metric:** normalized interval width ρ_{i,w} = (hi − lo)/(hi + lo) and Shannon-type concentration C = 1 − entropy/log(n_w). Certainty is NOT uniform (bottom-two contestants tightly constrained, safe contestants loosely).

### Solution Strategy
1. Parse CSV into long format (season, week, couple, judge score, place, eliminated flag); build judge-rank ordering.
2. For percentage seasons: `scipy.optimize.linprog` (HiGHS) for interval bounds per coordinate; entropy point via `scipy.optimize.minimize` with softmax parameterization and analytic gradients.
3. For rank seasons: enumerate admissible candidate rankings when n_w <= 8; else sample permutations consistent with judge ranks (rejection/SMC).
4. Across-week linkage: particle filter with ~10^4 particles per contestant (numpy only).
5. Outputs: estimates.csv (p̂_lo, p̂, p̂_hi, ρ, σ_w per contestant-week); consistency replay (target >= 95% of eliminations reproduced); figures: feasibility-width vs. week; case plots for S27 Bobby Bones and S2 Jerry Rice.

### Validation
- Zero-violation replay of all weekly eliminations (target >= 95%), mismatches documented.
- Held-out week check: drop one week's outcome constraint, re-solve, verify eliminated contestant falls in predicted bottom-two.
- Rank-vs-percentage invariant check in no-conflict weeks (sanity plot).

---

## Model 2: Counterfactual Aggregation Comparator — Rank vs. Percentage vs. Judges' Veto (C-ACC)

### Purpose
Apply both historical combination rules (rank and percentage) to every season and week, using Model 1's fan estimates, to (a) detect outcome differences, (b) test which method favors fan votes more, and (c) run counterfactuals on the listed controversies (Jerry Rice S2, Billy Ray Cyrus S4, Bristol Palin S11, Bobby Bones S27) including the S28+ "judges pick from bottom-two" mechanism.

### Mathematical Formulation
- **Rank rule R:** combined value v_i^R = judge-rank position + fan-rank position (lower = stronger); eliminate argmax v^R (ties broken by judge rank).
- **Percentage rule P:** v_i^P = (s_i/Σs + p_i)/2; eliminate argmin v^P.
- **Fan leverage:** Λ(w, rule) = number of survival-status flips per δ = 0.05 fan-share perturbation, averaged over weeks/seasons. Higher Λ ⇒ more fan-favored rule.
- **Controversy counterfactuals:** recompute weekly survival paths and final placements under R, P, and P + judges-veto (judges save the stronger dancer among the bottom two, measured by cumulative contest-gap score Σ_w (s_{i,w} − s̄_w)/s̄_w).
- **Statistical comparison:** McNemar test on paired (R, P) weekly disagreements; bootstrap over seasons (10^4 resamples) for 95% CIs.

### Solution Strategy
1. Ingest Model 1 p̂ intervals; propagate counterfactuals over interval endpoints (worst/best case); "outcome robust" only if R and P agree on both endpoints.
2. Fan-leverage: per week, per rule, δ-injection loop over contestants.
3. Controversy paths: recompute season trajectory under each rule with observed judge-score sequences fixed.
4. Judges-veto simulation at bottom-two weeks under percentage rule.
5. Bootstrap over seasons for CIs on disagreement rate, leverage, and controversy placements.

### Expected Outputs
- outcomes_compare.csv (eliminated under R, P, P+veto per week; agree flag); flip-rate table by season; controversy dossiers; figures: disagreement heatmap, leverage bars, controversy timeline plot.

### Validation
- Benchmark sanity: R and P must reproduce televised outcomes in the majority of weeks under the season's actual rule.
- Known-case check: Jerry Rice (S2) survives under R, drops under P.
- Interval stress test with maximal fan uncertainty; only report conclusions that survive.

---

## Model 3: Hierarchical Attribution Model + Fairness-Optimal Voting Rule (HAM-F)

### Purpose
Quantify the impact of celebrity characteristics (age, industry, gender) and pro dancer on judge scores and estimated fan votes — testing whether the two channels respond differently — and propose + defend a better voting system.

### Mathematical Formulation
- **Outcomes:** y1 = normalized judge score; y2 = logit(p̂) fan share from Model 1.
- **Bayesian hierarchical model per outcome k:**
  y_k,iw ~ Normal(μ_k,iw, σ_k),
  μ_k,iw = β_k,0 + β_k,week + β_k,age·(age−30)/10 + β_k,male·1[gender] + Σ_g γ_k,g·1[industry=g] + u_k,pro(i) + ε_k,i,
  with u_k,pro ~ N(0, τ²_pro), ε_k,i ~ N(0, τ²_celeb), random week effects.
- **Heterogeneity ratio:** H_g = γ_1,g / γ_2,g (judge-channel vs fan-channel effect); H_g > 1 ⇒ judges reward trait g more; H_g < 1 ⇒ fans over-reward.
- **Pro-dancer ranking:** posterior means of u_k,pro with shrinkage, per channel.
- **Welfare criterion:** W(rule) = α·Fairness + (1−α)·Excitement, Fairness = Spearman ρ(rule ranking, judge ranking); Excitement = elimination upsets penalized by final-3 concentration.
- **Proposed system:** v_i = θ·(s_i/Σs) + (1−θ)·p_i with adaptive θ_w raised toward 0.6 when judge–fan conflict is high and identification tight; plus judges-veto at bottom-two and a fan-share cap at (2 × mean share). Grid search θ ∈ [0.3, 0.7], cap ∈ [1.5, 3] to maximize W.

### Solution Strategy
1. Build regression frame from Model 1 output + CSV covariates.
2. Fit with `pymc` (NUTS); cross-check judge channel with `statsmodels` MixedLM.
3. Grid search W(θ, cap) reusing Model 2's replay machinery.
4. Sensitivity: α ∈ {0.3, 0.5, 0.7}; recommended (θ, cap) must be stable to ±0.1.

### Expected Outputs
- effects_table.csv (posterior means + 95% CIs per trait and pro, both channels; H_g); rule_search.csv (W surface, optimum); figures: forest plot, pro-dancer dot plot, W-surface heatmap, Pareto front.

### Validation
- Posterior predictive checks (KS test by season block).
- Holdout: fit on S1–27, predict S28–34; report MAE.
- Rule robustness: recommended rule must beat R and P on W for all α ∈ [0.3, 0.7] and under maximized p̂ uncertainty.

---

## Integration
Model 1 produces the hidden-variable estimates (fan shares with intervals); Model 2 consumes these for the historical counterfactuals (rule comparison + controversy cases) with uncertainty-aware robustness flags; Model 3 consumes both for the attribution findings and the recommended adaptive-θ + judges-veto + popularity-cap system. Together they answer every bullet of the problem statement.
