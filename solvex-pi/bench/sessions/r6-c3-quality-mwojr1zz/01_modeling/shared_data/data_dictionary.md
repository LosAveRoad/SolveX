# data_dictionary.md — Shared DWTS dataset (2026 MCM Problem C)

Built by `prep_data.py` from `../../data/2026_MCM_Problem_C_Data.csv` (raw: 421 rows × 53 cols).
Output files (this directory):

| file | grain | rows |
|---|---|---|
| `contestants.csv` | one row per celebrity-season | 421 |
| `week_scores.csv` | one row per contestant-week actually danced | 2777 |
| `season_weeks.csv` | one row per season-week while the season is live | 335 |

Global encoding rules (critical — established during Phase 1 inspection; see `checks.md`):

- **`'N/A'` (raw) → NaN**: the judge *slot* did not score that week. Two cases: (a) the permanent
  4th judge slot before season 19 (only 3 judges scored seasons 1–18 except guest weeks);
  (b) guest-judge rotation in later seasons (e.g. S34 week 1 has only 2 judges).
- **`0` in raw → treated as "not competing that week"**: post-elimination filler. Distinct from N/A.
- **Active weeks are contiguous, starting at week 1** for every contestant (verified; 0 exceptions
  once 0-vs-N/A handling is correct).
- **Column `week{w}_judge{j}_score` is judge *position* j, not a named judge.** Judge panels rotate
  across and within seasons, and the assignment of named judges to positions is not identified in
  the data. Any judge-level analysis treats j as position.
- **Multi-dance weeks**: a weekly score may be (i) the *sum* over 2 dances (judge cells > 10), or
  (ii) the *average* over 2 dances (non-half-integer cells like 9.6666 = mean of 10, 10, 9). Both
  readings are flagged; week totals are comparable *within* a season-week (all couples of that
  week are recorded under the same convention — verified numerically for each flagged week).
- Weekly standard: seasons 1–7 three judges (max total 30); seasons 8+ mostly three judges with
  sporadic four-judge weeks (max 40); multi-dance weeks raise totals (max 45).
- Semifinal folding: in some seasons, the (n−1)th finalist exits at the *finale* episode vote
  (e.g. S17 Bill Engvall "Eliminated Week 11" but last danced week 10). Their vote basis is their
  last scored week.
- `'Eliminated Week 1'` (16 cases): premiere-night elimination; vote basis = week 1 itself.
- Withdrawals (10 cases): departure is health/personal (not a vote outcome); recorded with their
  last scored week, excluded from vote-based elimination likelihoods.

## contestants.csv columns

| column | type | meaning |
|---|---|---|
| `season` | int 1–34 | season number |
| `celebrity_name` | str | celebrity (whitespace-stripped; 13 celebrities appear in 2 seasons → rows are unique by (season, name)) |
| `ballroom_partner` | str | original raw partner string; may include helper annotations like `"Witney Carson (Xoshitl Gomez week 9)"` (6 rows, all season 34) |
| `partner_primary` | str | primary pro partner = text before first `(` or `/` (54 distinct pros) |
| `partner_annotation` | 0/1 | whether partner string includes a mid-season partner-switch annotation |
| `celebrity_industry` | str | cleaned occupational category (25 levels after merging casing variant `"Social media personality"`→`"Social Media Personality"` and `"Beauty Pagnet"`→`"Beauty Pageant"`); range: Actor/Actress 128, Athlete 95, TV Personality 67, Singer/Rapper 61, … |
| `celebrity_homestate` | str | US state or `NA` (56 missing) |
| `celebrity_homecountry/region` | str | country/region or `NA` (0 missing) |
| `celebrity_age_during_season` | int years | 14–82 |
| `results` | str | raw verdict: `"Eliminated Week k"`, `"Withdrew"`, `"{1st,2nd,...} Place"` |
| `result_type` | str | `eliminated` | `finalist` | `withdrew` |
| `report_week` | float | k from "Eliminated Week k" (NULL otherwise). NOTE: vote basis = `last_week`, which = report_week except folded cuts (report−1) |
| `placement` | int | final season rank 1..n_start (1 = winner; tied ranks allowed: S33 has two pairs, S34 one pair) |
| `weeks_active` | str | semicolon list of weeks the contestant earned any judge score, always `1;2;...;last_week` |
| `n_weeks_active` | int | count of weeks danced (2–11) |
| `first_week` / `last_week` | int | first / last scored week (**`last_week` = vote-basis week for exits**) |
| `season_n_start` | int | contestants in the season's cast (6–16) |
| `finale_week` | int | last week any contestant of the season danced (4–11) |
| `season_judge_total` | float | sum of weekly totals across active weeks |
| `mean_weekly_total` | float | average weekly total over active weeks (dance-count robust) |

