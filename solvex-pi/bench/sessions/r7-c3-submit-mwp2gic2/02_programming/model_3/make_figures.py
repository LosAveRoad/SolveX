#!/usr/bin/env python3
"""Figures for Model 3 (F7-F10). Deterministic; reads only CSVs + results.json."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import json
from pathlib import Path

plt.rcParams["font.family"] = "serif"
HERE = Path(__file__).resolve().parent
FX = HERE / "figures"
FX.mkdir(exist_ok=True)
res = json.load(open(HERE / "results.json"))

# ---------------- F7: forest plot of trait effects, three channels ----------------
eff = pd.read_csv(HERE / "model3_covariate_effects.csv")
focal = ["age_cs", "ind_Athlete", "ind_Comedian", "ind_Model", "ind_TV_Personality",
         "ind_Other", "home_US", "home_UK_Ireland", "home_Other_Intl"]
lab = {"age_cs": "Age (per 13.3y)", "ind_Athlete": "Athlete", "ind_Comedian": "Comedian",
       "ind_Model": "Model", "ind_TV_Personality": "TV Personality",
       "ind_Other": "Other industry", "home_US": "Home: US",
       "home_UK_Ireland": "Home: UK/Ireland", "home_Other_Intl": "Home: other intl"}
fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.4), dpi=300, sharey=True)
ylabels = None
for ax, chan, ttl in zip(
        axes, ["judge", "fan", "differential"],
        ["Judge channel (S, points)", "Fan channel (logit of share)",
         "Differential R = z(S) - z(phi)"]):
    sub_c = eff[eff["channel"] == chan]
    sub = sub_c.set_index("covariate").reindex(focal).dropna(how="all")
    # keep everything that exists in this channel
    y = np.arange(len(sub))[::-1]
    colors = ["#b91c1c" if p < 0.05 else "#9ca3af" for p in sub["p"]]
    lo = (sub["coef"] - sub["ci_low"]).to_numpy()
    hi = (sub["ci_high"] - sub["coef"]).to_numpy()
    for j in range(len(sub)):
        ax.errorbar(sub["coef"].to_numpy()[j], y[j], xerr=[[lo[j]], [hi[j]]],
                    fmt="o", color="black", ecolor=colors[j], elinewidth=2.2,
                    capsize=3, markersize=5)
    ax.axvline(0, ls="--", lw=1, color="#4b5563")
    labs = [lab.get(c, c) for c in sub.index]
    if chan == "judge":
        ylabels = labs
        ax.set_yticks(y)
        ax.set_yticklabels(labs, fontsize=9)
    else:
        ax.set_yticks(y)
    ax.set_title(ttl, fontsize=10.5)
    ax.set_xlabel("effect on the channel")
fig.suptitle("F7: covariate effects on the judges' vs fans' channel "
             "(95% CI; red = significant at 5%)", fontsize=12.5)
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(FX / "F7_forest_effects.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- F8: archetype survival curves ----------------
arc = pd.read_csv(HERE / "model3_archetypes.csv")
fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
cmap = plt.get_cmap("viridis")
weeks = np.arange(1, 11)
for i, (_, r) in enumerate(arc.iterrows()):
    surv = np.array([r[f"surv_week_{w}"] for w in weeks])
    ax.plot(weeks, surv, "-o", ms=3.5, lw=1.8, color=cmap(i / len(arc)),
            label=f"{r['archetype']} (age {int(r['age'])})")
ax.set_xlabel("week in the season")
ax.set_ylabel("median estimated survival probability")
ax.set_title("F8: counterfactual-cast survival (400 Cox-\\u03b2 draws, D4 model)",
             fontsize=12)
ax.legend(fontsize=8, loc="lower left")
ax.set_ylim(-0.02, 1.03)
ax.grid(alpha=0.25)
fig.savefig(FX / "F8_archetype_survival.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- F9: over/under-rating by industry (heatmap + raw gap) ---------
ind = pd.read_csv(HERE / "model3_industry_differential.csv")
ind = ind[ind["size"] >= 8].sort_values("mean")
fig, ax = plt.subplots(figsize=(9.5, 6.5), dpi=300)
vals = ind["mean"].to_numpy()
im = ax.imshow(vals.reshape(-1, 1), aspect="auto", cmap="RdYlGn_r",
               vmin=-0.8, vmax=0.8)
ax.set_yticks(range(len(ind)))
ax.set_yticklabels([f"{n}  (n_wk={s})" for n, s in zip(ind["celebrity_industry"],
                                                       ind["size"])], fontsize=9)
ax.set_xticks([])
for i, v in enumerate(vals):
    ax.annotate(f"{v:+.3f}", (0.5, i), ha="center", va="center", fontsize=9,
                color="black" if abs(v) < 0.55 else "white")
cb = fig.colorbar(im, ax=ax, shrink=0.7)
cb.set_label("mean R = z(judge score) - z(fan share)  (>0 = fans like them LESS "
             "than judges)")
ax.set_title("F9: fans' over/under-rating vs judges, by industry", fontsize=12)
fig.savefig(FX / "F9_industry_differential.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- F10: partner strip plot (mean judge score vs fan share) -------
part = pd.read_csv(HERE / "model3_partner_summary.csv")
part = part.sort_values("mean_S", ascending=False)
fig, ax = plt.subplots(figsize=(10, 6.5), dpi=300)
x = np.arange(len(part))
sc = ax.scatter(x, part["mean_S"], c=part["mean_phi"], cmap="plasma", s=60,
                edgecolor="k", linewidth=0.4)
ax.set_xticks(x)
ax.set_xticklabels(part["p_g"], rotation=60, ha="right", fontsize=8)
ax.set_ylabel("mean weekly judge score S")
cb = fig.colorbar(sc, ax=ax, shrink=0.8)
cb.set_label("mean estimated fan share \\u03c6\u0302")
ax.set_title("F10: partner effects on judges (y) and fans (color)", fontsize=12)
ax.grid(alpha=0.2, axis="y")
fig.savefig(FX / "F10_partner_effects.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------- F11: fan-vote certainty by week (from weekly panel) ------------
pan = pd.read_csv(HERE / "model3_weekly_panel.csv")
g = pan.groupby(["season", "week"]).apply(
    lambda d: pd.Series({"width": (d["phi_hi90"] - d["phi_lo90"]).mean()}),
    include_groups=False).reset_index()
fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=300)
wk_mean = g.groupby("week")["width"].mean()
wk_p90 = g.groupby("week")["width"].quantile(0.9)
ax.plot(wk_mean.index, wk_mean.values, "-o", label="mean 90% interval width")
ax.plot(wk_p90.index, wk_p90.values, "--s", label="90th percentile width")
ax.set_xlabel("week in the season")
ax.set_ylabel("width of the 90% φ̂ interval (fan-vote share units)")
ax.set_title("F11: fan-vote certainty by week (widest in deeper weeks = fewer "
             "surviving couples)", fontsize=11.5)
ax.legend()
ax.grid(alpha=0.25)
fig.savefig(FX / "F11_certainty_by_week.png", dpi=300, bbox_inches="tight")
plt.close(fig)

print("figures written:", sorted(p.name for p in FX.glob('*.png')))
