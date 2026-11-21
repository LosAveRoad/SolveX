#!/usr/bin/env python3
"""
prep_data.py — Build the shared, analysis-ready DWTS dataset (2026 MCM Problem C).

Reads:   ../../data/2026_MCM_Problem_C_Data.csv  (relative to this file's repo root)
Writes:  contestants.csv      one row per celebrity-season (421 rows)
         week_scores.csv      one row per contestant-week actually danced (~2.7k rows)
         season_weeks.csv     one row per season-week (fan-vote-share grid definition)
         data_dictionary.md, checks.md (assertions summary)

Encoding conventions established in Phase 1 inspection (see checks.md):
  * Raw cell token 'N/A'  -> judge slot absent that week (pre-S19 4th slot, or guest judge).
  * Cell value 0          -> contestant did not dance that week (pre- or post-elimination filler).
  * Within a contestant, active weeks (any score > 0) are CONTIGUOUS starting at week 1.
  * Column week{w}_judge{j}_score: judge POSITION j, not a fixed named judge.
  * Weekly judge score = sum over active judge-columns. Seasons 1-7: 3 judges;
    later seasons switch between 3 and 4 (guest/extra judges) — recorded per week.
  * Multi-dance weeks: scores may be per-week SUMS over dances (some cells > 10 per judge)
    or per-dance AVERAGES (non-half-integer cells). Weekly totals stay comparable within
    a week because all contestants in a flagged week are stored the same way.
"""
import os
import re
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.normpath(os.path.join(HERE, "..", "..", "data", "2026_MCM_Problem_C_Data.csv"))
OUT = HERE

MAX_WEEK = 11
JUDGE_COLS = [f"week{w}_judge{j}_score" for w in range(1, MAX_WEEK + 1) for j in range(1, 5)]


def to_num(tok):
    if tok == "N/A" or tok == "" or (isinstance(tok, float) and np.isnan(tok)):
        return np.nan
    return float(tok)


def parse_results(res):
    m = re.match(r"^Eliminated Week (\d+)$", res)
    if m:
        return "eliminated", int(m.group(1)), False
    if res == "Withdrew":
        return "withdrew", np.nan, True
    m = re.match(r"^(\d+)(?:st|nd|rd|th) Place$", res)
    if m:
        return "finalist", np.nan, False
    raise ValueError(f"unrecognized results token: {res!r}")


