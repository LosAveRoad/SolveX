# Data Dictionary — 2026 MCM Problem C "Data With The Stars"

Raw source: `data/2026_MCM_Problem_C_Data.csv` (421 rows × 53 cols), one row per
celebrity-season, wide weekly judge scores. **The shared dataset below is what all
Phase-2 models must load; it is built once by `prep_data.py` and never modified.**

---

## Shared tables (in `01_modeling/shared_data/`)

### `contestants.csv` — one row per celebrity-season (421 rows)

| column | type | units/values | notes |
|---|---|---|---|
| row_id | int | 0..420 | stable join key = raw row index |
| celebrity_name | str | | whitespace-normalized; trailing `\xa0` stripped (e.g., "Dwight Howard") |
| ballroom_partner | str | | pro dancer name |
| celebrity_industry | str | 24 cleaned categories | canonical spelling; "Social media personality"→"Social Media Personality", "Beauty Pagent"→"Beauty Pageant" |
| celebrity_industry_raw | str | 26 raw categories | as in source, kept for audit |
| celebrity_homestate | str | US state (or empty) | non-US celebrities have blank state |
| celebrity_homecountry_region | str | 26 values | e.g. "United States", "Taiwan China" |
| celebrity_age_during_season | int | years | complete, 14..82 |
| season | int | 1..34 | |
| results | str | 17 distinct strings | verbatim from source |
| status | str | `eliminated` / `withdrew` / `finalist` | derived |
| elim_week | float | 1..10, NaN | derived; = week k if results=="Eliminated Week k"; NaN for withdrew/finalist |
| placement | int | 1..16 | final ranking within season; ties are genuine same-week double eliminations (S33 w2/w3, S34 w2) |
| place_word | float | 1..5 or NaN | ordinal parsed from "Nth Place" strings (finalists) |
| last_danced_week | int | 1..11 | last week with ≥1 positive judge score |
| n_danced_weeks | int | 1..11 | count of danced weeks |
| mean_week_score | float | judge points (0-10 scale) | mean over danced weeks of `week_score_mean` |
| best_week_score | float | judge points | best single-week mean |

Special cases:
- `results=="Withdrew"` (10 rows): left for injury/personal reasons; no elim_week.
- `status=="finalist"`: results in {1st..5th Place}; placement = place.
- Eliminated-in-finale contestants who stop receiving scores before the show's final week
  (finale cut): their zero-cells are dropped — they show up with `last_danced_week < 11`.

### `weekly_scores.csv` — one row per celebrity-season-**danced-week** (2,777 rows)

Only weeks in contention (≥1 positive judge score). Weeks with all-zero cells are excluded.

| column | type | notes |
|---|---|---|
| row_id, season, week, celebrity_name, ballroom_partner | keys | |
| status, placement, elim_week | | from contestants.csv |
| judge1..judge4 | float | individual judge scores (0-10); may be N/A if panel <4 |
| n_cells_valid | int | judge cells with a value that week (0 if all zero) |
| n_cells_zero | int | judge cells ==0 (never during an active week) |
| n_judges_scored | int | 3 or 4 |
| week_score_mean | float | mean of positive judge cells = per-dance average (0-10 scale), the "judge score" S_iw |
| week_score_sum | float | sum of positive judge cells |
| scoring_type | str | `normal` or `aggregate` (see below) |
| judge_share | float | week_score_mean / Σ_k week_score_mean within (season,week) — the percentage-rule input |
| week_rank_judges | int | rank of week_score_mean within (season,week), 1=best, average ties — the rank-rule input |

`scoring_type == "aggregate"` for 52 season-weeks (e.g. S9w1, S15w7, S33w6, S34w11):
raw cells hold **distributed totals** (thirds like 11.3333, eighths like 10.125) because
celebrities performed 2+ dances that week. `week_score_mean` recovers the per-dance average;
`judge_share` and `week_rank_judges` are encoding-invariant. Within-week comparisons must
use these columns, never raw cells.

### `week_panel.csv` — one row per season-week in contention (335 rows)

| column | notes |
|---|---|
| season, week | |
| n_competitors | couples dancing that week |
| n_eliminated_this_week | couples cut that week (0..3; 0 = non-elimination/bottom-2-only week) |
| n_judges_scored | max judge columns used |
| fourth_judge_used | guest judge present that week |
| scoring_type | as above |

---

## Key data properties & caveats

1. **Judge panels**: 3 permanent judges are the norm; a 4th guest-judge column appears in
   many weeks (S11-S34 irregularly, full-time in S19-20). `n_judges_scored` covers this;
   `week_score_mean` is always the per-judge average, so panels are comparable.
2. **Zeros are filler, not scores**: U.S. DWTS judges never award 0. Cells equal to 0 mark
   weeks the couple did not dance (post-elimination or finale-cut). Excluded everywhere.
3. **Aggregate weeks** (52): covered above. Also affects week_score_sum — use mean/share.
4. **Double eliminations**: S33 wk2 & wk3, S34 wk2 cut two couples (ties in placement).
5. **Withdrew**: 10 celebrities left off-competition; models must not treat their exit as
   a fan-vote-bottom event.
6. **Diana Nyad S18**: data shows scores only for week 1 but results say "Eliminated Week 2"
   (missing week-2 scores in source; single documented exception).
7. **Joey McIntyre S1 / Joey Lawrence S3**: finalists with finale-week cut recorded as 0
   (no scores for cut celebrities in finale) — already handled by excluding those weeks.
8. **Name hygiene**: `Metta World Peace (Ron)`, `Nicole "Snooki" Polizzi`, `Mike "The Miz"
   Mizanin` contain parentheses/quotes; `Dwight Howard` had a trailing non-breaking space
   (cleaned). Names are join keys within `row_id`, never string-matched.
9. **No fan-vote data exists** — fan votes are latent; they are the estimation target of
   Model 1 in the master plan.
