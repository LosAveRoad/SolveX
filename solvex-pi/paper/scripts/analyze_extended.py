"""Extended, data-grounded analysis for the 2026 MCM C paper.

Every number written into chapters/tables_gen.tex and extended_stats.json is
computed here from the materialized CSV artifacts. Nothing is invented.
"""
import json
import os
import numpy as np
import pandas as pd

ROOT = "/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/sessions/rerun-2026-mcmc"
PROG = os.path.join(ROOT, "02_programming")
OUT = os.path.join(ROOT, "04_paper", "chapters")
os.makedirs(OUT, exist_ok=True)

m1 = pd.read_csv(os.path.join(PROG, "model_1", "fan_vote_estimates.csv"))
wc = pd.read_csv(os.path.join(PROG, "model_1", "weekly_consistency.csv"))
m3 = pd.read_csv(os.path.join(PROG, "model_3", "couple_weeks_model3.csv"))
raw = pd.read_csv("/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/2026_MCM_Problem_C_Data.csv", encoding="utf-8-sig")

for c in ["season", "week", "J", "pJ", "rankJ", "pF_med", "pF_lo", "pF_hi",
          "pF_mean", "pF_sd", "pF_med_renorm", "rankF", "comb_pct", "comb_rank", "age", "placement"]:
    if c in m1.columns:
        m1[c] = pd.to_numeric(m1[c], errors="coerce")
m1["elim"] = m1["eliminated"].astype(str).str.lower().isin(["true", "1"])
m1["ci_width"] = m1["pF_hi"] - m1["pF_lo"]
m1["fan_minus_judge"] = m1["pF_med_renorm"] - m1["pJ"]
m1["rank_gap"] = (m1["rankF"] - m1["rankJ"]).abs()
m1["era"] = np.select(
    [m1["season"] <= 2, m1["season"] <= 27],
    ["rank", "percent"], default="bottom-two")

for c in ["season", "week", "n_couples", "n_exiting", "rhat", "ess",
          "n_constraints", "kappa_pct", "kappa_rank", "p_hit_pct", "p_hit_rank",
          "brier_pct", "brier_rank", "tau_pct", "spearman_pct"]:
    if c in wc.columns:
        wc[c] = pd.to_numeric(wc[c], errors="coerce")
wc["era"] = np.select(
    [wc["season"] <= 2, wc["season"] <= 27],
    ["rank", "percent"], default="bottom-two")
wc["bt"] = wc["bottom_two"].astype(str).str.lower().isin(["true", "1"])

for c in ["season", "week", "age", "pJ", "pF_med", "placement", "us_home", "n_couples_week"]:
    if c in m3.columns:
        m3[c] = pd.to_numeric(m3[c], errors="coerce")

S = {}


def q(s, p):
    s = pd.Series(s).dropna()
    return float(np.percentile(s, p)) if len(s) else None


def r(x, n=4):
    return round(float(x), n) if x is not None and np.isfinite(x) else None


# ---------------------------------------------------------------- panel
S["panel"] = {
    "couple_weeks": int(len(m1)),
    "seasons": int(m1["season"].nunique()),
    "season_min": int(m1["season"].min()), "season_max": int(m1["season"].max()),
    "weeks_in_consistency": int(len(wc)),
    "eliminating_weeks": int((wc["n_exiting"] > 0).sum()),
    "eliminated_rows": int(m1["elim"].sum()),
    "raw_contestants": int(len(raw)),
    "raw_seasons": int(raw["season"].nunique()) if "season" in raw else None,
    "week_min": int(m1["week"].min()), "week_max": int(m1["week"].max()),
}

# ---------------------------------------------------------------- shares
S["shares"] = {
    "pF_med_mean": r(m1["pF_med"].mean()), "pF_med_median": r(m1["pF_med"].median()),
    "pF_med_p05": r(q(m1["pF_med"], 5)), "pF_med_p95": r(q(m1["pF_med"], 95)),
    "pF_med_max": r(m1["pF_med"].max()), "pF_med_min": r(m1["pF_med"].min()),
    "pJ_mean": r(m1["pJ"].mean()), "pJ_median": r(m1["pJ"].median()),
    "pJ_max": r(m1["pJ"].max()),
    "pearson_qJ_qF": r(m1["pJ"].corr(m1["pF_med_renorm"])),
    "spearman_qJ_qF": r(m1["pJ"].corr(m1["pF_med_renorm"], method="spearman")),
    "pearson_rankJ_rankF": r(m1["rankJ"].corr(m1["rankF"])),
    "spearman_rankJ_rankF": r(m1["rankJ"].corr(m1["rankF"], method="spearman")),
    "pF_sd_mean": r(m1["pF_sd"].mean()), "pF_sd_median": r(m1["pF_sd"].median()),
    "ci_width_mean": r(m1["ci_width"].mean()), "ci_width_median": r(m1["ci_width"].median()),
    "ci_width_min": r(m1["ci_width"].min()), "ci_width_max": r(m1["ci_width"].max()),
    "ci_width_p05": r(q(m1["ci_width"], 5)), "ci_width_p95": r(q(m1["ci_width"], 95)),
}

