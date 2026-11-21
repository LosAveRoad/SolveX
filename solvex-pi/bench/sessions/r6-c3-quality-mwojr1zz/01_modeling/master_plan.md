# Master Plan — 2026 MCM Problem C: "Data With The Stars"

## Overview

**Problem.** 34 seasons (421 contestant-runs, 2,777 contestant-weeks, 335 season-weeks) of DWTS
judge scores and elimination outcomes are given; fan votes are the closely-guarded unknown.
We must (i) estimate fan votes for every contestant-week with defensible uncertainty,
(ii) re-run the show's two historical combination rules (rank-based, percentage-based) under
those estimates and compare them, including the four famous controversies, (iii) quantify how
pro dancer and celebrity traits drive judge scores vs fan support, (iv) propose and stress-test
a fairer weekly system, and (v) write a producers' memo.

**Core mathematical difficulty.** Fan votes are never observed cardinally. Each week is a
constrained-likelihood inverse problem: the observed elimination set E_w reveals only the argmin
(or argmins, for double/triple eliminations) of an unknown linear combination
`comb = (1-λ)·percent(v̂) + λ·percent(x)` of hidden fan-share v and observed judge-share x
(possibly with rank-first coupling), for every basis week of 34 seasons jointly. That is a
ceiling on identification: any model that claims more certainty than the ordinal information
carries is over-fitting fiction. Our design therefore (a) pools partial-weekly signals across
421 runs in a hierarchical Bayesian softmax with a single coupling parameter β per
platform (before 2024's platform shift; later models may allow τ²), and (b) reports calibrated
posterior intervals + rank-stability probabilities instead of point votes alone.

**Shared data (Phase 1 deliverables — `01_modeling/shared_data/`).**
- `contestants.csv` (421 rows; key: season + celebrity_name; `last_week` = vote-basis week;
  `result_type`, `placement`, `partner_primary`, industry/age/geography, `finale_week`).
- `week_scores.csv` (2,777 rows; `weekly_total` = sum of judge scores in the week's panel with
  dance-count convention merged; `n_judges_judged`; `multi_dance_week` flag).
- `season_weeks.csv` (335 rows; grid definition with `n_competing`, `n_eliminated`,
  `n_withdrew`, `n_finalist_exits`, `is_finale_week`, `multi_dance_week`).
- Encoding rules are documented in `data_dictionary.md`; 13/15 structural checks recorded in
  `checks.md` (see that file for the elimination-basis and multi-dance conventions).
Every model below loads ONLY these three tables (paths relative to repo root:
`01_modeling/shared_data/*.csv`), never the raw CSV.

**Model architecture (three specialized models, chained).**
Model 1 is the identification engine: it turns judge scores + elimination sets into posterior
distributions of weekly fan-vote shares ŝ (and contested counterfactual distributions). It is
the only model that "creates" information; Models 2–3 consume its outputs read-only.
Model 2 is the behavioral–causal layer: driver attribution (pro, industry, age, gendercoded
prior fame proxy via prior-week shares) with train/test honesty, delivering both judge-score
and fan-share halves, plus decomposition of platform shift over season index.
Model 3 is the decision laboratory: full-system counterfactuals (rank vs percent vs judges-save
vs our proposed "Rescue Skeleton") evaluated with the same utility, phase, and exit conditions,
producing the producers' recommendation and sensitivity-to-model risk quantification.

---

## Model 1: Constrained-Ordinal Bayesian Fan-Vote Identification (softargmax market-share grid, multi-elimination likelihood, weighted rank constraints)

### Purpose
Produce the weekly fan-vote share surface ŝ_{c,w} (share of total fan votes going to couple c in
basis week w of season s) with calibrated posterior uncertainty, under the ordinal constraint
system implied by every observed elimination. This is the minimal-information engine that all
later models consume. A naive placeholder fish would just crank a logistic on judge z-scores;
we instead enforce *every* elimination as a hard soft constraint (mixed-ceiling market share),
which collapses the feasible set dramatically and makes the recovered uncertainty honest.

### Mathematical Formulation

Notation: basis weeks w = 1..T_s of season s (finale weeks excluded from elimination constraints,
handled separately). Competing set C_{s,w} with |C| = n_{s,w} (from `season_weeks.csv`).
Judge total x_{c,w} ∈ [8, 45] (dance-count normalized via z-scores inside week, see strategy).
Latent fan share φ_{c,w} ≥ 0, Σ_c φ_{c,w} = 1. Latent "judgedness" quality q_{c,w}.

Week-1 cold-start prior (no elimination info at w=1):
  q_{c,1} = μ_s + a_c(book) = μ_s + a_dir(partner) + a_ind(c.celebrity_industry) + γ·z(age_{c}) −
            age-penalty(J(c)) + η_s(season) + ε_{c,1},  ε ~ N(0, σ_ε²)   [1–2σ prior]
with hierarchical priors: a_dir ~ N(0, τ_dir²), a_ind ~ N(0, τ_ind²), η_s ~ N(0, τ_SEAS²),
σ_ε ~ HalfNormal(1). These give an initial φ̂_{c,1} that Model 3/2 use as "prior popularity".

Market-share link (softmax / Bchoice-style constrained-attraction model):
  φ_{c,w} = exp(b_{c,w}) / [ Σ_{c'∈C_w} exp(b_{c'w}) + exp(0) ],  b_{c,w} = μ_s + β_J·z(x_{c,w}) + p_c(report trend) + u_{c,w}