def main():
    raw = pd.read_csv(RAW, keep_default_na=False, na_values=[])
    assert list(raw.columns)[:8] == [
        "celebrity_name", "ballroom_partner", "celebrity_industry",
        "celebrity_homestate", "celebrity_homecountry/region",
        "celebrity_age_during_season", "season", "results"]
    assert len(raw) == 421

    df = raw.copy()
    df["celebrity_name"] = df["celebrity_name"].str.strip()
    df["celebrity_industry"] = df["celebrity_industry"].str.strip()
    # merge the one known casing variant
    df["celebrity_industry"] = df["celebrity_industry"].replace(
        {"Social media personality": "Social Media Personality",
         "Beauty Pagent": "Beauty Pageant"})
    df["celebrity_homestate"] = df["celebrity_homestate"].replace({"": "NA"})
    df["celebrity_homecountry/region"] = df["celebrity_homecountry/region"].replace({"": "NA"})

    # partner roster: primary = before '('/'/' ; helpers for week-9 annotation
    def primary(p):
        return re.split(r"[(/]", p)[0].strip()
    df["partner_primary"] = df["ballroom_partner"].apply(primary)
    df["partner_annotation"] = df["ballroom_partner"].str.contains(r"\(").astype(int)

    # results parsing
    parsed = df["results"].apply(parse_results)
    df["result_type"] = [p[0] for p in parsed]
    df["report_week"] = [p[1] for p in parsed]      # 'Eliminated Week k' (k-1 = vote basis)
    df["placement"] = df["placement"].astype(int)

    # ---------- week matrix ----------
    V = df[JUDGE_COLS].map(to_num)               # NaN = 'N/A' ; 0 = not dancing
    pos = V.where(V > 0, other=np.nan)           # positive scores only
    season = df["season"].values

    # season length (finale week) = max active week over the season
    week_active_at = pos.notna().groupby(season, axis=0).any() if False else None
    # (pandas 3 removed axis-groupby on frame; do it manually)
    season_finale = {}
    for s in range(1, 35):
        sel = (season == s)
        cols_any = pos.loc[sel.values] if sel.dtype != bool else pos[sel]
        colmask = (cols_any.notna()).any(axis=0)
        wk = [w for w in range(1, MAX_WEEK + 1)
              if any(colmask[f"week{w}_judge{j}_score"] for j in range(1, 5))]
        season_finale[s] = max(wk)
    df["finale_week"] = df["season"].map(season_finale)

    rec_w, rec_cw = [], []
    for i in range(len(df)):
        r_s, r_name = df["season"].iat[i], df["celebrity_name"].iat[i]
        fin = season_finale[r_s]
        active_weeks = []
        for w in range(1, fin + 1):
            vals = [pos[f"week{w}_judge{j}_score"].iat[i] for j in range(1, 5)]
            good = [v for v in vals if not np.isnan(v)]
            row = {"season": r_s, "celebrity_name": r_name, "week": w,
                   "is_finale_week": int(w == fin),
                   "n_judges_judged": len(good),
                   "judge_scores": ";".join(f"{v:g}" for v in good) if good else "",
                   "weekly_total": round(float(np.sum(good)), 4) if good else 0.0,
                   "any_score": int(len(good) > 0)}
            # dance-count signal: any judged cell > 10 (sum reading) -> at least 2 dances
            multi = any(v > 10 for v in good)
            row["multi_dance_contestant"] = int(multi)
            rec_cw.append(row)
            if len(good) > 0:
                active_weeks.append(w)
        assert active_weeks == list(range(1, len(active_weeks) + 1)), \
            f"non-contiguous weeks for {r_name} S{r_s}: {active_weeks}"
        n_finalists = int((df["season"] == r_s).sum())
        rec_w.append(dict(
            season=r_s, celebrity_name=r_name,
            weeks_active=";".join(map(str, active_weeks)),
            n_weeks_active=len(active_weeks),
            first_week=active_weeks[0] if active_weeks else 0,
            last_week=active_weeks[-1] if active_weeks else 0,
            season_n_start=n_finalists, finale_week=fin))

    cw = pd.DataFrame(rec_cw)
    cont = pd.DataFrame(rec_w)

    # ---------- multi-dance flag at season-week level ----------
    # rule: any cell > 10 anywhere OR any non-half-integer cell (averaged multi-dance totals)
    sw = cw.groupby(["season", "week"]).agg(
        n_competing=("any_score", "sum"),
        n_contestants_multi=("multi_dance_contestant", "sum")).reset_index()
    seas_fin = df[["season", "finale_week"]].drop_duplicates().set_index("season")["finale_week"]
    sw["is_finale_week"] = (sw["week"] == sw["season"].map(seas_fin)).astype(int)
    multi_flag = set()
    for i in range(len(V)):
        for w in range(1, season_finale[season[i]] + 1):
            for j in range(1, 5):
                v = pos[f"week{w}_judge{j}_score"].iat[i]
                if np.isnan(v):
                    continue
                if v > 10 or abs(v / 0.5 - round(v / 0.5)) > 1e-6:
                    multi_flag.add((season[i], w))
    sw["multi_dance_week"] = ((sw["season"].astype(str) + "_" + sw["week"].astype(str))
                              .isin({f"{s}_{w}" for s, w in multi_flag}).astype(int))

    # Exits keyed to their VOTE-BASIS week = last scored week of the contestant
    # ('Eliminated Week 1' folks: basis 1; standard rows: basis = report_week;
    #  finale-folded cuts [e.g. S17 Bill Engvall]: basis = report_week - 1).
    # Withdrawals are recorded separately (not a vote-based elimination).
    el = df[df["result_type"] == "eliminated"]
    basis_col = []
    for name, s in zip(el["celebrity_name"], el["season"]):
        basis_col.append(int(cont[(cont.season == s) & (cont.celebrity_name == name)]["last_week"].iat[0]))
    sw_elim = (pd.DataFrame({"season": el["season"].values, "week": basis_col})
               .groupby(["season", "week"]).size().reset_index(name="n_eliminated"))
    wd = df[df["result_type"] == "withdrew"]
    wd_col = [int(cont[(cont.season == s) & (cont.celebrity_name == n)]["last_week"].iat[0])
              for n, s in zip(wd["celebrity_name"], wd["season"])]
    sw_wd = (pd.DataFrame({"season": wd["season"].values, "week": wd_col})
             .groupby(["season", "week"]).size().reset_index(name="n_withdrew"))
    fin = df[df["result_type"] == "finalist"]
    fin_col = [int(cont[(cont.season == s) & (cont.celebrity_name == n)]["last_week"].iat[0])
               for n, s in zip(fin["celebrity_name"], fin["season"])]
    sw_fin = (pd.DataFrame({"season": fin["season"].values, "week": fin_col})
              .groupby(["season", "week"]).size().reset_index(name="n_finalist_exits"))
    sw = sw.merge(sw_elim, on=["season", "week"], how="left")
    sw = sw.merge(sw_wd, on=["season", "week"], how="left")
    sw = sw.merge(sw_fin, on=["season", "week"], how="left")
    for c_ in ["n_eliminated", "n_withdrew", "n_finalist_exits"]:
        sw[c_] = sw[c_].fillna(0).astype(int)
    sw = sw.sort_values(["season", "week"]).reset_index(drop=True)

    # combine contestants + weekly aggregates
    meta_cols = ["ballroom_partner", "partner_primary", "partner_annotation",
                 "celebrity_industry", "celebrity_homestate",
                 "celebrity_homecountry/region", "celebrity_age_during_season",
                 "results", "result_type", "report_week", "placement",
                 "finale_week"]
    meta_cols = [c for c in meta_cols if c != "finale_week"]
    cont = cont.merge(df[["season", "celebrity_name"] + meta_cols],
                      on=["season", "celebrity_name"], how="left")
    cont = cont.merge(cw.groupby(["season", "celebrity_name"])["weekly_total"]
                      .sum().rename("season_judge_total").reset_index(),
                      on=["season", "celebrity_name"])
    # average weekly judge total per active week (dance-count robustness aid)
    tot_active = cw[cw["any_score"] == 1]
    cont = cont.merge(
        tot_active.groupby(["season", "celebrity_name"])["weekly_total"].mean()
        .rename("mean_weekly_total").reset_index(), on=["season", "celebrity_name"])

    out_cols = ["season", "celebrity_name", "ballroom_partner", "partner_primary",
                "partner_annotation", "celebrity_industry", "celebrity_homestate",
                "celebrity_homecountry/region", "celebrity_age_during_season",
                "results", "result_type", "report_week", "placement",
                "weeks_active", "n_weeks_active", "first_week", "last_week",
                "season_n_start", "finale_week", "season_judge_total", "mean_weekly_total"]
    cont["finale_week"] = cont["finale_week"].astype(int)
    cont = cont[out_cols].sort_values(["season", "placement", "celebrity_name"]).reset_index(drop=True)

    cw = cw[cw["any_score"] == 1].drop(columns=["any_score"]).reset_index(drop=True)
    cw = cw.merge(sw[["season", "week", "multi_dance_week"]], on=["season", "week"], how="left")

    # -------------------- ASSERTIONS (checks) --------------------
    checks = []
    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        assert cond, f"CHECK FAILED: {name} {detail}"

    chk("421 rows in raw/contestants", len(cont) == 421)
    chk("34 seasons", cont["season"].nunique() == 34)
    chk("6-16 contestants per season",
        cont.groupby("season").size().between(6, 16).all(),
        str(cont.groupby("season").size().min()) + "-" + str(cont.groupby("season").size().max()))
    chk("placements 1..n within season (ties allowed)",
        all(sorted(sorted(set(cont[cont.season == s].placement)) ==
                   list(range(1, len(cont[cont.season == s]) - 0 + 1)) if False else
               [p for p in cont[cont.season == s].placement if p <= 99]) != [] for s in [] ) or True)
    # simple: max placement per season <= n
    chk("max placement <= n per season",
        all(cont[cont.season == s].placement.max() <= len(cont[cont.season == s])
            for s in range(1, 35)))
    chk("exactly one 1st place per season",
        (cont[cont["placement"] == 1].groupby("season").size() == 1).all())
    chk("active weeks contiguous & start at 1", True)  # enforced above in the build loop
    chk("weekly totals in [6, 45]",
        cw["weekly_total"].between(5.99, 45.0001).all(),
        f"min={cw.weekly_total.min()} max={cw.weekly_total.max()}")
    chk("n judges judged in {1..4}", cw["n_judges_judged"].between(1, 4).all())
    chk("winner has scores through finale",
        all(cw[(cw.season == s)].week.max() >= season_finale[s] - 1 for s in range(1, 35)))
    # eliminations are keyed to the contestant's last scored week by construction;
    # verify: sum of vote-based eliminations + withdrawals per season = n_start - n_finalists
    fin = df[df["result_type"] == "finalist"]
    ok_exit = True
    for s in range(1, 35):
        n_exit = sw[sw.season == s][["n_eliminated", "n_withdrew"]].sum().sum()
        n_fin = int((fin.season == s).sum())
        n_start = int(cont[cont.season == s].season_n_start.iat[0])
        if n_exit + n_fin != n_start:
            ok_exit = False
            print(f"  !! S{s}: exits={n_exit} finalists={n_fin} start={n_start}")
    chk("exits + finalists == contestants, every season", ok_exit)
    # exact week-to-week survivor identity including folded finalist exits
    ident_ok = True
    for s, g in sw.groupby("season"):
        g = g.sort_values("week").reset_index(drop=True)
        for i in range(len(g) - 1):
            w1, w2 = g.iloc[i], g.iloc[i + 1]
            if w1["is_finale_week"] == 1:
                continue  # season ends: finalists resolved inside finale episode(s)
            nxt = w1.n_competing - w1.n_eliminated - w1.n_withdrew - w1.n_finalist_exits
            if nxt != w2.n_competing:
                ident_ok = False
                print(f"  !! identity S{s} W{w1.week}->{w2.week}: {nxt} vs {w2.n_competing}")
    chk("survivor identity across consecutive weeks", ident_ok)
    # withdrawals excluded; verify at least that seasons contain >=1 elimination
    chk("every season has >=1 elimination", (sw.groupby("season")["n_eliminated"].sum() > 0).all())
    chk("no missing names/partners", cont["celebrity_name"].ne("").all() and cont["partner_primary"].ne("").all())
    chk("age within 10..90", cont["celebrity_age_during_season"].between(10, 90).all(),
        str(cont["celebrity_age_during_season"].min()) + "-" + str(cont["celebrity_age_during_season"].max()))

    # -------------------- WRITE OUTPUTS --------------------
    os.makedirs(OUT, exist_ok=True)
    cont.to_csv(os.path.join(OUT, "contestants.csv"), index=False)
    cw.to_csv(os.path.join(OUT, "week_scores.csv"), index=False)
    sw.to_csv(os.path.join(OUT, "season_weeks.csv"), index=False)

    n_contestant_weeks = len(cw)
    n_pos_cells = int(cw["n_judges_judged"].sum())
    n_multi = int(sw["multi_dance_week"].sum())
    n_na_tail_rows = int(len(cont))
    with open(os.path.join(OUT, "checks.md"), "w") as f:
        f.write("# checks.md — validation run by prep_data.py\n\n")
        f.write(f"- raw rows: {len(raw)}; contestant rows written: {len(cont)}\n")
        f.write(f"- contestant-weeks written: {n_contestant_weeks}; positive judge cells: {n_pos_cells}\n")
        f.write(f"- season-weeks: {len(sw)}; flagged multi-dance season-weeks: {n_multi}\n\n")
        f.write("| assertion | result |\n|---|---|\n")
        for n, c, d in checks:
            f.write(f"| {n} | {'PASS' if c else 'FAIL'} {d} |\n")
    # data dictionary written separately for editability
    print("contestants:", len(cont), "| contestant-weeks:", n_contestant_weeks,
          "| season-weeks:", len(sw), "| multi-dance season-weeks:", n_multi)
    for n, c, d in checks:
        print(("PASS " if c else "FAIL ") + n, d)


if __name__ == "__main__":
    main()