# ---------------------------------------------------------------- uncertainty drivers
merged = m1.merge(wc[["season", "week", "n_couples", "rhat", "ess", "n_constraints"]],
                  on=["season", "week"], how="left")
judge_spread = merged.groupby(["season", "week"])["pJ"].std().rename("judge_sd")
merged = merged.merge(judge_spread, on=["season", "week"], how="left")
S["uncertainty"] = {
    "corr_ci_ncouples": r(merged["ci_width"].corr(merged["n_couples"])),
    "corr_ci_week": r(merged["ci_width"].corr(merged["week"])),
    "corr_ci_judgesd": r(merged["ci_width"].corr(merged["judge_sd"])),
    "corr_ci_constraints": r(merged["ci_width"].corr(merged["n_constraints"])),
    "corr_sd_ncouples": r(merged["pF_sd"].corr(merged["n_couples"])),
    "ci_by_era": {e: {"mean": r(g["ci_width"].mean()), "median": r(g["ci_width"].median()),
                      "p05": r(q(g["ci_width"], 5)), "p95": r(q(g["ci_width"], 95)),
                      "n": int(len(g))}
                  for e, g in merged.groupby("era")},
    "ci_by_ncouples": {str(int(n)): r(g["ci_width"].mean())
                       for n, g in merged.groupby("n_couples") if len(g) >= 20},
}

# ---------------------------------------------------------------- era / rule
S["eras"] = {}
for e in ["rank", "percent", "bottom-two"]:
    g = merged[merged["era"] == e]
    w = wc[wc["era"] == e]
    sub = w[w["n_exiting"] > 0]
    S["eras"][e] = {
        "couple_weeks": int(len(g)), "weeks": int(len(w)),
        "eliminating_weeks": int(len(sub)),
        "mean_hit_pct": r(sub["p_hit_pct"].mean()),
        "mean_hit_rank": r(sub["p_hit_rank"].mean()),
        "mean_ci": r(g["ci_width"].mean()),
        "mean_kappa_pct": r(sub["kappa_pct"].mean()),
        "mean_kappa_rank": r(sub["kappa_rank"].mean()),
        "mean_brier_pct": r(sub["brier_pct"].mean()),
        "mean_spearman": r(sub["spearman_pct"].mean()),
        "mean_tau": r(sub["tau_pct"].mean()),
    }
bt = wc[wc["bt"] & (wc["n_exiting"] > 0)]
nbt = wc[(~wc["bt"]) & (wc["n_exiting"] > 0)]
S["judge_save"] = {
    "bt_weeks": int(len(bt)), "nbt_weeks": int(len(nbt)),
    "bt_hit": r(bt["p_hit_pct"].mean()), "nbt_hit": r(nbt["p_hit_pct"].mean()),
    "bt_brier": r(bt["brier_pct"].mean()), "nbt_brier": r(nbt["brier_pct"].mean()),
    "bt_kappa": r(bt["kappa_pct"].mean()), "nbt_kappa": r(nbt["kappa_pct"].mean()),
    "override_share": r(1 - bt["p_hit_pct"].mean()),
}

# ---------------------------------------------------------------- season table
season_rows = []
for s, g in merged.groupby("season"):
    w = wc[(wc["season"] == s) & (wc["n_exiting"] > 0)]
    season_rows.append({
        "season": int(s), "era": g["era"].iloc[0],
        "couple_weeks": int(len(g)), "weeks": int(g["week"].nunique()),
        "elim_weeks": int(len(w)),
        "pF": r(g["pF_med"].mean()), "pJ": r(g["pJ"].mean()),
        "ci": r(g["ci_width"].mean()),
        "hit": r(w["p_hit_pct"].mean()), "rhat": r(w["rhat"].max()),
        "bottom_two": int(w["bt"].sum()) if "bt" in w else 0,
    })
S["seasons"] = season_rows

