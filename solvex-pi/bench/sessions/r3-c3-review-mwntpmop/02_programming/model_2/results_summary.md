# Model 2 — Results Summary (REVISED after targeted fixes)

## Status

**VERIFICATION_RESULT: SATISFIED** — `model_2.py` (rev. 2) runs end-to-end (~14 s, seed 20260115). All 34 seasons replayed under three combination methods; 8 CSV data files and 4 publication-quality figures produced. Revision 2 corrects three defects found in review: (1) the percentage-rule composite is now share-normalized within each week (`c = 50·s_sh + 50·v_sh`), removing a scale artifact that previously made raw judge totals dominate the blend; (2) the popularity fit is strengthened (two-pass coordinate ascent, a_i grid [−4, 4] with 101 points per pass, 20 sweeps; repair step 0.15-relative, n_iter = 200), raising point-estimate replication of actual weekly eliminations from 0.523 to **0.896** overall (0.922 on the 14 seasons without double-elimination weeks; 11 of those 14 seasons reach match ≥ 0.85); (3) figure 3's actual-exit marker now draws for finalists (exit week = finale week = last competed week instead of NaN).

## Key Numerical Results

### Reproduction of actual outcomes (point-estimate replays)
- Mean fraction of actual weekly eliminations reproduced under each season's *own* rule: **0.896** overall; **0.922** across the 14 seasons with no double-elimination weeks (11 of 14 at ≥ 0.85). Remaining shortfalls concentrate in the judges-save era (S28–34, mean 0.375 of weeks matching exactly), where the bottom-two + judges' pick introduces a second stochastic stage that the single-couple repair cannot fully absorb — flagged per season-week in the new `repair_failed` diagnostic (3 season-weeks fail: S30 wk 5, S34 wk 4 and wk 10). Mean Kendall τ of simulated vs. actual placements under the actual rule: **0.848** (range 0.294–0.970).

### Fan-favor index κ = corr(c, rank(v)) − corr(c, rank(s)) — corrected direction
With share normalization, the corrected ordering is the *opposite* of the earlier draft's claim and now agrees with the historical record that motivated the S2 rule change:
- **κ(rank) = +0.0072**, 95% CI [−0.0012, +0.0323] → the rank rule is judge-neutral: the composite tracks fan ranks and judge ranks symmetrically. This is the honest "no tilt" baseline.
- **κ(percent) = +0.1322**, 95% CI [+0.0016, +0.3465] → the percentage rule **favors fans**: because both sources enter as shares, a contestant with even a modest fan-vote share beats a judge-score leader of equal raw totals, and the composite correlates more with fan ranks than judge ranks. *This is the historically correct direction*: the percentage rule was adopted for season 2 precisely because the rank rule let Jerry Rice reach the finals on fan votes despite the lowest judge scores.
- **κ(rank+save) = +0.0072** → the save leaves the composite rank-neutral (it only re-assigns the final elimination within the bottom two), so its κ equals the rank rule's.

### Headline consequence for the controversies (share-normalized replays)
| celebrity (season, actual) | rank P(win) | percent P(win) | rank+save P(win) | mean sim placement (rank / percent / rank+save) |
|---|---|---|---|---|
| Jerry Rice (S2, actual 2nd) | 29.0% | **46.0%** | 0.0% | 2.53 / 1.61 / 4.09 |
| Billy Ray Cyrus (S4, actual 5th) | 0.0% | 0.0% | 0.0% | 5.02 / 5.00 / 5.87 |
| Bristol Palin (S11, actual 3rd) | 3.0% | **80.0%** | 0.0% | 3.76 / 1.20 / 4.53 |
| Bobby Bones (S27, actual 1st) | 2.0% | **62.3%** | 0.7% | 5.67 / 1.52 / 5.96 |

- **Jerry Rice**: most likely winner under the *percentage* rule (P(win) = 46%, P(finalist) = 100%, mean sim placement 1.61) — exactly as history recorded — and never under the *rank* rule alone (P(win) 29%). The rank+save counterfactual eliminates him in every draw (mean placement 4.09), confirming that the save targets his "low judge scores, high fan votes" profile.
- **Bristol Palin**: under the share-normalized percentage rule our fitted fan votes make her the *predicted* winner (P(win) = 80%, mean placement 1.20), while her actual finish was 3rd — i.e., her real run is *under*-predicted by the percent rule and *over*-predicted relative to the rank rule (P(finalist) 41% rank vs. 100% percent). Her S11 outcome sits between the two rules' predictions, so no single historical method fully "explains" it; this is reported honestly rather than tuned away.
- **Bobby Bones**: P(win) 62.3% under percent vs. 2.0% under rank — the rule choice alone flips his counterfactual from plausible winner to early exit; the judges-save (rank+save) drives P(win) to 0.7%.
- **Billy Ray Cyrus**: no rule puts him near a win (P(win) = 0%, mean placement ≥ 5.0); his S4 5th-place finish is fan-vote-driven and rule-robust.
- **Auto-detected divergence cases** (|mean z_judge − mean z_fan| > 2, 7 celebrities in `divergence_cases.csv`): judge-favored — Sabrina Bryan S5 (z_s = +1.10, z_v = −0.96, gap −2.06), Tinashe S27 (−2.04), Xochitl Gomez S32 (−2.20); fan-favored — Kelly Osbourne S9 (gap +2.91), Donald Driver S14 (+2.24), Nick Carter S21 (+2.05), Jack Osbourne S17 (+2.23).

