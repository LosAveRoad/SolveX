# 2026 MCM Problem C: Data With The Stars (execution-focused run)

=== OPERATOR EXECUTION CONSTRAINTS (not part of the contest statement) ===
- Do NOT use the web, arxiv, web_search, webReader, curl, wget, or any network access. Do NOT install packages.
- The dataset is already provided in data/2026_MCM_Problem_C_Data.csv. Do not search the filesystem for it.
<!-- solvex:phase P1 -->
- Work efficiently. Your FIRST tool call MUST be `write` to create 01_modeling/master_plan.md.
- master_plan.md MUST contain 3 sections named exactly "## Model 1: ...", "## Model 2: ...", "## Model 3: ...", each with a concise mathematical formulation and a solution strategy (10-20 lines each).
- After the file is written, stop immediately. Do not run bash, do not iterate, do not refine.
<!-- /solvex:phase -->
=== END CONSTRAINTS ===

---

# 2026 MCM Problem C: Data With The Stars

Source: COMAP official 2026 MCM/ICM problem statement (https://contest.comap.com/undergraduate/contests/mcm/contests/2026/problems/2026_MCM_Problem_C.pdf).

Data file attached: 2026_MCM_Problem_C_Data.csv (seasons 1-34, contestant info, results, weekly judge scores).

---

Problem C: Data With The Stars



Dancing with the Stars (DWTS) is the American version of an international television franchise
based on the British show “Strictly Come Dancing” (“Come Dancing” originally). Versions of
the show have appeared in Albania, Argentina, Australia, China, France, India, and many other
countries. The U.S. version, the focus of this problem, has completed 34 seasons.

Celebrities are partnered with professional dancers and then perform dances each week. A panel
of expert judges scores each couple’s dance, and fans vote (by phone or online) for their favorite
couple that week. Fans can vote once or multiple times up to a limit announced each week.
Further, fans vote for the star they wish to keep, but cannot vote to eliminate a star. The judge
and fan votes are combined in order to determine which couple to eliminate (the lowest
combined score) that week. Three (in some seasons more) couples reach the finals and in the
week of the finals the combined scores from fans and judges are used to rank them from 1st to 3rd
(or 4th, 5th).

There are many possible methods of combining fan votes and judge scores. In the first two
seasons of the U.S. show, the combination was based on ranks. Season 2 concerns (due to
celebrity contestant Jerry Rice who was a finalist despite very low judge scores) led to a
modification to use percentages instead of ranks. Examples of these two approaches are provided
in the Appendix.

In season 27, another “controversy” occurred when celebrity contestant Bobby Bones won
despite consistently low judges scores. In response, starting in season 28 a slight modification to
the elimination process was made. The bottom two contestants were identified using the
combined judge scores and fan votes, and then during the live show the judges voted to select
which of these two to eliminate. Around this same season, the producers also returned to using
the method of ranks to combine judges scores with fan votes as in seasons one and two. The
exact season this change occurred is not known, but it is reasonable to assume it was season 28.

Judge scores are meant to reflect which dancers are technically better, although there is some
subjectivity in what makes a dance better. Fan votes are likely much more subjective, influenced
by the quality of the dance, but also the popularity and charisma of the celebrity. Show producers
might actually prefer, to some extent, conflicts in opinions and votes as such occurrences boost
fan interest and excitement.

Data with judges scores and contestant information is provided and described below. You may
choose to include additional information or other data at your discretion, but you must
completely document the sources. Use the data to:
• Develop a mathematical model (or models) to produce estimated fan votes (which are
unknown and a closely guarded secret) for each contestant for the weeks they competed.
o Does your model correctly estimate fan votes that lead to results consistent with who
was eliminated each week? Provide measures of the consistency.
o How much certainty is there in the fan vote totals you produced, and is that certainty
always the same for each contestant/week? Provide measures of your certainty for the
estimates.

• Use your fan vote estimates with the rest of the data to:
o Compare and contrast the results produced by the two approaches used by the show to
combine judge and fan votes (i.e. rank and percentage) across seasons (i.e. apply both
approaches to each season). If differences in outcomes exist, does one method seem
to favor fan votes more than the other?
o Examine the two voting methods applied to specific celebrities where there was
“controversy”, meaning differences between judges and fans. Would the choice of
method to combine judge scores and fan votes have led to the same result for each of
these contestants? How would including the additional approach of having judges
choose which of the bottom two couples to eliminate each week impact the results?
Some examples you might consider (there may also be others you identified):
 season 2 –Jerry Rice, runner up despite the lowest judges scores in 5 weeks.
 season 4 – Billy Ray Cyrus was 5th despite last place judge scores in 6 weeks.
 season 11 – Bristol Palin was 3rd with the lowest judge scores 12 times.
 season 27 – Bobby Bones won the despite consistently low judges scores
o Based on your analysis, which of the two methods would you recommend using for
future seasons and why? Would you suggest including the additional approach of
judges choosing from the bottom two couples?

• Use the data including your fan vote estimates to develop a model that analyzes the impact of
various pro dancers as well as characteristics for the celebrities available in the data (age,
industry, etc). How much do such things impact how well a celebrity will do in the
competition? Do they impact judges scores and fan votes in the same way?

• Propose another system using fan votes and judge scores each week that you believe is more
“fair” (or “better” in some other way such as making the show more exciting for the fans).
Provide support for why your approach should be adopted by the show producers.

• Produce a report of no more than 25 pages with your findings and include a one- to two-page
memo summarizing your results with advice for producers of DWTS on the impact of how
judge and fan votes are combined with recommendations for how to do so in future seasons.
