# Model 2 — Counterfactual Season Re-Play (CSR): Results Summary

## Status
FAILURE (incomplete run). The replay engine (`run_model2.py`) was implemented
and launched, but crashed at line 189 before producing any output files, with:

```
KeyError: 'Jgap'
D = dfp["Jgap"].values   (judges-save pairwise fitting block)
```

Root cause: in the bottom-two pair construction loop the dict key `Jgap` was
never attached to the `wk_pairs` records (only `season`, `week`, `eliminated`,
`other` were written), so the DataFrame lookup for the judge-gap column failed.
Fix instruction: replace the record construction with
`wk_pairs.append(dict(season=s, week=w, eliminated=..., other=..., Jgap=float(Jsaved-Jelim)))`
and re-run `python3 run_model2.py`. No Model-2 CSVs or figures exist on disk.
(Support modules `dwts_common.py` and `fanvote_model1.py` import cleanly.)

## Key Numerical Results
- None available. All Model-2 outputs (season replay table, winner-flip
  probabilities, fan-favor index, κ estimate) are missing because the driver
  aborted in the judges-save fitting block (see error above).
- Verified inputs: 34 seasons parsed, 34 schedules built (e.g., s1: 6
  contestants, finale week 4; s27: 13 contestants, finale week 8); all weekly
  judge totals parse to positive floats; within-week judge-score counts are
  consistent (0 anomalies); zero gap-weeks in contestant score trajectories.

## Sanity Checks
- Schedule integrity checks passed for all 34 seasons (contestants-per-week
  monotonically decreases to the finale; no negative/zero-score anomalies
  except documented 0.0 = did-not-compete sentinel rows).
- The 4 documented controversy celebrities (Jerry Rice s2, Billy Ray Cyrus s4,
  Bristol Palin s11, Bobby Bones s27) are all present in the parsed schedules.
- Replay-level sanity checks (elimination chain reproduction, winner-flip
  rates, α-sensitivity sweep) could not be computed due to the crash.

## Model Parameters
- Pairwise judge-save tendency κ: NOT ESTIMATED (the maximum-likelihood grid
  search over κ ∈ [0.01, 6] sits exactly in the crashed code block).
- Fixed prior hyperparameters (documented in `fanvote_model1.py`):
  BETA_Q = 0.18 (fan–judge coupling), SIGMA_Q = 0.55 (prior dispersion of fan
  z-scores), EPS_PRIOR = 3.0 (idiosyncratic noise), SHOCK_P = 0.05 /
  SHOCK_SD = 1.00 (popularity shocks), 50/50 judge–fan mix weight α = 0.5.

## Data Files Generated
- None. `outputs/` is empty (0 CSV/JSON files). The figures directory is also
  empty. Only source code files were written:
  `dwts_common.py`, `fanvote_model1.py`, `run_model2.py`, `replay_draft.py`.

## Figures
- None generated (`figures/` is empty).

## Issues or Limitations
1. Blocking bug (KeyError 'Jgap') must be fixed in `run_model2.py` line ~187
   before any Model-2 numbers exist; all quantitative claims above are input
   -verification results only, not model results.
2. Even after the fix, results inherit Model 1's identifiability limits:
   fan-vote scales are only constrained up to the 50/50 mix normalization.
3. Runtime is untested end-to-end; 32 seasons × 150 replicates × full-chain
   replay may need batch-caching of per-week fan-vote posterior samples.
4. The 'withdrew' contestants are excluded (documented), and s9/s18/s21
   double-elimination weeks are handled by eliminating exactly the recorded
   number of bottom couples per week.
