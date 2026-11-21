# Master Plan — 2026 MCM Problem C: "Data With The Stars"

## Overview
DWTS eliminates the couple with the lowest combination of judge scores and fan votes; fan votes are hidden. The core mathematical challenge is therefore an **inverse problem**: recover weekly fan-vote shares consistent with observed judge scores and observed eliminations/rankings, then use the recovered votes to run **counterfactual replays** of alternative aggregation rules (rank vs. percentage vs. judge-save), and finally **attribute performance** to pro dancers and celebrity covariates.

Strategy: three interlocking models.
- **Model 1 (Inverse Fan-Vote Engine)** estimates hidden fan-vote shares per contestant-week with uncertainty, using feasibility-set inference (linear constraints from elimination logic) + Bayesian posterior sampling. Its outputs (posterior samples of fan-vote shares) feed everything downstream.
- **Model 2 (Counterfactual Rules Laboratory)** replays every season under multiple aggregation rules (rank-based, percentage-based, judge-save bottom-two, and a proposed "geo-mean + deficit-cap" system), computing flip rates on controversial celebrities and fairness/excitement metrics.
- **Model 3 (Attribution & Effect Model)** is a hierarchical Bayesian model decomposing judge scores and estimated fan shares into pro-dancer effects, celebrity covariate effects (age, industry, fame proxy), and week/dance-type effects — answering whether pros and demographics affect judges and fans differently.

Data flow: Model 1 → posterior fan-vote samples → Model 2 (rule analysis) and Model 3 (response variable). Model 3's fitted "fair fan-share" (what fans *should* vote given dance quality) also feeds Model 2's proposed system.

---

## Model 1: Constrained Bayesian Inverse Model for Hidden Fan Votes

### Purpose
Recover weekly fan-vote totals/shares for every contestant-week, with per-cell uncertainty, such that combining inferred votes with observed judge scores reproduces the actual eliminations and final rankings. Key insight: eliminations give **inequalities**, not equations — the feasible set of fan-share vectors per week is a polytope; we characterize it by sampling, not point estimation.

### Mathematical Formulation
Let week w have contestants i = 1..n_w, judge score s_{iw} (normalized 0–1: s/max possible), hidden fan-vote share f_{iw} ≥ 0, Σ_i f_{iw} = 1. Two combination rules:
- **Percentage rule**: p_{iw} = α·s_{iw} + (1−α)·f_{iw}, eliminate argmin_i p_{iw} (α = ½ in most seasons; documented rank-tilted variants handled by fitting α).
- **Rank rule**: R = rank-sum r^J_{iw} + r^F_{iw} (ranks on judge score and fan votes, 1 = best); eliminate argmax R. Rank of fan votes induces an ordering constraint: the eliminated couple's fan-rank must be low enough that its combined rank is worst.