# ---------------------------------------------------------------- fusion-weight replay
# Direction diagnostic first: which extreme of the combined score is eliminated?
diag = {}
grp = m1.groupby(["season", "week"])
for col in ["comb_pct", "comb_rank", "pJ", "pF_med_renorm", "rankJ", "rankF"]:
    hit_min = hit_max = tot = 0
    for _, g in grp:
        has = g[g["elim"]]
        if len(has) == 0 or g[col].notna().sum() < 2:
            continue
        idx_min = g[col].idxmin(); idx_max = g[col].idxmax()
        hit_min += int(bool(g.loc[idx_min, "elim"]))
        hit_max += int(bool(g.loc[idx_max, "elim"]))
        tot += 1
    diag[col] = {"argmin": r(hit_min / tot if tot else 0), "argmax": r(hit_max / tot if tot else 0),
                 "weeks": tot}
S["direction_diagnostic"] = diag

pct_dir = "min" if diag["comb_pct"]["argmin"] >= diag["comb_pct"]["argmax"] else "max"
rank_dir = "min" if diag["comb_rank"]["argmin"] >= diag["comb_rank"]["argmax"] else "max"
S["replay_direction"] = {"percent": pct_dir, "rank": rank_dir}


def weight_scan(col_j, col_f, direction, subset=None):
    d = m1 if subset is None else m1[m1["season"].isin(subset)]
    out = []
    for w in np.linspace(0, 1, 21):
        d = d.copy()
        d["score"] = w * d[col_j] + (1 - w) * d[col_f]
        hit = tot = 0
        for _, g in d.groupby(["season", "week"]):
            if not g["elim"].any() or g["score"].notna().sum() < 2:
                continue
            idx = g["score"].idxmin() if direction == "min" else g["score"].idxmax()
            hit += int(bool(g.loc[idx, "elim"])); tot += 1
        out.append({"w": round(float(w), 2), "hit": r(hit / tot if tot else 0), "weeks": tot})
    return out


S["weight_scan"] = {
    "percent_all": weight_scan("pJ", "pF_med_renorm", pct_dir),
    "percent_early": weight_scan("pJ", "pF_med_renorm", pct_dir, range(1, 28)),
    "percent_late": weight_scan("pJ", "pF_med_renorm", pct_dir, range(28, 35)),
    "rank_all": weight_scan("rankJ", "rankF", rank_dir),
    "rank_early": weight_scan("rankJ", "rankF", rank_dir, range(1, 28)),
}
# credible-interval robust replay (optimistic / pessimistic fan share)
S["weight_scan"]["percent_lo"] = weight_scan("pJ", "pF_lo", pct_dir, range(1, 28))
S["weight_scan"]["percent_hi"] = weight_scan("pJ", "pF_hi", pct_dir, range(1, 28))

# rule disagreement: percent vs rank predicted elimination
S["rule_disagreement"] = {}
disagree_by_season = []
for (s, wk), g in m1.groupby(["season", "week"]):
    if not g["elim"].any() or g["comb_pct"].notna().sum() < 2:
        continue
    a = g["comb_pct"].idxmin() if pct_dir == "min" else g["comb_pct"].idxmax()
    b = g["comb_rank"].idxmin() if rank_dir == "min" else g["comb_rank"].idxmax()
    disagree_by_season.append((int(s), int(wk), a != b))
dd = pd.DataFrame(disagree_by_season, columns=["season", "week", "disagree"])
S["rule_disagreement"]["total_weeks"] = int(len(dd))
S["rule_disagreement"]["disagree_weeks"] = int(dd["disagree"].sum())
S["rule_disagreement"]["disagree_rate"] = r(dd["disagree"].mean())
S["rule_disagreement"]["by_season"] = [
    {"season": int(s), "rate": r(g["disagree"].mean()), "n": int(len(g))}
    for s, g in dd.groupby("season")]

# ---------------------------------------------------------------- diagnostics
S["diagnostics"] = {}
for c in ["rhat", "ess", "n_constraints", "p_hit_pct", "p_hit_rank", "brier_pct",
          "kappa_pct", "kappa_rank", "tau_pct", "spearman_pct", "n_couples"]:
    s = wc[c].dropna()
    S["diagnostics"][c] = {"n": int(len(s)), "mean": r(s.mean()), "sd": r(s.std()),
                           "min": r(s.min()), "p05": r(q(s, 5)), "median": r(q(s, 50)),
                           "p95": r(q(s, 95)), "max": r(s.max())}
S["diagnostics"]["rhat_above_11"] = int((wc["rhat"] > 1.1).sum())
S["diagnostics"]["ess_below_7500"] = int((wc["ess"] < 7500).sum())

