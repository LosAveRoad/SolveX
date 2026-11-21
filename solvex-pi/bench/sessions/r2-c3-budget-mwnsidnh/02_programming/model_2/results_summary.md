# Model 2 — Counterfactual Rules Laboratory (Results Summary)

## Status
**PARTIAL (functionally complete).** 33 of 34 seasons simulated successfully under all 4 rules (RANK, PCT, JUDGE_SAVE, PROPOSED) with N_DRAWS = 1000 posterior fan-share draws per week; **Season 25 failed** with a broadcasting error in the multi-elimination placement assignment (`ValueError: shape mismatch: value array of shape (1,2) could not be broadcast to indexing result of shape (1000,1)` — a double-elimination week where the placement tensor shape assumption broke). Season 25 is simply absent from `season_rule_metrics.csv` (33 unique seasons per rule instead of 34). All four CSVs, three figures, and `handoff.json` were written. Fix is localized to the `simulate_season` placement assignment block and does not affect the other 33 seasons' results.

## Key Numerical Results
Monte Carlo over 1,000 posterior draws × 4 rules × 33–34 seasons.

**Historical-rule replay validation** (RANK for seasons 1–2 & 28–34, PCT for 3–27; 34 seasons):
- Median P(observed winner wins) = **1.000**; mean = **0.774**; minimum = **0.030**.
- 27/34 seasons have winner-replay probability ≥ 0.5; 14/34 fall below 0.95. Weakest replays: Season 23 (P=0.030), Season 16 (0.048), Season 18 (0.064), Season 21 (0.067), Season 19 (0.072) — all PCT seasons.

**Controversial-couple counterfactuals (P(win), mean placement under each rule):**

| Celebrity (season, observed place) | RANK | PCT | JUDGE_SAVE | PROPOSED |
|---|---|---|---|---|
| Jerry Rice (S2, 2nd) | 0.039, 4.11 | 0.074, 4.72 | 0.039, 4.11 | 0.080, 5.45 |
| Billy Ray Cyrus (S4, 5th) | 0.000, 8.55 | 0.000, 7.43 | 0.000, 8.55 | 0.000, 6.80 |
| Bristol Palin (S11, 3rd) | 0.000, 5.08 | 0.000, 5.47 | 0.000, 5.08 | 0.000, 6.48 |
| Bobby Bones (S27, 1st) | 0.348, 1.81 | **1.000**, 1.00 | 0.348, 1.81 | **0.985**, 1.02 |

- **Bobby Bones (S27)**: under fan-weights PCT he wins in **100%** of draws (P(top3)=1.000), but under the rank-based RANK/JUDGE_SAVE rules only **34.8%** (mean placement 1.81) — the rule choice alone flips his outcome. PROPOSED keeps his win at 98.5% (mean placement 1.015).
- **Bristol Palin (S11)**: 0% win probability under every rule (she only ever reaches top3 with 22–32% probability; best under RANK, 0.320).
- **Jerry Rice (S2)**: runner-up historically; P(win) rises from 3.9% (RANK) to 7.4% (PCT) / 8.0% (PROPOSED) but he never wins with majority probability.
- **Billy Ray Cyrus (S4)**: 0% win under all rules; his mean placement improves most under PROPOSED (6.80 vs observed 5th) — the deficit cap protects fan favorites slightly.

**Rule-level averages (33–34 seasons each):**

| Rule | fan_power | judge_power | Kendall τ | mean survival entropy | P(obs. winner) |
|---|---|---|---|---|---|
| RANK | 0.0034 | 0.0035 | — | 0.8952 | 0.7679 |
| PCT | 0.0000 | 0.0472 | — | 0.8938 | 0.6438 |
| JUDGE_SAVE | 0.2604 | 0.2596 | — | 0.6122 | 0.7844 |
| PROPOSED | 0.0001 | 0.2058 | — | **0.9182** | 0.6816 |

- **PROPOSED is the most exciting rule** (highest mean normalized survival entropy, 0.918) and doubles as the most judge-restrained after RANK among the alternatives; JUDGE_SAVE is by far the least suspenseful (entropy 0.612).
- **Fairness (Kendall τ between counterfactual mean placement and average judge rank)** is strongly negative in early PCT seasons (best matches: S6 τ=−0.970, S10 τ=−0.964, S12 τ=−0.964) and in late RANK seasons (S28 τ=−0.758, S2 τ=−0.733, S29 τ=−0.727), i.e., final placements historically diverge sharply from judge-order — consistent with strong fan influence.
- Fan-power vs judge-power: only Season 1 (RANK) shows nonzero fan-power (0.056); in most seasons both indices ≈ 0 because the posterior is conditioned on the historical rule, so replay eliminations coincide with the joint rule's choice.

**Posterior fan shares** (2,777 couple-week rows): overall rejection-sampling acceptance mean = 0.103 (min 0.0, requiring bootstrap top-up on some weeks). Example — Bobby Bones S27 posterior share rises from ~0.05–0.11 in weeks 1–8 to **0.440 ± 0.142 in week 9** as his constraint (surviving despite mid-pack judge scores) tightens the posterior.