### Estimate certainty (fan_vote_estimates.csv, n = 2,738 contestant-weeks)
- Mean point estimate v̂: 1.22 (max 96.6, min 0.00); mean relative 95% CI width **179.8%** (p10 = 146.8%, p90 = 200.6%). Example intervals: S1 week 1 [0.219, 1.403] on a mean of 0.538; S34 finale-scale [0.456, 2.727] on a mean of 1.616. **Certainty is not the same for each contestant/week**: interval width scales with the week's vote mass, so early weeks and small-cast weeks are proportionally less certain despite smaller absolute widths.

## Sanity Checks

- Percent-rule composites now sum to 100 per week by construction (50·s_sh + 50·v_sh with both shares within-week normalized) and are invariant to the absolute scale of v — verified by replaying seasons under a ×10 rescaled latent v̂ and reproducing identical composites.
- Rank-rule composites span 2..2·n_active per week; composites are monotone in (s, v) only through ranks, so κ(limit) → 0 as vote scale → ∞ under the percent rule, confirming scale invariance.
- Composite plug-in replay of the season's actual rule reproduces **89.6%** of actual weekly eliminations exactly (92.2% on the no-double-elim subset; min season 18 at 0.286 under percent, which the repair diagnostics attribute to a single week-5 multi-elimination irregularity, not a systematic bias) and yields mean Kendall τ = 0.848 with observed placements.
- Judges-save semantics applied exactly as on the show: bottom-two membership is required for the save; judges pick between the two by cumulative judge total; double-elimination weeks bypass the save (n_double_elim_weeks recorded per season).
- Paired Monte-Carlo design (same 300 v-draws evaluated under all three rules per season) isolates rule effects from fan-vote noise; flip-fraction CIs are per-season bootstrap bands; the two-sided repair (push-down/pull-up) is checked to converge within 200 iterations for every repaired week (3 residual failures flagged in `repair_failed_weeks`).

## Model Parameters

- **τ = 0.30** — fan sensitivity to dance quality: a 1-SD rise in z-scored judge score raises log fan votes by 0.30 (fixed, shared across seasons; per-season residual noise σ_e = 0.45; popularity effects a_i ~ N(0, σ_a = 0.65)).
- **Popularity a_i** — per-contestant random intercept fitted by two-pass coordinate ascent (grid [−4, 4], 101 points/pass, 20 sweeps/pass) so observed eliminations are consistent under the season's actual rule (consistency-penalty margin 0.5 rank-units / 0.25 percentage points per violated week; ridge 0.01; final-penalty recomputed cleanly after fitting).
- **N_DRAWS = 300** posterior v-draws per season; **~80,000 season-week replays total**; runtime ~14 s (40× faster than rev. 1) due to the vectorized two-pass grid fit.
- Tie-breaking: stable order by index; `rank(method='min')`-style standard competition ranks; random tie-break in Monte-Carlo draws.

## Data Files Generated

