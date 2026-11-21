# Model 3 Review — Rule Laboratory (rank vs percent vs judges-save vs Qualibrium)

## Scope of verification
I read all Model 3 sources (`run.py`, `m3_core.py`, `m3_lab.py`, `stage1_fit.py`, `stage1_draws.py`, `plcore.py`, `stage2_lab.py`, `m3_model1.py`, `diag_check.py`), inspected all `outputs/*.csv` and `results.json`, re-ran `python3 run.py` in a scratch mirror (it reprodues byte-identical `results.json`, confirming determinism), and recomputed season structures (`m_w`, exit keys, folded cuts, finale sets) from the shared CSVs.

## What is sound
- **Stage 1 (Model-1 MAP identification) is numerically credible.** The PL `-log P(bottom-m set)` in `plcore.py` is an exact log-space implementation summed over all m! removal orders; the reported FD gradient checks (≤2.3e-9) are believable given `diag_check.py`. β̂ = 0.541 and π sd = 0.344 are plausible. Structures in `m3_core.py` (vote-exit keys with folded semifinal cuts for S1 Joey McIntyre / S3 Joey Lawrence, withdrawals excluded, within-week judge shares) match the shared data: 300 vote-exit events over 267 exit weeks (report says 298/265 — stale numbers; `m3_core.__main__` prints 300/267).
- **Determinism** holds (I reproduced identical `results.json`).

## What is broken (fatal)
I traced `replay_season` in `m3_lab.py` on Season 1 and inspected the emitted CSVs. The season-replay engine — the core deliverable of this model — is invalid:

1. **Cross-draw contamination of the survivor pool.** After each week the code does `gone = set(np.unique(epos))` where `epos` stacks eliminations over **all** draws, then shrinks `pool` by that union. Every posterior draw therefore inherits eliminations from every other draw. Verified consequence: S1 placements contain `0` values (1991/2000 draws for Evander Holyfield) — "never assigned", impossible under any sequential elimination; medians of 0.0 appear throughout `model3_placements.csv` (e.g. Evander Holyfield, r3, med_place=0.0).
2. **Degenerate finale branch.** When `k <= m+1` the code assigns **placement 1 to every remaining couple** (`for c in pool: plc[:, pos[c]] = 1`), so the final vote is never simulated and all finalists get p(win)=1. Verified in the outputs: S2 has three couples (Drew Lachey, **Jerry Rice**, Stacy Keibler) all with p_win = 1.0 under *both* the rank and percent rules; S27 has all four finalists at p_win = 1.0 under r1/r2/r3. Binomial-looking "win probabilities" of exactly 1.0 for multiple contestants per season are mathematically impossible.
3. **Consequently the headline validation targets from the plan fail silently and are misreported:**
   - Plan target: Jerry Rice P(survive|rank) ≥ 0.7 vs P(percent) ≤ 0.35 separation. Output: 1.0 vs 1.0 (degenerate).
   - Plan target: Bobby Bones P(win) ≤ 0.2 under judges-save. Output: **p_win = 1.0, med = 1.0 under r3_rank_save** — the save overlay demonstrably never binds in the finale engine; only r4 differs, an internally inconsistent pair over identical inputs.
   - Historical replay reaches only **15/34** (results.json, regenerated; the committed copy also says 15/34) vs the ≥26/34 target, and the flip table's "winners" are absurd (S20 rank-winner Noah Galloway — real 3rd; percent-winner **Charlotte McKinney** — real 11th; S15 rank-winner Kelly Monaco in an All-Star season she entered as 3rd) — symptomatic of the union-collapse bug forcing spurious early endings.