## week_scores.csv columns (one row per contestant-week danced)

| column | type | meaning |
|---|---|---|
| `season`, `celebrity_name`, `week` |  | key |
| `is_finale_week` | 0/1 | week == season's finale_week |
| `n_judges_judged` | int 1–4 | judge slots with a score that week (panel size) |
| `judge_scores` | str | semicolon-joined scores in judge-slot order |
| `weekly_total` | float | sum of `judge_scores`; the weekly judge-signal used by all models |
| `multi_dance_contestant` | 0/1 | any single judge cell > 10 (sum-reading) for this row |
| `multi_dance_week` | 0/1 | shared flag from season_weeks (56 season-weeks flagged) |

## season_weeks.csv columns (vote-grid definition)

| column | type | meaning |
|---|---|---|
| `season`, `week` |  | key; 335 rows over weeks that actually had competition |
| `n_competing` | int | contestants dancing that week (survivor count before the elimination) |
| `n_contestants_multi` | int | rows with any judge cell > 10 |
| `is_finale_week` | 0/1 | finale episode of the season |
| `multi_dance_week` | 0/1 | 56 weeks flagged (cells > 10, or averaged cells, anywhere in the week) |
| `n_eliminated` | int | vote-based exits keyed via `last_week`: 221 singles, 29 doubles, 1 triple (S26 W3) |
| `n_withdrew` | int | withdrawals keyed at last scored week |
| `n_finalist_exits` | int | all finalists of the season exit at `last_week` = finale week (their `placement` ranks them); e.g. 3 per season for S1–S26, 4 for S27–S31, 5 for S32–S34 |

Identity verified per season (see checks): for consecutive non-finale weeks,
`n_competing(w+1) = n_competing(w) − n_eliminated(w) − n_withdrew(w) − n_finalist_exits(w)`.

## Known quirks / caveats for Phase 2

1. Fan votes are NOT in the data (that is the modeling task) — no ground truth.
2. Elimination reveals only the argmin (or argmins for double/triple eliminations) of the combined
   ranking each week — ordinal constraints, not cardinal fan votes.
3. Judge-score "0" is absence, not a zero score; weekly judge totals are dance-count-dependent.
4. `Eliminated Week k` label = the episode of announcement; the vote basis is usually week k's
   scores (same-episode format) — basis = last scored week everywhere.
5. Multi-dance week totals are NOT cross-week comparable within a season without flag treatment —
   use `mean_weekly_total` or per-week z-scores inside judge-score models.
6. Season 26 is 4 weeks only (all-athletes edition); season 33: no week 10 (radio format).
7. 13 celebrities competed in two seasons (Kelly Monaco, Drew Lachey, Emmitt Smith, Bristol
   Palin, Apolo Anton Ohno, Joey Fatone, Gilles Marini, Helio Castroneves, Kirstie Alley,
   Melissa Rycroft, Pamela Anderson, Sabrina Bryan, Shawn Johnson) — random effect must NOT
   pool their two runs (repurpose: within-celebrity replication).
