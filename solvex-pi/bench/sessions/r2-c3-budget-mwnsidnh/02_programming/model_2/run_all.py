"""
run_all.py — End-to-end run of Model 2 (Counterfactual Rules Laboratory).

For each of the 34 seasons:
  1. Build the season structure from the official CSV.
  2. Estimate the Model 1 posterior of weekly fan shares (Dirichlet prior
     centered on judge shares, rejection-conditioned on observed eliminations
     under each season's historical rule).
  3. Simulate the whole season under 4 counterfactual rules over all
     posterior draws: RANK, PCT (alpha=0.5), JUDGE_SAVE, PROPOSED.
  4. Compute placement distributions, winner probabilities, flip rates vs.
     observed history, fan/judge power indices, Kendall-tau fairness and
     weekly survival entropy (excitement).
Outputs CSV tables + 3 figures + handoff.json in this directory.
"""
import sys, os, json, time, traceback
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "serif"

import dwts_model2 as D

BASE = os.path.dirname(os.path.abspath(__file__))
FIGDIR = os.path.join(BASE, "figures")
os.makedirs(FIGDIR, exist_ok=True)
DATA = "/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r2-c3-budget-mwnsidnh/data/2026_MCM_Problem_C_Data.csv"

N_DRAWS = 1000
RULES = ["RANK", "PCT", "JUDGE_SAVE", "PROPOSED"]
CONTROVERSIAL = [("Jerry Rice", 2), ("Billy Ray Cyrus", 4),
                 ("Bristol Palin", 11), ("Bobby Bones", 27)]

df = D.load_data(DATA)
t_start = time.time()

rows_pl, rows_season, rows_post = [], [], []
failed = {}

for season in range(1, 35):
    try:
        sd = D.build_season(df, season)
        post = D.season_posterior(sd, n_draw=N_DRAWS, seed=7)
        n, k, S, names = sd["n"], sd["k"], sd["S"], sd["names"]
        place_obs = df[df.season == season]["placement"].to_numpy(float)

        # posterior summary (mean fan share & sd per couple-week)
        for t, dmat in enumerate(post["draws_by_col"]):
            mu = dmat.mean(axis=0); sdm = dmat.std(axis=0)
            for i in range(n):
                if sd["S"][i, t] > 0 and not np.isnan(sd["S"][i, t]):
                    rows_post.append(dict(
                        season=season, week=sd["week_nums"][t],
                        celebrity=names[i], judge_score=float(sd["S"][i, t]),
                        fan_share_mean=float(mu[i]), fan_share_sd=float(sdm[i]),
                        week_accept=post["accept"][t]))

        res_obs = {}
        for rule in RULES:
            res = D.simulate_season(sd, post, rule)
            pl = res["placements"]
            res_obs[rule] = pl

            # per-celebrity placement distribution
            for i in range(n):
                pi = pl[:, i]
                rows_pl.append(dict(
                    season=season, celebrity=names[i], rule=rule,
                    mean_placement=float(np.nanmean(pi)),
                    sd_placement=float(np.nanstd(pi)),
                    p_win=float(np.mean(pi == 1)),
                    p_top3=float(np.mean(pi <= 3)),
                    observed=place_obs[i]))

            # season-level metrics
            fp = float(np.mean(res["fan_alone_hit"])) if res["fan_alone_hit"] else np.nan
            jp = float(np.mean(res["judge_alone_hit"])) if res["judge_alone_hit"] else np.nan
            mean_pl = np.nanmean(pl, axis=0)
            # average judge rank across the weeks a couple competed
            jrank = np.full(n, np.nan)
            for i in range(n):
                wks = np.where(~np.isnan(S[i]))[0]
                if len(wks) == 0: continue
                rks = []
                for t in wks:
                    act = np.where(~np.isnan(S[:, t]))[0]
                    vals = S[act, t] + 1e-9 * np.arange(len(act))
                    rks.append(D._ranks_desc(vals[None, :])[0][list(act).index(i)])
                jrank[i] = np.mean(rks)
            from scipy.stats import kendalltau
            tau = float(kendalltau(-mean_pl, jrank, nan_policy="omit").statistic)
            # winner replay consistency (historical rule only)
            hero = sd["rule"]
            winner_ok = float(np.mean(pl[:, 0] == 1)) if rule == ("RANK" if hero == "RANK" else rule) else np.nan
            # observed winner = couple with placement 1
            obs_w = int(np.argmin(place_obs))
            p_obswin = float(np.mean(pl[:, obs_w] == 1))
            rows_season.append(dict(
                season=season, rule=rule, fan_power=fp, judge_power=jp,
                kendall_tau=tau, mean_entropy=float(np.mean(res["survivor_entropy"])),
                p_observed_winner=p_obswin))
        print(f"season {season:2d} ok ({time.time()-t_start:.0f}s)", flush=True)
    except Exception:
        failed[season] = traceback.format_exc()
        print(f"season {season:2d} FAILED", flush=True)

pl_df = pd.DataFrame(rows_pl)
se_df = pd.DataFrame(rows_season)
po_df = pd.DataFrame(rows_post)

