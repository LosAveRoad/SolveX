# Shared dataset - validation checks (run by prep_data.py)

## Summary

- Build timestamp: 2026-11-20 22:27
- Raw file: /Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r7-c3-submit-mwp2gic2/data/2026_MCM_Problem_C_Data.csv
- contestants.csv rows: 421 | weekly_scores.csv rows: 2777 | week_panel.csv rows: 335
- Seasons: 1..34; contestants/season 6..16; show length 4..11 weeks

## Assertion results

- [PASS] raw row count == 421 - got 421
- [PASS] raw column count == 53 - got 53
- [PASS] no exact duplicate (celebrity_name, season) row
- [PASS] results vocabulary has only 3 status families (17 distinct strings) - statuses=['eliminated', 'finalist', 'withdrew'], n_distinct_results=17
- [PASS] placement is filled and within 1..16 - range 1..16
- [PASS] all seasons 1..34 present with 6..16 contestant rows
- [PASS] results place-word consistent with placement column (finalists)
- [PASS] placement ties only occur as same-week double eliminations (S33: w2,w3; S34: w2) - ties: S33 w2.0: 2 rows, S33 w3.0: 2 rows, S34 w2.0: 2 rows
- [PASS] ages complete and sane (14..82) - 14..82
- [PASS] all score cells are numeric in [0,13.34] or explicitly N/A - numeric cells=13783, explicit zeros=4671, N/A=4741
- [PASS] eliminated: last danced week == 'Eliminated Week k' for >=98% of rows - match rate 0.997; exceptions: Diana Nyad S18 last=1 elim=2.0
- [PASS] finalists dance the season's final week (expect <=4 documented exceptions) - Joey McIntyre S1 last=5 show=6; Joey Lawrence S3 last=9 show=10
- [INFO] withdrawals - Sara Evans S3 danced thru wk5; Misty May-Treanor S7 danced thru wk2; Tom DeLay S9 danced thru wk3; Dorothy Hamill S16 danced thru wk2; Billy Dee Williams S18 danced thru wk2; Tamar Braxton S21 danced thru wk9; Kim Zolciak-Biermann S21 danced thru wk2; Ray Lewis S28 danced thru wk2; Jeannie Mai S29 danced thru wk7; Selma Blair S31 danced thru wk5
- [INFO] zero-cells inside active weeks (w with >=1 zero cell but week danced) - none
- [PASS] zero cells during active weeks are never followed by another danced week (i.e. they mark the finale cut)
- [PASS] aggregate-scoring season-weeks identified (cells hold distributed totals, e.g. thirds/eighths) - n=52 -> see week_panel.csv
- [INFO] aggregate season-weeks - S2w8, S3w10, S4w10, S5w10, S9w1, S9w6, S9w9, S9w10, S10w6, S10w10, S11w6, S11w10, S12w9, S12w10, S13w9, S13w10, S14w6, S14w10, S15w5, S15w7, S15w8, S15w9, S15w10, S16w3, S16w7, S16w10, S17w6, S17w11, S18w10, S19w8, S19w11, S20w7, S21w8, S21w10, S21w11, S22w10, S23w8, S23w11, S24w10, S25w10, S28w8, S29w8, S29w9, S30w7, S31w5, S31w8, S32w6, S32w8, S32w9, S33w6, S34w7, S34w11
- [INFO] seasons where a 4th (guest) judge column is used - S11: wk[7], S12: wk[7], S15: wk[4], S17: wk[10], S18: wk[3, 4, 5, 6, 7, 8, 9], S19: wk[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], S20: wk[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], S21: wk[3, 5, 6], S22: wk[4, 5], S23: wk[1, 2, 3, 6, 7, 9, 11], S24: wk[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], S25: wk[6, 10], S26: wk[2, 3], S28: wk[4, 9], S30: wk[1, 2, 4, 5, 6, 7, 8, 9, 10], S31: wk[1, 2, 3, 4, 5, 6, 7, 8, 9, 10], S32: wk[3, 6, 7, 8, 9], S33: wk[3, 4], S34: wk[5, 6, 7, 8, 9]

## Interpretation notes
- Judge cells equal to 0 are *not* real scores (U.S. DWTS judges never award 0). They encode 'did not dance this week' (post-elimination filler or finale-cut weeks). They are excluded from week_score_mean and never appear as their own row in weekly_scores.csv.
- 'N/A' cells mark weeks beyond the contestant's career in the raw wide layout; weeks a contestant did not dance are simply absent from weekly_scores.csv.
- scoring_type='aggregate' season-weeks store multi-dance or normalized totals (thirds like 11.3333, eighths like 10.125; some cells >10). Within-week judge_share and week_rank_judges are invariant to this encoding, which is why they are the recommended competition inputs.
- status='withdrew' rows are dropped from elimination-supervision checks by Phase-2 models (they leave for non-competition reasons).
- Placement ties are genuine double eliminations (two couples cut the same week, same placement): S33 week 2 & week 3, S34 week 2. Phase-2 elimination models must allow multiple eliminations per week.
- 16 contestants share 'Eliminated Week 1' style strings but early seasons (S1) have no week-1 eliminations; the audit above ties the elim-week strings to last-danced weeks per row.
