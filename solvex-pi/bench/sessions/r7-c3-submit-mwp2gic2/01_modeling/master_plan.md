# Master Plan — 2026 MCM Problem C: "Data With The Stars"

## Overview

**Problem core.** 34 seasons of DWTS data supply *judge scores* (4 judge columns × 11 weeks,
wide, with zeros as filler and encoded multi-dance "aggregate" weeks) and *outcomes*
(elimination week / final placement), but **fan votes are entirely latent**. The three
mathematical deliverables are: (i) estimate weekly fan votes per contestant with honest
uncertainty, (ii) contrast the show's two combination rules (rank-based vs
percentage-based) and resolve famous controversies, and (iii) quantify how celebrity
characteristics (age, industry, partner) shape judge vs fan support.

**Data foundation.** All models load the shared dataset built by
`01_modeling/shared_data/prep_data.py` (see `shared_data/data_dictionary.md` and
`shared_data/checks.md`):
- `contestants.csv` — 421 celebrity-season rows: demographics, status
  (eliminated/withdrew/finalist), `elim_week`, `placement`, `last_danced_week`.
- `weekly_scores.csv` — 2,777 celebrity-season-**danced-week** rows: per-judge scores,
  `week_score_mean` S_iw (per-dance average, 0–10), `judge_share` (percentage-rule input),
  `week_rank_judges` (rank-rule input), `scoring_type` (normal/aggregate).
- `week_panel.csv` — 335 season-week rows: `n_competitors`, `n_eliminated_this_week`
  (0–3, allowing double eliminations S33 w2/w3 and S34 w2), `fourth_judge_used`.

The three models form a deliberate pipeline:

```
shared_data ──▶ Model 1 (fan-vote inversion + certainty)
                     │  φ_iw estimates + intervals
                     ├─▶ Model 2 (dual-rule counterfactual elimination engine)
                     └─▶ Model 3 (covariate impact on judge vs fan approval)
```

**Bayesian implementation stack** (all verified present in this environment):
`statsmodels` (discrete-time hazard Logit, MixedLM), `pymc` + `arviz` (Bayesian fan-vote
model, R-hat/ESS diagnostics, HDIs), `scipy.optimize` (MAP, calibration), `matplotlib`/
`seaborn` (figures). No network access; no package installation.

**Notation** (used by all three models): seasons s = 1…34; celebrities i = 1…n_s;
weeks w = 1…W_s; S_iw = judge score of celebrity i in week w; n_w = couples dancing in
week w; E_iw = 1 if celebrity i is eliminated at the end of week w; D_iw = bottom-2
(nomination) indicator; φ_iw = latent fan vote share of celebrity i in week w
(0 ≤ φ_iw ≤ 1, Σ_i φ_iw = 1); ρ_iw = judge score share S_iw/Σ_k S_kw.

---

## Model 1: Sub-Seasonal Survival Inversion of Latent Fan Votes (Bayesian + Belief Functions)

### Purpose
Produce the *estimated fan vote share* φ̂_iw for every couple in every week they danced —
the quantity the contest asks us to recover even though it is never observed — together
with genuine *uncertainty quantification* (certainty is explicit in the task). The key
insight: eliminations reveal the **tail** of the fan-vote distribution each week (the show
identifies a bottom-2/bottom-3 and eliminates from it), which severely constrains both a
survival model and a Dempster-Shafer (D–S) belief reconstruction of the latent shares; two
approaches (parametric–Bayesian and non-parametric–belief-function) are deliberately
cross-validated against each other.

### Mathematical Formulation
**Latent fan shares.** For each season-week w, fan votes follow a multinomial over the
n_w active couples:
  (V_1w,…,V_{n_w}w) ~ Multinomial(1; φ_1w,…,φ_{n_w}w),  φ_iw > 0, Σφ = 1.

