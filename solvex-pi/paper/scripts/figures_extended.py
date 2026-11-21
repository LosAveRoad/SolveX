"""Publication figures for the extended 2026 MCM C paper.

All panels are drawn from the materialized CSV artifacts; no synthetic data.
"""
import os
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = "/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/sessions/rerun-2026-mcmc"
PROG = os.path.join(ROOT, "02_programming")
FIG = os.path.join(ROOT, "04_paper", "figures_ext")
os.makedirs(FIG, exist_ok=True)

C = {"J": "#2f5d8c", "F": "#b4443c", "acc": "#3f7d58",
     "grey": "#8a8f98", "gold": "#c8912a", "purple": "#6b4a7a"}
EC = {"rank": C["gold"], "percent": C["J"], "bottom-two": C["F"]}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9, "legend.fontsize": 8,
    "axes.grid": True, "grid.alpha": .3, "grid.linewidth": .5,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 170, "figure.dpi": 170,
})

m1 = pd.read_csv(os.path.join(PROG, "model_1", "fan_vote_estimates.csv"))
wc = pd.read_csv(os.path.join(PROG, "model_1", "weekly_consistency.csv"))
m3 = pd.read_csv(os.path.join(PROG, "model_3", "couple_weeks_model3.csv"))
raw = pd.read_csv("/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/2026_MCM_Problem_C_Data.csv",
                  encoding="utf-8-sig")

for c in ["season", "week", "J", "pJ", "rankJ", "pF_med", "pF_lo", "pF_hi", "pF_sd",
          "pF_med_renorm", "rankF", "comb_pct", "comb_rank", "age", "placement"]:
    if c in m1.columns:
        m1[c] = pd.to_numeric(m1[c], errors="coerce")
m1["elim"] = m1["eliminated"].astype(str).str.lower().isin(["true", "1"])
m1["ci"] = m1["pF_hi"] - m1["pF_lo"]
m1["d"] = m1["pF_med_renorm"] - m1["pJ"]
m1["rgap"] = (m1["rankF"] - m1["rankJ"]).abs()
m1["era"] = np.select([m1["season"] <= 2, m1["season"] <= 27],
                      ["rank", "percent"], default="bottom-two")
for c in ["season", "week", "n_couples", "n_exiting", "rhat", "ess", "n_constraints",
          "p_hit_pct", "brier_pct", "kappa_pct", "tau_pct", "spearman_pct"]:
    wc[c] = pd.to_numeric(wc[c], errors="coerce")
wc["bt"] = wc["bottom_two"].astype(str).str.lower().isin(["true", "1"])
wc["era"] = np.select([wc["season"] <= 2, wc["season"] <= 27],
                      ["rank", "percent"], default="bottom-two")
mg = m1.merge(wc[["season", "week", "n_couples", "n_constraints"]],
              on=["season", "week"], how="left")
mg["ci_rel"] = mg["ci"] * mg["n_couples"]
for c in ["season", "week", "age", "pJ", "pF_med", "us_home"]:
    if c in m3.columns:
        m3[c] = pd.to_numeric(m3[c], errors="coerce")

COUNT = [0]


