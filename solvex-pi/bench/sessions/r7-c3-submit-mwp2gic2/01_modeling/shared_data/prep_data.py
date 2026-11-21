#!/usr/bin/env python3
"""
2026 MCM Problem C - "Data With The Stars" - SHARED DATASET BUILDER (Phase 1).

Raw input (already in workspace, do not modify):
    ../../data/2026_MCM_Problem_C_Data.csv
    one row per celebrity-season, wide format: weekly judge scores week1..week11 x judge1..judge4.

Outputs (written next to this script, consumed by every Phase-2 model as-is):
    contestants.csv    one row per celebrity-season (demographics + outcome + summary)
    weekly_scores.csv  one row per celebrity-season-week actually in contention (long format)
    week_panel.csv     one row per season-week (panel size, competitor count, scoring type)
    checks.md          validation assertions actually run + results

Run:  python3 prep_data.py
"""
import os
import re
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.normpath(os.path.join(HERE, "..", "..", "data", "2026_MCM_Problem_C_Data.csv"))
OUT = HERE

NWEEKS, NJUD = 11, 4
SCORE_COLS = [f"week{w}_judge{j}_score" for w in range(1, NWEEKS + 1) for j in range(1, NJUD + 1)]

# ---------------------------------------------------------------- helpers
def tonum(x):
    s = str(x).strip().replace("\xa0", " ").strip()
    if s == "" or s.upper() == "N/A" or s.lower() == "nan":
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def clean_text(x):
    s = str(x).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_place_word(res):
    m = re.match(r"^(\d+)(?:st|nd|rd|th) Place$", str(res).strip())
    return int(m.group(1)) if m else None


def status_of(res):
    s = str(res).strip()
    if s.startswith("Eliminated Week"):
        return "eliminated"
    if s == "Withdrew":
        return "withdrew"
    if parse_place_word(s) is not None:
        return "finalist"
    return "UNKNOWN"


INDUSTRY_CANON = {
    "social media personality": "Social Media Personality",
    # known typos kept but standardised:
    "beauty pagent": "Beauty Pageant",
    "tv personality": "TV Personality",
}
ALT_INDUSTRIES = {
    "Actor/Actress": "Actor/Actress", "Athlete": "Athlete",
}

def canon_industry(x):
    s = clean_text(x)
    key = s.lower()
    if key in INDUSTRY_CANON:
        return INDUSTRY_CANON[key]
    return s

# ---------------------------------------------------------------- load
raw = pd.read_csv(RAW, keep_default_na=False, dtype=str)
assert list(raw.columns)[:9] == [
    "celebrity_name", "ballroom_partner", "celebrity_industry", "celebrity_homestate",
    "celebrity_homecountry/region", "celebrity_age_during_season", "season", "results", "placement",
], "unexpected header"
missing_score_cols = [c for c in SCORE_COLS if c not in raw.columns]
assert not missing_score_cols, f"missing score columns: {missing_score_cols}"

log = []   # human-readable check lines -> checks.md