Feasible set per week: F_w = {f ≥ 0, Σf = 1 : argmin under the season's rule = observed eliminated couple i* , and all observed bottom-two/survival constraints hold}. Prior: f ~ LogisticNormal(μ_{iw}, σ²) where μ_{iw} = g(celebrity fame covariates, judge score, survival week) — fans weakly track quality but overweight charisma; μ estimated via logistic regression on survival time (longer survivor ⇒ higher prior fan share). Posterior: π(f | data) ∝ Π_w 1[f_w ∈ F_w] · Π_i LogNormal(f_{iw}; μ_{iw}, σ²), sampled with **hit-and-run / Hamiltonian Monte Carlo on the polytope** (unnormalized; rejection-free walk on feasible set). Multi-week coupling: if only weekly eliminations bind, weeks are independent given priors; seasons with non-elimination weeks or judge-save weeks drop the corresponding constraint (documented as increased uncertainty). Certainty per cell = posterior credible interval width; expectation: uncertainty is **largest early weeks** (only "not eliminated" binds) and collapses near the finale (ordering constraints accumulate).

Consistency measures: (a) constraint-satisfaction rate = 1 by construction on training weeks; (b) hold-out validation — estimate votes from weeks 1..k-1 only, predict week-k eliminated couple, report top-1 accuracy and Brier score; (c) Spearman ρ between implied fan ranks and the prior-model fan ranks.

### Solution Strategy
1. Parse CSV → panel (season, week, couple, judge score(s), eliminated flag). Normalize scores; build per-week constraint matrices.
2. Build prior μ via logistic regression of weekly hazard on judge score + celebrity covariates (statsmodels/sklearn).
3. Sample posterior: hit-and-run MCMC on the polytope (custom NumPy implementation; ~2000 draws/week, thinning, R-hat-style diagnostics via chain splitting).
4. Output posterior samples f_{iw}^{(m)}, 95% credible bands, per-cell coefficient of variation.
5. Figures: heatmap of fan-share means with CI whiskers by week; uncertainty-vs-week curve; consistency (hold-out accuracy) table.

Libraries: numpy, pandas, scipy (polytope vertices via scipy.spatial for small n), statsmodels, matplotlib. No packages installed.

### Expected Outputs
- Table: estimated fan-vote share + 95% CI for every contestant-week.
- Consistency report: hold-out elimination-prediction accuracy, calibration plot.
- Certainty analysis: interval width by week-index and by contestant type.

### Validation
- Elimination replay accuracy must be 100% in-sample (by construction); hold-out accuracy ≥ ~85% indicates prior transports well.
- Sanity: inferred fan shares should show Bristol Palin / Bobby Bones with top fan shares despite bottom judge ranks; Jerry Rice with high fan share in S2.
- MCMC diagnostics: split-R̂ < 1.05, effective sample size > 400.

---

## Model 2: Counterfactual Rules Laboratory (Rank vs. Percentage vs. Judge-Save vs. Proposed System)

### Purpose
Apply every aggregation rule to every season using Model 1's posterior fan-vote samples, quantify outcome flips (especially for Jerry Rice, Billy Ray Cyrus, Bristol Palin, Bobby Bones), test whether judges-save from bottom-two changes results, and design/support a proposed fairer system.

### Mathematical Formulation
For each posterior draw m and season s, simulate trajectory with rule ρ ∈ {RANK, PCT, JUDGE-SAVE(RANK base), PROPOSED}:
- **RANK**: weekly combined rank R_i = r^J_i + r^F_i; eliminate argmax R_i.
- **PCT**: eliminate argmin of ½·snorm_i + ½·f_i (fan votes scaled to judge-score percentage scale, per the show's Appendix method).
- **JUDGE-SAVE**: form bottom two under RANK; judges (modeled) vote to save the couple with the higher normalized judge score (deterministic tie-break by s); eliminate the other. Randomizes over posterior draws of f.
- **PROPOSED ("Deficit-Capped Geometric Rule")**: protect dance quality from total fan dominance while rewarding fan engagement: combined score C_i = √(s_i · f̃_i) where f̃_i = f_i capped at f_max relative to judge leader (f̃_i = min(f_i, f_max · s_i / max_j s_j)); eliminate argmin C_i, with a one-time-per-season "judges' redemption" rescuing the bottom-two couple with the highest 3-week judge average. Rationale: geometric mean penalizes extreme imbalance in either direction; the cap prevents pure popularity sweeps; the redemption preserves excitement (fan-favorite comebacks) while capping injustice.

Aggregates over draws m: flip probability P_ρ(s, i reaches placement p), upset index U(ρ) = Σ_simulations 1[placement differs from observed], fan-power index FP(ρ) = average |∂placement/∂f_i| (how often fan votes alone overturn judge ordering), and judge-power index analog. Fairness metric: Kendall τ between final placement and average judge rank; excitement metric: variance of weekly survival entropy H_w = −Σ f log f.

Counterfactual queries: placement distribution of each controversial celebrity under each ρ; probability Jerry Rice (S2), Billy Ray (S4), Bristol (S11), Bobby Bones (S27) win/finish top-3 under PCT vs RANK vs JUDGE-SAVE; report whether method choice alone flips their outcome.

### Solution Strategy
1. Load Model 1 posterior draws (couple-week fan shares).
2. Weekly-elimination simulator: given a rule, march weeks 1→finale, eliminating one couple per week (respect number of finalists per season and any documented non-elimination weeks); capture final ranking.
3. Monte Carlo over 2000 posterior draws → placement distributions per celebrity per rule.
4. Compute flip matrices (rule × celebrity × placement), FP/Judge-power indices per season, Kendall-tau fairness table.
5. Sensitivity: vary prior strength (Model 1 prior vs. near-uniform) and α in PCT to bound conclusions; the controversy conclusions should be sign-stable across the posterior.
6. Figures: placement-distribution violin plots for the 4 controversial contestants × 4 rules; season-level fan-power vs. judge-power scatter; survival-entropy (excitement) curves by rule.

Libraries: numpy, pandas, matplotlib, seaborn; simulator in pure NumPy vectorized over draws.

### Expected Outputs
- Placement-distribution tables for all contestants under each rule (all 34 seasons).
- Flip table for the four named controversies; probability the S28 judge-save change reverses any historical elimination.
- Fan-power vs. judge-power plot; recommendation matrix (fairness, excitement, simplicity).

### Validation
- Baseline replay under each season's historical rule must reproduce the observed winner within ~95% of draws (residual gaps = genuine estimation uncertainty to report honestly).
- Hand-check: season with fully observed ordering constraints (finale weeks) should have near-degenerate fan-posterior → near-deterministic replay.
- Ablation: run with uniform fan prior; if conclusions on controversies persist, they are robust.

---

## Model 3: Hierarchical Attribution Model — Pros, Celebrities, and Divergent Effects

### Purpose
Quantify how much pro dancers and celebrity characteristics (age, industry/fame) affect competition outcomes, and crucially whether these factors affect **judge scores and fan votes differently** (e.g., pros lift technical scores; charisma/industry lift fan votes).

### Mathematical Formulation
Two linked response models per contestant-week i in season s, week w:
- Judge score: logit(snorm_{i,s,w}) = θ_{pro(i)} + β^J·x_i + γ_w + δ_{sty(i)} + ε^J
- Fan share (Model 1 posterior mean, logit-transformed with variance from draws): logit(f_{i,s,w}) = θ'_{pro(i)} + β^F·x_i + γ'_w + δ'_{sty(i)} + ε^F
where x_i = celebrity covariates (age, age², industry dummies: athlete/actor/musician/TV-host/reality/other, gender), θ_pro ~ N(μ_θ, τ²) hierarchical partial pooling over pro dancers (with pro experience count as covariate on τ), δ = dance-style fixed effects, γ_w = week effect (scores rise through season — partial out before comparing celebs). Divergence metric per covariate/pro: Δ = β^F − β^J with posterior P(Δ > 0); a pro with θ high but θ' ~ 0 is a "technique asset"; a celebrity with β^F high, β^J low is a "fan magnet". Outcome-level model: cumulative survival predicted by softmax over weekly combined score → variance decomposition of final placement into pro/covariate/judge/fan components (Lindeman–Merenda–Gold style shares via posterior draws).

### Solution Strategy
1. Engineer covariates from CSV (age at season, industry classification from contestant description, pro identity, pro season count; fame proxy = prior TV prominence coded from industry + imputed, documented).
2. Fit two Bayesian hierarchical logistic models with PyMC-style Gibbs-free sampling; if PyMC unavailable, use variational/logistic fallback via statsmodels mixed GLM (random intercept per pro) — both specified so results agree in sign.
3. Compute Δ posteriors, shrinkage plots (pros), forest plots (covariates), variance decomposition of placement.
4. Counterfactuals: swap-pro simulation (celebrity X with pro Y) → expected placement shift; age curve of judge vs. fan effect.
5. Figures: shrinkage forest plot of pro effects on judges vs. fans (the money plot: scatter θ vs θ'); age-effect curves; industry effect bars; variance-decomposition stacked bars.

Libraries: statsmodels (MixedLM / Binomial BayesMixedGLM), numpy, matplotlib, seaborn.

### Expected Outputs
- Ranked table: pro effects on judge score vs. fan vote with 90% CrIs.
- Covariate effect table with divergence statistic Δ and P(Δ>0).
- Variance decomposition of final placement; swap-pro counterfactual chart.

### Validation
- Posterior predictive check: simulated weekly score distributions must match observed per-season histograms (KS statistic < 0.1).
- Leave-one-season-out: refit without season s, predict s's judge-score ranks, report Spearman ρ (target > 0.6).
- Convergence: trace inspection + split-R̂ < 1.05 for all hyperparameters.

---

## Integration
- **Model 1 → Model 2/3**: posterior fan-share draws are the common currency; all counterfactual and attribution analyses propagate Model 1's uncertainty via Monte Carlo instead of pretending point estimates are truth.
- **Model 2 → recommendation**: flip tables + fairness/excitement metrics justify the Deficit-Capped Geometric Rule with judges' redemption; the four named controversies serve as narrative anchors (expected finding: percentage rule alone doesn't dethrone pure fan favorites — e.g., Bobby Bones still wins under PCT — while the geometric-cap + judge-redemption does).
- **Model 3 → Model 2 rationale**: quantified divergence (pros ≈ technique, celebrity industry/age ≈ fan share) explains *why* methods disagree, grounding the fairness recommendation in evidence rather than intuition.
- Final deliverables: 25-page report + producer memo built from Model 2's recommendation matrix, Model 1's uncertainty statement (fan votes are recoverable only as feasible bands; certainty is week- and contestant-dependent), and Model 3's attribution findings.
