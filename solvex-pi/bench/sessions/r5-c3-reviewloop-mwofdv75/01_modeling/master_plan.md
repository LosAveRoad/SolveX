# Master Plan — 2026 MCM Problem C: "Data With The Stars"

## Overview
DWTS combines secret fan votes F_iw with public judge scores S_iw to eliminate one couple per week
under two historical aggregation rules: **rank-based** (share of total rank points) and
**percentage-based** (share of normalized votes). The fan votes are unobserved, so the modeling
problem decomposes into three coupled sub-problems:

1. **Inverse problem (Model 1):** recover fan-vote totals/percentage shares v_iw for every
   contestant-week, subject to being consistent with observed eliminations, with honest
   uncertainty (a feasible *polytope* of vote vectors, not a point estimate).
2. **Counterfactual engine (Model 2):** apply both aggregation rules (rank vs. percentage vs.
   bottom-two-then-judges-veto) to the estimated votes in every season; measure outcome
   divergence, especially for the four "controversy" celebrities.
3. **Effect decomposition (Model 3):** hierarchical mixed-effects model splitting performance
   into a celebrity-quality signal and a pro-dancer signal, and testing whether they affect
   judges' scores and fan votes differently.

Pipeline: Model 1 outputs posterior vote trajectories → Model 2 consumes them for rule
counterfactuals → Model 3 explains *why* fan/judge gap arises. Model 2's divergence statistics
feed the final recommendation (informed-plurality hybrid rule) in the Integration section.
Data: `data/2026_MCM_Problem_C_Data.csv` (seasons 1–34, contestant info, weekly judge scores,
eliminations). Implement in Python: pandas/numpy, scipy.optimize (linprog, SLSQP),
cvxpy (feasibility polytope), statsmodels (mixed LM), matplotlib.

Consistency metrics used throughout: elimination-agreement rate A = (1/T)·1[ŷ_elim = y_elim],
top-3 recapture rate for finalists, and Kendall τ between predicted and actual elimination order.

---

## Model 1: Constrained Inverse Fan-Vote Estimator (Feasibility-Polytope Bayesian Inversion)

### Purpose
Estimate the unobserved fan-vote share v_iw ∈ [0,1] for contestant i in week w, consistent with
(i) the shown elimination sequence, (ii) the known cast size and judge scores, and (iii) plausible
fan-behavior dynamics (popularity momentum). Crucially, produce *interval* estimates: certainty is
NOT uniform across contestants/weeks — it shrinks as a contestant survives longer with strong
judge scores (few binding elimination constraints) and widens near elimination boundaries.

### Mathematical Formulation
Let n_w = cast size in week w, r_iw = rank of judge score S_iw in week w (1 = best).
For each week w define the TV show's combined percentage score:
  c_iw = α·(r-normalized judge share) + (1−α)·v_iw, where the judge share under the
  percentage rule is J_iw = S_iw / Σ_j S_jw  and under the rank rule R_iw = (n_w + 1 − r_iw)/Σ_j (n_j... )
  computed exactly as in the problem Appendix (rank points / maximum rank points).
Elimination constraint (percentage rule): the eliminated couple e_w satisfies
  c_{e_w,w} = min_j c_{jw}  ⇔  v_{e_w,w} < v_{jw} + slack_j for all j (linear constraints in v).