The exp(0) term is an *outside sentiment* (some fans do not vote for anyone that week);
u_{c,w} ~ N(0, σ_b²) is week-level heterogeneity influencing fan idiosyncrasy.

Combined score per couple, platform-parameterized elimination utility:
  Combined_{c,w} = (φ_{c,w})^(1-ω) · (x̃_{c,w})^ω  on the percentage grid (power mean),
where x̃_{c,w} = x_{c,w} / Σ_{c'∈C_w} x_{c',w}. The show's *percentage method* is exactly ω = 1/2
in the log-chance formulation (50/50 on percent shares). The *rank method* replaces this with
  Combined^rank_{c,w} rankₓ = rank_φ(c,w) + rank_x(c,w)  (sum of ranks; lowest combined rank at risk).
Our model computes BOTH from the same posterior draws: φ draws project onto the rank grid z-ranking.

Elimination likelihood for a basis week with exit set E_w (|E| = m_w, m_w ∈ {1,2,3} from
`n_eliminated`): all m_w exits must be the lowest-combined m_w couples.
With ω-stage coupling:  P(obs exit set) ∝ Π_{c∈E_w} [ Combined_{c,w}^{-1} ] boundary-softmax:
  L(w) = Σ_{π} exp(−α · Σ_{c∈E_w} rank^comb_π(c,w))  approximated by the Plackett–Luce
sequential draw over Combined_{c,w} (faster: GumbEL-free sequential removal likelihood).

**Rank-constraint weighting for Model uncertainty gates:**
For every posterior draw d and exit week w: q^dRSS (residual) := [rank_x(E_w members) mass below
median] → weight ω_d = exp(−κ·q^d), κ 1–2. The posterior is therefore NOT symmetric: draws that
violate obvious judge-elimination facts are exponentially downweighted (a soft version of the
(b) constraints in the MCM appendix quadratic program, but integrated over draws).

Posterior (stage-A MAP then stage-B variational):
  max_{b, μ_s, β }  Σ_w log L(w)  − λ/2 ||b||²  − prior terms                [stage A]
  then Laplace/ADVI around the MAP:  q_{c,w} posterior variance V_{c,w}.       [stage B]

Final fan-share interval per contestant-week:
  ŝ_{c,w} = E_q[φ_{c,w}], CI = quantile_{0.025/0.975}(φ draws), and
  σ̂_{c,w}/ŝ_{c,w} (CV)..week reporting: fan-share share × 100,000 (percent of total votes).

**Exit-condition fits** used everywhere downstream:
  φ̂_{c,w}, σ̂_{c,w}, rank-prob Pr(recover actual next-week combined bottom set).

