# Model 2 — Judge–Fan Fusion Engine: Rank vs Percentage Combination (Results Summary)

## Status

**COMPLETE (revision 2 — cross-review fixes applied).** The full pipeline runs end-to-end
deterministically (`python3 run.py`, ~30 s, seed 42): `results.json` contains no
wall-clock or random state and is byte-identical across consecutive re-runs. All
outputs — 12 CSV data files, 10 figures (PNG, 300 dpi), `results.json`, `handoff.json`
— are regenerated from the shared dataset alone. Revision 2 added: the event-weighted
cut-event ledger (fix 1), a dedicated S28+ rule/stage decomposition table with corrected
numbers (fix 3), the plan-required HDI-bound sensitivity experiment (fix 5, new
`hdi_bound_sensitivity.csv` + Figure F12), the three promised `shared_data` copies
(now verified written; fix 6), the in-sample calibration caveat (fix 7), and a
non-overlapping re-render of Figure F5 (fix 7).

## Key Numerical Results

**Calibration (composite pseudo-likelihood of the observed 298 eliminations, 2,780 couple-weeks):**
- θ̂ = (α, β, σ) = (1.5, 0.0, 0.05); composite log-lik = −47.37 (grid stage-2 winner)
- Runner-up local mode (0.1, 1.5, 0.05) at −47.96 — the two members of the ridge are
  within 0.6 log-lik points; parameters trade off (weekly vs career judge signal)

**Fan-vote estimates φ̂ (2,780 cells, 34 seasons):**
- mean φ̂ = 0.1205 across active couples; median relative 90%-band width = 15.8% of φ̂
- absolute band widths: p10 = 0.0049, p90 = 0.0346 (bands widen for low-φ̂ couples —
  certainty is heterogeneous by design)
- Fitted fan-appeal u_i extremes: highest Marie Osmond +2.50, Mya +1.75, Amy Purdy /
  Riker Lynch / Helio Castroneves / Bindi Irwin +1.50; lowest Shannen Doherty / Redfoo
  −2.00, David Alan Grier −1.75; Bobby Bones (S27) +0.625

**Observed-era replay validation (era-correct rule per season):**
- **88.9% is the mean of per-season cut-match rates** (`replay_validation_by_season.csv`,
  34 seasons). The event-weighted ledger from the same runs is **265 matched of 299 cut
  events = 88.6%** (299 = Σk_w; one more than the 298 eliminated contestants because the
  S18 quota arithmetic carries +1 for the Billy Dee Williams withdrawal/Diana Nyad patch —
  see Sanity Checks).
- pooled bottom-set Jaccard = 0.881 (mean of season means); placement MAE = 0.56; τ = 0.902
- by era (mean of per-season rates): S1–2 rank **100%**, S3–27 percentage **99.2%**,
  S28+ rank+dance-off **49.0%** — see the S28+ decomposition below for what drives that.

**Rank (R) vs percentage (P) divergence across 34 seasons (same fan votes φ̂):**
- weekly rule-disagreement rate γ_s: mean 0.468, median 0.444 of elimination weeks
- zero-disagreement seasons: S1, S25, S26 (γ_s = 0 — method choice irrelevant there)
- most disagreement: S9 γ_s = 0.889; high-disagreement: S8/S11/S13 0.778, S7/S12 0.750
- pooled over all elimination weeks: **129 disagreement weeks / 265 elimination weeks =
  48.7%** (from `rule_disagreement_by_season.csv`)