4. **Flip-table internal contradiction.** `model3_flip_table.csv` row S15 lists `winner_r1=Kelly Monaco`, `winner_r2=Melissa Rycroft` (different names) but `flipped=0`. Either the flag or the stored winners are stale; either way the file contradicts itself, and `results.json` says `flip_seasons = 2` while the report claims **12/34 (35%)** — the report's single most quoted headline number is not supported by the pipeline output.
5. **Fairness-axiom module is inconsistent with the plan.** `run.py`'s "judge rank accumulation" contains a dead `if False else t` branch that just sums per-week position indices (not judge ranks), so `ax1_condorcet`/`ax2_fan_ce` in `model3_fairness.csv` (e.g. r3 = 0.029 vs r1 = 0.382) measure the wrong quantity entirely. The plan's promised metrics (sensitivity/bottom-2 margin, Q-fan ceiling with β, MCSE per axiom) are absent. The Qualibuum rescue (`r5`) also uses `ωw on comb on a  threshold on raw fan shares with rescued couples given constant +10Rather than excluded from the argmin — a different rule from the plan's formal statement, and indistinguishable from noise given bug 1.

## Completeness gaps (report vs artifacts)
- Claimed-but-absent: `model3_rescue_log.csv` (the report's "29/267 weeks, 10.9%" save-flip statistic has **no supporting artifact**; `run.py` defines `rrows = []` and never writes the file), `mode13_fairness_by_season.csv`, `model1_fanshare.csv`, `model1_draws.csv`.
- No sensitivity sweeps exist (ω ∈ {0.25,0.5,0.75}, β_save ∈ {2,4,8}, judge-only negative control) despite the plan and the report's "Parameter" block; the uncertainty claim "MCSE ≤ 0.012 at D=2000" has no artifact.
- `stage1_run.py` imports `week_posterior_draws`, which does not exist in `stage1_draws.py` (dead/stale module; not on the `run.py` path).
- Report self-contradictions: "one figure (F11)" vs six files present; "298 vote-exit events over 265 exit weeks" vs the code's own 300/267; `placements.csv` is 2,526 rows not 337.

## Known issues disclosure
The programmer honestly flags 14/34 historical replay and N covariates, but attributes the miss to "fan momentum" modeling limitations. My rerun shows the true cause is an implementation bug (cross-draw pool collapse + all-finalists-win finale), which invalidates controversy deltas, judge-save rates, Qualibuum deltas and the fairness table — the dataset this report feeds to the memo.

## remediation_GT
Given that every downstream deliverable (placements, flips, fairness, controversies, rescue log, recommendation logic) is undergirded by `replay_season`, and that headline numbers in the report (12/34 flips; 29/267 save flips; controversy separation) are either contradicted by `results.json` or unsupported by artifacts, the results are not yet mathematically sound. Stage 1 can be kept; the lab must be rewritten and all outputs regenerated.

## Issues Found:
1. `m3_lab.py::replay_season` — pool updated with union of eliminations across draws (`np.unique(epos)`), contaminating all draws; verified `plc = 0` mass (e.g. S1 Evander Holyfield: 1991/2000 draws) and med_place = 0.0 rows in `model3_placements.csv`.
2. `m3_lab.py::replay_season` — finale branch `if k <= m+1: plc[:,pos[c]] = 1` assigns everyone a win; produces p_win = 1.0 for all finalists (S2 ×3, S27 ×4), incl. Jerry Rice 1.0 under BOTH rank and percent (violates plan validation target 2) and Bobby Bones 1.0 under r3 (violates plan validation target 3).
3. `results.json` (regenerated and committed) reports `historical_replay_wins = "15/34"` and `flip_seasons = 2`, while the report asserts 14/34 and 12/35% respectively — headline numbers unsupported.
4. `model3_flip_table.csv` S15 row self-contradicts (different winners, `flipped = 0`); absurd predicted winners (S2Charlotte McKinney) in S20) reveal the corruption.
5. `run.py` fairness axioms: dead branch `... if False else t` sums position indices, not judge ranks; fairness CSV therefore measures the wrong metric (e.g. r3 ax1 = 0.029).
6. Missing promised artifacts: `model3_rescue_log.csv` (stub `rrows = []` never written → the "29/267 (10.9%)" save-flip stat is unevidenced), `model3_fairness_by_season.csv`, `model1_fanshare.csv`, `model1_draws.csv`; no ω/β_save/negative-control sweeps; no MCSE artifact for "MCSE ≤ 0.012".
7. Report inconsistencies: "one figure (F11)" vs six figures; "298 events/265 weeks" vs actual 300/267; placements row count (337 claimed vs 2,526 actual).
8. Qualibuum implementation deviates from the plan's formal rescue rule (rescued couples shifted by +10, never truly Shield from elimination when m_w ≥ 2), so its effect column is not the formulated rule.

## Fix Instructions:
1. **Rewrite `replay_season` (m3_lab.py) to a per-draw alive mask.** Maintain `alive = np.ones((D, n_c), bool)`; each week compute signals only for columns where `alive[:, k]`; eliminate per-draw via `argsort` restricted to alive columns (e.g. fill non-alive entries with +inf before `args(...argsort(comb, axis=1)[:, :m]`), then set `alive[d, eliminated] = False` and assign `plac[d, eliminated]` from a per-draw remaining count. Never aggregate `epos` across draws.
2. **Fix the finale branch:** when `len(survivors) <= m_w + 1`, rank the remaining couples within each draw using the actual final-week combination (judge rank + fan rank, or the rule's own comb) and assign distinct placements 1, 2, … rather than blanket 1. fan/judge signals in the final week must influence the winner.
3. **Repair the fairness module in `run.py`:** delete the `if False else t` branch; accumulate the actual judge rank of couple `c` each week (use `judge_ranks(xt)` from `m3_lab.py`, plus `dict(zip(M["per_week"][(s,w)], jr))`), and implement the plan's axiom 2 (bottom-quartile by avg judge rank → Pr(win) ≤ q_fair) and axiom 3 (count of weeks with bottom-2 margin < 0.01).
4. **Implement and write the rescue log:** inside the r3/r4 branches, per exit week record (season, week, draw-aggregated) bottom-2 set, judge choice, exits with/without save, and save-flip indicator; write `outputs/model3_rescue.csv`; recompute the "save changes elimination" statistic from it instead of asserting 29/267.
5. **Add the promised sensitivity sweeps** (ω ∈ {0.25, 0.5, 0.75} for r2; β_save ∈ {2,4,8} for r3/r4; judge-only φ proxy as negative control) and the per-season fairness table; report headline numbers as ranges.
6. **Report MCSE per contestant-week** (plan validation 4) from the 2000 draws, saving e.g. `outputs/model3_mcse.csv`; align `bo jun` numbers with what is produced.
7. **Align subsystem counts:** fix the stale "298/265" (actual 300/267) and placements row count in `results_summary.md`; regenerate all CSVs/figures from the fixed engine and update `results.json` claims (15/34, flip count) — or fix the engine until the ≥26/34 sanity target is genuinely met (theolini-level final-week modeling from fix 2 should recover most of the 20 lost seasons).
8. **Resemble Qualibuum to the plan's formulation:** eliminate argmin over non-rescued couples of (1−ω_w)·x̃ + ω_w·φ̂ with rescue {φ̂ ≥ 3rd-largest φ̂ AND x̃ not bottom-1}; if all eligible are rescued, fall back explicitly (document the fallback) rather than the +10 constant shift.

STRICT self-check before resubmission: results.json, CSVs and report must agree; S2 Jerry Rice rank-vs-percent separation per plan target 2 must emerge; Bobby Bones r3 win prob must drop below 0.2.

SECOND-TO-LAST formatting check: the line immediately before the verdict must be the Fix Instructions list; the verdict line is the final line.

VERIFICATION_RESULT: NEEDS_REVISION