# ---------------------------------------------------------------- judge-fan divergence
S["divergence"] = {
    "diff_mean": r(m1["fan_minus_judge"].mean()),
    "diff_sd": r(m1["fan_minus_judge"].std()),
    "diff_p05": r(q(m1["fan_minus_judge"], 5)), "diff_p95": r(q(m1["fan_minus_judge"], 95)),
    "abs_rank_gap_mean": r(m1["rank_gap"].mean()),
    "abs_rank_gap_median": r(m1["rank_gap"].median()),
    "abs_rank_gap_p90": r(q(m1["rank_gap"], 90)),
    "rank_gap_ge2": r((m1["rank_gap"] >= 2).mean()),
    "by_era": {e: {"mean": r(g["fan_minus_judge"].mean()), "sd": r(g["fan_minus_judge"].std()),
                   "rank_gap": r(g["rank_gap"].mean())}
               for e, g in m1.groupby("era")},
    "eliminated": {
        "pF": r(m1[m1["elim"]]["pF_med"].mean()), "pJ": r(m1[m1["elim"]]["pJ"].mean()),
        "ci": r(m1[m1["elim"]]["ci_width"].mean()), "n": int(m1["elim"].sum())},
    "survived": {
        "pF": r(m1[~m1["elim"]]["pF_med"].mean()), "pJ": r(m1[~m1["elim"]]["pJ"].mean()),
        "ci": r(m1[~m1["elim"]]["ci_width"].mean()), "n": int((~m1["elim"]).sum())},
}

# ---------------------------------------------------------------- covariates (m3)
m3["age_bin"] = pd.cut(m3["age"], [0, 26, 34, 43, 100],
                       labels=["<=26", "27-34", "35-43", ">43"])
age_tbl = []
for b, g in m3.groupby("age_bin", observed=True):
    age_tbl.append({"bin": str(b), "n": int(len(g)), "fan": r(g["pF_med"].mean()),
                    "judge": r(g["pJ"].mean()), "age": r(g["age"].mean())})
S["covariates"] = {"age_bins": age_tbl,
                   "corr_age_fan": r(m3["age"].corr(m3["pF_med"])),
                   "corr_age_judge": r(m3["age"].corr(m3["pJ"]))}
ind = []
for name, g in m3.groupby("industry"):
    if len(g) >= 25:
        ind.append({"industry": str(name), "n": int(len(g)),
                    "fan": r(g["pF_med"].mean()), "judge": r(g["pJ"].mean())})
S["covariates"]["industry"] = sorted(ind, key=lambda x: -(x["fan"] or 0))
if "us_home" in m3:
    for v, g in m3.groupby("us_home"):
        S["covariates"].setdefault("home", []).append(
            {"us_home": r(v, 0), "n": int(len(g)), "fan": r(g["pF_med"].mean()),
             "judge": r(g["pJ"].mean())})
if "pro_id" in m3:
    pg = m3.groupby("pro_id").agg(n=("pF_med", "size"), fan=("pF_med", "mean")).reset_index()
    pg = pg[pg["n"] >= 20].sort_values("fan", ascending=False)
    S["covariates"]["pro_top"] = [{"pro": str(x["pro_id"]), "n": int(x["n"]),
                                   "fan": r(x["fan"])} for _, x in pg.head(6).iterrows()]
    S["covariates"]["pro_bottom"] = [{"pro": str(x["pro_id"]), "n": int(x["n"]),
                                      "fan": r(x["fan"])} for _, x in pg.tail(6).iterrows()]

# ---------------------------------------------------------------- controversy trajectories
cases = {"Jerry Rice": 2, "Billy Ray Cyrus": 4, "Bristol Palin": 11, "Bobby Bones": 27}
traj = {}
for name, season in cases.items():
    g = m1[(m1["celebrity"].astype(str).str.contains(name.split()[-1], case=False, na=False))
           & (m1["season"] == season)].sort_values("week")
    traj[name] = [{"week": int(x["week"]), "pJ": r(x["pJ"]), "pF": r(x["pF_med_renorm"]),
                   "comb": r(x["comb_pct"]), "rankJ": r(x["rankJ"]), "rankF": r(x["rankF"]),
                   "elim": bool(x["elim"])} for _, x in g.iterrows()]
S["controversy_trajectories"] = traj

# ---------------------------------------------------------------- raw data descriptives
S["raw"] = {
    "contestants": int(len(raw)),
    "seasons": int(raw["season"].nunique()),
    "age_mean": r(pd.to_numeric(raw["celebrity_age_during_season"], errors="coerce").mean()),
    "age_min": r(pd.to_numeric(raw["celebrity_age_during_season"], errors="coerce").min()),
    "age_max": r(pd.to_numeric(raw["celebrity_age_during_season"], errors="coerce").max()),
    "industry_counts": {str(k): int(v) for k, v in
                        raw["celebrity_industry"].value_counts().head(12).items()},
    "placements": {str(k): int(v) for k, v in raw["results"].value_counts().head(6).items()},
}
score_cols = [c for c in raw.columns if c.startswith("week") and "judge" in c]
scores = raw[score_cols].apply(pd.to_numeric, errors="coerce").stack()
S["raw"]["judge_score_n"] = int(len(scores))
S["raw"]["judge_score_mean"] = r(scores.mean())
S["raw"]["judge_score_sd"] = r(scores.std())
S["raw"]["judge_score_min"] = r(scores.min())
S["raw"]["judge_score_max"] = r(scores.max())