Constraints set:
  (C1) 0 ≤ v_iw ≤ 1, Σ_i v_iw = 1 (vote shares per week; totals = share × cap·n_w if scaling desired).
  (C2) elimination feasibility: v_{e_w,w} ≤ v_{jw} + ε_w for all surviving j.
  (C3) momentum prior: v_iw = ρ·​v_{i,w−1} + (1−ρ)·g(S_iw, z_i) + η_iw, g a popularity score from
        celebrity covariates z_i (Model 3's fitted fan-appeal), η ~ N(0, σ²).
Objective: minimize ‖v_iw − (ρ v_{i,w−1} + (1−ρ) g_iw)‖² over the polytope (C1)–(C2)
  → a convex QP solved per season (cvxpy / scipy SLSQP fallback).
Uncertainty: sample the feasible polytope via hit-and-run / coordinate Hit-and-Run MCMC
  (or, cheaper, 2,000 LP jitter samples: re-solve QP with randomized objectives ṽ = v + u,
  u ~ Logistic(0, λ)). Interval = [q_{0.05}, q_{0.95}] per contestant-week; certainty map
  K_iw = width of 90% interval. Bootstrap over ε_w ∈ {0, 0.005, 0.01, 0.02} for rule-tolerance
  sensitivity. Sharpness check: K must be smallest for finalists with high judge scores and
  largest at the elimination boundary — report K_iw heat-map (seasons × weeks).
Validation: hold-out weeks — hide each week's elimination in turn, re-solve, check predicted
eliminator matches (agreement rate A ≥ 0.9 target); verify Model 1 reproduces rank-rule seasons
(28–34) under the rank Objective variant as a consistency cross-check.

### Solution Strategy
1. Preprocess: per-season cast lists, weekly judge scores S_iw, elimination flags; handle weeks
   with forfeits/withdrawals and finale multi-couple weeks (exclude finals from elimination
   constraints; use only final ranking for the top-k constraint set).
2. Build constraint matrices A_ub, A_eq per season; solve QP with cvxpy (ECOS/OSQP).
3. Hit-and-run sampler (custom ~80-line implementation, numpy) for posterior draws; summarize
   posterior mean + 90% credible intervals per contestant-week.
4. Deliverables: `fan_votes.csv` (mean, CI, width), certainty heat-map figure, elimination
   agreement table by season; dual (LP shadow prices) identifying "swing weeks" where votes nearly
   changed the outcome — these are the high-interest contestants (Bobby Bones–type profiles).

### Expected Outputs
Estimated fan-vote share trajectories with CIs for all contestants (seasons 1–34); weekly
consistency measures: elimination agreement rate, Kendall τ of combined-score order vs. actual
elimination order; swing-week identification list; certainty analysis showing non-uniform
uncertainty quantified by interval width.
Validation: leave-one-week-out elimination reproduction; rank-rule/percentage-rule dual
consistency check; a worst-case adversarial check spanning the full polytope (max spread of
outcomes consistent with data = lower bound on outcome certainty).

---

## Model 2: Aggregation-Rule Counterfactual Engine (Rank vs. Percentage vs. Judges' Veto)

### Purpose
Apply each known DWTS combination rule to Model 1's vote estimates in every season and every week:
RANK (seasons 1–2, 28–34 style), PERCENTAGE (seasons 3+ style), and the bottom-two + judges-veto
overlay. Quantify where rule choice flips eliminations, whether it systematically favors fan votes,
and re-run the four controversies (Jerry Rice S2, Billy Ray Cyrus S4, Bristol Palin S11,
Bobby Bones S27). This produces the evidence base for the producers' recommendation.

### Mathematical Formulation
For each week w with estimated shares v̂_w and judge ranks/scores:
  RANK rule:      rank points P_iw^R = (n_w + 1 − r_iw^J)·n_w·0.5 + v̂_share-rank points
                  (implement exactly per the problem Appendix: couple rank in judges + rank in
                  fans, equal weight); eliminate argmin.
  PERCENT rule:   P_iw^P = 0.5·J_iw + 0.5·v̂_iw; eliminate argmin.
  VETO overlay:   identify bottom-two set B_w = {argmin, 2nd-argmin} under the base rule, then
                  judges (modeled by their observed score order, with a rule-based judgePU policy:
                  eliminate the lower-judge-scored member; sensitivity over tie policies).
Decision-flip indicator for week w: X_w = 1[P^A-elim ≠ P^B-elim] for each rule pair A,B.
Seasonal fan-favor index: FF^A = −corr(r_iw^J, final placement under rule A); a more fan-favoring
rule has lower |corr| and higher mean placement of fan-beloved-but-poorly-judged contestants
("fan-judge gap": G_iw = v̂_iw − J_iw).
Controversy counterfactuals: for each celebrity, simulate their full trajectory under both rules
and the veto overlay; report final placement changes and whether the controversy outcome replicates.
Uncertainty: propagate Model 1's posterior samples — for each of 2,000 vote draws, re-run the
season; report the **probabilistic reversal rate**: Pr(rule A eliminates i | data) vs rule B,
and the probability the observed outcome was actually the modal outcome under each rule.

### Solution Strategy
1. Encapsulate each rule as a pure function rule(scores, votes, week_meta) → survivor set; unit-test
   against hand-computed Appendix examples and against historical eliminations (rules should
   reproduce known outcomes for rank-rule seasons using rank-variants).
2. Monte Carlo season replay: 2,000 posterior vote draws × 34 seasons × 3 rules; parallelize with
   numpy vectorization (seasons × rules as a batch loop).
3. Statistics: flip-rate table by season-pair, paired bootstrap CI on mean flip rate; fan-favor
   index with rank-correlation tests; controversy case-study panels (placement under each rule).
4. Sensitivity: vary ε_w (Model 1 tolerance), judge-veto policy (score-based vs random vs
  abcú split of fan preference), weight β ∈ [0,1] on judge vs fan share.

### Expected Outputs
Rule-flip matrix (seasons × rule pairs) with Monte Carlo CIs; fan-favor index comparison; four
controversy case-study figures (trajectory charts under 3 rules); probability each historical
elimination was "robust" vs "knife-edge"; basis for the recommendation section.
Validation: (a) rank rule replay of seasons 28–34 must match recorded eliminations under the
posterior mode; (b) total-flip probability sum rule (Σ_w flip probs bounded, sanity ≲ n_w−2);
(c) permutation test — shuffle v̂ across contestants within week: flip rates must collapse to
chance level, confirming the engine responds to true signal not artifacts.

---

## Model 3: Hierarchical Judge–Fan Effect Decomposition (Celebrity Traits × Pro Dancer)

### Purpose
Quantify how much of a celebrity's performance is explained by celebrity covariates (age,
industry/fame proxy, prior dance exposure) versus pro-dancer identity, and test the key hypothesis:
**pros and celebrity traits affect judge scores and fan votes differently** (pros → technical
quality = judge signal; celebrity charisma → votes). Also supplies g_iw (predicted fan appeal)
used as the prior in Model 1, closing the loop.