### Solution Strategy (10–20 lines)
Python; libraries: numpy, pandas, scipy.optimize (L-BFGS-B for MAP), scipy.stats, autodiff-free
closed-form gradients (finite-difference fallback), and **PyMC 6.4** for the ADVI/NUTS stage-B
(4 chain × 1000 draws is feasible: the latent vector is only ΣT_s·|C_{s,w}| ≈ 2.8k).
1. Load `week_scores.csv` + `season_weeks.csv`; z-normalize x per (season, week) using the
   dance-count-aware weekly mean/sd (z handles 3-judge vs 4-judge and multi-dance weeks).
2. For each (s, w): build C_w, E_w (exits keyed via `last_week`, finale-folded included);
   initialize b^0 via the hierarchical Model-1 prior (partner/industry/age random effects).
3. MAP (stage A): optimize joint log-posterior with the product of Plackett–Luce elimination
   likelihoods; analytic gradients; L-BFGS-B with 200 restarts from perturbed inits.
4. Stage B (uncertainty): Laplace approximation of Hessian (dense 2.8k×2.8k is fine) OR PyMC
   ADVI; then importance-resample 4000 draws with the rank-violation weight ω_d (κ=1).
5. Compute φ draws via softmax with the exp(0) outside option; store share, sd, 95% CI.
6. Derive rank-method and percent-method combined scores from the SAME φ draws
   (rank grid = rank of φ̂; percent grid = φ̂ directly) → master pipeline for Model 3.
7. Cold weeks (w=1, no E): report prior-based φ with wide CIs; flag `certainty="low"`.
8. Finale weeks: no elimination constraints; φ up-weighted by finalist down-weighting of
   already-computed popularity and final-placement ordering constraints (3-5 finalists).
9. Weekly vote-popularity time series per celebrity: fans' spring toward/away over the season
   (proxy for fanbase momentum; feeds Model 2 responses and Model 3 dynamics).

### Expected Outputs
- `model1_fanshare.csv`: season, celebrity, week, φ̂, sd, lo95, hi95, cv, ambiguity flag.
- `model1_draws.csv`: 4000 draws × top-moment summaries (for ViB propagation to Model 3).
- `model1_exitfit.csv`: per exit-week: Pr(φ-model recovers actual exit set), rank of each exit
  in the posterior combined ordering, log-loss vs baseline (uniform) and vs judge-only.
- `model1_popularity_timeseries.csv`: per celebrity-run weekly popularity curve.
- Figures F1–F5: (F1) heatmap season × week mean φ̂; (F2) posterior violin for S2 Jerry Rice
  weeks 1–8; (F3) calibration curve exit-probability vs observed; (F4) σ̂ by n_competing and
  week-within-run; (F5) recovered φ̂ vs judge-z scatter (the "fan vs judge" joint plot).

### Validation (numbers Phase 2 must hit; honestly derived from 291 vote-based exits)
1. **Exit-hit rate.** Using posterior mean combined score, the most-at-risk couple must equal
   the observed exit in ≥ 85% of the 2659 single-exit week-rows (n=261 non-withdrawal auditor pairs)
   and ≥ 75% of 29 double-exit weeks and the single triple (S26 W3) — report all three numbers.
   Upper bound already set by judge-only logit (~74.6% bottom-3 capture): we must beat judge-only.
2. **Survivor identity.** Reconstructed next-week n_competing must match `season_weeks.csv`
   exactly for all 335 season-weeks (a hard identity, no exceptions).
3. **Posterior coverage.** Empirical coverage of the 95% CI on φ̂ ≥ 93% (slightly conservative
   target); the CV must vary: mean CV of week-1 rows > mean CV of mid-run rows by ≥ 20%
   (certainty is NOT constant, per the problem statement).
4. **Judge-vs-fan tension.** Standard deviations: σ(pairwise fan-share gap) between the top judge
   and bottom judge couple in each week ≥ 0.05 on average — proves fans add non-trivial noise.
5. **No-leakage check.** Re-run stage A with the w-th elimination removed (leave-one-week-out):
   φ̂ recomputed must keep ≥ 80% Kendall-τ with the full φ̂ — identification is not desperate.
6. **Smoke test for feasibility.** Stage A converges in < 60 s (2.8k latent dims, sparse graph):
   feasible on laptops. If ADVI stalls, the Laplace fallback is the deliverable path.

