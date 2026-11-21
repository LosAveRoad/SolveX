"""Figures for Model 1 (ME-FVI), REVISED. Reads the CSVs produced by me_fvi.py."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

plt.rcParams["font.family"] = "serif"
HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

est = pd.read_csv(os.path.join(HERE, "fan_votes_estimates.csv"))
wk = pd.read_csv(os.path.join(HERE, "weekly_certainty.csv"))
nul = pd.read_csv(os.path.join(HERE, "null_model_pvalues.csv"))
cap = pd.read_csv(os.path.join(HERE, "kappa_capped_weeks.csv"))
pct = est[est.rule == "pct"].copy()
pct["halfwidth"] = (pct.fan_share_hi95 - pct.fan_share_lo95) / 2

# --- Fig 1: certainty by week (pct rule)
g = pct.groupby("week").agg(hw_mean=("halfwidth", "mean"),
                            hw_q25=("halfwidth", lambda x: x.quantile(0.25)),
                            hw_q75=("halfwidth", lambda x: x.quantile(0.75))).reset_index()
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.plot(g.week, g.hw_mean, "o-", color="#1f4e79", lw=2, label="mean 90% interval half-width")
ax.fill_between(g.week, g.hw_q25, g.hw_q75, alpha=0.25, color="#1f4e79",
                label="interquartile range")
ax.set_xlabel("Week number"); ax.set_ylabel("90% interval half-width (fan-vote share)")
ax.set_title("Certainty of ME-FVI fan-vote estimates by competition week\n"
             "(percentage rule; 90% Dirichlet-bootstrap predictive intervals)")
ax.legend(); ax.grid(alpha=0.3)
fig.savefig(os.path.join(FIG, "fig1_certainty_by_week.png"), bbox_inches="tight"); plt.close(fig)

# --- Fig 2 (REVISED): judge-fan divergence heatmap, pct rule only, no rank claim
pivot = pct.pivot_table(index="season", columns="week",
                        values="gap_F_minus_J", aggfunc="mean")
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
im = ax.imshow(pivot.values, aspect="auto", cmap="RdBu_r", vmin=-0.08, vmax=0.08)
ax.set_xticks(range(pivot.shape[1]), pivot.columns)
ax.set_yticks(range(0, pivot.shape[0], 3), pivot.index[::3])
ax.set_xlabel("Week"); ax.set_ylabel("Season")
ax.set_title("Judge-fan divergence  F$^*$ - J  (percentage rule)\n"
             "red = fans outrank judges ('entertainment gap')")
fig.colorbar(im, ax=ax, label="fan share minus judge share")
fig.savefig(os.path.join(FIG, "fig2_gap_heatmap.png"), bbox_inches="tight"); plt.close(fig)

# --- Fig 3: case studies (controversial contestants), pct rule
fig, axes = plt.subplots(2, 2, figsize=(8, 6), dpi=300)
for ax, (nm, (s, c)) in zip(axes.ravel(), [
        ("Jerry Rice (S2)", (2, "Jerry Rice")), ("Billy Ray Cyrus (S4)", (4, "Billy Ray Cyrus")),
        ("Bristol Palin (S11)", (11, "Bristol Palin")), ("Bobby Bones (S27)", (27, "Bobby Bones"))]):
    d = pct[(pct.season == s) & (pct.celebrity == c)].sort_values("week")
    ax.plot(d.week, d.judge_share_pct.astype(float), "s--", color="#c0392b", label="judge share")
    ax.plot(d.week, d.fan_share, "o-", color="#1f4e79", label="fan share (ME est.)")
    ax.fill_between(d.week, d.fan_share_lo95, d.fan_share_hi95, alpha=0.25, color="#1f4e79")
    ax.set_title(nm, fontsize=10); ax.grid(alpha=0.3)
axes[0, 0].legend(fontsize=8)
for ax in axes[1, :]: ax.set_xlabel("Week")
for ax in axes[:, 0]: ax.set_ylabel("Vote share")
fig.suptitle("Controversial contestants: judges vs inferred fans (percentage rule)", y=1.0)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig3_case_studies.png"), bbox_inches="tight"); plt.close(fig)

# --- Fig 4 (REVISED): gamma_max distribution with 1/n bound, band-width vs gamma_max,
#     and model-vs-null hit-rate validation
fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4), dpi=300)

ax = axes[0]
ax.hist(wk.gamma_max_pct, bins=30, color="#1f4e79", alpha=0.85,
        label="exact $\\gamma_{max}$ (LP)")
bound = 1.0 / (wk.n_couples - wk.n_elim)
ax.scatter(wk.n_couples - wk.n_elim, wk.gamma_max_pct, s=8, color="#c0392b", zorder=3,
           label="per-week theoretical bound $1/n_{surv}$")
for nsv in sorted(np.unique(wk.n_couples - wk.n_elim)):
    ax.axvline(0, 0, 0)   # placeholder to keep legend simple
ax.set_xlabel(r"$\gamma_{max}$ (pct rule)"); ax.set_ylabel("number of season-weeks")
ax.set_title(r"Elimination slack $\gamma_{max}$: exact LP values" "\n"
             r"all satisfy $\gamma_{max} \leq 1/n_{survivors}$")
ax.legend(fontsize=8); ax.grid(alpha=0.3)

ax = axes[1]
corr = np.corrcoef(pct.groupby(["season", "week"]).halfwidth.mean().values,
                   wk.set_index(["season", "week"]).gamma_max_pct.values)[0, 1]
ax.scatter(wk.gamma_max_pct, pct.groupby(["season", "week"]).halfwidth.mean(), s=12,
           alpha=0.65, color="#1f4e79")
ax.set_xlabel(r"$\gamma_{max}$"); ax.set_ylabel("mean 90% band half-width (share)")
ax.set_title("Certainty vs elimination slack\n" + f"Pearson r = {corr:.2f}")
ax.grid(alpha=0.3)

ax = axes[2]
ax.hist(nul.null_hit_rate, bins=25, alpha=0.6, color="#c0392b",
        label=f"null (uniform-Dirichlet), mean {nul.null_hit_rate.mean():.2f}")
ax.hist(wk.hit_rate_pct, bins=25, alpha=0.6, color="#2e7d32",
        label=f"calibrated ME-FVI, mean {wk.hit_rate_pct.mean():.2f}")
ax.set_xlabel("share of draws reproducing the recorded elimination")
ax.set_ylabel("number of season-weeks")
ax.set_title(f"Model vs null consistency\n({(nul.binom_p_value_model_vs_null < 0.01).sum()}/264 weeks p < 0.01)")
ax.legend(fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig4_calibration.png"), bbox_inches="tight"); plt.close(fig)

print("figures:", sorted(os.listdir(FIG)))