def chk(name, ok, detail=""):
    log.append(f"- [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    return ok

def info(name, detail):
    log.append(f"- [INFO] {name} - {detail}")

chk("raw row count == 421", len(raw) == 421, f"got {len(raw)}")
chk("raw column count == 53", raw.shape[1] == 53, f"got {raw.shape[1]}")
chk("no exact duplicate (celebrity_name, season) row",
    not raw.duplicated(subset=["celebrity_name", "season"]).any())

# ---------------------------------------------------------------- build contestants table
rows = []
for i, r in raw.iterrows():
    res = str(r["results"]).strip()
    status = status_of(res)
    elim_week = int(res.split()[-1]) if status == "eliminated" else np.nan
    place_word = parse_place_word(res)
    rows.append({
        "row_id": i,
        "celebrity_name": clean_text(r["celebrity_name"]),
        "celebrity_name_raw": r["celebrity_name"],
        "ballroom_partner": clean_text(r["ballroom_partner"]),
        "celebrity_industry_raw": r["celebrity_industry"],
        "celebrity_industry": canon_industry(r["celebrity_industry"]),
        "celebrity_homestate": clean_text(r["celebrity_homestate"]),
        "celebrity_homecountry_region": clean_text(r["celebrity_homecountry/region"]),
        "celebrity_age_during_season": int(float(r["celebrity_age_during_season"])),
        "season": int(r["season"]),
        "results": res,
        "status": status,
        "elim_week": elim_week,
        "placement": int(float(r["placement"])),
        "place_word": place_word,          # parsed from results (may be None)
    })
ct = pd.DataFrame(rows)

# assertions on parsed contestant table
chk("results vocabulary has only 3 status families (17 distinct strings)",
    set(ct["status"]) == {"eliminated", "withdrew", "finalist"},
    f"statuses={sorted(set(ct['status']))}, n_distinct_results={raw['results'].nunique()}")
chk("placement is filled and within 1..16",
    ct["placement"].between(1, 16).all(), f"range {ct['placement'].min()}..{ct['placement'].max()}")
chk("all seasons 1..34 present with 6..16 contestant rows",
    set(ct["season"].unique()) == set(range(1, 35)) and ct.groupby("season").size().between(6, 16).all())
place_match = (ct["place_word"].fillna(ct["placement"]) == ct["placement"]) | ct["place_word"].isna()
chk("results place-word consistent with placement column (finalists)",
    bool(place_match[ct["status"] == "finalist"].all()))
dup_pl = ct[ct.duplicated(subset=["season", "placement"], keep=False)]
from collections import Counter
tie_groups = Counter(zip(dup_pl["season"], dup_pl["_elim_week"] if "_elim_week" in dup_pl else dup_pl["elim_week"]))
chk("placement ties only occur as same-week double eliminations (S33: w2,w3; S34: w2)",
    all(s in (33, 34) for (s, _) in tie_groups) and len(dup_pl) == 6,
    "ties: " + ", ".join(f"S{s} w{k}: {v} rows" for (s, k), v in sorted(tie_groups.items())))
ages = ct["celebrity_age_during_season"]
chk("ages complete and sane (14..82)", bool(ages.between(14, 82).all()), f"{ages.min()}..{ages.max()}")

# ---------------------------------------------------------------- weekly score matrix
nums = raw[SCORE_COLS].apply(lambda col: col.map(tonum))
na_mask = nums.isna()                                   # 'N/A' or empty
zero_mask = (nums == 0) & ~na_mask                      # explicit 0
pos_mask = (nums > 0) & ~na_mask                        # real dance score (judges never give 0)

chk("all score cells are numeric in [0,13.34] or explicitly N/A",
    bool(((nums.fillna(0) >= 0) & (nums.fillna(0) <= 13.34) | na_mask).all().all()),
    f"numeric cells={(~na_mask).sum().sum()}, explicit zeros={int(zero_mask.sum().sum())}, N/A={int(na_mask.sum().sum())}")

score_by_row = {i: {} for i in nums.index}
for i in nums.index:
    for w in range(1, NWEEKS + 1):
        cols = [f"week{w}_judge{j}_score" for j in range(1, NJUD + 1)]
        score_by_row[i][w] = [nums.at[i, c] for c in cols]

def danced_weeks(i):
    """weeks with at least one strictly positive judge cell"""
    return [w for w in range(1, NWEEKS + 1) if any(v > 0 for v in score_by_row[i][w])]

ct["last_danced_week"] = [max(danced_weeks(i)) if danced_weeks(i) else np.nan for i in ct["row_id"]]
ct["n_danced_weeks"] = [len(danced_weeks(i)) for i in ct["row_id"]]

# season-level show length = max danced week that season
show_weeks = ct.groupby("season")["last_danced_week"].max().astype(int).to_dict()

# ---------------------------------------------------------------- semantic audits
# (a) eliminated contestants should have last_danced_week == elim_week
elim = ct[ct["status"] == "eliminated"]
bad = elim[elim["last_danced_week"] != elim["elim_week"]]
rate = 1 - len(bad) / len(elim)
chk("eliminated: last danced week == 'Eliminated Week k' for >=98% of rows",
    rate >= 0.98, f"match rate {rate:.3f}; exceptions: "
    + "; ".join(f"{r.celebrity_name} S{r.season} last={r.last_danced_week} elim={r.elim_week}" for r in bad.itertuples()))

# (b) finalists should have last_danced_week == season show length (with documented exceptions)
fin = ct[ct["status"] == "finalist"]
fin_bad = fin[fin["last_danced_week"] != fin["season"].map(show_weeks)]
chk("finalists dance the season's final week (expect <=4 documented exceptions)",
    len(fin_bad) <= 4,
    "; ".join(f"{r.celebrity_name} S{r.season} last={r.last_danced_week:.0f} show={show_weeks[r.season]}" for r in fin_bad.itertuples()))

# (c) withdrew contestants: last danced week, they withdraw before the NEXT week's show
wd = ct[ct["status"] == "withdrew"]
info("withdrawals", "; ".join(f"{r.celebrity_name} S{r.season} danced thru wk{r.last_danced_week:.0f}" for r in wd.itertuples()))

# (d) AUDIT zero cells strictly inside danced career (a zero during an active week, with a danced week AFTER it
#     or equal to last_danced) -> judges never score 0, so these aremiss-coded 'did not dance this week'
middle = []
for i in ct["row_id"]:
    dw = danced_weeks(i)
    for w in range(1, NWEEKS + 1):
        vals = score_by_row[i][w]
        if (w in dw) and any(v == 0 for v in vals):
            has_later = any(w2 > w for w2 in dw)
            middle.append((int(ct.at[i, "season"]), ct.at[i, "celebrity_name"], w, has_later))
info("zero-cells inside active weeks (w with >=1 zero cell but week danced)",
     f"n={len(middle)}; all have no later danced week: {all(not m[3] for m in middle)}"
     if middle else "none")
chk("zero cells during active weeks are never followed by another danced week (i.e. they mark the finale cut)",
    all(not m[3] for m in middle) if middle else True)

# (e) aggregate-scoring (multi-dance / distributed-total) season-weeks
agg_weeks = []
for (s,), g in ct.groupby(["season"]):
    for w in range(1, NWEEKS + 1):
        vals = []
        for i in g["row_id"]:
            vals += [v for v in score_by_row[i][w] if not np.isnan(v)]
        vals = [v for v in vals if v > 0]
        if not vals:
            continue
        over10 = any(v > 10.5 for v in vals)
        odd_frac = any(abs(v - round(v)) > 1e-9 and abs(v * 2 - round(v * 2)) > 1e-9 for v in vals)
        if over10 or odd_frac:
            agg_weeks.append((int(s), w, round(float(np.mean(vals)), 4)))
chk("aggregate-scoring season-weeks identified (cells hold distributed totals, e.g. thirds/eighths)",
    len(agg_weeks) > 0, f"n={len(agg_weeks)} -> see week_panel.csv")
info("aggregate season-weeks", ", ".join(f"S{s}w{w}" for s, w, _ in agg_weeks))

# (f) judge panel composition per season (3-judge vs guest 4th judge regimes)
panel = {}
for s, g in ct.groupby("season"):
    j4_used = set()
    for i in g["row_id"]:
        for w in range(1, NWEEKS + 1):
            if not np.isnan(nums.at[i, f"week{w}_judge4_score"]):
                j4_used.add(w)
    panel[int(s)] = sorted(j4_used)
info("seasons where a 4th (guest) judge column is used", ", ".join(f"S{s}: wk{v}" for s, v in panel.items() if v))

# ---------------------------------------------------------------- weekly long table
long_rows = []
for i, r in ct.iterrows():
    dw = set(danced_weeks(r["row_id"]))
    s = r["season"]
    for w in sorted(dw):  # only weeks in contention
        vals = score_by_row[r["row_id"]][w]
        valid = [v for v in vals if not np.isnan(v)]
        pos = [v for v in valid if v > 0]
        zero_ct = sum(1 for v in valid if v == 0)
        mean = float(np.mean(pos)) if pos else np.nan
        long_rows.append({
            "row_id": r["row_id"],
            "season": s,
            "week": w,
            "celebrity_name": r["celebrity_name"],
            "ballroom_partner": r["ballroom_partner"],
            "status": r["status"],
            "placement": r["placement"],
            "elim_week": r["elim_week"],
            "judge1": vals[0] if not np.isnan(vals[0]) else np.nan,
            "judge2": vals[1] if not np.isnan(vals[1]) else np.nan,
            "judge3": vals[2] if not np.isnan(vals[2]) else np.nan,
            "judge4": vals[3] if not np.isnan(vals[3]) else np.nan,
            "n_cells_valid": len(valid),
            "n_cells_zero": zero_ct,
            "week_score_mean": mean,
            "week_score_sum": float(np.nansum(valid)),
        })
ws = pd.DataFrame(long_rows)
n_j = ws[["judge1", "judge2", "judge3", "judge4"]].notna().sum(axis=1)
ws["n_judges_scored"] = n_j.values

# scoring type per (season, week)
styp = {}
for w in range(1, NWEEKS + 1):
    g = ws[ws["week"] == w]
    for (s, wk), gg in g.groupby(["season", "week"]):
        pass
for (s, wk), gg in ws.groupby(["season", "week"]):
    bad = [v for v in gg["week_score_mean"].values if not np.isnan(v)]
    over10 = any(v > 10.5 for v in bad)
    odd = any(abs(v - round(v)) > 1e-9 and abs(v * 2 - round(v * 2)) > 1e-9 for v in bad)
    styp[(int(s), int(wk))] = "aggregate" if (over10 or odd) else "normal"
ws["scoring_type"] = [styp[(int(a), int(b))] for a, b in zip(ws["season"], ws["week"])]

# judge-side normalized share (percentage rule input) and rank within week
def add_shares_ranks(df):
    df = df.sort_values(["season", "week", "celebrity_name"]).copy()
    df["judge_share"] = df.groupby(["season", "week"])["week_score_mean"].transform(
        lambda v: v / v.sum() if v.sum() > 0 else np.nan)
    df["week_rank_judges"] = df.groupby(["season", "week"])["week_score_mean"].rank(
        ascending=False, method="average").astype(int)
    return df

ws = add_shares_ranks(ws)

# ---------------------------------------------------------------- panel table
pn_rows = []
for (s, wk), gg in ws.groupby(["season", "week"]):
    pn_rows.append({
        "season": int(s), "week": int(wk),
        "n_competitors": len(gg),
        "n_eliminated_this_week": int(((ct["season"] == s) & (ct["elim_week"] == wk)).sum()),
        "n_judges_scored": int(gg["n_judges_scored"].max()),
        "fourth_judge_used": bool((gg["n_judges_scored"] == 4).mean() > 0.5),
        "scoring_type": styp[(int(s), int(wk))],
    })
wp = pd.DataFrame(pn_rows).sort_values(["season", "week"])

# ---------------------------------------------------------------- final contestant table
ct["mean_week_score"] = ws.groupby("row_id")["week_score_mean"].mean().reindex(ct["row_id"]).values
ct["best_week_score"] = ws.groupby("row_id")["week_score_mean"].max().reindex(ct["row_id"]).values
ct_out = ct[[
    "row_id", "celebrity_name", "ballroom_partner", "celebrity_industry", "celebrity_industry_raw",
    "celebrity_homestate", "celebrity_homecountry_region", "celebrity_age_during_season",
    "season", "results", "status", "elim_week", "placement", "place_word",
    "last_danced_week", "n_danced_weeks", "mean_week_score", "best_week_score",
]]
ws_out = ws[[
    "row_id", "season", "week", "celebrity_name", "ballroom_partner", "status", "placement",
    "elim_week", "judge1", "judge2", "judge3", "judge4", "n_cells_valid", "n_cells_zero",
    "n_judges_scored", "week_score_mean", "week_score_sum", "scoring_type",
    "judge_share", "week_rank_judges",
]]

# ---------------------------------------------------------------- save
os.makedirs(OUT, exist_ok=True)
ct_out.to_csv(os.path.join(OUT, "contestants.csv"), index=False)
ws_out.to_csv(os.path.join(OUT, "weekly_scores.csv"), index=False)
wp.to_csv(os.path.join(OUT, "week_panel.csv"), index=False)

# ---------------------------------------------------------------- checks.md
extra = []
extra.append(f"Build timestamp: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
extra.append(f"Raw file: {RAW}")
extra.append(f"contestants.csv rows: {len(ct_out)} | weekly_scores.csv rows: {len(ws_out)} | week_panel.csv rows: {len(wp)}")
extra.append(f"Seasons: 1..{int(ct['season'].max())}; contestants/season 6..16; show length 4..11 weeks")
md = ["# Shared dataset - validation checks (run by prep_data.py)", "", "## Summary", ""] + [f"- {e}" for e in extra] + ["", "## Assertion results", ""] + log + [
    "",
    "## Interpretation notes",
    "- Judge cells equal to 0 are *not* real scores (U.S. DWTS judges never award 0). They encode 'did not dance this week' (post-elimination filler or finale-cut weeks). They are excluded from week_score_mean and never appear as their own row in weekly_scores.csv.",
    "- 'N/A' cells mark weeks beyond the contestant's career in the raw wide layout; weeks a contestant did not dance are simply absent from weekly_scores.csv.",
    "- scoring_type='aggregate' season-weeks store multi-dance or normalized totals (thirds like 11.3333, eighths like 10.125; some cells >10). Within-week judge_share and week_rank_judges are invariant to this encoding, which is why they are the recommended competition inputs.",
    "- status='withdrew' rows are dropped from elimination-supervision checks by Phase-2 models (they leave for non-competition reasons).",
    "- Placement ties are genuine double eliminations (two couples cut the same week, same placement): S33 week 2 & week 3, S34 week 2. Phase-2 elimination models must allow multiple eliminations per week.",
    "- 16 contestants share 'Eliminated Week 1' style strings but early seasons (S1) have no week-1 eliminations; the audit above ties the elim-week strings to last-danced weeks per row.",
]
with open(os.path.join(OUT, "checks.md"), "w") as f:
    f.write("\n".join(md) + "\n")

print("\n".join(log))
print("\nWrote contestants.csv, weekly_scores.csv, week_panel.csv, checks.md")