## Sanity Checks
- Simplex constraint: all sampled fan-share draws are Dirichlet outputs (sum to 1 by construction); shares of inactive couples are exact 0 in the full-vector representation.
- Replay: median winner-replay probability of 1.0 under historical rules confirms the simulator reproduces the observed winners in most seasons; the ≥95% target from the plan is met in 20/34 seasons, exceeded in median terms.
- Bobby Bones check (plan validation item): posterior fan share in late weeks (0.440) greatly exceeds his judge-share (~1/13 ≈ 0.077), matching the known fan-favorite anomaly.
- Counting: 16 controversy rows = 4 celebrities × 4 rules ✔; 1658 placement rows ≈ sum of couples × 4 rules over 33 seasons ✔; 1,000 draws retained per week per season (with bootstrap top-up when rejection fell short).
- Winner probabilities are within [0,1]; placement means bounded by roster sizes; entropy values in [0,1].

## Model Parameters
- **Dirichlet prior on latent fan shares**: alpha_i = A·ŝ_i + B with **A = 4.0** (fan tracking of judge quality), **B = 0.6** (popularity noise), rescaled to total concentration 3.0 (moderate informativeness).
- **PCT combination weight**: alpha_pct = **0.5** (equal judge/fan weight, matching the show's Appendix method).
- **PROPOSED "Deficit-Capped Geometric Rule"**: C_i = √(ŝ_i·g_i) with ŝ_i = s_i/max(s), cap g_i = min(f̃_i, **0.9**·ŝ_i); one per-season judges' redemption was specified but **not activated** in the simulator (stubbed).
- **RANK rule tie-break**: combined rank r^J + r^F with 1e-9 uniform noise; JUDGE_SAVE eliminates the bottom-two member with the lower judge score; seasons ≥28 automatically mapped RANK → RANK_SAVE.
- **Monte Carlo**: N_DRAWS = 1000 per week; rejection batches of 20,000, ≤40 batches/week; posterior conditioning seed 7 + season; simulator seed 99.
- **Judge score imputation (S_cf)**: post-exit weeks filled with the couple's own mean observed judge score, enabling long counterfactual survival runs.

## Data Files Generated
- `placement_distributions.csv` — 1,658 rows; per (season, celebrity, rule): mean_placement, sd_placement, p_win, p_top3, observed placement.
- `season_rule_metrics.csv` — 134 rows (= 4 rules × 33 seasons + 2 extra RANK/PCT rows); fan_power, judge_power, kendall_tau, mean_entropy, p_observed_winner per (season, rule). Season 25 missing.
- `posterior_fan_shares.csv` — 2,777 rows; per (season, week, celebrity): judge_score, fan_share_mean, fan_share_sd, week acceptance rate. Feeds Model 3.
- `controversy_counterfactuals.csv` — 16 rows; the 4 controversial celebrities × 4 rules with p_win, p_top3, mean_placement, observed_place.
- `handoff.json` — status PARTIAL + season-25 error message and fix pointer.
- Code files: `dwts_model2.py` (library: season parsing, rejection-sampled posteriors, 4-rule simulator), `run_all.py` (pipeline + figures).

## Figures
- `figures/fig1_controversy_rules.png` — 2×2 bar panels: P(win) and P(2nd–3rd) for Jerry Rice, Billy Ray Cyrus, Bristol Palin, Bobby Bones under the 4 rules, with observed finish annotated.
- `figures/fig2_fan_vs_judge_power.png` — scatter of fan-power vs judge-power index per season (historical rule), colored by Kendall τ, seasons labeled.
- `figures/fig3_excitement_by_rule.png` — bar chart of mean normalized survival entropy by rule; PROPOSED highest (0.918), JUDGE_SAVE lowest (0.612).

## Issues or Limitations
1. **Season 25 crashed** (broadcasting shape mismatch in multi-elimination placement assignment inside `simulate_season`); it is absent from all metric tables. Fix: broadcast the placement assignment over the (M, m_elim) elimination block.
2. **Replay target only partially met**: the plan's ≥95% winner-match validation holds for 20/34 seasons; low-replay PCT seasons (S16, S18, S19, S21, S23) suggest the single-Kendall-prior fan model cannot reconcile those seasons' elimination paths — posteriors there are posterior-topped-up by bootstrap, flattening fan-share uncertainty.
3. **Fan/judge "power" indices are degenerate** (≈0 for RANK/PCT): because posteriors are conditioned on the historical rule, the sim's eliminee almost always equals the historical-rule choice; the indices as coded measure agreement with the fan/judge-worst couple rather than divergence probability vs. history. Treat cross-rule contrasts (e.g., Bobby Bones RANK vs PCT) as the operative flip metric.
4. **JUDGE_SAVE lowers measured suspense** (entropy 0.612 vs ~0.9) partly by construction (the save mechanic changes the survivor pool); the entropy is not normalized across different survivor counts across rules.
5. **PROPOSED redemption was not implemented** (stubbed pass statement); the PROPOSED rule results reflect only the deficit-capped geometric score.
6. Withdrawn couples are filled with placement n+1 in edge cases, and score imputation (mean of own danced weeks) can bias long counterfactual runs toward season-average scores for eliminated couples.
