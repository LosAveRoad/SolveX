# Model 2 — Judge–Fan Behavioral Attribution (2026 MCM Problem C)

Fan-surface inputs: Model 1's delivered posterior `phi_share`
(`../model_1/model1_fanshare.csv`, canonical), merged on (season, week,
celebrity_name); the in-house identification stage is retained as the sensitivity
column `fanshare_lite` (R² 0.392 vs 0.477 canonical).
Deviations from the plan: (i) OLS with celebrity-run cluster-robust SEs replaces the
PyMC hierarchical spec (identical functional form; no R-hat/ESS gates apply); (ii) the
pro × industry interaction is dropped (sparse cells, 25×52 design); (iii) u_c is
reported as the between-run share of residual variance (residual ICC), not a fitted
random-effect sd.

## Status
**COMPLETE & DETERMINISTIC (post cross-review revision 3).** `python3 run.py`
regenerates every output deterministically (fixed seed 2026; two consecutive runs
produce byte-identical `results.json`; wall-clock fields are excluded from the
payload). All headline numbers below come from the regenerated `results.json`.
Round-3 note: canonical fan input switched to Model 1's `phi_share` (graceful
in-house fallback retained); fan-surface decomp/consistency/rankings/swap numbers
restated from the regenerated `results.json`; judge-side outputs byte-equivalent
(R² judge 0.3358, judge pro decomp and rankings unchanged).

## Key Numerical Results
- **Fan-share stage ("Model-1-lite", self-contained because Model 1 ran in
  parallel):** MAP nll **436.58**; judge–fan coupling **β = 1.387**; week trend
  **θ = −0.0001**; posterior share range **[0.0015, 0.5702]**; weekly softmax sums
  = 1.000000 for all 335 season-weeks (2,777 contestant-weeks; 52 pros; 116 params;
  run-cluster SEs).
