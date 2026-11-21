# 2026 MCM Problem C — Data With The Stars: Master Modeling Plan (Model 1 execution copy)

Note: `01_modeling/master_plan.md` is read-only in this task (write is restricted to
`02_programming/model_1/`). This file mirrors the plan; the full plan text with
Models 1–3 is preserved here and summarized in results_summary.md.

Data: `data/2026_MCM_Problem_C_Data.csv` (seasons 1–34: contestant info, results, weekly judge scores).
Hidden quantity: weekly fan-vote totals/shares per contestant, inferred from judge scores + observed eliminations.

---

## Model 1: Constrained Bayesian Inverse Model for Hidden Fan Votes

### Purpose
Recover weekly fan-vote totals/shares for every contestant-week, with per-cell uncertainty, such that combining inferred votes with observed judge scores reproduces the actual eliminations and final rankings. Key insight: eliminations give **inequalities**, not equations — the feasible set of fan-share vectors per week is a polytope; we characterize it by sampling, not point estimation.

### Mathematical Formulation
Let week w have contestants i = 1..n_w, judge score s_{iw} (normalized 0–1: s / max possible), hidden fan-vote share f_{iw} ≥ 0, Σ_i f_{iw} = 1. Two combination rules:
- **Percentage rule**: p_{iw} = α·s_{iw} + (1−α)·f_{iw}; eliminate argmin_i p_{iw} (α = ½ in most seasons; rank-tilted variants handled by fitting α).
- **Rank rule**: R = rank-sum r^J_{iw} + r^F_{iw} (ranks on judge score and fan votes, 1 = best); eliminate argmax R. The fan-rank induces an ordering constraint: the eliminated couple's fan-rank must be low enough that its combined rank is worst.

Feasible set per week: F_w = {f ≥ 0, Σf = 1 : argmin under the season's rule = observed eliminated couple i*, and all observed bottom-two/survival constraints hold}. Prior: f ~ LogisticNormal(μ_{iw}, σ²), μ_{iw} = g(celebrity fame covariates, judge score, survival week) — fans weakly track quality but overweight charisma; μ estimated via logistic regression on survival time. Posterior: π(f | data) ∝ Π_w 1[f_w ∈ F_w] · Π_i LogNormal(f_{iw}; μ_{iw}, σ²), sampled with hit-and-run MCMC on the polytope (rejection-free). Weeks are conditionally independent given priors; seasons with non-elimination weeks drop the constraint (increased uncertainty). Certainty per cell = posterior CI width; uncertainty largest early weeks, collapses near finale.

Consistency measures: in-sample constraint satisfaction = 1 by construction; hold-out validation (estimate from weeks 1..k−1, predict week-k eliminated couple; top-1 accuracy + Brier score); Spearman ρ vs prior ranks.

### Solution Strategy
1. Parse CSV → panel (season, week, couple, judge score(s), eliminated flag); normalize; build per-week constraint matrices.
2. Prior μ via logistic regression of survival hazard on judge score + covariates.
3. Hit-and-run MCMC on polytope (custom NumPy; ~2000 draws/week, thinning, split-R̂).
4. Posterior samples, 95% credible bands, per-cell CV.
5. Figures: fan-share heatmap with CI, uncertainty-vs-week, hold-out accuracy table.

Validation: 100% in-sample replay; hold-out ≥ ~85%; Bristol Palin / Bobby Bones top fan shares despite bottom judge ranks; Jerry Rice high fan share S2; R̂ < 1.05, ESS > 400.

---

## Model 2: Counterfactual Comparison of Combination Rules (Rank vs. Percentage) and Judges' Bottom-Two Veto

### Purpose
Apply both historic combination rules to every season using Model 1 fan estimates, replay each week/season, quantify outcome differences (controversial celebrities), plus the effect of the season-28-style "judges pick from bottom two" rule.

### Mathematical Formulation
For each season s, week w with fan shares f̂_{iw} (posterior draws for uncertainty):
- **Rank rule** (S1–2, S28+): R_{iw} = r^J_{iw} + r^F_{iw}; eliminate argmax R (ties → fan vote).
- **Percentage rule** (S3–27): p_{iw} = ŝ_{iw} + f̂_{iw} (each normalized to sum 1); eliminate argmin p.
Counterfactual rule swap: apply rule B where A ruled; measure per-week top-1 disagreement, final-placement Kendall τ vs. actual, elimination flips for Jerry Rice (S2), Billy Ray Cyrus (S4), Bristol Palin (S11), Bobby Bones (S27). Judges-veto variant: bottom two under each rule, eliminate lower mean normalized judge score; recompute survival paths.

### Solution Strategy
1. Compute r^J, r^F, r^P per contestant-week; propagate posterior draws → P(eliminated) per couple-week.
2. Sequential season replay (elimination changes future cast — not one-week swaps).
3. Output disagreement matrix by season, flip lists per controversy, sensitivity decomposition (rank discards magnitude → favors fans?).

### Validation
In-sample replay under actual rule ≥ 95% eliminations matched; posterior P(eliminated) for each controversy under both rules.

---

## Model 3: Regression of Judge and Fan Scores on Pro Dancer and Celebrity Characteristics

### Purpose
Quantify how pro dancer and celebrity characteristics (age, industry, sex) affect outcomes and whether they move judge scores and fan votes differently.

### Mathematical Formulation
- Judge score: s_{iw} = β0 + β1·age_i + β2·industry_k(i) + β3·δ_{pro(i)} + β4·week_w + u (cluster-robust SE by season).
- Fan share: logit(f̂_{iw}) = γ0 + γ1·age_i + γ2·industry + γ3·δ_{pro} + γ4·logit(s_{iw}) + γ5·week.
- Hazard: logit(h_{iw}) = θ0 + θ1·s_{iw} + θ2·f̂_{iw} + θ3·covariates.
Pro effect δ as shrunk random effect (partial pooling by appearance count).

### Solution Strategy
1. Merge Model 1 fan estimates with celebrity metadata and pro identities.
2. Fit judge-score, fan-share, hazard regressions; compare standardized effects judge vs. fan.
3. Pro effect ranks with 95% CIs; judge–fan gap per characteristic.
4. Output: coefficient table, forest plot of pro effects, industry bars, judge–fan comparison.

### Validation
Per-equation R² / pseudo-R², residual diagnostics, signs checked against documented anecdotes (charismatic low-scoring celebrities get fan support but not judge support).