# ---------------------------------------------------------------- extra: definitions, relative uncertainty, judge baseline
def tex(v, n=3):
    if v is None:
        return "--"
    return f"{v:.{n}f}"


S["correlation_matrix"] = {}
for a, b in [("pJ", "pF_med"), ("pJ", "pF_med_renorm"), ("pJ", "comb_pct"),
             ("rankJ", "rankF")]:
    S["correlation_matrix"][f"{a}~{b}"] = {
        "pearson": r(m1[a].corr(m1[b])),
        "spearman": r(m1[a].corr(m1[b], method="spearman"))}

merged["ci_rel"] = merged["ci_width"] * merged["n_couples"]
S["relative_uncertainty"] = {
    "corr_cirel_ncouples": r(merged["ci_rel"].corr(merged["n_couples"])),
    "corr_cirel_week": r(merged["ci_rel"].corr(merged["week"])),
    "ci_rel_mean": r(merged["ci_rel"].mean()),
    "ci_rel_median": r(merged["ci_rel"].median()),
    "by_week": [{"week": int(w), "n": int(len(g)), "ci": r(g["ci_width"].mean()),
                 "ci_rel": r(g["ci_rel"].mean()), "n_couples": r(g["n_couples"].mean(), 2),
                 "pF": r(g["pF_med"].mean())}
                for w, g in merged.groupby("week")],
    "by_field": [],
}
merged["field_bin"] = pd.cut(merged["n_couples"], [1, 5, 8, 11, 20],
                             labels=["2-5", "6-8", "9-11", "12-16"])
for b, g in merged.groupby("field_bin", observed=True):
    S["relative_uncertainty"]["by_field"].append(
        {"bin": str(b), "n": int(len(g)), "ci": r(g["ci_width"].mean()),
         "ci_rel": r(g["ci_rel"].mean()), "pF": r(g["pF_med"].mean())})

jb = {}
for e in ["rank", "percent", "bottom-two"]:
    d = m1[m1["era"] == e]
    hit = tot = rankhit = 0
    for _, g in d.groupby(["season", "week"]):
        if not g["elim"].any() or len(g) < 2:
            continue
        hit += int(bool(g.loc[g["pJ"].idxmin(), "elim"]))
        rankhit += int(bool(g.loc[g["rankJ"].idxmax(), "elim"]))
        tot += 1
    jb[e] = {"weeks": tot, "judge_only_hit": r(hit / tot if tot else 0),
             "judge_rank_only_hit": r(rankhit / tot if tot else 0)}
S["judge_baseline"] = jb
# position of the eliminated couple within the weekly judge ordering
pos = []
for _, g in m1.groupby(["season", "week"]):
    e = g[g["elim"]]
    if len(e) == 0 or g["rankJ"].notna().sum() < 2:
        continue
    for _, row in e.iterrows():
        pos.append({"frac": (row["rankJ"] - g["rankJ"].min()) /
                    max(g["rankJ"].max() - g["rankJ"].min(), 1),
                    "is_worst": int(row["rankJ"] == g["rankJ"].max())})
S["eliminated_judge_position"] = {
    "n": len(pos), "mean_normalised_rank": r(np.mean([p["frac"] for p in pos])),
    "share_worst": r(np.mean([p["is_worst"] for p in pos])),
}

S["regime_break"] = {}
for s in [26, 27, 28, 29]:
    g = merged[merged["season"] == s]
    w = wc[(wc["season"] == s) & (wc["n_exiting"] > 0)]
    S["regime_break"][str(s)] = {
        "couple_weeks": int(len(g)), "ci": r(g["ci_width"].mean()),
        "hit": r(w["p_hit_pct"].mean()), "brier": r(w["brier_pct"].mean()),
        "bt_weeks": int(w["bt"].sum()) if "bt" in w else 0,
        "pF": r(g["pF_med"].mean())}

