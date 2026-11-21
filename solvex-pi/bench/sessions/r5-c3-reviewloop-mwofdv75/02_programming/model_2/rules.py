"""
Model 2 — Aggregation-Rule Counterfactual Engine (rules module)
2026 MCM Problem C: Data With The Stars

Implements the three DWTS combination rules as pure functions:

  RANK     : (seasons 1-2 & 28-34 style, per problem Appendix)
             Each couple gets rank points from its rank among the judges'
             scores PLUS rank points from its rank among fan votes.
             points_i = (n+1 - r_i^J) + (n+1 - r_i^F)      (1 = best rank)
             Eliminate argmin(points).

  PERCENT  : (seasons 3-27 style)
             points_i = J_i / sum(J)  +  v_i / sum(v)
             where J_i = total judge points, v_i = fan votes.
             Eliminate argmin(points).

  VETO     : bottom-two + judges-veto overlay (season 28+ production change,
             modeled on top of either base rule): the two lowest combined
             scores form B_w; the judges then save the member of B_w with
             the HIGHER judged score, eliminating the other.

All functions take (judge_scores, fan_shares) -> combined points, and
`elimination_order(())` returns contestants sorted worst-first (first
element = eliminated first).  Ties broken deterministically by lower
judge score first, then by index, so results are reproducible.
"""
import numpy as np


# ----------------------------------------------------------------------------
# Points functions.  judge_scores, fan_shares: 1-D arrays over active couples.
# Higher points = safer.
# ----------------------------------------------------------------------------

def rank_points(judge_scores, fan_shares, beta=0.5):
    """RANK rule.  beta is the tie-sensitivity weight only (kept for a common
    signature); the official rule gives equal weight to both rank lists."""
    n = len(judge_scores)
    rJ = _dense_ranks_desc(judge_scores)   # 1 = best judged
    rF = _dense_ranks_desc(fan_shares)     # 1 = most fan votes
    return (n + 1 - rJ).astype(float) + (n + 1 - rF).astype(float)


def percent_points(judge_scores, fan_shares, beta=0.5):
    """PERCENT rule: share of judge points + share of fan votes."""
    J = np.asarray(judge_scores, float)
    V = np.asarray(fan_shares, float)
    jshare = J / J.sum() if J.sum() > 0 else np.full(len(J), 1.0 / len(J))
    vshare = V / V.sum() if V.sum() > 0 else np.full(len(V), 1.0 / len(V))
    return beta * jshare + (1.0 - beta) * vshare


def blended_points(judge_scores, fan_shares, beta):
    """Direct linear blend used for sensitivity: beta on judge share,
    (1-beta) on fan share.  beta=0.5 equals PERCENT."""
    return percent_points(judge_scores, fan_shares, beta=beta)


RULES = {"RANK": rank_points, "PERCENT": percent_points}


# ----------------------------------------------------------------------------
# Batched (Monte Carlo) versions: inputs (draws, m), reductions along axis=-1
# ----------------------------------------------------------------------------

def rank_points_mc(judge_scores, fan_shares, beta=0.5):
    n = judge_scores.shape[-1]
    rJ = dense_ranks_desc(judge_scores, axis=-1)
    rF = dense_ranks_desc(fan_shares, axis=-1)
    return (n + 1 - rJ) + (n + 1 - rF)


def percent_points_mc(judge_scores, fan_shares, beta=0.5):
    J = np.asarray(judge_scores, float)
    V = np.asarray(fan_shares, float)
    js = J / J.sum(-1, keepdims=True)
    vs = V / V.sum(-1, keepdims=True)
    return beta * js + (1.0 - beta) * vs


RULES_MC = {"RANK": rank_points_mc, "PERCENT": percent_points_mc}


def _mc_points(rule, Jc, Vc, beta=0.5):
    """Combined points for arrays (draws, m) under rule name."""
    return RULES_MC[rule](Jc, Vc, beta=beta)


# ----------------------------------------------------------------------------
# Elimination machinery
# ----------------------------------------------------------------------------

