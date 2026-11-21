# Master Plan — Model 3 (Hierarchical Driver Model) — 2026 MCM Problem C

## Model 1: Fan-Vote Estimation (Constrained Inversion / Elimination-Consistent Fan Shares)
### Purpose
Produce weekly estimated fan-vote shares E[v_iw] for every couple, consistent with
observed eliminations and judge scores.
### Formulation
Judge share p_iw = judge_iw / sum_w judge_iw. Unknown fan share v_iw obeys
v_iw >= 0, sum_i v_iw = 1; combined score c_iw = 0.5 p_iw + 0.5 v_iw must reproduce the
observed eliminated couple each week. Solve
  min_v sum_i (v_iw - p_iw)^2  s.t. c_iw >= c_elim + margin
(maximum-entropy / minimum-deviation program). Dirichlet smoothing over the feasible
region width gives posterior fan-vote shares with 95% intervals.
### Validation
Reproduce 100% of observed eliminated couples; report weekly feasible-region widths.

## Model 2: Judge-Channel Driver Model (Judge Scores ~ Covariates)
### Formulation
y^J_iw ~ Beta(mu_iw * phi, (1-mu_iw) * phi);
logit(mu_iw) = b0 + b_age*age_i + b_athlete*athlete_i + b_fame*tier_i + u_pro(i) + u_season(w);
u_pro ~ N(0, sigma_pro^2), u_season ~ N(0, sigma_seas^2); priors N(0, 2^2), half-normal sigmas.

## Model 3: Fan-Channel Driver Model + Judge/Fan Contrast (THIS TASK)
### Purpose
Quantify whether pro-dancer identity and celebrity traits (age, athlete flag, fame tier)
affect judge scores and fan votes in the SAME way. Fan-channel response is the posterior
fan-vote share E[v_iw] from Model 1, same hierarchical Beta structure. Key output:
contrast Delta = beta^fan - beta^judge per covariate with 95% credible intervals;
pro random-effect rankings with CIs for both channels; variance partition
(pro / star / residual).
### Solution Strategy
Adaptive random-walk Metropolis, 3 chains, standardized predictors, run on both channels;
LOSO held-out-season error vs baselines; posterior predictive checks.
### Outputs
forest_delta.png, variance partition chart, posterior-summary CSVs, results_summary.md.