**S28+ rule/stage decomposition (event-weighted, from `s28plus_rule_overlay.csv`):**
| stage combo | matched / cut events | event rate | mean bottom Jaccard |
|---|---|---|---|
| plain rank (no dance-off) | 58/65 | **89.2%** | 0.859 |
| plain percentage (no dance-off) | 34/65 | 52.3% | 0.506 |
| rank + dance-off (= observed era engine) | 33/65 | 50.8% | 0.456 |
| percentage + dance-off | 31/65 | 47.7% | 0.447 |
The S28+ divergence between the engine and the observed record is therefore driven by
the dance-off stage itself ( judges' deliberation choices, which are not in the data),
NOT by the choice between rank and percentage: dropping the dance-off stage lifts
reproduction from ~51% to 89% under rank, while swapping rank→percentage without the
stage drops it to 52%.

**Controversies (placement: observed | rank R | percentage P | z-score Z):**
| celebrity (season) | observed | R | P | Z | verdict |
|---|---|---|---|---|---|
| Jerry Rice (S2) | 2 | 2 | 2 | 2 | identical under both rules — no method-attributable effect |
| Billy Ray Cyrus (S4) | 5 | 5 | 5 | 7 | R and P agree with observed; Z would cut 2 weeks earlier |
| Bristol Palin (S11) | 3 | 4 | 2 | 5 | **under P she is runner-up (2nd; the replayed P winner is Kyle Massey); R cuts her one week earlier (4th)** |
| Bobby Bones (S27) | 1 | 5 | 3 | 5 | neither rule reproduces the win; P gets closest (3rd) |
| Mya (S9) | 2 | 2 | 1 | 1 | P/Z would have made Mya champion (observed Donny Osmond 1st: R=1, P=2) |
| Sabrina Bryan (S5) | 7 | 7 | 7 | 7 | early S5 elimination predicted identical under every rule |
| Sabrina Bryan (S15) | 8 | 3 | 8 | 2 | **rank-style rules would have kept her to the finale (R 3rd / Z 2nd); the percentage-era exit is reproduced exactly under P** |

**Fan-vote flip elasticity (φ̂ × multiplier from week 1, placement after replay,
from `controversy_flip_curves.csv`):**
- Bristol Palin: ×2 → R 4th, P 2nd; ×4/×8/×16 → P 1st but **R stays 2nd at every
  multiplier (never wins under R)** — the percentage rule is strictly more responsive
  to fan surges in her case
- Bobby Bones: ×2 → R 4th, P 2nd; ×4 → R 2nd, P 1st; ×8/×16 → R 2nd, P 1st (same
  ceiling: rank rule never makes him champion in the replay)
- Mya: ×2 → P 1st (already champion), R stays 2nd through ×16
- Jerry Rice: ×2 → R 2nd (unchanged), P 1st; further multipliers change nothing under R
- Billy Ray Cyrus: ×2 → R 5th→5th, P 1st; R reaches 3rd at ×4 and stays there
- Sabrina Bryan S15: ×2 → R 2nd, P 4th (the rank rule rewards her earlier fan support more)
- Sabrina Bryan S5: even ×16 only lifts R to 1st from 7th at ×8 (P reaches 1st at ×4)

**HDI-bound sensitivity (new, fix 5; `hdi_bound_sensitivity.csv` + Figure F12):**
re-running the controversy replays with the focal celebrity's φ̂ at its 90% band edges
(lo/hi in every week they danced, all other couples at point φ̂):
- **7 of 8 verdicts are robust**: Jerry Rice 2/2/2, Billy Ray Cyrus 5/5/5, Bristol
  Palin R 4/4/4 + P 2/2/2, Mya R 2 + P 1, Donny Osmond R 1 + P 2, Sabrina Bryan S5
  7/7/7, Sabrina Bryan S15 R 3 + P 8 — placement identical at lo, point, hi in every
  case (σ = 0.05 gives thin vote noise; one band edge moves φ̂ by ≈±8% relative —
  the median full 90% width is 15.8%).
- **1 verdict is fragile**: Bobby Bones P_base = 3rd, P_lo (φ̂ at its lower 90%
  edge) = **4th**, P_hi = 3rd — the lower band edge *worsens* his P projection by one
  podium place (3rd → 4th), the upper edge changes nothing; the headline verdict
  (P does not reproduce his win) is unchanged at both edges.

**Dance-off overlay (S28+, Rule R without vs with judges' save stage):**
- changes the cut in 2–5 of 6–9 elimination weeks per season (28:2, 29:5, 30:4, 31:3,
  32:5, 33:3, 34:5); placement shifts for 5–11 couples per season
- the era-correct (rank+dance-off) engine reproduces the observed record only 50.8%
  event-weighted (33/65) — see the S28+ decomposition above

**Recommendation metrics (averaged over 34 seasons):**
| rule | judge-consistency τ | fan-voice Gini | top-3-φ̂ shock rate |
|---|---|---|---|
| R (rank) | −0.756 | 0.546 | 0.038 |
| P (percentage) | −0.618 | 0.559 | 0.003 |
| Z (z-scored) | −0.799 | 0.530 | 0.050 |

The judges' dance-off layer, when added, favors judges by construction; the percentage
rule is the **least** judge-consistent (|τ| smallest: 1 = best placement vs 1 = best
judge percentile means a judge-aligned rule approaches τ = −1; Z at −0.799 is the MOST
judge-consistent, R −0.756, P −0.618) — P decouples outcomes most from judge quality,
which is why fan surges can flip them: it nearly eliminates shock eliminations
of fan favorites (0.3% vs 3.8% rank / 5.0% z).

## Sanity Checks

- Quota arithmetic: Σ_k_w = 299 across all seasons vs 298 eliminated-status contestants;
  the +1 is the S18 quota artifact of the Diana Nyad missing-week-2 patch (her week-2
  elimination is carried into the engine but Billy Dee Williams' contemporaneous
  withdrawal does not consume a quota slot) — documented, no other season deviates.
- φ̂ sums to 1 within every one of the 335 season-weeks (softmax, asserted)
- Era-correct reproduction: rank era 100%, percentage era 99.2% (mean of per-season
  rates) — the engine reproduces the observed record almost exactly where the show's
  data and rule are aligned; event-weighted equivalents are 100% and 99.1% (222/224)
- Crossover check: the 3 zero-γ_s seasons show R ≡ P identically (no spurious disputes)
- Determinism: two full runs → byte-identical results.json (no runtime field)
- Controversy directions match historical documentation: Bristol Palin S11 was a
  percentage-era beneficiary (replay: P 2nd vs R 4th); Sabrina Bryan S15's
  percentage-era exit is reproduced exactly under P and reversed under rank-style rules
- HDI-bound verdicts at 90% band edges confirm the controversy conclusions are not
  artifacts of φ̂ uncertainty (7/8 fully robust; the single adverse shift is Bobby Bones
  P 3rd→4th at the lower edge — the upper edge leaves 3rd unchanged — which does not
  change the verdict "P does not reproduce the win")
- U bounded in [−2.75, +2.5] ⊂ [−3, 3] (parameter cap respected)

## Model Parameters

- α (weekly judge-share weight) = 1.5, β (career judge-share weight) = 0.0,
  σ (lognormal vote-noise scale) = 0.05 — point identified on the composite ridge;
  the (α,β) = (0.1, 1.5) member is statistically indistinguishable (Δlog-lik 0.6)
- φ model: log φ_iw = u_i + α·log ρ_iw + β·log cJ_iw (softmax-normalized weekly)
- u_i: 421 free fan-appeal parameters (one per couple), coordinate-ascent fitted
- Judge dance-off proxy (S28+): lowest season-to-date mean judge score among bottom-(k+1)
- Elimination calendar (quotas k_w) held fixed at observed values in all replays —
  counterfactuals change WHO is cut, never WHEN/how many
- φ uncertainty: 120-draw profile-grid posterior over (α, β, σ) x 150-draw lognormal
  vote noise (common random numbers per season-week)

## Data Files Generated

| file | rows | content |
|---|---|---|
| `results.json` | 1 obj | every headline number (calibration, φ summary, per-season validation/γ, controversies, S28+ ledger, HDI sensitivity, dance-off overlay, recommendation metrics, figure list) |
| `fanvote_estimates.csv` | 2,780 | row_id, season, week, celebrity, φ̂, φ_lo90, φ_hi90, judge score/share, n_active |
| `rule_replay.csv` | 335 | per season-week: observed cut set + R/P/Z/obs-era cut sets and match flags |
| `rule_disagreement_by_season.csv` | 34 | weeks_with_elim, disagreement weeks (R vs P), γ_s |
| `controversy_table.csv` | 8 | named cases: placements under R/P/Z/obs-rule/dance-off + flip multipliers |
| `controversy_flip_curves.csv` | 56 | placement vs multiplier curves: 8 (celebrity, season) pairs × 7 multipliers (×1.0 base excluded) |
| `s28plus_rule_overlay.csv` | 4 | S28+ event-weighted reproduction by rule/stage combo (R/P × with/without dance-off) |
| `hdi_bound_sensitivity.csv` | 8 | controversy placements at φ̂ 90% band edges (R/P × lo/hi) |
| `replay_validation_by_season.csv` | 34 | era-correct cut-match, bottom-Jaccard, placement MAE + τ (now with matched/total event counts) |
| `u_fan_appeal.csv` | 421 | fitted fan-appeal u_i per couple (with names) |
| `calibration_grid.csv` | 214 | composite log-lik over the (α, β, σ) grid search |
| `danceoff_overlay_by_season.csv` | 7 | S28+: weeks where the dance-off stage changes the cut, changed weeks, placement shifts |
| `rule_metrics_by_season.csv` | 34 | per-season R/P/Z: judge-consistency τ, fan-voice Gini, shock rate, cut-match |
| `handoff.json` | 1 obj | {status, issues, fixInstructions, summaryPath} |
| `shared_data/model2_fanvote_estimates.csv` | 2,780 | copy for downstream models |
| `shared_data/model2_rule_replay.csv` | 335 | copy for downstream models |
| `shared_data/model2_controversy_table.csv` | 8 | copy for downstream models |

## Figures

- `figures/F4_gamma_by_season.png` — rule-disagreement rate γ_s per season (bar, era shading)
- `figures/F5_placement_flow.png` — re-rendered non-overlapping per-contestant rows:
  observed → Rule R / Rule P placement arrows for the 7 named controversies (+ legend)
- `figures/F6_tau_vs_gini.png` — judge-consistency vs fan-voice scatter, per rule, all 34 seasons
- `figures/F7_bobbybones_phi.png` — Bobby Bones S27 φ̂ trajectory with 90% band + judge-share overlay
- `figures/F7_jerryrice_phi.png` — Jerry Rice S2 φ̂ trajectory with 90% band
- `figures/F8_bandwidth_by_week.png` — φ̂ relative 90%-band width by week-in-season (certainty)
- `figures/F9_validation_by_season.png` — era-correct eliminated-couple reproduction by season
- `figures/F10_flip_curves.png` — flip curves: celebrity placement vs fan-vote multiplier
- `figures/F11_danceoff_flips.png` — dance-off overlay effect by season (S28+)
- `figures/F12_hdi_sensitivity.png` — controversy placements at φ̂ 90% band edges (error-bar style)

## Issues or Limitations

- **No Model-1 output existed** (`01_modeling/shared_data/fanvote_estimates.csv` was never
  produced by an upstream phase), so this model implements the φ̂ inversion itself —
  a single, documented, Module-1-compatible estimator. Downstream models should consume
  this project's `fanvote_estimates.csv`.
- **In-sample calibration (fix 7 flag):** u_i comprises 421 free parameters fitted
  against the same 2,780 couple-weeks / 299 cut events whose reproduction is reported.
  u_i therefore absorbs most of the identifiable fan signal, and the 88.9%/88.6%
  reproduction numbers are in-sample fit statistics, not honest out-of-sample
  predictions; no leave-one-season-out validation is performed in this model (it is
  deferred to a dedicated cross-validation pass). The (α,β) ridge adds the same
  caveat at the θ level.
- **Parameter ridge:** (α, β) = (1.5, 0.0) vs (0.1, 1.5) are within 0.6 log-lik points;
  we report the higher-likelihood point and its empirically similar replay behavior.
- **S28+ decomposition (corrected, fix 3):** the earlier claim that "percentage applied
  to S28+ reproduces 99%" was wrong. Correct event-weighted numbers: plain rank 89.2%,
  rank+dance-off 50.8%, plain percentage 52.3%, percentage+dance-off 47.7% — the S28+
  divergence is driven by the dance-off stage (judges' deliberation choices, not in the
  data), not by rank vs percentage. All S28+ counterfactuals carry this caveat.
- **Elimination calendar held fixed**: counterfactuals never change weeks/quota — by
  design (isolates rule effects); the S18 +1 quota artifact is a consequence of this
  design choice plus the Diana Nyad patch.
- **Certainty is not uniform**: bands are wider for low-φ̂ couples (relative widths
  reach ≈16% of φ̂ at the median and more at the tail) — flagged for downstream use.
- **HDI-bound sensitivity scope**: the band-edge experiment (fix 5) is performed for
  the 8 named controversies only, with the focal celebrity's φ̂ at its edges and other
  couples at point φ̂ — a partial (not full-joint) propagation of φ̂ uncertainty;
  a full-joint HDI-bound replay over all couples simultaneously is deferred (performed here only for the focal celebrity at its band edges).
- Diana Nyad (S18) missing week-2 scores and the two finale-cut finalists are patched by
  score carry-forward (documented in `build_season_context`).
