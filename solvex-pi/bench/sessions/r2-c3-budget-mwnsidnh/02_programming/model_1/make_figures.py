"""
make_figures.py — publication-quality figures for Model 1.

  1. fig_fan_pathways.png        — posterior fan-share pathways (mean + 95% CI)
                                   for the four controversy celebrities.
  2. fig_uncertainty_week.png    — mean posterior CV and CI width by week index.
  3. fig_holdout_calibration.png — histogram of prior replay probability.
  4. fig_s27_case.png            — S27 case study: fan support vs judge scores.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "serif"
FIG = "02_programming/model_1/figures"
os.makedirs(FIG, exist_ok=True)

post = pd.read_csv("02_programming/model_1/fan_votes_posterior.csv")
hold = pd.read_csv("02_programming/model_1/holdout_results.csv")

CASES = [("Jerry Rice", 2, "S2, rank rule"),
         ("Billy Ray Cyrus", 4, "S4, pct rule"),
         ("Bristol Palin", 11, "S11, pct rule"),
         ("Bobby Bones", 27, "S27, pct rule")]

# ---------------- Figure 1: fan pathways ----------------
fig, axes = plt.subplots(2, 2, figsize=(8, 6), dpi=300)
for ax, (name, season, subtitle) in zip(axes.ravel(), CASES):
    d = post[(post.celebrity == name) & (post.season == season)].sort_values("week")
    ax.plot(d.week, d.fan_mean, "-o", ms=4, lw=1.5, color="#1f77b4",
            label="posterior fan share")
    ax.fill_between(d.week, d.fan_lo, d.fan_hi, alpha=0.25, color="#1f77b4",
                    label="95% credible band")
    ax.set_title(f"{name} ({subtitle})", fontsize=10)
    ax.set_xlabel("week")
    ax.set_ylabel("fan-vote share")
    ax.tick_params(labelsize=8)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{FIG}/fig_fan_pathways.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- Figure 2: uncertainty vs week ----------------
fig, ax = plt.subplots(figsize=(8, 4.4), dpi=300)
for rule, color in [("pct", "#1f77b4"), ("rank", "#d62728")]:
    d = post[post.rule == rule]
    cv = d.groupby("week").apply(lambda g: np.average(g.fan_cv), include_groups=False)
    ciw = d.groupby("week").apply(lambda g: np.average(g.fan_hi - g.fan_lo),
                                  include_groups=False)
    ax.plot(cv.index, cv.values, "-o", ms=4, lw=1.5, color=color,
            label=f"{rule} rule: mean CV")
    ax.plot(ciw.index, ciw.values, "--s", ms=3, lw=1.2, color=color, alpha=0.6,
            label=f"{rule} rule: mean 95% CI width")
ax.set_xlabel("week index")
ax.set_ylabel("uncertainty of fan-share estimate")
ax.set_title("Uncertainty of inferred fan votes by week number", fontsize=11)
ax.legend(fontsize=8)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{FIG}/fig_uncertainty_week.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- Figure 3: hold-out replay distribution ----------------
fig, ax = plt.subplots(figsize=(8, 4.0), dpi=300)
ax.hist(hold.replay_p, bins=24, color="#1f77b4", alpha=0.85, edgecolor="white")
ax.axvline(hold.replay_p.mean(), color="#d62728", lw=1.5,
           label=f"mean = {hold.replay_p.mean():.3f}")
ax.axvline(hold.replay_p.median(), color="#2ca02c", lw=1.5, ls="--",
           label=f"median = {hold.replay_p.median():.3f}")
ax.set_xlabel("prior-only probability that the observed elimination is replayed")
ax.set_ylabel("# elimination-weeks")
ax.set_title("Hold-out validation: prior-only replay probability (232 weeks)", fontsize=11)
ax.legend(fontsize=9)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{FIG}/fig_holdout_calibration.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- Figure 4: S27 Bobby Bones case study ----------------
fig, ax = plt.subplots(figsize=(8, 4.6), dpi=300)
d = post[post.season == 27].groupby("celebrity").agg(
    js=("judge_share", "mean"), fs=("fan_mean", "mean"),
    flo=("fan_lo", "mean"), fhi=("fan_hi", "mean")).reset_index().sort_values("fs")
y = np.arange(len(d))
blue, red = "#1f77b4", "#d62728"
ax.hlines(y, d.flo, d.fhi,
          color=[red if c == "Bobby Bones" else blue for c in d.celebrity],
          lw=2.4, alpha=0.8)
ax.plot(d.loc[d.celebrity != "Bobby Bones", "fs"],
        y[d.celebrity != "Bobby Bones"], "o", color=blue, ms=5, label="other S27 cast")
ax.plot(d.loc[d.celebrity == "Bobby Bones", "fs"],
        y[d.celebrity == "Bobby Bones"], "o", color=red, ms=6, label="Bobby Bones (winner)")
ax.set_yticks(y)
ax.set_yticklabels(d.celebrity, fontsize=8)
ax.set_xlabel("season-average fan-vote share (lines = 95% credible intervals)")
ax.set_title("Season 27: inferred fan support vs. judge scores (red = winner)", fontsize=11)
ax.legend(fontsize=8, loc="lower right")
ax.grid(axis="x", alpha=0.3)
fig.tight_layout()
fig.savefig(f"{FIG}/fig_s27_case.png", dpi=300, bbox_inches="tight")
plt.close(fig)

print("figures saved:", sorted(os.listdir(FIG)))