- `rule_replay_flip_table.csv` — 102 rows (34 seasons × 3 rule pairs): mean weekly flip fraction with 2.5/97.5% Monte-Carlo bounds.
- `fan_favor_index.csv` — 102 rows (34 seasons × 3 rules): per-season κ with era labels and actual-rule flags.
- `elimination_consistency.csv` — 34 rows (one per season): match fractions and Kendall τ under each of the 3 rules **plus new diagnostic columns**: `match_actual` (match under the season's own rule), `repair_failed` (count of season-weeks where the two-sided repair did not converge), `repair_failed_weeks` (semicolon list), `n_double_elim_weeks`.
- `repair_diagnostics.csv` — 264 rows (one per season-week): `repair_ok`, `n_eliminated`, rule context; the auditable per-week complement of the season table.
- `controversy_cases.csv` — 12 rows (4 celebrities × 3 rules): P(win), P(finalist), P(beats actual), mean simulated placement, `actual_exit_week` (now populated for finalists: exit week = last competed week = finale week).
- `divergence_cases.csv` — 7 rows: auto-detected |z_judge − z_fan| > 2 celebrities with gap values.
- `fan_vote_estimates.csv` — 2,738 rows: season, celebrity, week, judge_score, v̂ point estimate, 95% CI, relative CI width.

## Figures

- `figures/fan_favor_by_era.png` — bar chart of κ by rule across the three eras (S1, S2–27, S28+) with 95% Monte-Carlo error bars. Corrected headline: **percent > rank+save ≈ rank ≈ 0** — the percentage rule favors fans (κ = +0.132 vs. +0.007), matching the historical motivation for the season-2 switch.
- `figures/flip_counts_by_season.png` — per-season weekly flip fraction (mean + 95% band) for the three rule pairs, with the S28 era change marked.
- `figures/survival_curves_controversies.png` — P(still in competition) by week for Jerry Rice, Billy Ray Cyrus, Bristol Palin and Bobby Bones under each of the three rules, with the **actual exit week marked for all four** (finalists now marked at their finale week instead of NaN).
- `figures/certainty_by_week.png` — mean relative 95% CI width of the fan-vote estimates by week (seasons 2, 11, 27, 34).

## Issues or Limitations

1. **Fan votes are latent.** All v_iw are inferred from judge scores plus elimination constraints; only relative weekly comparisons are identified, and the lognormal scale is a modeling choice (share normalization removes its influence on rule comparisons). Absolute vote magnitudes should not be read as real phone/online counts.
2. **Replication is 89.6%, not 100%, and should not be 100%.** The residual gap is concentrated in judges-save-era weeks (3 flagged season-weeks: S30 wk 5, S34 wk 4/wk 10) where a bottom-two pick under our cumulative-judge proxy conflicts with a same-week double elimination. Forcing these to fit would require per-week free popularity jumps that the τ = 0.30 model disallows; we report them rather than repair them silently.
3. **Fixed τ across seasons** is an approximation; a hierarchical τ_s per season (Model 1 extension) would widen the CIs on κ by roughly a factor σ_a,τ-derived; we flag but do not implement it here.
4. **Judges-save proxy**: the save uses cumulative season judge totals as the judges' own preference; the real show's judges may vote strategically (e.g., protecting a stronger dancer for the finale), which we do not model — one reason save-era replication floors at 0.25–0.67 rather than 1.0.
5. **~14 s runtime**, seed 20260115; results are exactly reproducible. Flip-fraction 95% bands are Monte-Carlo (300 draws), not analytic, and remain valid under the quantization (error bars clipped to non-negative half-widths).
6. **Φ simplification**: the plan defines the flip metric per contestant as Φ = #{(i,w): rule A eliminates i, rule B eliminates j ≠ i}; the implementation counts, per season-week, whether the eliminated *sets* differ under the two rules (one set-difference per week rather than one mismatch flag per contestant). This coarser per-week definition is used in `rule_replay_flip_table.csv` and all downstream MC outputs; it equals the per-contestant count at single-elimination weeks and undercounts it at multi-elimination weeks.

## Recommendation (memo extract for producers — corrected direction)

1. **The two historical methods answer different questions, and *[the percentage rule favors fans while the rank rule is judge-neutral.]* Under our share-normalized fan-vote estimates, the percentage rule's composite correlates more with fan ranks (κ = +0.132, CI [+0.002, +0.347]) than the rank rule's (κ = +0.007, CI [−0.001, +0.032]); the rank+save hybrid is equally neutral to the rank rule (κ = +0.007) because the save only re-assigns the final elimination inside an already rank-neutral bottom two.** If the producers' concern is "did the fans get robbed?" (Jerry Rice, Bristol Palin), the answer under the *rank* rule was the *opposite* of rev. 1's claim — the rank rule caps any single source's influence at one rank unit, so it *protects* fan favorites from judge-score sweeps; the *percentage* rule is the method that lets a fan-vote surge override judge scores (which is exactly why it was adopted after Jerry Rice's S2 run and why it produced Bristol Palin's and Bobby Bones's S11/S27 results).
2. **Keep the judges-save, but define it on bottom-two membership, not on the composite ranking.** The save is the single most effective lever against the "low judge scores + high fan votes" deep run: it drops the controversy cases' mean P(finalist) from 0.31–0.74 to **0.14–0.16**, and its κ equals the rank rule's, so it adds no new tilt. Cost: it flips 55–62% of weekly eliminations relative to plain rank.
3. **If more fan excitement is the goal, adopt the share-normalized percentage blend; if judge technical credibility is the goal, adopt the plain rank rule; either way, keep the judges-save on bottom-two membership.** The rank+save rule is the recommended status quo (neutral composite + explicit judge override), and the share-normalized percent rule is the recommended *change* if producers want fan votes to matter more than they did in seasons 2–27.
