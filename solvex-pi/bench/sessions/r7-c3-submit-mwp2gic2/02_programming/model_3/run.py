#!/usr/bin/env python3
"""
Entrypoint for Model 3. Running `python3 run.py` from this directory regenerates
every output deterministically (SEED = 42, deterministic optimizer / LOO splits).
Outputs:
  model3_results.json            - all headline numbers (single source of truth)
  model3_weekly_panel.csv        - per danced-week: scores, phi_hat, S_hat, R, ...
  model3_covariate_effects.csv   - effects on the three channels + 95% CI + p
  model3_survival_effects.csv    - Cox step-1/step-2 coefficients (collinearity)
  model3_archetypes.csv          - counterfactual cast predictions + survival
  model3_loio_robustness.csv     - leave-one-industry-out refits
  model3_season_jackknife.csv    - leave-one-season-out D1 age coefficients
  model3_industry_summary.csv    - raw industry profiles
  model3_partner_summary.csv     - raw partner profiles
  model3_industry_differential.csv - industry sorted by mean over/under-rating R
  model3_log.json                - full run log
  figures/*.png                  - F7-F10 figures
"""
from model3_covariates import run_main, clean_json
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    res = run_main()
    with open(HERE / "model3_results.json", "w") as fh:
        json.dump(clean_json(res), fh, indent=1)
    print("[run.py] model3_results.json written")
