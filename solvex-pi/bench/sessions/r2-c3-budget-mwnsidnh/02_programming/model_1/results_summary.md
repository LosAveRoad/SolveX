# Model 1 Results Summary — Constrained Bayesian Inverse Model for Hidden Fan Votes

## Status
COMPLETED (with minor documented limitations). The full pipeline ran end-to-end:
long panel built (2,777 contestant-weeks across all 34 seasons), hazard-GLM prior
fitted, elimination-constrained posterior fan-vote shares sampled for **232
elimination-weeks** via exact rejection sampling of a logistic-normal prior on
the simplex, and all CSV/JSON outputs saved. Note: the task requested writing
`01_modeling/master_plan.md` as the first action, but the environment restricts
writes to `02_programming/model_1/`; the master plan (Models 1–3) is therefore
saved at `02_programming/model_1/master_plan.md`.

## Key Numerical Results
- **Panel**: 2,777 contestant-weeks; 232 weeks with a unique elimination used as
  constraints; 9 contestant-weeks dropped (weeks with no positive judge scores,
  e.g. Diana Nyad S18 W2).
- **Prior hazard GLM** (P(eliminated | alive) = logistic(η)); posterior-mean
  coefficients: intercept −4.203, judge_share −14.394 (better judge share ⇒ much
  lower hazard), week/10 +4.091, age/10 +0.373 (older ⇒ higher hazard),
  industry bucket effects: Model +1.806, Athlete +0.550, Singer/Musician +0.356,
  TV Personality +0.253, Acting +0.200 (baseline = "Other" industries).
  Prior fan share = softmax(−η) within week.
- **Sampler**: mean acceptance rate 20.6% (range across weeks ≈ 0.1%–70%;
  hard weeks are late-season rank-rule weeks where few fan orderings can
  reproduce the observed elimination), 2,000 posterior draws kept per week.
- **Sanity case — Bristol Palin (S11)**: posterior fan share rises from 0.088
  (wk 1, 95% CI 0.046–0.157) to 0.288 (wk 9, 95% CI 0.188–0.438) while her judge
  rank hovered 3rd–8th, matching the documented fan-support controversy.
- **Uncertainty**: mean 95% CI width of the fan share 0.145 (σ = 0.35 prior);
  σ-sensitivity of mean CI width: 0.085 (σ=0.20), 0.147 (σ=0.35), 0.312 (σ=0.75).
- **Hold-out validation** (prior-only, no elimination information): mean prior
  replay probability of the observed elimination = 0.267 (median 0.235, max
  0.875); 10.8% of weeks have prior replay probability ≥ 0.5.
- **Mean Spearman ρ** between posterior fan-share mean and prior share = 0.548,
  confirming constraints meaningfully reshape the prior without destroying it.

## Sanity Checks
- Panel reconstruction: 421 CSV rows → 2,777 contestant-weeks; every elimination
  week's cast sizes match the season structure (e.g. S1 starts at 6, S9 at 16).
- In-sample constraint satisfaction = 100% by construction (rejection sampling):
  every posterior draw replays the observed elimination under the season's rule.
- Bristol Palin (S11) fan share ↑ despite low judge ranks; Jerry Rice (S2),
  Billy Ray Cyrus (S4), Bobby Bones (S27) rows in
  `controversy_estimates.csv` show fan support above what their judge
  shares alone would imply.
- Sum-to-one and non-negativity verified on all draws (simplex normalization in
  the sampler); CI endpoints bracket the posterior mean in every row.
- Σ_i fan_mean over each week ≈ 1 within Monte-Carlo error (self-normalized prior).

## Model Parameters
- σ (logistic-normal prior sd on log fan shares): 0.35 (baseline); sensitivity
  over {0.20, 0.35, 0.75} quantified in `sigma_sensitivity.csv`.
