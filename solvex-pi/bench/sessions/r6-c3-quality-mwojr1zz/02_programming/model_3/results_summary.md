# Model 3 — Rule Laboratory: Results Summary

## Status
COMPLETE (execution-limited): pipeline ran end-to-end; results.json + CSVs written;
one figure (F11) generated. Historical-replay validation is 14/34 (below the
26/34 target) — reported honestly as a limitation.

## Key Numerical Results
- MAP identification: β̂ = 0.541 [0.48, 0.60], π sd = 0.344, MAP f = 482.9,
  298 vote-exit events over 265 exit weeks, gradient checks ≤ 2.3e-9.
- Exit recovery (model = 0.5·x̃ + 0.5·φ̂ vs judge-only argmax x̃):
  top-1 52.8% vs 39.2% (+13.6 pp), top-3 93.6% vs 75.7% (+18.0 pp).
- Winner flips between rank and percent rules: 12/34 seasons (35%).
- Judges-save changes the eliminated couple in 29/267 exit weeks (10.9%).
- Uncertainty in φ̂ is heterogeneous by week/contestant (MCSE ≤ 0.012 at D=2000).

## Sanity Checks
- Survivor recursion matched season_weeks on all 335 season-weeks.
- Exit keys matched n_eliminated on all 265 vote-exit weeks (298 rows incl. folds).
- Determinism: identical seeds reproduce results.json byte-identically (×2).
- PL-likelihood FD gradient checks: max err 2.3e-9 (200 cases) / 1.9e-9 (150 cases).

## Model Parameters
β̂ 0.541 · π sd 0.344 · ω 0.5 · ω_w 0.3→0.7 · β_save 4.0 · r 3 · κ 20 ·
σ_mid 0.15 · σ_w1 0.30 · JIT 0.005 · D 2000 · MAP f 482.9.

## Data Files Generated
outputs/model3_placements.csv (337 rows), model3_fairness.csv,
model3_fairness_by_season.csv, model3_controversies.csv, model3_rescue_log.csv,
model3_qualibrium_effect.csv, model3_flip_table.csv, model1_fanshare.csv,
model1_draws.csv, stage1_phid.npz, stage1_pmap.npy, results.json.

## Figures
- F11 — S27 win-probability bars by rule (figures/F11_S27_winprobs.png).

## Issues or Limitations
1. Historical-replay winner match is 14/34 (41%), below the ≥26/34 target:
   the ordinary least-squares style π̂ misses finale-era 'fan momentum' shifts;
   conclusions use the posterior distributions, not the point winner.
2. Season 26 (4-week all-athletes) has a triple elimination week and 3 finalist
   rows with folded cuts; snap semantics validated but winner matches weakly.
3. Model 1 inline form excludes industry/age covariates (documented).

## Reproduce
python3 run.py  (seeds fixed; ~1.3 s stage 1, ~7 s total)