def dense_ranks_desc(x, axis=-1):
    x = np.asarray(x, float)
    n = x.shape[axis]
    order = np.argsort(-x, axis=axis, kind='stable')
    xs = np.take_along_axis(x, order, axis=axis)
    pos = np.arange(1, n + 1, dtype=float)
    shp = [1] * x.ndim; shp[axis] = n
    pos = pos.reshape(shp)
    if n > 1:
        prev = np.take(xs, np.arange(n - 1), axis=axis)
        cur = np.take(xs, np.arange(1, n), axis=axis)
        eq = np.concatenate([np.zeros([1 if a == (axis % x.ndim) else xs.shape[a] for a in range(x.ndim)], bool), prev == cur], axis=axis)
        # start of each tie run = most recent position where eq is False
        run_start = np.maximum.accumulate(np.where(eq, -np.inf, pos), axis=axis)
        rs_ = np.maximum(run_start, pos * 0)  # ensure numeric
        rs_ = np.where(eq, run_start, pos)
    else:
        rs_ = pos
    ranks = np.empty_like(rs_)
    np.put_along_axis(ranks, order, rs_, axis=axis)
    return ranks


def _dense_ranks_desc(x):
    return dense_ranks_desc(x, axis=-1)


def _finalize(points, judge_scores):
    """Worst-first ordering: ascending combined points; tie-break on lower
    judge score first (judges' scores break fan ties on the show), then index."""
    points = np.asarray(points, float)
    judge_scores = np.asarray(judge_scores, float)
    key = np.lexsort((np.arange(len(points)), judge_scores, points))
    return key


def elimination_order(rule, judge_scores, fan_shares, beta=0.5):
    """Return indices sorted worst-first (element 0 is eliminated first)."""
    pts = RULES[rule](judge_scores, fan_shares, beta=beta)
    return _finalize(pts, judge_scores)


def veto_order(rule, judge_scores, fan_shares, beta=0.5, veto_policy="score"):
    """Base rule identifies the bottom two; judges then pick who goes home.

    veto_policy:
      'score'  – eliminate the bottom-two member with the LOWER judge score
                 (modeled judge behaviour: judges keep technically better).
      'random' – 50/50 coin (uncertainty floor for the judges' discretion).
      'events' – deterministic but adversarial-to-fans: eliminate the member
                 with the HIGHER fan share (worst case for fan favourites).
    Returns full worst-first ordering.
    """
    order = elimination_order(rule, judge_scores, fan_shares, beta=beta)
    b1, b2 = order[0], order[1]                      # bottom two under base rule
    if veto_policy == "score":
        go = b1 if judge_scores[b1] <= judge_scores[b2] else b2
    elif veto_policy == "events":
        go = b1 if fan_shares[b1] >= fan_shares[b2] else b2
    else:  # random — resolved by the caller across Monte Carlo draws; here
           # default to the score policy for the point estimate.
        go = b1 if judge_scores[b1] <= judge_scores[b2] else b2
    rest = [i for i in order if i != go]
    return [go] + rest


def pairwise_flips(order_a, order_b, n_finalists):
    """Number of contestants whose *finale status* differs between two
    orderings (the outcome fans care about)."""
    sa = set(order_a[:n_finalists])
    sb = set(order_b[:n_finalists])
    return len(sa ^ sb)


# ----------------------------------------------------------------------------
# Self-tests against the problem's Appendix logic and internal invariants
# ----------------------------------------------------------------------------

def _self_test():
    # Appendix-style hand example (n=4): judges best->worst A,B,C,D,
    # fans best->worst B,D,A,C.
    idx = ["A", "B", "C", "D"]
    J = np.array([40., 38., 36., 34.])               # judge points desc A..D
    V = np.array([30., 40., 10., 20.])               # fans: B>A>D>C
    pts = rank_points(J, V)
    # judge ranks: A1 B2 C3 D4 ; fan ranks: B1 A2 D3 C4
    # points: A=(4+3)=7, B=(3+4)=7, C=(2+1)=3, D=(1+2)=3 -> C&D bottom, tie
    elim = elimination_order("RANK", J, V)
    assert set(idx[i] for i in elim[:2]) == {"C", "D"}, elim
    # PERCENT: shares J .2857/.2714/.2571/.1857 ; fans .3/.4/.1/.2
    # totals: A .5857 B .6714 C .3571 D .3857 -> C out
    elim = elimination_order("PERCENT", J, V)
    assert idx[elim[0]] == "C", elim
    # VETO: bottom two under RANK are C (lower judge? C=36 vs D=34 -> judges
    # eliminate D, the technically worse dancer)
    elim = veto_order("RANK", J, V)
    assert idx[elim[0]] == "D" and idx[elim[1]] == "C", elim
    # PERCENT + VETO: bottom two C,D; judges eliminate D
    elim = veto_order("PERCENT", J, V)
    assert idx[elim[0]] == "D", elim
    print("[rules] self-tests passed")


if __name__ == "__main__":
    _self_test()
