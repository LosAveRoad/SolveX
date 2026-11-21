"""
dwts_common.py — Data parsing & schedule construction for Model 2 (2026 MCM Problem C).

Parses data/2026_MCM_Problem_C_Data.csv into per-season contest schedules:

  - contestant record: celebrity, pro, industry, age, placement, results,
    broadcast elimination week b_i (finale contestants get b_i = W_fin),
    weekly judge totals T[i][w] (from week{w}_judge{j}_score columns).
  - weekly active set A_w = {i : b_i >= w}  (withdrawn contestants excluded)
  - weekly elimination multiset E_w = {i : b_i = w} for w < W_fin
  - finale week W_fin: survivors ranked by the 'placement' column.

Rules (history):
  season 1-2  : RANK combination, no judges-save
  season 3-27 : PCT combination, no judges-save
  season 28-34: RANK combination + judges-save (bottom two identified, judges pick).
"""
import re
import numpy as np
import pandas as pd

DATA_PATH = None  # set by caller

N_WEEK_COLS = 11  # week1..week11 judge columns present in the file


def parse_results(results: str):
    """'Eliminated Week 7' -> 7 ; '1st Place' -> None (finale contestant)."""
    m = re.match(r"Eliminated Week\s+(\d+)", str(results))
    if m:
        return int(m.group(1))
    return None


def load_data(csv_path):
    df = pd.read_csv(csv_path, na_values=["N/A"])
    jcols = {}
    for w in range(1, N_WEEK_COLS + 1):
        for j in range(1, 5):
            c = f"week{w}_judge{j}_score"
            if c in df.columns:
                jcols.setdefault(w, []).append(c)

    seasons = {}
    for s, g in df.groupby("season"):
        cont = []
        for _, r in g.iterrows():
            scores = {}
            for w in range(1, N_WEEK_COLS + 1):
                vals = [r[c] for c in jcols.get(w, []) if pd.notna(r[c])]
                # NOTE: a weekly total of 0 means the couple did not compete.
                tot = sum(float(v) for v in vals)
                scores[w] = tot if tot > 0 else None
            bw = parse_results(r["results"])
            cont.append(dict(
                celeb=str(r["celebrity_name"]).strip(),
                pro=str(r["ballroom_partner"]).strip(),
                industry=str(r["celebrity_industry"]).strip(),
                age=int(r["celebrity_age_during_season"]),
                placement=int(r["placement"]),
                results=str(r["results"]).strip(),
                bw=bw,
                withdrew=("Withdrew" in str(r["results"])),
                scores=scores,
            ))
        seasons[int(s)] = cont
    return seasons


def build_schedule(season_conts):
    """Return schedule dict for a season (withdrawn contestants removed)."""
    conts = [c for c in season_conts if not c["withdrew"]]
    # broadcast elimination week; finale contestants -> W_fin
    elim_weeks = [c["bw"] for c in conts if c["bw"] is not None]
    W_fin = max(elim_weeks) if elim_weeks else 1
    for c in conts:
        c["b"] = c["bw"] if c["bw"] is not None else W_fin
    order = sorted(conts, key=lambda c: c["placement"])
    weeks = {}
    for w in range(1, W_fin + 1):
        active = [c for c in conts if c["b"] >= w]
        elim = [c for c in conts if c["b"] == w and w < W_fin]
        weeks[w] = dict(active=active, elim=elim, is_finale=(w == W_fin))
    return dict(season_conts=conts, W_fin=W_fin, weeks=weeks,
                n=len(conts))


def weekly_judge_vectors(sched):
    """For each week: list of judge totals for active contestants.

    Couples eliminated in week w DID dance in week w (scores exist). If a
    score is unexpectedly missing label it None; caller may impute."""
    out = {}
    for w, rec in sched["weeks"].items():
        vec = []
        for c in rec["active"]:
            t = c["scores"].get(w)
            vec.append((c, t))
        out[w] = vec
    return out


def dense_placement(conts):
    """Actual placements restricted to non-withdrawn -> dense ranks 1..m."""
    pl = sorted(c["placement"] for c in conts)
    rank_map = {p: i + 1 for i, p in enumerate(pl)}
    return {c["celeb"]: rank_map[c["placement"]] for c in conts}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/2026_MCM_Problem_C_Data.csv"
    seasons = load_data(path)
    print(f"seasons: {len(seasons)}")
    problems = 0
    for s in sorted(seasons):
        sched = build_schedule(seasons[s])
        # consistency checks
        msg = []
        for w, rec in sched["weeks"].items():
            n_active = len(rec["active"])
            n_score = sum(1 for c in rec["active"] if c["scores"].get(w) is not None)
            if rec["is_finale"]:
                pass
            if n_score < n_active:
                msg.append(f"w{w}: {n_score}/{n_active} scores")
            # verify judge totals positive & decreasing count
        elims = {w: len(rec["elim"]) for w, rec in sched["weeks"].items() if rec["elim"]}
        print(f"s{s:2d}: n={sched['n']:2d} W_fin={sched['W_fin']:2d} "
              f"elims={elims} {' | ' + '; '.join(msg) if msg else ''}")
        problems += len(msg)
    print("score-missing flags:", problems)
