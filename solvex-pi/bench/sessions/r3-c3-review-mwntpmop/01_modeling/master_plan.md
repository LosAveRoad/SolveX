# Master Plan — 2026 MCM Problem C: Data With The Stars

## Overview
DWTS judge scores are public but fan votes are secret. We must (A) invert weekly eliminations to recover estimated fan votes with honest uncertainty, (B) compare the show's two combination rules (rank vs. percentage) plus the judges-save counterfactual, using the controversial celebrities as stress tests, and (C) quantify how pro dancers and celebrity traits (age, industry) drive judge scores vs. fan votes. The pipeline is sequential: Model 1 produces posterior fan-vote estimates v̂_iw; Model 2 reruns history on v̂_iw under both rules; Model 3 links outcomes to contestant characteristics. Data: `data/2026_MCM_Problem_C_Data.csv` (seasons, contestants, weekly judge scores, eliminations).

## Model 1: Bayesian Fan-Vote Inversion (Elimination-Constraint Sampler)
### Purpose
Estimate the hidden weekly fan-vote share v_iw for every contestant i in week w, and its certainty, exploiting the only hard signal we have: who survived each week.
### Mathematical Formulation
- Known: judge score share s_iw = j_iw / Σ_k j_kw (j = judge points), elimination status E_iw, combination rule R(season).
- Latent: feasible vote-share region F_w = {v_w : Σ v_iw = 1, v_iw ≥ ε, bottom-1 (or bottom-2 + judges' tiebreak, season ≥ 28) under R(season) matches observed elimination}.
- Prior on latent popularity: z_iw = logit(v_iw) ~ N(μ_i + δ_w + θ·(s_iw), σ²), with hierarchical celebrity-mean μ_i ~ N(0, τ²); popularity prior mixes technical quality s_iw with celebrityITERAL appeal.
- Posterior: p(v | E, s) ∝ Π_w 1[v_w ∈ F_w] Π_i N(z_iw; μ_i + δ_w + θ s_iw, σ²), sampled by constrained MCMC (mirror/bootstrap within feasible region) or ABC.
- Certainty: 90% credible intervals of v_iw, effective sample size, per-week posterior elimination-accuracy p(match | v^(m)).
### Solution Strategy
Parse CSV → build per-week composite score under the season's rule → Markov-Chain feasibility sampler (Python: numpy + scipy.optimize for region polytope vertices, custom Metropolis-within-Gibbs; ~200k draws, thinning) → posterior summaries. Cross-check with an inverse-optimization point estimate maximizing closeness of composite scores (max-margin slack) per week.
### Expected Outputs
Table v̂_iw ± 90% CI for all contestant-weeks; heat map of coefficient of variation by week; consistency metric = fraction of posterior draws reproducing every elimination (target ≥ 0.85 within feasible sets).
### Validation
Forward test: sample v from posterior, re-run combination rule, verify replicated eliminations match history; hold-out check on weeks with double eliminations; compare rank-based and percentage-based feasible regions for non-overlap warnings.

## Model 2: Counterfactual Rule Engine (Rank vs. Percentage, Judges-Save)
### Purpose
Replay all 34 seasons under both historical combination methods and the season-28+ judges-save, quantify which rule favors fans vs. judges, and resolve the Rice/Cyrus/Palin/Bones controversies.
### Mathematical Formulation
- Rank rule: composite c_iw = rank(s_iw) + rank(v_iw); Percentage rule: c_iw = 100·(s_iw + v_iw)/(Σ_k s_kw + Σ_k v_kw); eliminate argmin c.
- Judges-save: bottom-2 by c, judges pick elimination by their own season-total rank scores.
- Metrics: per-season flip count Φ_season = #{(i,w): rule A eliminates i, rule B eliminates j ≠ i}; fan-favor index κ = corr(c, rank(v)) − corr(c, rank(s)); controversial trajectory counterfactual: given observed rank(s_iw) history, compute P(win | method) over posterior v-draws from Model 1.
- Sensitivity: propagate Model 1's v̂ uncertainty through both rules → distributions of Φ and of each celebrity's finishing position.
### Solution Strategy
Vectorized replay engine (pandas groupby season/week; ranks via `rank(method='min')` tie handling per show rules), Monte Carlo over posterior samples for uncertainty bands; case-study module hardcoded to the four named celebrities plus automated detection of all judge-fan divergence cases (|z_s − z_v| > 2).
### Expected Outputs
Season-by-season flip table; bar chart of fan-favor index by era (S1–2 ranks, S2–27 percentages, S28+ ranks+save); survival curves for Jerry Rice, Billy Ray Cyrus, Bristol Palin, Bobby Bones under each method; final recommendation matrix.
### Validation
Sanity check replays against documented outcomes (e.g., percentage rule must reproduce actual seasons 2–27 eliminations given point estimates); ties broken consistently with announced results; bootstrap CIs on flip counts.

## Model 3: Hierarchical Driver Model (Pros, Age, Industry → Judges vs. Fans)
### Purpose
Quantify how pro dancer identity and celebrity characteristics (age, industry/fame, gender) affect judge scores and fan votes, and whether effects differ between the two channels.
### Mathematical Formulation
- Response 1: judge share y^J_iw; Response 2: posterior fan-vote share E[v_iw] (and logit ranks) from Model 1.
- y_iw ~ Beta(μ_iw, φ) on link scale: logit(μ_iw) = β0 + β1·age_i + β2·athlete_i + β3·fame_tier_i + u_pro(i) + u_season(w), u_pro ~ N(0, σ_pro²), u_season ~ N(0, σ_seas²).
- Key contrast vector Δ = β^fan − β^judge with 95% credible intervals; variance decomposition V_pro, V_star, V_residual per response.
### Solution Strategy
Bayesian hierarchical Beta/binomial regression (Python: `bambi`/`pymc` or `statsmodels` mixed models as fallback); weakly-informative priors N(0, 2²); standardize predictors; compare judge-channel vs. fan-channel posteriors for each coefficient.
### Expected Outputs
Forest plot Δ (pro effect, age effect, industry effect) for both channels; pro-dancer random-effect rankings with CIs; variance-partition chart; answer to "do pros/traits matter equally to judges and fans?"
### Validation
Posterior predictive checks (replicated per-week share distributions); leave-one-season-out prediction error vs. baselines; convergence diagnostics (R̂ < 1.01, ESS for key parameters).

## Integration
Model 1 turns eliminations into fan-vote posteriors — the raw material for everything else. Model 2 consumes those posteriors to replay history under each combination rule and deliver the producers' central question (which method, and is the judges-save needed?). Model 3 explains *why* fans and judges diverge, feeding the fairness/excitement recommendation. Final deliverable: the ≤25-page report + memo, with the rule recommendation justified by low-regret choice: pick the method maximizing judge–fan balance and flip transparency under Model 1's uncertainty.