---

## Model 2: Judge–Fan Behavioral Attribution (identification of pro/partner effect, industry, age on judge scores vs fan shares; platform-shift decomposition; hierarchical Bayesian response surfaces)

### Purpose
Answer the third bullet with clean causal logic: how much do the pro dancer's skill/track record,
the celebrity's industry, age, and prior fame drive *judge scores* and *fan votes*?
Key subtlety the judges' reading of the problem statement demands: judge scores and fan votes are
incentivized differently (technical merit vs popularity), so effects must be estimated SEPARATELY
on the two outcome surfaces, never co-mingled. Model 2 consumes Model 1's posterior fan shares
(ρ = E[φ]) alongside the observed judge totals.

### Mathematical Formulation

Two parallel hierarchical Bayesian response models (shared structure, different outcomes y):
  **Judge surface:**  y^J_{c,w} = z(x_{c,w}) normalized (within-week, dance-count aware)
  **Fan surface:**    y^F_{c,w} = logit(φ̂_{c,w} + δ) with a tiny offset (weekly share ∈ (0,1))

Model (linear mixed with heterogeneous slopes, fit separately for y^J and y^F):
  y_{c,w} = α_s + π_{p(c, s)} + ι_{ind(c)} + f(age_{c}) + g(weekcounter_{c,w})
            + θ·(pro × industry interaction) + u_c + ε_{c,w}

where
  - α_s: season fixed effect (production drift, judge panel size, era),
  - π_p: **pro-dancer random effect** — the quantity of interest (54 pros, min 2 seasons each).
    Prior: π_p ~ N(π̄, τ_π²), hyperprior τ_π ~ HalfNormal(0.5). Pooling handles sparse pros.
  - ι_ind: industry effect (25 levels, hierarchical: ι ~ N(I·bar-industry, τ_I²)),
  - f(age): a restricted cubic spline (4 knots at 20/30/45/65) so age effects are flexible
    but monotone-plausible; identical functional form for both surfaces,
  - g(weekcounter): within-run learning curve (celebrities improve) — fitted separately for
    judge surface (should be positive) and fan surface (may be negative — fans punish formality),
  - u_c: contestant random intercept N(0, σ_u²) (charisma/fame residual, not explained by covariates),
  - ε_{c,w} ~ N(0, σ²) (per-week noise).

**Key decomposition (the headline result):** for each covariate class k,
  R_k = Var_k[ŷ] / Var[ŷ]  (fraction of outcome variance explained by class k),
reported for k ∈ {pro, industry, age, week, season, residual-fame u_c}, side-by-side for the
judge and fan surfaces. The equality or divergence of R^J_k vs R^F_k is the "do they impact both
in the same way?" answer, with a permutation test for each (shuffle the covariate within season;
1,000 shuffles → null band of R_k).

**Anti-instrumental check (mandatory, honest selection):** pro-dancer assignments are NOT random
(Bean Counting error: pros are assigned by producers possibly related to celebrity caliber). We
therefore (i) report the naive R_k (no correction), and (ii) a "restricted" R_k from a mediation
specification where celebrity fixed effects absorb ability: π̂_p restricted = π̂_p − μ_pα(s Selection)
from a busy-direction decomposition. Final statements carry both numbers with a plain-language
caveat ("pro effect on judge scores is partially a sorting artifact; the honest lower bound is…").

### Solution Strategy (10–20 lines)
Python: statsmodels (mixed lm with var_identification via `mixedlm`), PyMC for the spline +
hierarchical version (NUTS, 4×800 draws — feasible: ~421 runs × ≈7 weeks avg = 2,777 rows),
scipy for splines (`scipy.interpolate` design matrices), permutation tests vectorized in numpy.
1. Merge `week_scores.csv` (per-week judge y^J) with `model1_fanshare.csv` (y^F) on
   (season, celebrity_name, week); merge `contestants.csv` covariates and `partner_primary`.
2. Filter: exclude weeks after a withdrawal (incomplete market) and flag multi-dance weeks
   with a fixed effect (utils the `multi_dance_week` shared flag).
