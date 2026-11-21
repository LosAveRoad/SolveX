"""m2_data.py -- data assembly for Model 2 (2026 MCM Problem C, "Data With The Stars").

Loads the Phase-1 shared tables and builds the contestant-week panel with:
  * pro-dancer ids (with alias merging verified against the data),
  * industry ids + 8 super-groups for hierarchical pooling,
  * season / multi-dance flags,
  * identity-safe weekly judge z-scores (panel size is constant within every
    season-week -- verified over all 335 season-weeks in Phase 1),
  * restricted cubic spline bases for age and week-in-run.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SHARED = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
          "r6-c3-quality-mwojr1zz/01_modeling/shared_data")

# Pros recorded under two spellings / married names across seasons (verified: "Val
# Chmerkovskiy" only in seasons 33-34, "Valentin Chmerkovskiy" seasons 13-32;
# "Kym Herjavec" only season 24, "Kym Johnson" seasons 3-20).
PRO_ALIASES = {
    "Val Chmerkovskiy": "Valentin Chmerkovskiy",
    "Kym Herjavec": "Kym Johnson",
}

# Hierarchical grouping of the 25 raw industry levels into 8 super-groups for partial
# pooling (hand-written mapping; every level covered, verified at load time).
INDUSTRY_SUPER = {
    "Actor/Actress": "Screen & Stage",
    "TV Personality": "TV & Media",
    "Radio Personality": "TV & Media",
    "News Anchor": "TV & Media",
    "Model": "Fashion & Beauty",
    "Beauty Pageant": "Fashion & Beauty",
    "Fashion Designer": "Fashion & Beauty",
    "Athlete": "Sports",
    "Racing Driver": "Sports",
    "Sports Broadcaster": "Sports",
    "Fitness Instructor": "Sports",
    "Singer/Rapper": "Music",
    "Musician": "Music",
    "Producer": "Music",
    "Comedian": "Comedy & Internet",
    "Social Media Personality": "Comedy & Internet",
    "Motivational Speaker": "Public Life",
    "Politician": "Public Life",
    "Military": "Public Life",
    "Astronaut": "Public Life",
    "Journalist": "Public Life",
    "Entrepreneur": "Business & Other",
    "Magician": "Business & Other",
    "Con artist": "Business & Other",
    "Conservationist": "Business & Other",
}
SUPER_ORDER = ["Screen & Stage", "TV & Media", "Music", "Sports",
               "Fashion & Beauty", "Comedy & Internet", "Public Life", "Business & Other"]

# Restricted cubic spline knots, identical functional form on both surfaces (plan spec).
RCS_KNOTS_AGE = np.array([20.0, 30.0, 45.0, 65.0])
RCS_KNOTS_WEEK = np.array([1.0, 3.0, 6.0, 10.0])


# ---------------------------------------------------------------- splines (Harrell)
def rcs_design(x: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Restricted cubic spline basis: [x, tail-corrected cubic terms].  k knots -> k-2 cols."""
    x = np.asarray(x, float)
    kn = knots.astype(float)
    denom = float((kn[-1] - kn[0]) ** 2)
    cols = [x]
    for j in range(len(kn) - 2):
        t = kn[j]
        term = np.maximum(x - t, 0.0) ** 3
        term -= np.maximum(x - kn[-2], 0.0) ** 3 * (kn[-1] - t) / (kn[-1] - kn[-2])
        term += np.maximum(x - kn[-1], 0.0) ** 3 * (kn[-2] - t) / (kn[-1] - kn[-2])
        cols.append(term / denom)
    return np.column_stack(cols)


# ---------------------------------------------------------------- loaders
def load_tables():
    ct = pd.read_csv(f"{SHARED}/contestants.csv")
    ws = pd.read_csv(f"{SHARED}/week_scores.csv")
    sw = pd.read_csv(f"{SHARED}/season_weeks.csv")
    return ct, ws, sw


def assemble(ct: pd.DataFrame, ws: pd.DataFrame, sw: pd.DataFrame):
    """Build the contestant-week panel `pan` plus lookup structures."""
    ct = ct.copy()
    ct["pro"] = ct["partner_primary"].replace(PRO_ALIASES)
    ct["super"] = ct["celebrity_industry"].map(INDUSTRY_SUPER)
    assert ct["super"].notna().all(), "industry not covered by super mapping"
    ct["super"] = pd.Categorical(ct["super"], categories=SUPER_ORDER)
    ct["run_id"] = np.arange(len(ct))          # positional run id (stable)
    ct["log_market"] = np.log(ct["season_n_start"].astype(float))
    ct["log_weeks"] = np.log(ct["n_weeks_active"].astype(float))

    pan = ws.merge(
        ct[["run_id", "season", "celebrity_name", "pro", "celebrity_industry", "super",
            "celebrity_age_during_season", "result_type", "placement", "last_week",
            "n_weeks_active", "season_n_start", "finale_week", "log_market", "log_weeks"]],
        on=["season", "celebrity_name"], how="left", validate="many_to_one")
    assert pan["run_id"].notna().all(), "contestants->weeks merge failed"

    pan = pan.merge(
        sw[["season", "week", "n_competing"]],
        on=["season", "week"], how="left", validate="many_to_one")
    assert pan["n_competing"].notna().all(), "season_weeks merge failed"

    # weekly z-scores (dance-count / panel-size robust); degenerate weeks -> 0
    grp = pan.groupby(["season", "week"])["weekly_total"]
    mu = grp.transform("mean")
    sd = grp.transform("std").replace(0.0, np.nan)
    pan["judge_z"] = ((pan["weekly_total"] - mu) / sd).fillna(0.0)
    pan["week_idx"] = pan["week"] - 1
    pan["fanshare"] = np.nan       # filled by the fan-share stage
    return ct, pan


def withdrawal_context_weeks(ct: pd.DataFrame) -> set:
    """Season-weeks in which a withdrawal occurred (or had occurred earlier in the same
    run-span): the market that week is incomplete for vote identification."""
    out = set()
    for _, r in ct[ct.result_type == "withdrew"].iterrows():
        for w in range(1, int(r["last_week"]) + 1):
            out.add((int(r["season"]), w))
    return out


def build_exit_sets(ct: pd.DataFrame) -> dict:
    """(season, basis week) -> python set of run_ids whose last danced week is this week
    AND whose exit was vote-based ('eliminated').  Withdrawals excluded by construction."""
    out = {}
    for _, r in ct[ct.result_type == "eliminated"].iterrows():
        out.setdefault((int(r["season"]), int(r["last_week"])), set()).add(int(r["run_id"]))
    return out


def build_week_table(pan: pd.DataFrame) -> dict:
    """(season, week) -> dict with row indices, run ids, judge totals, multi flag."""
    wt = {}
    for (s, w), g in pan.groupby(["season", "week"]):
        wt[(int(s), int(w))] = dict(
            rows=g.index.to_numpy(),
            runids=[int(v) for v in g["run_id"].to_numpy()],
            isd=g["weekly_total"].to_numpy(float),
            multi=int(g["multi_dance_week"].iloc[0]),
        )
    return wt


def load_all():
    ct, ws, sw = load_tables()
    ct, pan = assemble(ct, ws, sw)
    ctx = withdrawal_context_weeks(ct)
    exit_sets = build_exit_sets(ct)
    wt = build_week_table(pan)
    return dict(ct=ct, ws=ws, sw=sw, pan=pan, ctx=ctx, exit_sets=exit_sets, wt=wt)