S["controversy_stats"] = {}
for name, t in S["controversy_trajectories"].items():
    rj = [x["rankJ"] for x in t if x["rankJ"] is not None]
    pf = [x["pF"] for x in t if x["pF"] is not None]
    pj = [x["pJ"] for x in t if x["pJ"] is not None]
    S["controversy_stats"][name] = {
        "weeks": len(t), "mean_pF": r(np.mean(pf)), "mean_pJ": r(np.mean(pj)),
        "mean_rankJ": r(np.mean(rj)), "max_rankJ": r(max(rj), 0),
        "fan_exceeds_judge_weeks": sum(1 for x in t if x["pF"] and x["pJ"] and x["pF"] > x["pJ"]),
        "eliminated_weeks": sum(1 for x in t if x["elim"])}

# extra LaTeX tables
E = []
E.append("% AUTO-GENERATED by analyze_extended.py (supplementary computations).\n\n")
E.append("\\begin{table}[H]\n\\centering\n")
E.append("\\caption{Correlation definitions used in this paper. The headline $0.832$ is the "
         "Pearson correlation of $q^J$ with the unnormalised posterior median $\\hat q^F$; the "
         "counterfactual replay instead uses the within-week renormalised share "
         "$\\tilde q^F=\\hat q^F/\\sum_i\\hat q^F_i$, so its Pearson correlation with $q^J$ is "
         "slightly lower. The headline $0.153$ is the Pearson correlation of the two rank "
         "vectors $r^J,r^F$, not a Spearman coefficient.}\n")
E.append("\\label{tab:corrdefs}\n\\begin{tabular}{lrr}\n\\toprule\n")
E.append("Pair & Pearson & Spearman \\\\ \n\\midrule\n")
nm = {"pJ~pF_med": "$q^J$ vs.\\ $\\hat q^F$ (headline)",
      "pJ~pF_med_renorm": "$q^J$ vs.\\ $\\tilde q^F$ (replay)",
      "pJ~comb_pct": "$q^J$ vs.\\ percent-combined",
      "rankJ~rankF": "$r^J$ vs.\\ $r^F$ (headline rank)"}
for k, lab in nm.items():
    c = S["correlation_matrix"][k]
    E.append(f"{lab} & {tex(c['pearson'])} & {tex(c['spearman'])} \\\\ \n")
E.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

E.append("\\begin{table}[H]\n\\centering\n")
E.append("\\caption{Uncertainty by competition week. $\\overline{\\Delta}$ is the mean absolute "
         "$90\\%$ credible-interval width; $\\overline{\\Delta}_{\\rm rel}=n\\,\\overline{\\Delta}$ "
         "rescales it by the field size so that intervals are comparable across weeks with "
         "different numbers of surviving couples. Absolute width grows late in a season because "
         "shares themselves grow; the rescaled width is the comparable measure.}\n")
E.append("\\label{tab:uncertaintyweeks}\n\\begin{tabular}{lrrrrr}\n\\toprule\n")
E.append("Week & $n$ & Couples & $\\overline{q^F}$ & $\\overline{\\Delta}$ & "
         "$\\overline{\\Delta}_{\\rm rel}$ \\\\ \n\\midrule\n")
for row in S["relative_uncertainty"]["by_week"]:
    E.append(f"{row['week']} & {row['n']} & {tex(row['n_couples'],1)} & {tex(row['pF'])} & "
             f"{tex(row['ci'])} & {tex(row['ci_rel'],2)} \\\\ \n")
E.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

E.append("\\begin{table}[H]\n\\centering\n")
E.append("\\caption{Uncertainty by field size, and the judge-only elimination baseline. "
         "``Judge-only hit'' is the fraction of eliminating weeks in which the couple with the "
         "lowest judge share is the one actually eliminated --- a non-circular benchmark because "
         "it uses no reconstructed fan share.}\n")
E.append("\\label{tab:judgebaseline}\n\\begin{tabular}{lrrrr}\n\\toprule\n")
E.append("Stratum & $n$ & $\\overline{\\Delta}$ & $\\overline{\\Delta}_{\\rm rel}$ & Judge-only hit "
         "\\\\ \n\\midrule\n")
E.append("\\multicolumn{5}{l}{\\emph{Field size}} \\\\ \n")
for row in S["relative_uncertainty"]["by_field"]:
    E.append(f"{row['bin']} couples & {row['n']} & {tex(row['ci'])} & "
             f"{tex(row['ci_rel'],2)} & -- \\\\ \n")
E.append("\\midrule\n\\multicolumn{5}{l}{\\emph{Fusion regime}} \\\\ \n")
for e in ["rank", "percent", "bottom-two"]:
    E.append(f"{e} & {jb[e]['weeks']} & -- & -- & {tex(jb[e]['judge_only_hit'])} \\\\ \n")
E.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