3. Fit judge surface → coefficient table π̂_p, ι̂_ind, f̂(age), ĝ; repeat for fan surface.
4. Compute the variance-decomposition table R_k and the permutation p-values.
5. Rank pros by posterior E[π_p] with 95% CrI (top-5 and bottom-5 list; Derek Hough-type
   validation: known-elite pros should emerge).
6. Produce the "same-direction?" matrix: covariate k × surface (judge/fan) with effect sign,
   size, and a 2-sided bootstrap CI computed on 2,000 cluster bootstraps by season.
7. Deliver a small "counterfactual swap" exhibit: predicted placement distribution if an average
   celebrity (median everything) is paired with the best vs the median pro.

### Expected Outputs
- `model2_effects.csv`: long table covariate × level × surface × estimate × CrI × permutation p.
- `model2_decomp.csv`: R_k by surface, with permutation z-scores.
- `model2_pro_rankings.csv` (54 pros × {judge effect, fan effect, seasons, Ci}).
- Figures F6–F10: (F6) forest plot of top-15 pro effects, judge vs fan side-by-side;
  (F7) age spline (two curves, judge vs fan); (F8) industry coefficient heatmap;
  (F9) week-curve g (learning vs fatigue, judge vs fan); (F10) scatter π̂_p^judge vs π̂_p^fan
  (the "pros who lift judges are not always pros who lift fans" quadrant chart).

### Validation
1. **Known-pro sanity:** historically elite pros (Derek Hough, Mark Ballas, Cheryl Burke,
   Val Chmerkovskiy) must rank in the top 15 of π_p^judge; any blatant contradiction (an
   obvious novice above Derek) invalidates the model and must be debugged before proceeding.
2. **Convergence diagnostics:** R-hat < 1.01, ESS > 400 for all π_p; any divergent transitions
   in NUTS must be < 1% of draws.
3. **Holdout honesty:** leave-one-season-out (LOSO) prediction: out-of-sample R² ≥ 0.25 judge
   surface on z(x), ≥ 0.15 fan surface on logit(φ̂); if the fan surface underperforms, the
   Model 1 uncertainty likely propagates — report alongside the fan-surface naive R².
4. **Permutation nulls:** the realized R_pro must exceed its permutation 95th percentile on BOTH
   surfaces (otherwise "pro effect" is noise and the report says so).
5. **Sign discipline:** f̂(age) on the judge surface should be non-negative on [15, 45]
   (younger-flexible contestants judged favorably); ĝ (week slope) must be ≥ 0 for judges.
   Violations flagged, explained (e.g. older celebrities receive charm-based fan support but
   lower judge scores — the F7 crossing).

---

## Model 3: Rule Laboratory (rank vs percent vs judges-save counterfactuals and the proposed "Qualibrium" system; Monte Carlo over the Model 1 posterior)

### Purpose
Answer bullets 2 and 4 with reproducible, posterior-aware counterfactuals: for each of the 34
seasons, replay the season under (i) rank method, (ii) percentage method, (iii) rank + judges-save
(S28+ rule), and (iv) our proposed fairer "Qualibrium" rule, all multiple times per posterior
draw of Model 1's fan shares. The four named controversies (Jerry Rice S2, Billy Ray Cyrus S4,
Bristol Palin S11, Bobby Bones S27) get forensic deep-dives. The output is the recommendation
memo's evidence base: which rule is most robust to fan-vs-judge disagreement, which rule would
have changed history, and how often judges-save actually flips the outcome.

### Mathematical Formulation

Fixed weekly game for basis week w with competing set C_w, judge shares x̃ (from
`week_scores.csv`, dance-count aware), and posterior fan draws φ^d (d = 1..D from Model 1):

- **Rank method (S1–2, S28+ historical):** comb^rank_{c,w} = rank_x(c,w) + rank_{φ^d}(c,w)
  (1 = best). Eliminate the m_w couples with the LARGEST comb^rank.
