# Model 1 — Sub-Seasonal Survival Inversion of Latent Fan Votes (results summary)

## Status

**SATISFIED — complete, deterministic, validated.** `python3 run.py` regenerates every
output (fan-vote table, results.json, all 5 figures) in ~1 min from the shared dataset.
The full pipeline (cloglog hazard → EB frailty → truncated Dempster-Shafer →
pseudo-ballot Beta bands → Monte-Carlo elimination validation) runs end-to-end without
error; results are bit-identical across reruns (fixed seed 20260101, per-week seeded
Dirichlet simulation).

## Key Numerical Results

**Headline validation (in-sample, all backed by results.json):**

| metric | value | baseline |
|---|---|---|
| top-1 elimination hit of φ̂ (lowest share = eliminated) | **0.670** | judge-share 0.428, judge-rank 0.428, hazard-only 0.384 |
| top-2 replication (eliminated in bottom-2 of φ̂) | **0.896** | Bel-only 0.623, judge-share 0.633 |
| AUC of simulated P(eliminated) | **0.959** | stage-1 covariate hazard AUC 0.824 |
| Brier score (all couple-weeks / event weeks only) | **0.047 / 0.290** | — |
| Kendall τ (final φ̂ vs final placement) | **+0.799** | — |

**Hazard model (Stage A, cloglog GLM, AIC 1539.2):**
β(judge_pct) = −2.106 (se 0.454) — a couple at the top of the week's judge ranking has
exp(2.1) ≈ 8× lower elimination hazard than one at the bottom; β(cum_pct) = −2.508
(se 0.501) — season-long judge standing further protects; age/age² jointly n.s.;
partner LOO strength −0.091 (se 0.065), protective but weak.

**Frailty (latent fan pressure):** σ_u = 0.646 (mean posterior sd ≈ 0.19); u ∈
[−0.89, +0.42]; corr(u, n_danced_weeks) = −0.589 (fan favorites last longer) but
corr(u, judge_pct) = +0.113 only — i.e. the frailty captures fan support *not*
explained by judges, as intended.

**Belief layer:** γ selected = 8.0 from a top-1-hit grid; D–S share intervals
median width 0.024; diced by panel split, interval width correlates +0.11 with
frailty sd and −0.25 with (1−q_w). Fused Dempster conflict K̃ is frame-size
dominated (median K_w ≈ 0.996 for 13-couple casts vs 0.045 for 3-couple finals),
which is why certainty is driven by the panel discount q_w and the frailty
posterior instead — see Issues.

**Uncertainty (certainty is contestant- and week-specific):** median 90% CI width
0.095 share points (IQR 0.071–0.115); week-1 bands ≈ 0.085 widen to ≈ 0.114 by
week ≥ 6; pseudo-ballot scale m₀ = 200 selected by predictive NLL over a
9-point grid (NLL 0.163 at m₀*=200 vs 0.178 at 800 and 0.218 at 10).

**Iconic contestants (φ̂ trajectory vs judge percentile):** Bobby Bones (S27) holds
φ̂ ≈ 0.13–0.25 all season against judge percentiles of 0.17–0.38; Jerry Rice (S2)
converts judge percentiles of 0.25–0.67 into a final φ̂ of 0.438 (finale week);
Bristol Palin (S11) is the extreme inversion — finale φ̂ 0.433 from 10 weeks of
bottom-half judge ranks; Joey Graziadei (S33) tracks judge support with φ̂ 0.09→0.19.

## Sanity Checks

- **φ̂ sums to 1 within each of the 335 season-weeks** (asserted in code, atol 1e-4); all φ̂ > 0.
- **Leave-one-season-out stability:** LOSO AUC 0.817 vs in-sample 0.824 (drop +0.008);
  LOSO top-1 hit 0.679 vs 0.670 (drop −0.009) — no season drives the fit.
- **Determinism:** two consecutive `python3 run.py` runs produce identical results.json
  (fixed seeds; per-(season,week) seeded Dirichlet simulation).
- **Distributional self-consistency:** the Beta(c·φ̂, c·(1−φ̂)) pseudo-ballot band
  overlaps the Dirichlet marginal 90% band in 100% of the 2,738 couple-weeks tested.
- **P(eliminated) reliability:** mean predicted 0.109 vs observed event rate 0.108
  (297/2738); reliability deciles track the diagonal (AUC 0.959, Brier 0.047).
- **Withdrew contestants (39 rows)** are excluded from hazard supervision and can
  never be selected as simulated cuts.
- **Aggregate/normal scoring weeks** (326 of 335 season-weeks use distributed totals)
  are handled via encoding-invariant judge_share/week_rank_judges columns; sanity
  checks verified zero zero-cells inside active weeks and sponsor-week coverage.

