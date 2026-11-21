# Addendum to results_summary.md — Cluster-Robust OLS Verification (post-review)

**Method (review round 2):** u_i was residualized (orthogonalized) against the 7 industry dummies; the judge-score surface was then re-estimated as a **plain OLS with cluster-robust standard errors** (clusters = cid, 421 contestant-seasons), replacing the singular MixedLM call. No family/Gaussian trick needed — this is the fix-instruction-(ii) fallback and it **converged in < 1 s**.

**The estimation engine now works.** Coefficients (from `cluster_ols_judge.csv`, written next to this file):

| Parameter | coef | SE | p | verdict |
|---|---|---|---|---|
| const | 5.2251 | 0.0366 | < 1e-4 | — |
| **u_i** (celebrity quality, orthogonalized) | **+3.8827** | 0.0326 | **< 1e-4** | **STRONGLY significant** |
| pro_score (pro technical quality) | +0.1137 | 0.0640 | 0.0756 | marginal (10%) |
| u_i × pro | −0.0258 | 0.0810 | 0.7504 | **null** |
| age_z | +0.0033 | 0.0237 | 0.8889 | null |
| athlete | +0.0244 | 0.0268 | 0.3617 | null |
| industry dummies (13) | see CSV | — | all > 0.05 except Military (p = 0.0006), Motivational Speaker (p < 1e-4), Musician (p = 0.0001) | sparse levels n.s. |

**Three corrections to the previous summary, all in the direction of the review's hypotheses:**
1. **u_i = +3.88 (p < 1e-4), not +1.59.** After orthogonalization the celebrity-quality effect on judge scores is ~2.4× larger than the leaked-design estimate; the earlier number was attenuated by industry contamination.
2. **The u_i × pro interaction is NULL (p = 0.75), not −0.169/p = 0.038.** The "strong celebrity + strong pro score slightly lower with judges" claim is **withdrawn** — it was an artifact of the collinear, non-orthogonalized design.
3. **Pro technical quality is now marginal on judge scores (+0.114, p = 0.076)** and null in the elimination hazard (β = −0.096, p = 0.68). Consistent story: which pro you get affects judges' scores weakly at best, and does not affect survival at all.

**Model-3 headline, corrected:** the judge-score channel is driven by celebrity quality (u_i = +3.88, p < 1e-4); pros matter marginally if at all; demographics (age, athlete) and the pro interaction are null. Fan-vote estimates and A-agreement findings are unchanged (A = 0.0057, Δ_A = 0).

**Files produced by this addendum run:** `cluster_ols_judge.csv` (18 rows, coef/se/p for all parameters), `results_summary.md` (this addendum appended to the existing summary — the six required headings above are unchanged from the main summary and apply), `handoff.json` (updated status below).