- **Percentage method (S3–S27 historical):** comb^pct_{c,w} = ½·x̃_{c,w} + ½·φ̂^d_{c,w}
  (with ½ + ½ the historical 50/50 weight; sweep ω ∈ {0.25, 0.5, 0.75} as sensitivity).
  Eliminate the m_w smallest comb^pct. (Ties broken by judges' rank, as announced on the show.)
- **Judges-save overlay (S28+):** after comb^rank, take the bottom-2 set B_w; the exit is
  chosen by majority of a simulated judge panel using the judges' weekly x̃ ranking
  (i.e., the worse judge-ranked of B_w exits with probability softmax(β_save · Δx̃), β_save = 4
  calibrated so that historically judge-favored couples survive ~85% of the time in B_w).
- **Proposed Qualibrium rule (novelty).** Each week, (a) compute judge share x̃ and fan share φ̂;
  (b) instead of combining levels or ranks, require a couple to be "rescued" if
  φ̂_{c,w} > φ^{(r)}_{c,w} (the r-th largest fan share, r = 3rd) AND x̃ is not bottom-1;
  otherwise eliminate by comb^pct with a *tiered* weight ω_w = 0.3 + 0.4·(w/W_s)
  (judges dominate early, fans dominate late — early weeks filter technique, late weeks
  let popularity decide the finale, which is what the show's narrative wants).
  Formal statement: eliminate argmin_c [ (1−ω_w)·x̃_{c,w} + ω_w·φ̂_{c,w} ] among {c : NOT rescued},
  with the rescue condition {φ̂_c ≥ φ̂_(3) and x̃_c > min x̃}. (Full formal writeup in paper.)

For each rule R and each fan draw d: simulate ALL weeks of season s sequentially (each week's
exit removes the couple from subsequent weeks), producing a season-long counterfactual outcome
placement vector π^{R,d}_s ∈ S_n. Aggregate over d → distribution over each couple's placement.

**Controversy metrics:**
  P^{R}_{survive}(c, w) = Pr_d[c not eliminated at w under rule R] — trajectory curves.
  Flip rate:  Flip^{R1→R2}(c) = 1{ median placement of c differs between rules R1, R2 }.
  Judge-passivity index: Pr_d[c never in bottom-2 by judges' ranks but eliminated under R].
  Fairness axioms: (i) Condorcet-judge consistency: if a couple is judge-top-1 every week,
  Pr(win) should = 1 under a fair rule (report per rule); (ii) fan-sovereignty ceiling:
  a couple with judge-rank avg bottom-quartile should have Pr(win) ≤ q_fair (report per rule);
  (iii) sensitivity: expected number of weeks where the bottom-2 margin < 0.01.

**S26 special handling:** 4-week all-athletes season, triple elimination W3 — kept as-is (the
rule code must handle m_w=3, which it does, since E_w comes from `n_eliminated`).

### Solution Strategy (10–20 lines)
Python: numpy (vectorized per-draw week loops), pandas; 400 posterior draws × 34 seasons × ≤11
weeks × 4 rules ≈ 600k week-simulations — trivially fast (< 3 min) if vectorized over draws.
1. Load `model1_draws.csv` (D = 400 posterior fan-share draws per contestant-week, from Model 1
   stage B) and the shared tables for x̃, C_w, E_w, m_w, finale-structure.
2. Implement the four judges as pure functions of (x̃ vector, φ draw, week index, ω_w) → exit set.
3. Support both m_w ∈ {1, 2, 3} and the two historical "drop the bottom TWO then judges choose"
   semantics for rule 3; tie-break by judge rank with random-noise jitter ε ∼ N(0, 0.005) to
   avoid infinite tie loops (same jitter across rules within a draw for comparability).
4. Run the season simulator per rule per draw; collect placement distributions per celebrity.
5. Controversy files: for the four named celebrities (plus any auto-detected
   high-|corr(fan, judge)|^{-1} cases), produce week-by-week trajectory tables and the
   "what-if" placement distributions under every rule.
6. Fairness axioms: compute the three axiom metrics per rule per season; aggregate with CrIs.
7. Sensitivity: repeat the entire lab with (a) ω ∈ {0.4, 0.5, 0.6} for percent, (b) β_save ∈ {2, 4, 8},
   (c) with Model 1 φ̂ replaced by the crude judge-only proxy (negative control: any conclusion
   that survives this replacement is not really about fan votes; report as a caveat).
8. Output the recommendation logic: the rule that maximizes (fairness axioms satisfied,
   flip-right-weeks justified by narrative) with the strongest robustness to posterior
   uncertainty wins; write the producers' memo directly from this table.

### Expected Outputs
- `model3_placements.csv`: season × celebrity × rule × {P(1st), E[place], 95% place CI}.
- `model3_flip_table.csv`: per rule-pair flip counts and the named-controversy rows.
- `model3_fairness.csv`: axiom metrics per rule per season (plus aggregates).
- `model3_rescue_log.csv`: per week under judges-save: bottom-2 sets, judge-choice, flip-or-not.
- `model3_qualibrium_effect.csv`: season × celebrity outcome deltas for the proposed rule.
- Figures F11–F15: (F11) placement-distribution bump chart for S27 under 4 rules;
  (F12) Jerry Rice S2 trajectory (fan share CI band vs judge rank), (F13) same for Bristol
  Palin S11 and Bobby Bones S27; (F14) fairness-axiom radar per rule; (F15) heatmap of
  flip frequency by season and rule-pair.

### Validation
1. **Historical replay sanity:** under the historical rule-for-season (rank for S1–2 & S28+,
   percent for S3–S27), the simulated winners must match the real 34 winners in ≥ 26/34 seasons;
   the ≤8 discrepancies must be concentrated in the known contested finals (Bobby Bones S27,
   Iman Shumpert S30 etc.) — the point is that Model 1's φ̂ reproduces history BETTER than
   judge-only (which would flip ~10 finals), proving the identification is sane.
2. **Jerry Rice forensic target:** under the S2 RANK rule, P(survive to final) for Jerry Rice
   must be ≥ 0.7 (he really did make it under ranks); under the percent rule, ≤ 0.35. If this
   separation does not appear, the rank-first weighting in comb^rank is mis-implemented.
3. **Bobby Bones target:** under rank rule (S28+ convention applied to S27 as counterfactual):
   P(Bobby top-2) must stay ≥ 0.6 (rank method empowers fans); under judges-save: P(win) must
   drop to ≤ 0.2 — i.e., the S28 overlay would likely have prevented the S27 controversy.
   These two numbers are the memo's headline.
4. **Counterfactual determinism check:** re-running the lab twice with identical seeds yields
   identical outputs (no hidden state); Monte Carlo standard error on P(win) ≤ 0.02 (400 draws).
5. **Fairness-axiom sanity:** the proposed Qualibrium rule must dominate the two historical
   rules on judge-Condorcet consistency AND halve the count of "winners with bottom-quartile
   average judge rank" — else the recommendation is dishonest and the memo must say so.
6. **Sensitivity disclosure:** all headline numbers report the full range under ω and β_save
   sweeps; a conclusion that holds only at one parameter point is labeled fragile.

---

## Integration

**Pipeline.** prep_data.py → Model 1 (identification) → Model 2 (attribution, consumes φ̂) and
Model 3 (counterfactual lab, consumes the posterior draws). Model 2 and Model 3 are independent
of each other and can run in parallel; both read Model 1's outputs read-only.

**Reliability spine.** (i) Survivor identity (`n_competing` recursion, `season_weeks.csv`) is a
hard invariant checked in all three models; (ii) the historical-replay test in Model 3 doubles as
an end-to-end validation of Model 1; (iii) negative controls (judge-only φ̂; permuted covariates)
guard every causal statement in Model 2; (iv) all four headline rules are reported with
parameter sweeps — no single-point conclusions.

**Narrative deliverables.** The 25-page paper gets: a data section (from data_dictionary.md +
encoding findings), a methods section (three models), results (F1–F15), sensitivity, limitations
(fan votes are ordinal-identified; judge panels rotate; multi-dance conventions), and the
producers' memo with a clear recommendation: percentage-based with declining judge weight
(Qualibrium-lake likely winner), judges-save retained but recorded publicly.

**Runtime budget.** Model 1 ≈ 2 min; Model 2 ≈ 1 min; Model 3 ≈ 3 min; all fit comfortably in a
single workflow execution on the provided data (≤ 3k latent rows total).