### Mathematical Formulation
Hierarchical (multilevel) model with contestant-week observations, fitted separately for
response Y = log S_iw (judge score) and Y = logit(v̂_iw):
  Y_iw = μ + a_i + b_{p(i)} + θᵀ z_i + δ·(week index w) + dance-genre d_iw effects
         + interaction φᵀ(z_i ⊗ x_{p(i)}) + u_week + ε_iw,
  a_i ~ N(0, τ_a²)  (celebrity random effect = "charisma/star power", shared across Y surfaces),
  b_p ~ N(μ_b, τ_b²) (pro random effect),
  variance ratio of interest: VF = τ_b²_{votes} / τ_b²_{scores} and analogues for θ.
Key contrasts:
  Δ_pro = placement-shift from swapping pros (predictive simulation with the fitted model);
  Δ_judge vs Δ_fan = same covariate shift applied to the score model vs the vote model —
  different signs/magnitudes = differing channels.
Finale placement model: ordinal logistic on final placement using aggregated (Ī_i, v̄_i, z_i, b̂_p)
to translate weekly effects into "how far a celebrity goes."
Uncertainty: full Bayesian via variational/HMC-lite fallback — but since no package installs,
use `statsmodels.MixedLM` (REML) for the Gaussian parts and `scipy.optimize` for ordinal logistic
(bfgs) with a cluster bootstrap over celebrities (BCa CIs, 1,000 resamples).

### Solution Strategy
1. Feature engineering: pro identity, celebrity age, industry (athlete/actor/musician/TV/reality/other),
   finale week indicator, dance genre dummies, normalized week number, judge-score rank.
2. Fit MixedLM for judge scores and logit(v̂) (statsmodels Mixed Islands — groups = celebrity;
   pro as fixed effects with shrinkage via partial pooling if cast as random via a second grouping
   layer implemented manually with lme4-style BLUP estimates).
3. Cluster bootstrap by celebrity for CIs on θ, τ_b², Δ_pro, and the fan/judge asymmetry ratio.
4. Feed fitted fan-appeal μ + ˆθᵀz_i + b̂_p into Model 1's prior g_iw; re-run pipeline once
   (two-pass integration) and report the change in elimination-agreement A (Model 1) with and
   without the prior — an ablation proving the loop helps.

### Expected Outputs
Forest plot of coefficients with CIs for both response surfaces; pro-dancer ranking with effect
sizes and uncertainty ("who adds most: to judges' eyes vs. fans' eyes"); variance decomposition
pie charts (celebrity / pro / week / residual) for scores vs votes; Δ_pro swap simulator table;
verbal answer to "do traits affect judges and fans the same way?" backed by an interaction test
p-value. Validation: back-test predicting S_iw in held-out contestants (target R² ≥ 0.6 on
log-scores), residual diagnostics (normality, no season trend), and comparison to a plain OLS
baseline (must beat it on AIC and on vote-prior ablation gain of Model 1).

---

## Integration
Sequential pipeline with one feedback loop:
  Model 3 (fan-appeal prior g_iw) → Model 1 (vote estimation, QP + Hit-and-Run posterior) →
  Model 2 (rule counterfactuals & Monte Carlo over the posterior) →
  **Recommended system:** an *informed-plurality hybrid*: percentage-based combination (more
  granular, less rank-compression artifacts — evidenced by Model 2's flip-rate table), limited
  fan power via a week-varying weight β_w (β shrinks toward judges in early weeks to avoid
  instant-elimination of slow starters, grows in later weeks to preserve fan excitement), plus
  the bottom-two + judges'-veto overlay as a "safety valve" (Model 2 shows this kills
  Bobby-Bones-type extremes without erasing all fan influence). Support comes from:
  (i) Model 1's consistency metrics (elimination-agreement > target), (ii) Model 2's quantified
  fan-favor index and reversal probabilities for the four controversies, (iii) Model 3's finding
  that fans and judges respond to different signals — hence a hybrid that preserves both channels
  dominates either pure rule on the tournament's "informational efficiency" (correlation of combined
  score with true latent dance quality, measured by Model 3's a_i + b̂_p).

Deliverable artifacts: `fan_votes.csv`, rule-flip matrix figure, controversy case panels,
effect forest plots, certainty heat-map, and a ≤25 page report with a 2-page producer memo.
