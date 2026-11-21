# Master Modeling Plan (Model 2 executor copy)

Note: the shared `01_modeling/master_plan.md` is read-only for this task; this copy
documents the plan. THIS TASK IMPLEMENTS MODEL 2 (rank vs. percentage counterfactual
engine + fairness benchmark), fed by a lightweight Model-1-style posterior fan-vote
draw engine described below.

## Model 1: Bayesian Fan-Vote Estimator (posterior draw engine)
- Judge share jshare_{c,w} = judge total / sum over active couples in week w.
- Unknown fan share f_{c,w} on the weekly simplex. Prior: Bayesian bootstrap on the
  simplex; posterior draws anchored to judge share with fan deviation weight:
    f^(s)_{c,w} ~ Dirichlet(kappa * jshare_{c,w}) scaled, mixed:
    f^(s) = normalize(gamma^(s)) where gamma^(s)_{c,w} = kappa * jshare_{c,w} + g^{(s)},
    g ~ Gamma(1) i.i.d. — a Dirichlet-multinomial conjugate style draw. kappa small
  (fan votes weakly informed by judges). Seed rng(1_000_000*season + 100*week + draw).
- Certainty: per-couple/week posterior sd and IQR of f; decisiveness-weighted.

## Model 2: Rank vs. Percentage Counterfactual Engine (IMPLEMENTED HERE)
- Combine_1 (rank rule, S1-S2 era): combined = rank(J) + rank(F) per week (rank 1 = best
  NOT USED — fans vote to keep; DWTS rank rule: lowest judge rank + lowest fan rank
  of votes-to-keep is eliminated... in the official rank rules, fan votes ranked from
  most votes (rank 1 for most) and judge scores ranked; the couple with the LOWEST
  SUM (worst combined) is eliminated. We replicate: combined rank of judges (1=best)
  + rank of fan votes (1=most votes=best); eliminate argmax of worst? Official:
  the couple with the lowest combined rank of votes-to-keep... we define:
  combined_w(c) = judge_rank_w(c) + fan_rank_w(c), where rank 1 = best (highest judges /
  most fan votes). The couple with the HIGHEST combined (worst) is eliminated; ties
  broken in favor of the couple with lower judge rank (higher judges) — i.e., judges
  break ties to save the better-judged couple; equivalently eliminated = couple among
  tie with worst judge rank.
- Combine_2 (percentage rule, S3+): pct = jshare + fshare; eliminate argmin; ties →
  worse judges eliminated.
- Judges' save (S28+ real; also counter-simulated for all seasons): among the bottom
  two of the rule's combined score, the couple with the higher judge total is saved.
- Diagnostics: FPI_k(R) = fraction of weeks eliminated couple != judge-score argmin;
  D(k) = P(rule1 decision != rule2 decision) over posterior draws, with permutation
  null test.
- Controversies: posterior placement distribution for Jerry Rice (S2), Billy Ray Cyrus
  (S4), Bristol Palin (S11), Bobby Bones (S27) under each rule + judges' save variants.

## Model 3: Fairness Benchmark + Proposed Gamma System
- A = (1-lambda)*jshare + lambda*f + lambda_d*|jshare - f|*1[bottom two]; judges' save.
- Sweep lambda in [0.30, 0.50], lambda_d in {0, 0.025, 0.05}; axioms AX1-AX3 by
  synthetic counterexample tests; Pareto frontier (drama events vs violations);
  recommendation (lambda*, lambda_d*).