pl_df.to_csv(os.path.join(BASE, "placement_distributions.csv"), index=False)
se_df.to_csv(os.path.join(BASE, "season_rule_metrics.csv"), index=False)
po_df.to_csv(os.path.join(BASE, "posterior_fan_shares.csv"), index=False)

# ---------------------------------------------------------------- controversies
cont = po_df  # placeholder to keep namespace
cont_rows = []
for name, season in CONTROVERSIAL:
    for rule in RULES:
        sel = pl_df[(pl_df.season == season) & (pl_df.celebrity == name) & (pl_df.rule == rule)]
        if not len(sel):
            continue
        r = sel.iloc[0]
        obs = float(r["observed"])
        cont_rows.append(dict(
            celebrity=name, season=season, rule=rule,
            p_win=float(r["p_win"]), p_top3=float(r["p_top3"]),
            mean_placement=float(r["mean_placement"]),
            observed_place=obs))
cont_df = pd.DataFrame(cont_rows)
cont_df.to_csv(os.path.join(BASE, "controversy_counterfactuals.csv"), index=False)
print(cont_df.to_string(index=False))

# historical-rule replay check: P(observed winner wins) under historical rule
hist = se_df[((se_df.season <= 2) | (se_df.season >= 28)) & (se_df.rule == "RANK") |
             ((se_df.season >= 3) & (se_df.season <= 27) & (se_df.rule == "PCT"))]
print("\nReplay consistency (P(observed winner wins) under historical rule):")
print(hist[["season", "rule", "p_observed_winner"]].round(3).to_string(index=False))
print("median:", float(hist["p_observed_winner"].median()))

# ---------------------------------------------------------------- figures
# Fig 1: controversial celebs — P(win) & P(top3) by rule
fig, axes = plt.subplots(2, 2, figsize=(11, 8), dpi=300)
for ax, (name, season) in zip(axes.ravel(), CONTROVERSIAL):
    sub = cont_df[cont_df.celebrity == name]
    x = np.arange(len(RULES)); w = 0.35
    ax.bar(x - w/2, sub.p_win, w, label="P(win)", color="#1f77b4")
    ax.bar(x + w/2, sub.p_top3 - sub.p_win, w, bottom=sub.p_win,
           label="P(2nd–3rd)", color="#ff7f0e")
    ax.set_xticks(x); ax.set_xticklabels(RULES, fontsize=8)
    ax.set_title(f"{name} (Season {season}) — observed place {int(sub.observed_place.iloc[0])}")
    ax.set_ylabel("posterior probability"); ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8)
fig.suptitle("Counterfactual finish distributions under 4 aggregation rules", y=1.01)
fig.tight_layout()
fig.savefig(os.path.join(FIGDIR, "fig1_controversy_rules.png"), bbox_inches="tight")
plt.close(fig)

# Fig 2: fan power vs judge power per season (historical rule),kendall tau color
hf = se_df[se_df.rule.isin(["RANK", "PCT"])]
hist_rows = hf[((hf.season <= 2) | (hf.season >= 28)) & (hf.rule == "RANK") |
               ((hf.season >= 3) & (hf.season <= 27) & (hf.rule == "PCT"))]
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
sc = ax.scatter(hist_rows.fan_power, hist_rows.judge_power,
                c=hist_rows.kendall_tau, cmap="plasma", s=60, edgecolor="k")
for _, r in hist_rows.iterrows():
    ax.annotate(int(r.season), (r.fan_power, r.judge_power), fontsize=7)
plt.colorbar(sc, label="Kendall tau (placement vs judge rank)")
ax.set_xlabel("Fan-power index: P(counterfactual eliminee = fan-vote lowest)")
ax.set_ylabel("Judge-power index: P(counterfactual eliminee = judge-score lowest)")
ax.set_title("Fan power vs judge power by season (historical rule)")
fig.savefig(os.path.join(FIGDIR, "fig2_fan_vs_judge_power.png"), bbox_inches="tight")
plt.close(fig)

# Fig 3: mean survival entropy by rule (excitement), averaged over seasons
ent = se_df.groupby(["rule"]).apply(lambda g: g.mean_entropy.mean(), include_groups=False)
fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
ent.plot(kind="bar", ax=ax, color=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"])
ax.set_ylabel("mean normalized survival entropy (excitement)")
ax.set_title("Excitement by rule (higher = more suspense about who survives)")
ax.set_xlabel("")
fig.savefig(os.path.join(FIGDIR, "fig3_excitement_by_rule.png"), bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- handoff
status = "SATISFIED" if not failed else "PARTIAL"
with open(os.path.join(BASE, "handoff.json"), "w") as fh:
    json.dump(dict(
        status=status,
        issues=[f"season {s} failed: {failed[s].splitlines()[-1]}" for s in failed] or
               ["none"],
        fixInstructions="See results_summary.md Issues or Limitations; "
                        "failed seasons can be re-run by raising max_batches.",
        summaryPath=os.path.join(BASE, "results_summary.md")), fh, indent=2)

print("\nfiles:", sorted(os.listdir(BASE)))
print("figures:", sorted(os.listdir(FIGDIR)))
print("done in %.0fs" % (time.time() - t_start))
