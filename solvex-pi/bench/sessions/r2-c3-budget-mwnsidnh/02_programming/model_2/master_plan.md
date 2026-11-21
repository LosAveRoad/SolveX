# 2026 MCM Problem C — "Data With The Stars" Master Modeling Plan

Data: `data/2026_MCM_Problem_C_Data.csv` (seasons 1–34; contestant info; weekly judge scores; observed eliminations). Fan votes are latent (never observed). Three coupled models: (1) posterior estimation of latent fan votes, (2) counterfactual voting-rule laboratory (THIS MODEL), (3) driver analysis of contestant/pro characteristics.

## Model 1: Bayesian Latent Fan-Vote Estimation from Elimination Constraints
### Mathematical Formulation
Let couple i in season s, week w have judge score s_{i,w}. Define normalized judge strength j_{i,w} = (s_{i,w} − min_j s_{j,w}) / (max_j s_{j,w} − min_j s_{j,w}) + ε smoothing. Latent fan share f_{i,w} lives on the simplex Δ. Behavioral prior: f_{i,w} ~ Dirichlet(κ·j_{i,w} + η·u) — fans partially track judge quality (strength κ) with popularity noise (concentration η, u uniform). Elimination likelihood, season s using its historical rule: RANK rule (s1–2, s28–34 assumed) → week elimination is deterministic given (r^J, r^F); PCT rule (s3–27) → eliminate argmin (ŝ_i + f̃_i)/2 on a common scale. Posterior ∝ prior × ∏_weeks 1[observed eliminee i* is the rule's argopt at week w]. Sampled by Dirichlet rejection/importance sampling per season, keeping draws consistent with every observed weekly elimination.
### Solution Strategy
1. Pivot CSV to couple×week judge-score matrix per season; identify finale weeks, non-elimination weeks, number of finalists.
2. Per season, draw 2000+ prior fan-share vectors, filter those reproducing every observed elimination, retain posterior draws of weekly fan shares.
3. Certainty: posterior SD + entropy per couple-week; acceptance rate as diagnostic.
4. Export per-draw fan shares for Models 2 and 3.
### Validation
Replay under historical rule must reproduce the observed winner in ≥95% of accepted draws; Bobby Bones weeks must show fan share ≫ judge share.

## Model 2: Counterfactual Rules Laboratory (Rank vs. Percentage vs. Judge-Save vs. Proposed System)
### Mathematical Formulation
For each posterior draw m and season s, simulate the weekly trajectory under rule ρ ∈ {RANK, PCT, JUDGE-SAVE, PROPOSED}:
- RANK: R_i = r^J_i + r^F_i (sum of judge rank and fan rank within the week); eliminate argmax R_i (ties broken by lower judge score).
- PCT: normalize judge scores to percentages ŝ_i = s_i/Σ_j s_j and fan votes f̃_i = f_i/Σ_j f_j each scaled to the same total; eliminate argmin (ŝ_i + f̃_i)/2 (the show's season-3+ Appendix method).
- JUDGE-SAVE: bottom two couples by RANK; modeled judge panel deterministically saves the couple with the higher normalized judge score; the other is eliminated.
- PROPOSED "Deficit-Capped Geometric Rule": C_i = √(ŝ_i · g_i) where ŝ_i = s_i/max_j s_j and g_i = min(f̃_i, f_max · ŝ_i); eliminate argmin C_i; one per-season "judges' redemption" rescues the bottom-two couple with the best 3-week judge average.
Aggregates over draws m: placement distribution P_ρ(s,i,p); flip probability vs. observed placements; fan-power index FP(ρ,s) = share of weeks where fan ordering alone (ignoring judges) would produce a different eliminee; judge-power index JP(ρ,s) analog; Kendall τ between final placement and average judge rank (fairness); weekly survival entropy H_w = −Σ_i f̂_{i,w} log f̂_{i,w} (excitement).
### Solution Strategy
1. Load Model 1-approved posterior fan-share draws (or self-contained fallback: reconstruct posteriors by the same Dirichlet-rejection scheme so the simulator is runnable end-to-end).
2. Vectorized NumPy simulator: per season, march weeks 1→finale, eliminate one couple per week, respect finalists count and non-elimination weeks, rank survivors at finale.
3. Monte Carlo 2000 draws × 4 rules × 34 seasons → placement distributions per celebrity per rule.
4. Counterfactual queries: Jerry Rice (S2), Billy Ray Cyrus (S4), Bristol Palin (S11), Bobby Bones (S27) — finish-position distribution under each rule; does method choice alone flip their outcome; does judge-save reverse any historical elimination.
5. Fairness/excitement table per rule; sensitivity with uniform fan prior; recommendation matrix (fairness, excitement, simplicity).
### Validation
Historical-rule replay ≥95% winner match; conclusions sign-stable under prior ablation.

## Model 3: Heterogeneous Drivers of Performance (Pros, Age, Industry)
### Mathematical Formulation
Mixed model for judge score: s_{i,w} = β0 + β1·week_iw + β2·age_i + β3·industry_i + u_{pro(i)} + u_s + ε; and for log fan share with its own coefficients. u_{pro} ~ N(0, σ²_pro) are pro-dancer effects; contrast Δ_p = û_p(fan) − û_p(judge) isolates pros who lift popularity more than technique. Standardized effect sizes/partial R² quantify how much each factor moves outcomes; fit via REML-style coordinate ascent in numpy/scipy with bootstrap CIs over Model 1 posterior draws.
### Solution Strategy
1. Merge Model 2 posterior mean fan shares with covariates (age, industry, pro, season).
2. Fit random-intercept models by coordinate ascent; shrinkage pro effects; bootstrap CIs.
3. Rank pros by Δ_p; test industry effects on judges vs fans.
4. Figures: caterpillar plot of pro effects, covariate forest plot.
### Validation
LOO season prediction RMSE vs season-mean baseline; sign stability across draws.