- **Exit-set recovery (the plan's consistency measure), canonical Model-1 input:**
  observed exit in the bottom-m in **198/235 weeks (84.3%)**; single-exit weeks
  exact bottom-1 **170/206 (82.5%)**; bottom-3 capture **232/235 (98.7%)**;
  double/triple-exit weeks exact set **28/29**.
- **Response surfaces:** R² judge = **0.336**; R² fan = **0.477**.
- **Variance decomposition R_k (partial R², judge/fan):** pro **0.125/0.138**
  (perm. p = 0.003/0.090), industry **0.059/0.056** (p = 0.028/0.481), age
  **0.134/0.094** (p = 0.001/0.001), week **0.018/0.164** (p = 0.099/0.001),
  multi ≈ 0. Fan-side blocks use the canonical `fanshare` surface;
  `fanshare_lite` reproduces the ordering.
- **Pro rankings (eligible = ≥2 seasons, n = 41 of 52; centered effects, judge
  surface):** Derek Hough **#1** (+0.662 [95% CI 0.447, 0.942]), Artem Chigvintsev
  (+0.392), Valentin Chmerkovskiy **#3** (+0.280), Corky Ballas (+0.255), Mark
  Ballas **#5** (+0.188); Cheryl Burke **#15** (+0.056) — all four known-elite pros
  inside the plan's top-15 requirement. Judge-vs-fan effect correlation (eligible):
  **ρ = 0.623** — positive but far from collinear: pros who lift judges tend to
  lift fans, yet the two surfaces disagree materially for several pros.
  Canonical fan-surface top-5: Derek Hough (+0.534), Daniella Karagach (+0.402),
  Kym Johnson (+0.322), Jenna Johnson (+0.320), Valentin Chmerkovskiy (+0.308).
- **Sorting-adjusted ("honest lower bound"):** naive pro R² 0.128 (judge) / 0.134
  (fan) vs restricted **0.114 / 0.134** after the week-1 fan-logit fame control;
  on the judge surface ≈11% of the raw association is producer sorting; on the
  canonical fan surface the fame control absorbs almost the entire fan-side
  association — the honest fan-side pro effect conditional on week-1 fame is
  ≈0.134 (no attenuation; pro quality and fame are complementary, not confounded
  swaps).
- **Age (RCS, knots 20/30/45/65):** curve (ref = 36) age 20 → −0.27/−0.30;
  44 → −0.97/−0.93; 62 → −1.61/−1.17; 82 → −2.15/−1.26 (judge/fan) — decline with
  a fan-surface plateau late in life. SIGN-DISCIPLINE FLAG (judge surface): the
  judge age curve is NEGATIVE at age 20 (f̂(20) ≈ −0.27 < 0 over [15,45]); judge
  favorability peaks in mid-age (≈40–45) and declines monotonically toward older
  celebrities — the same F7 crossing narrative as the week slope (experience vs
  flexibility), not a bug.
- **Learning curve:** per-judge ABSOLUTE score rises within runs (+1.52 pts,
  p < 1e-6, 326 runs ≥4 weeks) while relative within-week z falls (−0.47) —
  survivorship composition, not decline; fan logit **+0.115 (p = 0.0007)** on the
  canonical input — fans reward improvement.
- **Platform/era drift (S1–17 / S18–27 / S28–34):** mean within-week |fan − judge|
  gap narrows **0.052 → 0.055 → 0.043**; within-week fan–judge Spearman drifts
  **0.539 / 0.510 / 0.465**; median weekly top/bottom share ratio ~6.0–7.3×.
  Reading: the elimination-relevant fan–judge tension did NOT collapse after the
  S28 reforms — φ became LESS aligned with judges while staying equally
  informative (84.3% exit-set recovery).
- **Counterfactual pro swap (median-profile celebrity; season S10, age 36,
  Actor/Actress, week 5; exact expit):** judge-z / fan-share = **+0.672 / 16.9%**
  (Derek Hough; stored 0.1685) vs **−0.081 / 10.6%** (Peta Murgatroyd, median;
  stored 0.1055) vs **−1.505 / 4.3%** (Koko Iwasaki, worst; stored 0.0432) —
  the partnership is worth ~2.2 judge-z units and ~12.5 pp of fan share
  (percentages displayed at 1 dp, half-up).

## Sanity Checks
- Weekly share normalization Σ_c φ = 1.000000 (335/335 season-weeks) on the
  canonical Model-1 input.
- Aggregate fan-surface wins vs judge-only baseline: bottom-m 198/235 (84.3%) vs
  88/235 (37.4%); single-exit exact 170/206 (82.5%) vs 39.8%; bottom-3 capture
  232/235 (98.7%) vs 179/235 (76.2%); all three met or exceeded by wide margins
  (in-house lite stage: 97/235, 81/206, 184/235 — sensitivity only).
- Known-elite validation: Derek Hough #1, Valentin #3, Mark #5, Cheryl #15 of 41
  eligible pros — PASS (top-15 requirement).
- Judge-surface decomposition (unchanged from pre-revision runs — byte-equivalent):
  pro 0.125 (p = 0.003), industry 0.059 (p = 0.028), age 0.134 (p = 0.001),
  week 0.018 (p = 0.099), multi ≈ 0; fan-side values from the canonical input:
  pro 0.138, industry 0.056, age 0.094, week 0.164.
- Permutation tests: 1,000 per block; per-block scheme documented in
  `model2_decomp.csv` notes; permuted pro/industry blocks use the identical
  drop-first coding and column order as the observed design.
- Determinism: two consecutive runs → byte-identical `results.json`; no
  wall-clock fields in the payload.
- Posterior-share plausibility: min/max [0.0015, 0.5702]; mean posterior sd 0.058;
  bands never inverted (lo95 ≤ hi95 for all 2,777 rows); certainty VARIES by week
  and market size (reported).
- LOSO: judge 0.141 raw / 0.157 intercept-recalibrated (target 0.25 NOT met —
  judge-panel calibration is season-specific; reported); fan −2.63 raw (unrecalibrated
  canon shares do not transfer: the level offset dominates) but **0.170
  intercept-recalibrated** and 0.199 season-FE-free (target 0.15 met on both
  transfer variants; the lite surface passes identically).

## Model Parameters
- Fan-share stage: β = 1.387 (judge-z → log-share), θ = −0.0001 (week), persona
  prior sd 1.0, shake sd 0.18 (log-ν), shake slope −0.06/10wk, copula sd 1.2,
  finale constraint weight 0.5, margin threshold 0.10; 500 shake blocks × 1,000
  copula draws (seed 2026); 267 soft ordinal constraints (235 exit weeks, exact PL
  set form for |E| ≤ 3; 32 finale orderings at half weight).
- Surfaces: intercept + 33 season dummies + 51 pro dummies (drop-first; reference =
  Alan Bersten) + 24 industry dummies (reference = Actor/Actress) + age RCS
  (knots 20/30/45/65) + week RCS (knots 1/3/6/10) + multi-dance flag; OLS with
  421-cluster (celebrity-run) robust covariance; 116 parameters per surface.
- Industry extremes (centered, judge surface, n = 25 levels): Producer +1.019,
  Astronaut +0.817, Musician +0.644; full table in `model2_industry_effects.csv`.

## Data Files Generated
- `results.json` — every headline number (source of all values in this summary);
  deterministic, no wall-clock fields.
- `model2_fanshare.csv` — 2,777 rows: φ posterior mean/sd/95% band per
  contestant-week; `fanshare` (canonical Model-1 `phi_share`) alongside
  `fanshare_lite` (in-house sensitivity stage); judge share; residual flags.
- `model2_decomp.csv` — 12 rows: R_k, null q95, permutation p per (surface ×
  block); per-block shuffle scheme documented in the module docstring.
- `model2_pro_rankings.csv` — 52 rows: centered effects and cluster-bootstrap CIs
  per pro, both surfaces, eligibility flag.
- `model2_industry_effects.csv` — 25 rows: centered industry effects, both
  surfaces, with CIs (reference rows flagged with NaN CIs by construction of the
  drop-first coding).
- `model2_effects.csv` — 94 rows: age spline (14–82) and week spline (1–11) curve
  values on a grid, both surfaces, plus multi-dance flag effect.
- `model2_exitfit.csv` — 235 rows: per-exit-week consistency diagnostics
  (bottom-m capture, exact-set hits) under both fan inputs.
- `model2_era_drift.csv` — 3 rows: era metrics (mean |fan − judge| gap,
  within-week Spearman, median top/bottom share ratio).
- `figures/F6..F10` PNGs (dpi 300).

## Figures
- `F6_pro_forest.png` — top-15 pro effects, judge vs fan with 95% CIs.
- `F7_age_spline.png` — age response curves, judge vs fan (monotone decline;
  fan-surface plateau late in life; judge curve negative at age 20).
- `F8_industry_heatmap.png` — 25 industry levels × 2 surfaces (centered effects).
- `F9_week_curve.png` — learning/fatigue curve, judge vs fan surfaces.
- `F10_pro_quadrant.png` — pro judge-vs-fan effect quadrant (ρ = 0.623).

## Issues or Limitations
1. Fan shares are ordinal-identified only (elimination orderings); the mean
   posterior sd (0.058) is the honest identification ceiling; certainty VARIES by
   week and market size (reported).
2. Exit recovery is input-dependent: canonical Model-1 φ gives 84.3% bottom-m /
   82.5% single-exit exact / 98.7% bottom-3 / 28-29 multi-exit; the in-house lite
   stage gives 41.3% / 39.4% (a statistical tie with judge-only on single-exit
   exact) / 78.3%. The deliverable value of Model 2's own stage is the persona
   surface, lite bottom-3 capture, and calibrated bands — the canonical number
   should be credited to Model 1's machinery.
3. LOSO judge target (0.25) not met (0.141/0.157): judge-panel calibration is
   season-specific and structurally untransferable; the fan surface meets its
   target on both transfer variants (0.170 recal / 0.199 season-FE-free).
4. Pro assignments are endogenous; the restricted spec (fame control, weeks-2+) is
   the honest lower bound (R_pro 0.114 judge / 0.134 fan); residual sorting may
   remain.
5. Judge positions are anonymous in the data (slots, not names); judge-identity
   effects are not identifiable — panel-level analysis only.
6. Multi-dance weeks leave R ≈ 0 after weekly z-normalization (by construction;
   the flag confirms no residual artifact, p > 0.6).
7. Pro dummies are drop-first coded (reference = Alan Bersten); reference rows in
   the rankings/industry tables carry NaN bootstrap CIs by construction.