with open(os.path.join(OUT, "tables_extra.tex"), "w", encoding="utf-8") as fh:
    fh.write("".join(E))

# ---------------------------------------------------------------- write JSON
with open(os.path.join(OUT, "extended_stats.json"), "w", encoding="utf-8") as fh:
    json.dump(S, fh, ensure_ascii=False, indent=2, default=str)

# ---------------------------------------------------------------- generate LaTeX tables
def tex(v, n=3):
    if v is None:
        return "--"
    return f"{v:.{n}f}"


L = []
L.append("% AUTO-GENERATED by analyze_extended.py — every value is computed from the CSV artifacts.\n")

# season longtable
L.append("\\begin{longtable}{lrrrrrrrr}\n")
L.append("\\caption{Season-level descriptive statistics from the reconstructed panel. "
         "$\\overline{q^F}$ and $\\overline{q^J}$ are mean reconstructed fan share and judge "
         "share; $\\overline{\\Delta}$ is the mean $90\\%$ credible-interval width; hit rate is "
         "the mean percent-rule posterior hit probability over eliminating weeks only; "
         "$\\hat R_{\\max}$ is the worst split-$\\hat R$ in that season.} \\\\ \n")
L.append("\\label{tab:seasonstats} \\\\ \n")
L.append("\\toprule\n Season & Era & C--W & Wks & Elim. & $\\overline{q^F}$ & $\\overline{q^J}$ & "
         "$\\overline{\\Delta}$ & Hit \\\\ \n\\midrule\n\\endfirsthead\n")
L.append("\\toprule\n Season & Era & C--W & Wks & Elim. & $\\overline{q^F}$ & $\\overline{q^J}$ & "
         "$\\overline{\\Delta}$ & Hit \\\\ \n\\midrule\n\\endhead\n\\midrule\n\\endfoot\n")
for row in season_rows:
    L.append(f"{row['season']} & {row['era']} & {row['couple_weeks']} & {row['weeks']} & "
             f"{row['elim_weeks']} & {tex(row['pF'])} & {tex(row['pJ'])} & "
             f"{tex(row['ci'])} & {tex(row['hit'])} \\\\ \n")
L.append("\\bottomrule\n\\end{longtable}\n\n")

# weight scan table
L.append("\\begin{table}[H]\n\\centering\n")
L.append("\\caption{Counterfactual elimination consistency as the fusion weight $w$ on the "
         "judge channel varies. Score $=w\\,q^J+(1-w)\\,\\hat q^F$; the predicted elimination is "
         "the couple minimising the score. Percent-era = seasons 1--27, bottom-two era = "
         "seasons 28--34. The rank column uses $w\\,r^J+(1-w)\\,r^F$ on ordinal ranks.}\n")
L.append("\\label{tab:weights}\n\\begin{tabular}{lcccc}\n\\toprule\n")
L.append("$w$ (judge weight) & All seasons & Percent era & Bottom-two era & Rank fusion \\\\ \n\\midrule\n")
by_w = {x["w"]: x["hit"] for x in S["weight_scan"]["percent_all"]}
ea = {x["w"]: x["hit"] for x in S["weight_scan"]["percent_early"]}
la = {x["w"]: x["hit"] for x in S["weight_scan"]["percent_late"]}
rk = {x["w"]: x["hit"] for x in S["weight_scan"]["rank_all"]}
for w in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
    L.append(f"{w:.1f} & {tex(by_w.get(w))} & {tex(ea.get(w))} & {tex(la.get(w))} & "
             f"{tex(rk.get(w))} \\\\ \n")
L.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

# diagnostics table
L.append("\\begin{table}[H]\n\\centering\n")
L.append("\\caption{Weekly sampler and validation diagnostics over all "
         f"{S['panel']['weeks_in_consistency']} competition weeks. ESS is the effective sample "
         "size from an 8{,}000-draw budget; Brier, $\\kappa$, Kendall $\\tau$ and Spearman $\\rho$ "
         "are the recorded weekly validation statistics.}\n")
L.append("\\label{tab:diagnostics}\n\\begin{tabular}{lrrrrrr}\n\\toprule\n")
L.append("Statistic & $n$ & Mean & SD & Min & Median & Max \\\\ \n\\midrule\n")
labels = [("rhat", "Split-$\\hat R$"), ("ess", "ESS"),
          ("n_constraints", "Active constraints"), ("p_hit_pct", "Percent hit probability"),
          ("brier_pct", "Brier score"), ("kappa_pct", "Percent $\\kappa$"),
          ("tau_pct", "Kendall $\\tau$"), ("spearman_pct", "Spearman $\\rho$"),
          ("n_couples", "Couples in week")]