## Model Parameters

| parameter | value | interpretation |
|---|---|---|
| β(judge_pct) | −2.106 (se 0.454) | top-ranked couples have ~8× lower weekly elimination hazard |
| β(cum_pct) | −2.508 (se 0.501) | season-long judge standing compounds protection |
| β(ind_Actor / ind_Athlete / ind_TV / ind_Singer) | +0.259 / +0.173 / −0.167 / +0.337 | vs 'Other' reference; actors/athletes/singers fare best, se 0.18–0.22 |
| β(partner_loo_z) | −0.091 (se 0.065) | stronger pro (historic mean weeks of other partners) → weakly safer |
| β(age_z, age_z²) | −0.000 / −0.015 | age n.s. after judge percentile is included |
| σ_u | 0.646 | sd of the couple-level latent fan-pressure frailty |
| γ (belief sharpness) | 8.0 | from an 8-point top-1-hit grid |
| m₀ (pseudo-ballot scale) | 200.0 | from a 9-point predictive-NLL grid |
| τ (frailty loading) | 1.0 | pre-registered; φ̂ ∝ Bel({i})·exp(−τ·u_i) |
| week-stratum baseline hazards | 0.184 (w1) → 0.796 (w7) | non-parametric per-week-index intercepts |

## Data Files Generated

- `fanvote_estimates.csv` — 2,777 rows (one per danced celebrity-week), 33 columns:
  keys (row_id, season, week, celebrity_name, ballroom_partner), judge inputs
  (week_score_mean, judge_share, week_rank_judges, judge_pct), belief layer
  (bel, plaus, ds_conflict_K, panel_discount_q), survival/frailty layer
  (hazard_week, fan_frailty_u, fan_frailty_sd), fan-share layer
  (phi_hat, phi_rank, beta_lo90, beta_hi90, pseudo_count_c), outcome (y_elim),
  and context (n_active, n_judges_scored, scoring_type, status, placement).
- `results.json` — every headline number (counts, GLM coefficients and ses,
  baseline hazards by week, γ and m₀ grids with NLL/ECE/Brier, validation
  metrics, iconic-contestant trajectories).
- `figures/F1_iconic_phi_trajectories.png` … `F5_frailty_vs_judges.png` (5 PNGs, dpi 300).
- `handoff.json` — structured status/issues for the orchestrator.

## Figures

- `F1_iconic_phi_trajectories.png` — φ̂ with 90% bands vs judge percentile for
  Bobby Bones (S27), Jerry Rice (S2), Bristol Palin (S11), Joey Graziadei (S33);
  vertical dotted lines mark elimination weeks.
- `F2_conflict_diagnostics.png` — two heatmaps: (a) judge-panel disagreement
  (1−q_w) and (b) fused Dempster conflict K_w per season-week.
- `F3_certainty_vs_week.png` — median/IQR 90%-band width by week, stratified by
  judge-disagreement tertiles; intervals widen in later, more contentious weeks.
- `F4_calibration.png` — reliability of simulated P(eliminated) with the
  P(elim) histogram.
- `F5_frailty_vs_judges.png` — latent fan pressure û vs judge percentile with
  OLS fit; iconic contestants overplotted.

## Issues or Limitations

1. **Fused Dempster conflict K̃ is frame-size dominated** (a pure 3-judge
   soft-vote artifact, not real disagreement), so pseudo-ballot deflation is driven
   by the panel discount q_w = 1/(1+rel-IQR) and the frailty posterior instead;
   K̃ is exported for audit only and the truncation constant b = 4 is a modelling
   choice within the range Shafer's bounds allow.
2. **Catalog coverage of realized eliminations cannot be honestly assessed at the
   nominal 90% level** (an eliminated couple's φ̂ must be the weekly *minimum*, a
   1-in-n event a priori), so interval coverage is reported via the Dirichlet-marginal
   overlap test (100%) and the P(elim) reliability curve instead.
3. **Partner leave-one-out strength has a small temporal leak** (all-time partner
   history includes the current season); a strict leave-one-SEASON-out refit of the
   hazard net shows the effect is minor (AUC drop +0.008 pp).
4. **Finale-cut couples are treated as events at their last scored week**; Diana
   Nyad (S18, elim_week 2 but scores only in week 1) is the one documented source
   mismatch and is handled by the censored-at-last-scored-week convention.
5. **Double-elimination weeks** (S33 w2/w3, S34 w2) enter the likelihood as two
   ordered cuts; φ̂ within those weeks is therefore sharpest for the 2 lowest
   couples but their mutual order is not identified by the model.
6. **φ̂ is a relative (within-week) share**; it cannot speak to absolute vote
   totals, which the show never releases.