**(a) Parametric layer — discrete-time survival with multiplicative hazard.** The weekly
hazard of *nomination to the bottom-2* of celebrity i in week w is
  λ_iw = λ_0w · exp( x_iw' β )   with covariates x_iw
       = (judges' percentile rank of S_iw within week, [low-judge-score dummy], season-normalized
       cumulative judge percentile, age, industry indicator, partner fixed effect).
  P(D_iw = 1 | survived to w) = 1 − exp(−λ_iw).
Observed data give exact survival: S_iw^surv = 1{D_iw = 0 ∀ w' ≤ w}. Because eliminations
are *observed in ordering within a week*, the contribution is an ordinal logit over the
bottom-2/bottom-3 set:
  ℓ_w = Σ_{k∈bottom set} log P(nominated_k) · P(placed k-th among nominated | ...)
The baseline hazard λ_0w is stratum-specific (per week-in-season index), estimated
non-parametrically (Breslow-type), so **no season-level parametric shape is imposed**.
  P(surviving weeks 1..W | judge scores) is then a plug-in of λ_0w and β̂.

**(b) Belief-function layer (Dempster–Shafer).** For each week, judge scores provide
evidence masses m_j over subsets of couples via a normalized plausibility transform of
within-week score shares {S_iw/ΣS}:
  m_j({i}) = softmax(γ · judge_share_iw / (1 + IQR_judge_disagreement)),
  m_j(A) = leftover mass to *unassigned* Θ (the "held-open" probability that fan votes
  contradict judges). The three-to-four judges' masses are combined by Dempster's rule;
  the combined conflict K_w (0 = full agreement) is retained as an uncertainty by-product.
Dempster's rule of combination then distributes the unassigned belief onto singletons:
  Bel({i}) = [(m_1 ⊕ m_2 ⊕ m_3 (⊕ m_4))({i})] / [1 − K_w],
and the fan-vote point estimate is the **MAP disbursement**
  φ̂_iw = argmax_{φ ∈ Δ_w} P(φ | judges, D_i· = 0 ∀≤w) ∝ Bel({i}) · P̄_surv(i,w),
where P̄_surv is (a)'s posterior survival probability — the model's estimate of fan support.
**Uncertainty** is threefold, all reported per (i, w):
  1. `plaus_low = Bel({i})`, `plaus_high = Pl({i})` → D–S interval [Bel, Pl];
  2. a Beta(α_iw, β_iw) posterior for share, fit by variational Dirichlet update with
     concentration κ estimated by maximizing marginal likelihood;Hpdi at 90%;
  3. conflict K_w — weeks where judges and fan-vote evidence disagree get wider intervals.

### Solution Strategy
1. Load `weekly_scores.csv` / `contestants.csv`; split into *active* (danced that week)
   vs eliminated-in-week rows; build within-week rank and share features.
2. Estimate (a) with `statsmodels.discrete.discrete_model.Logit` on the expanded
   (i, w) hazard panel with stratum dummies for week; verify baseline hazards are
   monotone-informative (they encode "same-season average fan support declines with rank").
3. Compute D–S masses per (season, week): scipy softmax on judge shares × conflict-scaled
   discount; combine by Dempster's rule; compute K_w and Bel/Pl.
4. Produce φ̂_iw = normalized product Bel({i})·P̂_surv(i,w) (projected onto Δ_w) and Beta
   posterior intervals; export `fanvote_estimates.csv`
   (row_id, season, week, φ̂_iw, Bel, Pl, Beta Lo/Hi 90%, K_w, n_w).
5. Python: `pandas`, `statsmodels` (Logit), `scipy` (softmax, optimize), `pymc`+
   `arviz` (optional Bayesian refit of the hazard with NUTS; R-hat < 1.01, ESS > 400).

### Expected Outputs
- `01_modeling/shared_data/fanvote_estimates.csv` — the fan-vote table consumed by
  Models 2 and 3.
- **Figures:** (F1) φ̂ trajectories for iconic contestants (Joey Graziadei S34, Bobby Bones
  S27, Jerry Rice S2, Bristol Palin S11) with 90% bands; (F2) season-heatmap of K_w
  (judge–fan conflict); (F3) certainty-vs-week plot showing intervals widen in
  high-conflict weeks.

### Validation
- **Elimination consistency (data-backed):** replicated-versus-observed *bottom-2*
  membership: report top-2 recovery rate of φ̂ within-week, which must exceed the
  judge-share-only baseline (ρ_iw ranks) — target ≥ 60% recovered eliminations (the
  theoretical max is ~65% given rank/percentage rule misalignment), and beat baseline by
  a margin. Also report Brier score against the 0/1 elimination outcome and a GA-type
  ranking concordance (Kendall τ between φ̂ and "did not get eliminated" ordering).
- **Calibration:** reliability curve of P(eliminated) vs observed; coverage of the 90%
  φ̂ intervals (target ≈ 90%).
- **Leave-one-season-out cross-validation:** refit (a) without season s, predict s's
  eliminations; report AUC / top-2 accuracy drop (target ≤ 5 pp).
- **Sanity checks:** force φ̂_iw ≥ 0, Σφ̂ = 1; withdrawn contestants excluded from
  supervision; double-elimination weeks (S33 w2/3, S34 w2) handled as multi-cuts.

---

## Model 2: Judge–Fan Fusion Engine (Permutation-Resilient Rank vs Percentage Combination)

### Purpose
Isolate and contrast the **two combination rules the show actually used** — the early
*rank-based* method where the couple with the lowest combined rank is eliminated, and the
post-Season-2 *percentage-based* method (combined 50/50
(z-scored) rank or share) — and replay the season to answer: (a) do the two rules produce
different elimination histories? (b) would famous controversial contestants (Jerry Rice /
S2, Billy Ray Cyrus / S4, Bristol Palin / S11, Bobby Bones / S27, plus any data-driven
others) have fared differently? (c) which combination rule is more "judge-consistent"?

### Mathematical Formulation
**Rank-based rule R.** Within week w of season s with active set A_w, each couple gets:
  r_judge(i,w) = rank of S_iw within A_w (1 = best, ties → average),
  r_fan(i,w)   = rank of φ̂_iw within A_w,
  TH^R_iw = (r_judge + r_fan)/2.
The couple(s) with the *lowest* TH are in the bottom-2; judges' dance-off (Model 3's
×  benefit) resolves the final cut: eliminate argmin_i TH^R_iw (ties broken by r_judge).

**Percentage-based rule P.** Recast rank shares or fan shares into a 0–1 scale:
  ŝi^judge = S_iw / Σ_k S_kw              (or z-scored/normalized mass),
  ŝi^fan   = φ̂_iw / Σ_k φ̂_kw,
  TH^P_iw = ( ŝi^judge + ŝi^fan ) / 2.
Eliminate argmin_i TH^P_iw (bottom-2 identified, judges resolve the final cut with our
encapsulated "upset-prone proxy" — see below).

**Judge dance-off proxy.** In Seasons 28+ the judges pick the eliminated couple among the
bottom-2. Absent judge-deliberation data we model this as: eliminate the bottom-2 couple
with the *lower* average judge score across the season (a persistence-aware rule). This
proxy is applied deterministically and its sensitivity tested (±1 half-point perturbation).

**Counterfactual replay.** Reweights are *only* applied from the week of the controversy
onward (so earlier weeks replicate the actual show); the alternative rule is then applied
to subsequent weeks using the shared fan-vote estimates φ̂ from Model 1.
  Δ_iw(s) = φ̂_iw·[rule R] − φ̂_iw·[rule P];  Δplacement_i(s) = placement^R_i(s) − placement^P_i(s).
Summary statistic per season: **rule disagreement rate** γ_s = (number of weeks where the two
rules produce different elimination sets) / (number of contests that season).

### Solution Strategy
1. For each (season, week): assemble active couples from weekly_scores.csv, join Model 1's
   φ̂ (join on row_id + week); compute both TH^R and TH^P; simulate the elimination
   sequence via the deterministic bottom-two + judge-dance-off rule.
2. **Replay validation first:** show that under the *observed* rule (which varied by era:
   rank in S1–2, percentage S3–27, bottom-2-judge-choice S28+) the model reproduces a
   majority of actual eliminations — report reproduction rate per season.
3. **Controversy analysis:** for Jerry Rice (S2), Billy Ray Cyrus (S4), Bristol Palin
   (S11), Bobby Bones (S27), plus Mya (S9), Sabrina Bryan (S5/S15) and any data-driven
   "fan-favorite / low-judge" cases: report Δplacement under R vs P, and the "both-rules"
   counterfactual. Also estimate what *percentage* of fan votes would have been needed to
   flip the outcome (elasticity of the judge share via φ̂ sensitivity ranges from Model 1).
4. **Recommendation engine:** score each rule on (i) judge-consistency (Kendall τ between
   final placement and mean judge percentile), (ii) fan-voice intensity (Gini coefficient
   of total fan-vote impact across a contestant's weeks), (iii) "shock rate"
   (elimination of a top-3 φ̂ contestant). Deliver a table + recommendation.
5. Python: `pandas`/`numpy` (vectorized week-by-week simulation), `scipy.stats`
   (Kendall τ, Gini), `matplotlib`/`seaborn` (Sankey-like placement-flow and
   divergence-by-week charts).

### Expected Outputs
- `01_modeling/shared_data/rule_replay.csv` — per (season, week, rule): eliminated
  celebrity, TH^R, TH^P, whether bottom-2 matches observed.
- `01_modeling/shared_data/controversy_table.csv` — the four (plus any discovered)
  named controversies with placement under each rule.
- **Figures:** (F4) season-by-season γ_s bar chart of rule-disagreement rate;
  (F5) placement-flow diagram R → observed → P for the four controversies;
  (F6) judge-consistency vs fan-impact scatter of the two rules across all 34 seasons.

### Validation
- **Reproduction check:** under the era-correct rule, reproduction of the actually
  observed eliminated celebrity in ≥ 55% of weeks (upper bound limited by rank/percentage
  misalignment documented in the literature and by φ̂ uncertainty); ≥ 70% bottom-2 (both
  rules pooled) overlap with observed elimination. These must be verified *before* any
  counterfactual claims are made.
- **Determinism:** rerunning the replay with identical inputs gives identical outputs
  (no stochastic state).
- **Crossover check:** on seasons where R and P agree in every week (γ_s = 0), the method
  choice is irrelevant — verify no model-induced spurious disputes appear there.
- **Sensitivity:** re-run with φ̂ at its 90% HDI bounds; controversy verdicts reported as
  robust / fragile depending on whether the verdict flips.

---

## Model 3: Celebrity-Covariate Impact Model (Judge Trajectory × Fan Support × Survival)

### Purpose
Quantify how contestant covariates — **age, celebrity industry, professional partner,
home region, season effects** — shape outcomes along *two distinct channels*: (a) the
**judges' channel** (weekly score level S_iw) and (b) the **fans' channel** (weekly fan
support φ̂_iw from Model 1). This final linkage — "do fan votes and judge scores respond
differently to the same celebrity trait?" — is the modeling question the show's producers
actually care about.

### Mathematical Formulation
**Delivery 1 — judges' channel (longitudinal mixed model).** For the weekly judge score
  S_iw = μ_week-index + a_i + b· age_i + c_industry(i) + d_partner(i) + c_season + ε_iw,
  a_i ~ N(0, σ_a²)?  (random intercept); ε_iw ~ N(0, σ²).  Estimation by `statsmodels`
  `MixedLM` (restricted maximum likelihood), with week-index and normalized cumulative-judge-
  score as within-season fixed effects. An AR(1) correlation lag-1 structure is tested
  against a plain random-intercept via likelihood ratio test.

**Delivery 2 — fans' channel.** The Model 1 estimate φ̂_iw enters as the response:
  logit(φ̃_iw) = μ + b̃· age_i + c̃_industry(i) + d̃_partner(i) + c̃_season + u_iw,
fit with observation weights 1/Var(φ̂_iw) from Model 1's posterior, so that weeks with
large fan-vote uncertainty are automatically down-weighted (uncertainty propagation).

**Delivery 3 — differential (judge-vs-fan) channel.** Define weekly residual
  R_iw = z(E[S_iw | covariates]) − z(φ̃_iw) — a normalized "fans overrate / underrate this
celebrity relative to the judges" axis — and regress it on the same covariates:
  R_iw = μ + b̃· age_i + … ; a trait with b· > 0 (raises judges) but b̃ < 0 (hurts fans)
  is identified as a "judges' darling / fans' villain" and vice versa.

**Delivery 4 — survival linkage (do the traits alter survival *beyond* the two scores?).**
Cox / discrete-time hazard with covariates (x_iw from Model 1) ∪ {age, industry, partner,
season}, the log-partial-likelihood ℓ(β):
  ℓ(β) = Σ_w Σ_{i ∈ D_w} [ x_iw'β − log Σ_{k ∈ A_w} exp(x_kw'β) ],
assessed for **collinearity with Model 1's judge/fan features**: traits that contribute no
extra signal once (S_iw, φ̂_iw) are in the model are explicitly labelled as such.

### Solution Strategy
1. Assemble a *cast-level* covariate table from `contestants.csv`:
   one-hot for industry (top 6 + "other"), partner (top-12 by tenure + "other"), scaled
   age (+ age²), home-country group (US / UK-Intl / other), plus season dummies.
2. Fit Delivery 1 via `statsmodels.MixedLM` (weekly scores as repeated measures);
   Delivery 2 via `statsmodels.GLM` (Binomial, freq_weights = 1/Var(φ̂)); Delivery 3 via
   OLS on within-couple weekly residuals; Delivery 4 via
   `statsmodels.duration.hazard_regression.PHReg` (or discrete-time Logit).
3. **Industry / partner importance**: partial R² and permutation importance on held-out
   seasons (shuffle each covariate; measure ΔAUC on validation seasons).
4. **Counterfactual casting**: predict S_iw and φ̃_iw for 8 archetypes (17-y-o social-media
   star, 50-y-o actor, 35-y-o athlete …) and simulate their expected survival curve
   through Model 1's hazard — a direct "who should the show cast?" answer.
5. Python: `statsmodels` (MixedLM, GLM, PHReg, Logit), `pandas`, `numpy`, `scipy.stats`,
   `matplotlib`/`seaborn` (forest plots, partial-dependence curves, archetype fan fans).

### Expected Outputs
- `01_modeling/shared_data/covariate_effects.csv` — effect-size table (per covariate,
  per channel) with 95% CIs and permutation p-values.
- **Figures:** (F7) forest plot of effects on the three channels (judge / fan /
  differential); (F8) archetype survival curves with uncertainty bands; (F9) heatmap of
  judge-vs-fan "over/under-rating" by industry; (F10) partner-effect strip plot.

### Validation
- **Held-out-season predictive check:** fit on 27 random seasons, predict S_iw and φ̃_iw
  on 7 held-out; target out-of-sample R² ≥ 0.55 for judges' channel, rankcorr ≥ 0.35 for
  fans' channel; survival AUC ≥ 0.75 on held-out seasons.
- **Sanity anchors:** Babies-theorem style checks — e.g., the "young + social-media star"
  archetype must show *positive* fan-channel and *non-negative* judge-channel effects
  (observed in raw means); veteran dancers' age effect must be non-positive on the
  judges' channel in the raw-data grouped summary.
- **Convergence diagnostics:** MixedLM converges (no boundary warnings), PHReg
  concordance reported; likelihood-ratio test favors the AR(1) extension only if
  p < 0.01 (parsimony rule pre-registered).
- **Robustness:** re-fit without withdrawn contestants and leaving out one industry at a
  time; effect signs must not flip (>90% of refits).

---

## Integration

**Data flow.** `prep_data.py` (already built, all checks PASS) → `weekly_scores.csv` is
the single source of weekly competition state for all three models. Model 1 produces
`fanvote_estimates.csv` (φ̂_iw + certainty), which is *the shared latent quantity* for
Models 2 and 3 — Models 2 and 3 **must not** refit φ̂ themselves, guaranteeing a single
consistent latent-vote story throughout the report.

**Model interdependence failsafes.** If Model 1's φ̂ intervals are extremely wide for a
season (median width ≥ 0.15), Model 2 automatically downgrades its counterfactual verdicts
for that season to "inconclusive" (protection against over-claiming); Model 3 already
weights observations by 1/Var(φ̂).

**Deliverable map (report / 25-page paper).**
- Q1 (fan-vote estimates + certainty) → Model 1 (+ F1–F3, consistency table).
- Q2 (rank vs percentage, controversies, judge-dance-off) → Model 2 (+ F4–F6,
  `controversy_table.csv`, recommendation table).
- Q3 (pro/celebrity characteristics; equal impact on both channels?) → Model 3
  (+ F7–F10, `covariate_effects.csv`, archetype table).
- The final recommendation to producers combines Model 2 (combination rule) and
  Model 3 (casting/advice), stated with the uncertainty language produced by Model 1.

**File conventions.**
- Phase-2 code lives in `02_programming/`; each model is a numbered module
  (`model1_fanvote.py`, `model2_rules.py`, `model3_covariates.py`) reading only
  `01_modeling/shared_data/` and writing `*_output.csv` + `figures/` PNGs under
  `02_programming/`.
- Random seeds fixed (numpy default_rng(42)) for all stochastic pieces; every figure
  regenerated by a single `run_all.py`.