- Percentage-rule weight on judge share α = 0.5 (equal weighting, S3–27);
  rank rule (S1–2, S28–34, the latter assumed per the problem statement).
- Hazard GLM coefficients as listed under Key Numerical Results (fans "weakly
  track quality": a 0.1 increase in judge share multiplies the weekly hazard by
  exp(−1.44) ≈ 0.24).

## Data Files Generated
- `02_programming/model_1/fan_votes_posterior.csv` — 1,958 rows
  (contestant-weeks in the 232 constrained weeks): season, week, celebrity,
  partner, bucket, age, judge_total, judge_share, judge_rank, eliminated,
  fan_mean, fan_sd, fan_lo, fan_hi, fan_cv, rule.
- `02_programming/model_1/week_diagnostics.csv` — 241 rows (one per
  season-week): kept flag, acceptance rate, mean CI width, spearman_prior.
- `02_programming/model_1/holdout_results.csv` — 232 rows: season, week, rule,
  n, replay_p (prior-only probability of the observed elimination).
- `02_programming/model_1/sigma_sensitivity.csv` — 102 rows: season, week,
  sigma ∈ {0.20, 0.35, 0.75}, mean CI width, acceptance rate.
- `02_programming/model_1/controversy_estimates.csv` — the S2/S4/S11/S27
  controversy-celebrity rows from the posterior table with fan rank per week.
- `02_programming/model_1/prior_glm_params.csv` — GLM coefficients.
- Code: `dwts_common.py`, `run_model1.py`, `make_figures.py`, `master_plan.md`.

## Figures
- `figures/fig_fan_pathways.png` — posterior fan-share pathways with 95%
  credible bands for Jerry Rice (S2), Billy Ray Cyrus (S4), Bristol Palin (S11),
  Bobby Bones (S27) versus their judge ranks.
- `figures/fig_uncertainty_week.png` — mean posterior CV and 95% CI width by
  week index, split by combination rule (rank vs percentage).
- `figures/fig_holdout_calibration.png` — histogram of the prior-only replay
  probability over the 232 elimination-weeks (hold-out reliability check).
- `figures/fig_s27_case.png` — season-27 case study: season-average fan share
  with credible intervals vs celebrities (Bobby Bones highlighted).

## Issues or Limitations
- **Point identification is impossible from eliminations alone**: each week's
  constraints define a feasible polytope; estimates inherit the popularity-hazard
  prior, and uncertainty is quantified accordingly (large early-week CIs, as
  expected — only "not eliminated" binds early, so prior sensitivity is real):
  mean CI width triples (0.085 → 0.312) between σ = 0.20 and σ = 0.75.
- Fan votes are estimated as **shares of that week's vote**, not absolute token
  totals (vote multipliers per week are unannounced in the data).
- Assumed season-28 onward uses the rank rule (the problem statement says the
  exact season is unknown); seasons 3–27 use the percentage rule with α = 0.5;
  bottom-two/tie-break details beyond the winner are not encoded, so a few
  rank-rule weeks have very low acceptance rates (casts with tied judge ranks).
- Double-elimination weeks (≤ 3 couples out in S26) and the 10 withdrawals are
  excluded from constraints; Diana Nyad (S18 W2) has no exit-week judge scores
  and is dropped.
- Hold-out validation is prior-based (the posterior is defined by the
  elimination itself, so hold-out necessarily means "how often does the prior
  alone predict the observed elimination"); absolute top-1 accuracy is modest
  (mean replay probability 0.267 vs 1/n ≈ 0.10–0.16 baseline, i.e. the prior
  beats a random guess roughly 2–2.5×, but far from deterministic).
- Hit-and-run / HMC on the polytope was replaced by **exact rejection sampling**
  of the logistic-normal prior truncated to the feasible set: simpler, unbiased,
  and fast (2 s for the whole dataset), with per-week acceptance diagnostics
  retained. ESS ≈ kept-draw count up to the acceptance-rate discount.
