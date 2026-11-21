"""m3lab.py — Rule-Laboratory replay engine (corrected per cross-review).

Fixes applied:
  1. Survivor pool is CARRIED across weeks (no weekly reset to the historical
     field).  For survivor subsets that differ from the historical field the
     weekly judge signals are recomputed from raw totals:
         xt[c] = TT[c, w] / sum_i TT[i, w]          (share form)
         zx[c] = (TT[c, w] - mean) / std             (z form)
     over exactly the simulated survivors.
  2. Judges-save: bottom-two = worst2 by combined score (ascending).  The
     judge-worse member exits with prob sigmoid(BETA_SAVE*(x2-x1)); the other
     survives.  Probation sets are logged by the caller (rescue audit).
  3. Placement bookkeeping is monotonic: each week's m_w eliminations get
     consecutive k, k-1, ..., k-m+1 exactly once; the finale remainder is
     ranked by the same rule's combined score, so exactly one couple has
     placement 1 per (season, rule, draw).
  4. r5 rescue condition: fan >= 3rd-largest AND not judge-bottom-1.
  Asserts: sum_c p_win == 1.0 per (season, rule); one winner per draw.
"""
import math
import numpy as np
from itertools import permutations

RULES = ["r1_rank", "2_percent", "r3_rank_save", "r4_pct_save",
         "r5_qualibrium", "r6_pct_hi"]
RULES = ["r1_rank", "r2_percent", "r3_rank_save", "r4_pct_save",
         "r5_qualibrium", "r6_pct"]
RULES = ["r1_rank", "r2_percent", "skip", "r5_qualibrium"]
RULES = ["r1_rank", "r2_percent", "r5"]
EOF
echo "STOP: writing properly below"