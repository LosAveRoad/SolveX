# Model 2 — Aggregation-Rule Counterfactual Engine (Rank vs. Percentage vs. Judges' Veto)

## Status
COMPLETE — Revision 2 (cross-review fixes applied). Week scoring now
counts only weeks with summed judge points > 0, so each week's active set
shrinks with real eliminations (`elim_by_week` maps each true elimination
week to only that week's eliminee(s)); seasons 28–34 now correctly use
RANK (`rule` column in `rule_flip_stats.csv` regenerated); hit rate is a
genuine consistency measure; the permutation test is discriminating;
fan-favour index recomputed on a consistent standing vector; all stated
numbers below recomputed from the regenerated CSVs.

## Key Numerical Results
- **Consistency (hit rate)**: over all scored elimination/finale weeks and
  34 seasons, P(observed outcome reproduced | posterior) = **0.362** at the
  posterior mode and **0.349** averaged over 2,000 draws. Baselines: the
  within-week permutation test averages **0.217** (chance ≈ 1/m_active);
  the engine responds to true vote signal, not artifacts.
  - Weakest reproduction: S1 (0.00 mode hit; Kelly Monaco's win requires
    above-modal fan support in the 3-way finale), S9 (0.20).
  - Strongest: S7 and S10 (0.56), S5 (0.50), S11 (0.50).
- **Rule-flip risk**: mean weekly P(RANK bottom pick ≠ PERCENT bottom pick)
  = **0.1289**; P(judges'-veto change of the base pick) = **0.1227**.
  Highest-risk seasons: S21 (0.262), S5 (0.257), S32 (0.224), S4 (0.223),
  S30 (0.211), S25 (0.207). **0/34 seasons have zero flip risk** — rule
  choice matters somewhere in every season. Σ_w Pr(flip) is bounded by
  the n−2 sanity rule (max 2.571 for S5, n=12).
- **Fan-favour index** = −corr(rank of season judge total, standing under
  rule A on the same standing vector): mean **0.978 (RANK) vs 0.965
  (PERCENT)**; PERCENT is the more fan-favouring rule in only **11/34
  seasons**, so neither rule dominates — the earlier "PERCENT always more
  fan-favouring" claim was an artifact of the old mixed-standing
  computation and is retracted. Correlation between season judge totals
  and final observed placements averages **0.975** (judges' cumulative
  scores overwhelmingly determine final placement already).
- **Controversy case studies** (finale-week counterfactual, truly active
  couples, 1 = would be eliminated/lowest first):
  - Jerry Rice (S2 runner-up): both rules rank him **worst of the 3
    finalists** (Pr = 1.00 → would be 3rd, not 2nd); fan cumulative
    share 13.0% vs judge share 29.1% (gap −0.161).
  - Billy Ray Cyrus (S4, 5th): **Pr(bottom pick) = 1.00 under both rules**
    — his observed Week-8 elimination is exactly reproduced; fan share
    2.4% vs judge share 15.8%.
  - Bristol Palin (S11, 3rd): both rules put her **worst of the 3
    finalists** (Pr = 1.00 → 3rd place preserved); fan share 13.0% vs
    judge share 30.0% (gap −0.170).
  - Bobby Bones (S27 winner): **Pr(worst of 4 finalists) = 0.997 (RANK) /
    0.999 (PERCENT)** → the counterfactual denies him the win under both
    rules; the observed win required above-modal fan support; fan share
    10.1% vs judge share 21.9% (gap −0.118).
  - **Judges'-veto effect in controversies: 0.00** — in each finale the
    controversial contestant is not merely bottom-two but the clear
    bottom pick, and their judge scores are also the lowest of the
    bottom pair, so the judges' veto saves nobody in these cases.
- Implication for producers: controversies arise because cumulative
  fan support (posterior) sits below judge support for these celebrities
  by 12–17 percentage points of the finale vote; both aggregation rules
  convert that identically. The binding lever is how strong a fan lead
  can offset judge deficit, not rank-vs-percentage bookkeeping.

## Sanity Checks
- Scored-week filter verified: e.g. S4 active sets shrink 11→10→…→3 with
  singleton eliminees weeks 2–9; `elim_by_week` maps week 2→1, …, 10→3.
- `rules.py` Appendix self-test passes (RANK ties C/D at 3 points,
  PERCENT eliminates C, judges' veto eliminates the technically worse D).
- Weekly fan shares sum to 1 in every draw (|Σ−1| < 1e-9).
- `dense_ranks_desc` tie handling verified: [267.7, 246.5, 267.7, …] →
  [1, 3, 1, 4, 5]; [5,5,3,3,3,1] → [1,1,3,3,3,6].
- Permutation test discriminating: true 0.362 vs shuffled 0.217 (chance).
- Σ_w Pr(flip) ≤ n−2 for all seasons (max 2.571, S5).

## Model Parameters
- κ = 25 (Dirichlet weekly fan-share concentration), γ = 1.0 (fan-share
  mean = softmax(γ·z̄) of cumulative judge z-scores), τ = 3.0 (importance
  enforcement of observed eliminations), β = 0.5 (equal judge/fan weight),
  N = 2,000 posterior draws (systematic resampling, seed 42).
- Season rule map: RANK for S1–2 and S28–34 (S28+ per problem statement's
  assumed change), PERCENT for S3–27.
- Veto policy 'score' (eliminate the lower-judged of the bottom two);
  'random' and 'events' (adversarial: eliminate the more fan-favoured)
  available for sensitivity.

## Data Files Generated
- `rule_flip_stats.csv` — 34 rows × 8 cols (season, rule, hit rates,
  mean/Σ flip probability, veto flip probability).
- `controversy_case_studies.csv` — 4 rows × 16 cols (Rice/Cyrus/Palin/
  Bones: mean finale position, Pr(bottom-1/2), Pr(veto saves), fan/judge
  cumulative shares and gap, under RANK and PERCENT).
- `fan_favor_index.csv` — 34 rows × 5 cols (judge–placement and judge–fan
  correlations; fan-favour index under RANK and PERCENT).
- `validation_permutation.csv` — 34 rows × 3 cols (true vs shuffled hit
  rates; shuffled mean 0.217 vs true 0.362).
- `posterior_fan_shares_sample.csv` — **134 rows** (seasons 2 and 27,
  all scored weeks of all active couples: mean posterior weekly fan
  share, cumulative judge points) — Model-1 hand-off product.
- `run_stats.json` — headline statistics for downstream phases.
- `rules.py`, `engine.py`, `run_model2.py` — solution code (rev 2).

## Figures
- `figures/fig1_flip_rates.png` — per-season bars (S1–34): weekly
  probability RANK vs PERCENT change the elimination decision and the
  probability the judges' veto changes the base pick (2,000 draws).
- `figures/fig2_controversies.png` — Pr(controversial contestant is the
  bottom pick) under RANK vs PERCENT and Pr(veto saves) at each one's
  final scored week (Rice/Cyrus/Palin/Bones ≈ 1.00, veto = 0).
- `figures/fig3_fanfavor_index.png` — scatter of fan-favour index, RANK
  vs PERCENT per season; **caption now reads "PERCENT above diagonal in
  11/34 seasons"** (corrected from the retracted 33/33 claim).

## Issues or Limitations
1. Hit rates (0.35–0.36) are genuine, not degenerate, but below 1:
   the posterior concentrates near judge-proportional fan shares and the
   τ = 3 conditioning, combined with only season-total-plus-weekly
   structure in the data, cannot force every observed outcome. The gap
   to chance (0.22) is the honest consistency measure; episodes where
   fan leverage was high (e.g. S1 finale) are exactly those the model
   misses — flagged, not smoothed over.
2. Permutation test is now discriminating (0.362 vs 0.217), so no
   degeneracy remains on that check.
3. Controversy counterfactuals use each celebrity's final scored week
   (finale roster) because mid-season reveal order is not reconstructable
   from the collapsed snapshot; weekly survival trajectories are modeled
   only through the conditioning.
4. Fan-vote posterior remains the internal Model-1 substitute (Dirichlet
   conditioned on observed eliminations), not an external Phase-1 file —
   swap-in point documented in handoff.json.
5. Withdrew contestants (10) excluded; judge-score tie ranks share the
   better rank, which may differ from the show's exact tie procedure.

VERIFICATION_RESULT: SATISFIED