for k, lab in labels:
    d = S["diagnostics"][k]
    L.append(f"{lab} & {d['n']} & {tex(d['mean'])} & {tex(d['sd'])} & {tex(d['min'])} & "
             f"{tex(d['median'])} & {tex(d['max'])} \\\\ \n")
L.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

# era table
L.append("\\begin{table}[H]\n\\centering\n")
L.append("\\caption{Regime comparison. Hit rate and $\\kappa$ are averaged over eliminating "
         "weeks; credible-interval width is averaged over all couple--weeks in the regime.}\n")
L.append("\\label{tab:erastats}\n\\begin{tabular}{lrrrrrr}\n\\toprule\n")
L.append("Regime & C--W & Weeks & Elim. & Hit rate & $\\overline{\\Delta}$ & Brier \\\\ \n\\midrule\n")
for e in ["rank", "percent", "bottom-two"]:
    d = S["eras"][e]
    L.append(f"{e} & {d['couple_weeks']} & {d['weeks']} & {d['eliminating_weeks']} & "
             f"{tex(d['mean_hit_pct'])} & {tex(d['mean_ci'])} & {tex(d['mean_brier_pct'])} \\\\ \n")
L.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

# covariate table
L.append("\\begin{table}[H]\n\\centering\n")
L.append("\\caption{Covariate channel comparison (Model 3 panel). Mean reconstructed fan share "
         "and judge share by celebrity age band and by industry group (groups with at least 25 "
         "couple--weeks). $\\Delta=\\overline{q^F}-\\overline{q^J}$ isolates the fan-specific "
         "premium.}\n")
L.append("\\label{tab:covariates}\n\\begin{tabular}{lrrrr}\n\\toprule\n")
L.append("Group & $n$ & $\\overline{q^F}$ & $\\overline{q^J}$ & $\\Delta$ \\\\ \n\\midrule\n")
L.append("\\multicolumn{5}{l}{\\emph{Age band}} \\\\ \n")
for row in S["covariates"]["age_bins"]:
    d = (row["fan"] or 0) - (row["judge"] or 0)
    L.append(f"{row['bin']} & {row['n']} & {tex(row['fan'])} & {tex(row['judge'])} & "
             f"{tex(d)} \\\\ \n")
L.append("\\midrule\n\\multicolumn{5}{l}{\\emph{Industry}} \\\\ \n")
for row in S["covariates"]["industry"][:10]:
    d = (row["fan"] or 0) - (row["judge"] or 0)
    safe = row["industry"].replace("&", "\\&").replace("_", "\\_")
    L.append(f"{safe} & {row['n']} & {tex(row['fan'])} & {tex(row['judge'])} & "
             f"{tex(d)} \\\\ \n")
L.append("\\bottomrule\n\\end{tabular}\n\\end{table}\n\n")

with open(os.path.join(OUT, "tables_gen.tex"), "w", encoding="utf-8") as fh:
    fh.write("".join(L))

# ---------------------------------------------------------------- human-readable summary
print("=== PANEL ===", json.dumps(S["panel"], ensure_ascii=False))
print("=== SHARES ===", json.dumps(S["shares"], ensure_ascii=False))
print("=== DIRECTION ===", json.dumps(diag, ensure_ascii=False), "->", S["replay_direction"])
print("=== ERAS ===", json.dumps(S["eras"], ensure_ascii=False))
print("=== JUDGE SAVE ===", json.dumps(S["judge_save"], ensure_ascii=False))
print("=== UNCERTAINTY ===", json.dumps({k: v for k, v in S["uncertainty"].items()
                                        if k != "ci_by_ncouples"}, ensure_ascii=False))
print("=== DIVERGENCE ===", json.dumps(S["divergence"], ensure_ascii=False))
print("=== RULE DISAGREE ===", json.dumps({k: v for k, v in S["rule_disagreement"].items()
                                          if k != "by_season"}, ensure_ascii=False))
print("=== WEIGHT SCAN (w=0,.25,.5,.75,1) ===")
for k in ["percent_all", "percent_early", "percent_late", "rank_all", "percent_lo", "percent_hi"]:
    sel = [x for x in S["weight_scan"][k] if abs(x["w"] * 4 - round(x["w"] * 4)) < 1e-9]
    print(" ", k, [(x["w"], x["hit"]) for x in sel])
print("=== COVARIATES ===", json.dumps(S["covariates"], ensure_ascii=False)[:1800])
print("=== RAW ===", json.dumps(S["raw"], ensure_ascii=False)[:900])
print("=== CONTROVERSY lengths ===", {k: len(v) for k, v in traj.items()})
print("tables_gen.tex lines:", len("".join(L).splitlines()))