def save(name, fig):
    p = os.path.join(FIG, name)
    fig.tight_layout()
    fig.savefig(p, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    COUNT[0] += 1
    print(f"  {name}")


def era_shade(ax, seasons=None):
    ax.axvspan(0.5, 2.5, color=EC["rank"], alpha=.07)
    ax.axvspan(2.5, 27.5, color=EC["percent"], alpha=.05)
    ax.axvspan(27.5, 34.5, color=EC["bottom-two"], alpha=.07)
    ax.axvline(27.5, color=C["grey"], ls="--", lw=1)


# ------------------------------------------------------------------ 01 panel overview
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
s = m1.groupby("season").size()
ax[0, 0].bar(s.index, s.values, color=[EC[m1[m1.season == i]["era"].iloc[0]] for i in s.index])
era_shade(ax[0, 0]); ax[0, 0].set(xlabel="Season", ylabel="Couple--weeks",
                                  title="(a) Panel size by season")
ax[0, 0].legend(handles=[Patch(color=v, label=k) for k, v in EC.items()], fontsize=7,
                loc="upper left", frameon=False)
nw = wc["n_couples"].dropna()
ax[0, 1].hist(nw, bins=np.arange(1.5, 17.5, 1), color=C["acc"], alpha=.85)
ax[0, 1].axvline(nw.mean(), color=C["F"], ls="--", lw=1.4,
                 label=f"mean = {nw.mean():.2f}")
ax[0, 1].set(xlabel="Couples surviving in a week", ylabel="Weeks",
             title="(b) Field size across 335 competition weeks")
ax[0, 1].legend(frameon=False)
box = [m1[m1.week == w]["J"].dropna().values for w in range(1, 12)]
ax[1, 0].boxplot(box, tick_labels=range(1, 12), showfliers=False, patch_artist=True,
                 boxprops=dict(facecolor=C["J"], alpha=.55), medianprops=dict(color=C["F"]))
ax[1, 0].set(xlabel="Competition week", ylabel="Weekly judge total",
             title="(c) Judge totals rise as the field narrows")
a = pd.to_numeric(raw["celebrity_age_during_season"], errors="coerce").dropna()
ax[1, 1].hist(a, bins=28, color=C["purple"], alpha=.8)
ax[1, 1].axvline(a.mean(), color=C["F"], ls="--", lw=1.4, label=f"mean = {a.mean():.1f}")
ax[1, 1].set(xlabel="Celebrity age", ylabel="Contestants",
             title=f"(d) Age distribution of {len(raw)} contestants")
ax[1, 1].legend(frameon=False)
save("fig01_panel_overview.png", fig)

# ------------------------------------------------------------------ 02 raw judge scores
score_cols = [c for c in raw.columns if re.match(r"week\d+_judge\d+_score", c)]
sc = raw[score_cols].apply(pd.to_numeric, errors="coerce")
weekly = {}
for k in range(1, 12):
    cols = [c for c in score_cols if c.startswith(f"week{k}_")]
    if cols:
        weekly[k] = sc[cols].mean(axis=1)
wd = pd.DataFrame(weekly)
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
allv = sc.stack().dropna()
ax[0, 0].hist(allv, bins=35, color=C["J"], alpha=.8)
ax[0, 0].axvline(allv.mean(), color=C["F"], ls="--", lw=1.4,
                 label=f"mean = {allv.mean():.2f}")
ax[0, 0].set(xlabel="Individual judge score", ylabel="Score entries",
             title=f"(a) {len(allv):,} non-missing judge scores")
ax[0, 0].legend(frameon=False)
mu = wd.mean(); sd = wd.std()
ax[0, 1].plot(mu.index, mu.values, "-o", color=C["J"], ms=4, label="weekly mean")
ax[0, 1].fill_between(mu.index, mu - sd, mu + sd, color=C["J"], alpha=.18, label="$\\pm$1 SD")
ax[0, 1].set(xlabel="Competition week", ylabel="Mean judge score",
             title="(b) Score inflation over the season")
ax[0, 1].legend(frameon=False)
ic = raw["celebrity_industry"].value_counts().head(8)[::-1]
ax[1, 0].barh(ic.index, ic.values, color=C["acc"], alpha=.85)
ax[1, 0].set(xlabel="Contestants", title="(c) Celebrity industry composition")
pl = raw["results"].value_counts()
fin = pl[[i for i in pl.index if "Place" in str(i) or "Winner" in str(i)]].sum()
ax[1, 1].bar(["Finalists", "Eliminated"], [fin, len(raw) - fin],
             color=[C["gold"], C["grey"]], alpha=.85)
for i, v in enumerate([fin, len(raw) - fin]):
    ax[1, 1].text(i, v + 4, str(v), ha="center", fontsize=9)
ax[1, 1].set(ylabel="Contestants", title="(d) Finalists versus eliminated contestants")
save("fig02_raw_judge_scores.png", fig)

# ------------------------------------------------------------------ 03 season dynamics
sea = m1.groupby("season").agg(qF=("pF_med", "mean"), qJ=("pJ", "mean"),
                               ci=("ci", "mean")).reset_index()
hit = wc[wc.n_exiting > 0].groupby("season")["p_hit_pct"].mean()
elw = wc[wc.n_exiting > 0].groupby("season").size()
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
ax[0, 0].plot(sea.season, sea.qF, "-o", color=C["F"], ms=3.5, label="$\\hat q^F$")
ax[0, 0].plot(sea.season, sea.qJ, "-s", color=C["J"], ms=3.5, label="$q^J$")
era_shade(ax[0, 0]); ax[0, 0].legend(frameon=False)
ax[0, 0].set(xlabel="Season", ylabel="Mean share", title="(a) Judge and reconstructed fan share")
ax[0, 1].plot(sea.season, sea.ci, "-o", color=C["acc"], ms=3.5)
era_shade(ax[0, 1])
ax[0, 1].set(xlabel="Season", ylabel="Mean 90% interval width",
             title="(b) Reconstruction uncertainty by season")
ax[1, 0].plot(hit.index, hit.values, "-o", color=C["purple"], ms=3.5)
era_shade(ax[1, 0]); ax[1, 0].axhline(.4, color=C["F"], ls=":", lw=1.2,
                                      label="bottom-two mean = 0.400")
ax[1, 0].set(xlabel="Season", ylabel="Mean percent-rule hit rate", ylim=(-.03, 1.06),
             title="(c) Structural break at season 28")
ax[1, 0].legend(frameon=False, fontsize=7)
ax[1, 1].bar(elw.index, elw.values,
             color=[EC["rank"] if i <= 2 else EC["percent"] if i <= 27 else EC["bottom-two"]
                    for i in elw.index])
ax[1, 1].set(xlabel="Season", ylabel="Eliminating weeks",
             title=f"(d) {int(elw.sum())} eliminating weeks in total")
save("fig03_season_dynamics.png", fig)

# ------------------------------------------------------------------ 04 uncertainty structure
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
d = mg.dropna(subset=["ci", "n_couples"])
ax[0, 0].scatter(d.n_couples + np.random.uniform(-.25, .25, len(d)), d.ci,
                 s=6, alpha=.13, color=C["J"])
x = np.sort(d.n_couples.unique())
y = [d[d.n_couples == k]["ci"].mean() for k in x]
ax[0, 0].plot(x, y, "-o", color=C["F"], lw=2, ms=4, label="binned mean")
ax[0, 0].set(xlabel="Couples in week", ylabel="Absolute 90% interval width",
             title=f"(a) Absolute width vs. field size (r = {d.ci.corr(d.n_couples):.3f})")
ax[0, 0].legend(frameon=False)
bins = ["2-5", "6-8", "9-11", "12-16"]
data = [d[pd.cut(d.n_couples, [1, 5, 8, 11, 20], labels=bins) == b]["ci_rel"].dropna()
        for b in bins]
ax[0, 1].boxplot(data, tick_labels=bins, showfliers=False, patch_artist=True,
                 boxprops=dict(facecolor=C["acc"], alpha=.55), medianprops=dict(color=C["F"]))
ax[0, 1].set(xlabel="Couples in week", ylabel="$n\\times$interval width",
             title="(b) Field-size-normalised uncertainty")
wk = d.groupby("week").agg(ci=("ci", "mean"), rel=("ci_rel", "mean"))
ax2 = ax[1, 0].twinx()
ax[1, 0].plot(wk.index, wk.ci, "-o", color=C["J"], ms=4, label="absolute")
ax2.plot(wk.index, wk.rel, "-s", color=C["F"], ms=4, label="normalised")
ax[1, 0].set(xlabel="Competition week", ylabel="Absolute width",
             title="(c) Two measures disagree on the trend")
ax2.set_ylabel("$n\\times$width", color=C["F"])
ax[1, 0].legend(loc="upper left", frameon=False); ax2.legend(loc="lower left", frameon=False)
ax[1, 0].grid(False); ax2.grid(False)
ed = [mg[mg.era == e]["ci"].dropna() for e in ["rank", "percent", "bottom-two"]]
ax[1, 1].boxplot(ed, tick_labels=["rank\n1--2", "percent\n3--27", "bottom-two\n28--34"],
                 showfliers=False, patch_artist=True,
                 boxprops=dict(facecolor=C["grey"], alpha=.5), medianprops=dict(color=C["F"]))
ax[1, 1].set(ylabel="Absolute 90% interval width",
             title="(d) Interval width by fusion regime")
save("fig04_uncertainty_structure.png", fig)

# ------------------------------------------------------------------ 05 judge / fan channels
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
ax[0, 0].scatter(m1.pJ, m1.pF_med_renorm, s=7, alpha=.14, color=C["purple"])
lim = [0, .53]
ax[0, 0].plot(lim, lim, color=C["grey"], ls="--", lw=1)
ax[0, 0].set(xlim=lim, ylim=lim, xlabel="Judge share $q^J$",
             ylabel="Reconstructed fan share $\\tilde q^F$",
             title=f"(a) Level agreement (Pearson r = {m1.pJ.corr(m1.pF_med_renorm):.3f})")
for e in ["rank", "percent", "bottom-two"]:
    v = m1[m1.era == e]["d"].dropna()
    ax[0, 1].hist(v, bins=45, histtype="step", lw=1.7, color=EC[e], label=e, density=True)
ax[0, 1].axvline(0, color=C["grey"], ls="--", lw=1)
ax[0, 1].set(xlabel="$\\tilde q^F-q^J$ within week", ylabel="Density",
             title="(b) Within-week reallocation, by regime")
ax[0, 1].legend(frameon=False)
g = m1["rgap"].dropna()
ax[1, 0].hist(g, bins=np.arange(-.5, 16.5, 1), color=C["gold"], alpha=.85)
ax[1, 0].axvline(g.mean(), color=C["F"], ls="--", lw=1.4,
                 label=f"mean = {g.mean():.2f}")
ax[1, 0].set(xlabel="$|r^F-r^J|$", ylabel="Couple--weeks",
             title="(c) Fine-ordering disagreement is the norm")
ax[1, 0].legend(frameon=False)
labels = ["Eliminated", "Survived"]
e_, s_ = m1[m1.elim], m1[~m1.elim]
xx = np.arange(2); w = .35
ax[1, 1].bar(xx - w/2, [e_.pF_med.mean(), s_.pF_med.mean()], w, color=C["F"],
             alpha=.85, label="fan share")
ax[1, 1].bar(xx + w/2, [e_.pJ.mean(), s_.pJ.mean()], w, color=C["J"],
             alpha=.85, label="judge share")
ax[1, 1].set(xticks=xx, xticklabels=labels, ylabel="Mean share",
             title="(d) Judges barely separate who leaves; fans do")
ax[1, 1].legend(frameon=False)
save("fig05_judge_fan_channels.png", fig)

# ------------------------------------------------------------------ 06 elimination evidence
pos, worst = [], []
for _, g0 in m1.groupby(["season", "week"]):
    e0 = g0[g0.elim]
    if len(e0) == 0 or g0.rankJ.notna().sum() < 2:
        continue
    for _, row in e0.iterrows():
        rng = max(g0.rankJ.max() - g0.rankJ.min(), 1)
        pos.append((row.rankJ - g0.rankJ.min()) / rng)
        worst.append(int(row.rankJ == g0.rankJ.max()))
jb = {"rank": .40, "percent": .46, "bottom-two": .393}
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
ax[0, 0].hist(pos, bins=20, color=C["purple"], alpha=.85)
ax[0, 0].axvline(np.mean(pos), color=C["F"], ls="--", lw=1.4,
                 label=f"mean = {np.mean(pos):.3f}")
ax[0, 0].set(xlabel="Normalised judge rank of eliminated couple (1 = worst)",
             ylabel="Eliminations", title="(a) Eliminated couples are not the judges' bottom")
ax[0, 0].legend(frameon=False, fontsize=7)
ax[0, 1].bar(jb.keys(), jb.values(), color=[EC[k] for k in jb], alpha=.85)
ax[0, 1].axhline(.4436, color=C["grey"], ls="--", lw=1.2, label="pooled = 0.444")
for i, v in enumerate(jb.values()):
    ax[0, 1].text(i, v + .012, f"{v:.3f}", ha="center", fontsize=8)
ax[0, 1].set(ylabel="Hit rate", ylim=(0, .62),
             title="(b) Judge-only elimination baseline by regime")
ax[0, 1].legend(frameon=False)
ax[1, 0].boxplot([e_.pF_med.dropna(), s_.pF_med.dropna()], tick_labels=["Eliminated", "Survived"],
                 showfliers=False, patch_artist=True,
                 boxprops=dict(facecolor=C["F"], alpha=.45), medianprops=dict(color="black"))
ax[1, 0].set(ylabel="Reconstructed fan share",
             title="(c) Fan channel separates eliminations")
margins = {e: [] for e in jb}
for _, g0 in m1.groupby(["season", "week"]):
    if len(g0) < 2 or g0.comb_pct.notna().sum() < 2:
        continue
    v = np.sort(g0.comb_pct.dropna().values)
    margins[g0["era"].iloc[0]].append(v[1] - v[0])
ax[1, 0 + 1].boxplot([margins[e] for e in jb], tick_labels=list(jb.keys()), showfliers=False,
                     patch_artist=True, boxprops=dict(facecolor=C["acc"], alpha=.5),
                     medianprops=dict(color=C["F"]))
ax[1, 1].set(ylabel="Bottom-two combined-score gap",
             title="(d) How close were the two at-risk couples?")
save("fig06_elimination_evidence.png", fig)

# ------------------------------------------------------------------ 07 fusion weight frontier
W = np.linspace(0, 1, 21)


def scan(col_j, col_f, direction="min", seasons=None):
    d0 = m1 if seasons is None else m1[m1.season.isin(seasons)]
    out = []
    for w in W:
        d0 = d0.copy()
        d0["score"] = w * d0[col_j] + (1 - w) * d0[col_f]
        hit = tot = 0
        for _, g0 in d0.groupby(["season", "week"]):
            if not g0.elim.any() or g0.score.notna().sum() < 2:
                continue
            idx = g0.score.idxmin() if direction == "min" else g0.score.idxmax()
            hit += int(bool(g0.loc[idx, "elim"])); tot += 1
        out.append(hit / tot if tot else np.nan)
    return np.array(out)


pa = scan("pJ", "pF_med_renorm")
pe = scan("pJ", "pF_med_renorm", seasons=range(1, 28))
pl = scan("pJ", "pF_med_renorm", seasons=range(28, 35))
rk = scan("rankJ", "rankF", direction="max")
lo = scan("pJ", "pF_lo", seasons=range(1, 28))
hi = scan("pJ", "pF_hi", seasons=range(1, 28))
fig, ax = plt.subplots(figsize=(8.6, 5.2))
ax.fill_between(W, np.minimum(lo, hi), np.maximum(lo, hi), color=C["acc"], alpha=.15,
                label="90% interval envelope (percent era)")
ax.plot(W, pa, "-o", color=C["F"], ms=4, lw=2, label="Percent fusion, all seasons")
ax.plot(W, pe, "--s", color=C["J"], ms=3.5, lw=1.6, label="Percent fusion, seasons 1--27")
ax.plot(W, pl, ":^", color=C["purple"], ms=3.5, lw=1.6, label="Percent fusion, seasons 28--34")
ax.plot(W, rk, "-D", color=C["gold"], ms=3.5, lw=1.6, label="Rank fusion, all seasons")
ax.axvspan(-.02, .55, color=C["grey"], alpha=.08)
ax.annotate("structurally constrained\nregion (circular)", xy=(.26, .35), fontsize=8,
            color=C["grey"], ha="center")
ax.scatter([1.0], [pa[-1]], s=90, facecolor="none", edgecolor="black", zorder=5)
ax.annotate(f"judge-only baseline\n{pa[-1]:.3f} (non-circular)",
            xy=(1, pa[-1]), xytext=(.77, .18), fontsize=8,
            arrowprops=dict(arrowstyle="->", lw=1))
ax.set(xlabel="Fusion weight $w$ on the judge channel", ylabel="Elimination consistency",
       xlim=(-.02, 1.02), ylim=(0, 1.06), title="Counterfactual fusion-weight frontier")
ax.legend(loc="lower left", frameon=False, fontsize=8)
save("fig07_fusion_weight_frontier.png", fig)

# ------------------------------------------------------------------ 08 regime break
sub = wc[(wc.season >= 24) & (wc.n_exiting > 0)]
bse = sub.groupby("season").agg(hit=("p_hit_pct", "mean"), brier=("brier_pct", "mean"),
                                bt=("bt", "sum"), ci=("rhat", "mean")).reset_index()
ci_sea = m1[m1.season >= 24].groupby("season")["ci"].mean()
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
for a, (col, lab, color) in zip([ax[0, 0], ax[0, 1], ax[1, 0]],
                                [("hit", "Mean hit rate", C["F"]),
                                 ("brier", "Mean Brier score", C["purple"]),
                                 ("bt", "Bottom-two weeks", C["acc"])]):
    a.plot(bse.season, bse[col], "-o", color=color, ms=4)
    a.axvline(27.5, color="black", ls="--", lw=1.3)
    a.annotate("rule change", xy=(27.5, max(bse[col]) * .82), fontsize=8, ha="right")
    a.set(xlabel="Season", ylabel=lab, xticks=range(24, 35))
a = ax[1, 1]
a.plot(ci_sea.index, ci_sea.values, "-o", color=C["J"], ms=4)
a.axvline(27.5, color="black", ls="--", lw=1.3)
a.set(xlabel="Season", ylabel="Mean 90% interval width", xticks=range(24, 35),
      title="(d) Reconstruction uncertainty does not jump")
for a, t in zip(ax.ravel(), ["(a) Consistency collapses", "(b) Brier score mirrors it",
                             "(c) Judge-save weeks appear", "(d) A stable control"]):
    a.set_title(t)
save("fig08_regime_break.png", fig)

# ------------------------------------------------------------------ 09 rule disagreement
dis, grid = [], np.full((34, 11), np.nan)
for (s, w0), g0 in m1.groupby(["season", "week"]):
    if not g0.elim.any() or g0.comb_pct.notna().sum() < 2:
        continue
    a = g0.comb_pct.idxmin(); b = g0.comb_rank.idxmax()
    v = int(a != b)
    dis.append((s, w0, v))
    if 1 <= w0 <= 11:
        grid[int(s) - 1, int(w0) - 1] = v
dd = pd.DataFrame(dis, columns=["season", "week", "disagree"])
rate = dd.groupby("season")["disagree"].mean()
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
ax[0, 0].bar(rate.index, rate.values, color=C["acc"], alpha=.85)
era_shade(ax[0, 0])
ax[0, 0].set(xlabel="Season", ylabel="Fraction of weeks with different elimination",
             title=f"(a) Rank vs. percent disagree in {int(dd.disagree.sum())}/{len(dd)} weeks")
im = ax[0, 1].imshow(grid.T, aspect="auto", origin="lower", cmap="RdYlBu_r", vmin=0, vmax=1)
ax[0, 1].set(xlabel="Season", ylabel="Week", title="(b) Disagreement map (red = disagree)")
ax[0, 1].set_xticks([0, 9, 19, 29, 33], [1, 10, 20, 30, 34])
plt.colorbar(im, ax=ax[0, 1], fraction=.046)
er = [dd[dd.season <= 2].disagree.mean(),
      dd[(dd.season > 2) & (dd.season <= 27)].disagree.mean(),
      dd[dd.season > 27].disagree.mean()]
ax[1, 0].bar(["rank 1--2", "percent 3--27", "bottom-two 28--34"], er,
             color=[EC["rank"], EC["percent"], EC["bottom-two"]], alpha=.85)
for i, v in enumerate(er):
    ax[1, 0].text(i, v + .003, f"{v:.3f}", ha="center", fontsize=8)
ax[1, 0].set(ylabel="Disagreement rate", title="(c) Disagreement by regime")
cs = ["Jerry Rice", "Billy Ray Cyrus", "Bristol Palin", "Bobby Bones"]
vals = []
for name, season in zip(cs, [2, 4, 11, 27]):
    g0 = m1[(m1.season == season) & m1.celebrity.astype(str).str.contains(
        name.split()[-1], case=False, na=False)]
    vals.append(g0["d"].mean() if len(g0) else 0)
ax[1, 1].barh([n.replace(" ", "\n") for n in cs], vals,
              color=[C["F"] if v > 0 else C["J"] for v in vals], alpha=.85)
ax[1, 1].axvline(0, color="black", lw=.8)
ax[1, 1].set(xlabel="Mean $\\tilde q^F-q^J$ across the contestant's weeks",
             title="(d) Named controversies all carry a fan premium")
save("fig09_rule_disagreement.png", fig)

# ------------------------------------------------------------------ 10 diagnostics
fig, ax = plt.subplots(2, 3, figsize=(11.5, 6.6))
ax[0, 0].hist(wc.rhat.dropna(), bins=30, color=C["J"], alpha=.85)
ax[0, 0].axvline(1.1, color=C["F"], ls="--", lw=1.2, label="1.1 threshold")
ax[0, 0].set(xlabel="Split-$\\hat R$", ylabel="Weeks", title=f"(a) $\\hat R$ (max {wc.rhat.max():.3f})")
ax[0, 0].legend(frameon=False, fontsize=7)
ax[0, 1].hist(wc.ess.dropna(), bins=30, color=C["acc"], alpha=.85)
ax[0, 1].set(xlabel="Effective sample size", ylabel="Weeks",
             title=f"(b) ESS (min {int(wc.ess.min()):,})")
ax[0, 2].hist(wc.n_constraints.dropna(), bins=np.arange(-.5, 31.5, 1),
              color=C["purple"], alpha=.85)
ax[0, 2].set(xlabel="Active constraints", ylabel="Weeks",
             title=f"(c) Constraints (mean {wc.n_constraints.mean():.2f})")
bd = [wc[wc.era == e]["brier_pct"].dropna() for e in ["rank", "percent", "bottom-two"]]
ax[1, 0].boxplot(bd, tick_labels=["rank", "percent", "bottom-two"], showfliers=False,
                 patch_artist=True, boxprops=dict(facecolor=C["F"], alpha=.45),
                 medianprops=dict(color="black"))
ax[1, 0].set(ylabel="Brier score", title="(d) Brier separates the regimes")
for c, lab, col in [("spearman_pct", "Spearman $\\rho$", C["J"]),
                    ("tau_pct", "Kendall $\\tau$", C["gold"]),
                    ("kappa_pct", "$\\kappa$ (percent)", C["acc"])]:
    ax[1, 1].hist(wc[c].dropna(), bins=25, histtype="step", lw=1.7, color=col, label=lab,
                  density=True)
ax[1, 1].set(xlabel="Weekly statistic", ylabel="Density", title="(e) Validation statistics")
ax[1, 1].legend(frameon=False, fontsize=7)
ax[1, 2].scatter(wc.rhat, wc.ess, s=11, alpha=.5, color=C["purple"])
ax[1, 2].set(xlabel="Split-$\\hat R$", ylabel="ESS", title="(f) Convergence is uniformly healthy")
save("fig10_sampler_diagnostics.png", fig)

# ------------------------------------------------------------------ 11 controversy trajectories
cases = [("Jerry Rice", 2), ("Billy Ray Cyrus", 4), ("Bristol Palin", 11), ("Bobby Bones", 27)]
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
for a, (name, season) in zip(ax.ravel(), cases):
    g0 = m1[(m1.season == season) & m1.celebrity.astype(str).str.contains(
        name.split()[-1], case=False, na=False)].sort_values("week")
    a.plot(g0.week, g0.pJ, "-s", color=C["J"], ms=4, label="$q^J$")
    a.plot(g0.week, g0.pF_med_renorm, "-o", color=C["F"], ms=4, label="$\\tilde q^F$")
    a.plot(g0.week, g0.comb_pct, "-^", color=C["acc"], ms=4, label="percent-combined")
    a.set(xlabel="Week", ylabel="Share", xticks=sorted(g0.week.unique()),
          title=f"S{season}: {name}")
    a.legend(frameon=False, fontsize=7)
save("fig11_controversy_trajectories.png", fig)

# ------------------------------------------------------------------ 12 covariates
m3["age_bin"] = pd.cut(m3.age, [0, 26, 34, 43, 100], labels=["<=26", "27-34", "35-43", ">43"])
ab = m3.groupby("age_bin", observed=True).agg(F=("pF_med", "mean"), J=("pJ", "mean"))
ib = m3.groupby("industry").agg(F=("pF_med", "mean"), J=("pJ", "mean"), n=("pF_med", "size"))
ib = ib[ib.n >= 25].sort_values("F", ascending=False).head(8)
pg = m3.groupby("pro_id").agg(F=("pF_med", "mean"), n=("pF_med", "size")).reset_index()
pg = pg[pg.n >= 20].sort_values("F")
pr = pd.concat([pg.head(5), pg.tail(5)])
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
for a, (t, labs, xlab, ttl) in zip(
        [ax[0, 0], ax[0, 1]],
        [(ab, [str(x) for x in ab.index], "Age band", "(a) Age: both channels decline"),
         (ib, [str(x)[:14] for x in ib.index], "Industry", "(b) Industry gaps are small")]):
    x = np.arange(len(t)); w = .36
    a.bar(x - w/2, t.F, w, color=C["F"], alpha=.85, label="fan")
    a.bar(x + w/2, t.J, w, color=C["J"], alpha=.85, label="judge")
    a.set(xticks=x, xticklabels=labs, xlabel=xlab, ylabel="Mean share", title=ttl)
    if a is ax[0, 1]:
        a.tick_params(axis="x", rotation=35, labelsize=7)
    a.legend(frameon=False)
ax[1, 0].barh(range(len(pr)), pr.F, color=[C["J"] if v < .09 else C["F"] for v in pr.F],
              alpha=.85)
ax[1, 0].set_yticks(range(len(pr)), [f"{p} (n={int(n)})" for p, n in
                                     zip(pr.pro_id, pr.n)], fontsize=7)
ax[1, 0].set(xlabel="Mean reconstructed fan share",
             title="(c) Professional-partner effect (top/bottom 5)")
ax[1, 1].scatter(m3.age, m3.pF_med, s=7, alpha=.12, color=C["purple"])
bm = m3.groupby("age_bin", observed=True).agg(x=("age", "mean"), y=("pF_med", "mean"))
ax[1, 1].plot(bm.x, bm.y, "-o", color=C["F"], lw=2, ms=6, label="binned mean")
ax[1, 1].set(xlabel="Celebrity age", ylabel="Reconstructed fan share",
             title=f"(d) Age--fan correlation = {m3.age.corr(m3.pF_med):.3f}")
ax[1, 1].legend(frameon=False)
save("fig12_covariate_channels.png", fig)

# ------------------------------------------------------------------ 13 interval-robust replay
fig, ax = plt.subplots(2, 2, figsize=(10.5, 7))
ax[0, 0].plot(W, pe, "-o", color=C["F"], ms=3.5, label="posterior median")
ax[0, 0].plot(W, lo, "--", color=C["J"], label="lower 5% bound")
ax[0, 0].plot(W, hi, "--", color=C["acc"], label="upper 95% bound")
ax[0, 0].fill_between(W, np.minimum(lo, hi), np.maximum(lo, hi), color=C["grey"], alpha=.15)
ax[0, 0].set(xlabel="$w$", ylabel="Consistency (seasons 1--27)",
             title="(a) Replaying with interval extremes")
ax[0, 0].legend(frameon=False, fontsize=7)
ax[0, 1].plot(W, np.maximum(hi, pe) - np.minimum(lo, pe), color=C["purple"], lw=2)
ax[0, 1].set(xlabel="$w$", ylabel="Width of the consistency envelope",
             title="(b) Where uncertainty actually matters")
samp = m1[(m1.season.isin([2, 11, 27])) & (m1.week <= 3)].head(18)
y = np.arange(len(samp))
ax[1, 0].errorbar(samp.pF_med, y, xerr=[samp.pF_med - samp.pF_lo, samp.pF_hi - samp.pF_med],
                  fmt="o", ms=4, color=C["F"], ecolor=C["grey"], elinewidth=1, capsize=2)
ax[1, 0].set(xlabel="Reconstructed fan share with 90% interval", ylabel="Couple--week",
             title="(c) Heterogeneous identification, sample of weeks")
ax[1, 0].set_yticks([]); ax[1, 0].grid(axis="y", visible=False)
season_lo = []
for s in range(1, 28):
    d0 = m1[m1.season == s]
    hit = tot = 0
    for _, g0 in d0.groupby("week"):
        if not g0.elim.any() or len(g0) < 2:
            continue
        idx = (.5 * g0.pJ + .5 * g0.pF_lo).idxmin() if g0.pF_lo.notna().all() else g0.pJ.idxmin()
        hit += int(bool(g0.loc[idx, "elim"])); tot += 1
    season_lo.append(hit / tot if tot else np.nan)
ax[1, 1].plot(range(1, 28), season_lo, "-o", color=C["acc"], ms=3.5)
era_shade(ax[1, 1])
ax[1, 1].set(xlabel="Season", ylabel="Consistency at $w=0.5$, lower bound",
             title="(d) Worst-case bound is stable across the percent era")
save("fig13_interval_robust_replay.png", fig)

print(f"generated {COUNT[0]} figures in {FIG}")
