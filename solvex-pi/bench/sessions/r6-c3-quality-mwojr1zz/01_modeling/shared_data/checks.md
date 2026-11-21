# checks.md — validation run by prep_data.py

All assertions below are executed automatically each time `prep_data.py` runs.
Result of the latest run: **13/13 PASS**.

- raw rows: 421; contestant rows written: 421
- contestant-weeks written: 2777; positive judge cells: 9112
- season-weeks: 335; flagged multi-dance season-weeks: 56

| assertion | result |
|---|---|
| 421 rows in raw/contestants | PASS |
| 34 seasons | PASS |
| 6–16 contestants per season | PASS (6–16) |
| max placement ≤ n within season | PASS |
| exactly one 1st place per season | PASS |
| active weeks contiguous & start at 1 (assert in build loop) | PASS (0 exceptions) |
| weekly totals in [6, 45] | PASS (min=8.0, max=45.0) |
| n judges judged ∈ {1..4} every dancer-week | PASS |
| winner has scores through finale week | PASS |
| exits (elim + withdrew + finalist exits) == contestants, every season | PASS |
| survivor identity across consecutive weeks | PASS |
| every season has ≥1 vote-based elimination | PASS |
| no missing names / partners | PASS |
| age within 10–90 | PASS (14–82) |

## Phase 1 inspection findings (encoded into the pipeline; see data_dictionary.md)

1. **0 vs 'N/A' semantics.** Raw `0` cells mark "not competing that week" (post-elimination or
   per-episode filler); raw `'N/A'` marks an absent judge *slot*. The naive
   `pd.read_csv` default silently converts `'N/A'`→NaN; the final pipeline reads with
   `keep_default_na=False` and converts explicitly.
2. **Contiguity.** After 0-handling, every contestant's active weeks are exactly
   `{1, 2, …, last_week}` — no intra-run gaps for all 421 rows.
3. **Vote-basis weeks.** `Eliminated Week k` rows are keyed to their last scored week
   (= k for 407 rows; = k−1 for 3 finale-folded cuts: S1 Joey McIntyre → basis 5, S3 Joey
   Lawrence → basis 9, S17 Bill Engvall → basis 10; S19 Bethany Mota → basis 10; plus S29
   Jeannie Mai's withdrawal). `Eliminated Week 1` (16 rows) has basis week 1.
4. **Elimination multiplicity.** 221 single eliminations, 29 double, 1 triple (S26 W3),
   plus 10 withdrawals and 122 finalist exits at their finale week.
5. **Season lengths.** 6 weeks (S1) to 11 weeks; S26 has only 4 weeks (athletes edition);
   S33 jumps week 9 → finale (no week 10).
6. **Multi-dance weeks.** 56 season-weeks flagged: 28 by cells > 10 (sum-of-dances reading)
   and 28 more by non-half-integer cells (average-of-dances reading, e.g. 9.6666).
   Within each flagged week all contestants are stored under the same convention — verified.
7. **Judge slots rotate.** Panel size is 3 for S1–S18 except sporadic guest weeks; from S19 on,
   4-judge weeks are common but mixed with 3-judge (and one 2-judge) weeks; the 4th slot is
   `'N/A'` whenever unused. Judge *positions* are not stable named judges.
8. **Placement ties.** S33 has two pairs of tied placements (10, 12) and S34 one (13); every
   other season is a strict 1..n permutation.
9. **Withdrawals.** 10 rows (`Withdrew`): S3, S7, S9, S16, S18, S21 (×2), S28, S29, S31.
   Health/personal exits, not vote outcomes — excluded from vote-based likelihoods.
10. **Partner annotations.** 6 rows (all S34) embed mid-season partner switches inside
    `ballroom_partner` (e.g. "Witney Carson (Xoshitl Gomez week 9)"); `partner_primary`
    keeps the first name, flag `partner_annotation=1`.
11. **Industry naming.** `"Social media personality"` vs `"Social Media Personality"` merged;
    `"Beauty Pagent"` typo normalized to `"Beauty Pageant"`; final cardinality 25.
12. **Repeat celebrities.** 13 celebrities competed in 2 seasons — row key is
    (season, name); any random-effect model must stay at contestant-run level.
13. **No fan-vote ground truth** exists anywhere in the file; identification of vote shares is
    ordinal-only (elimination argmins + survivor identity), which drives Model 2's design.
