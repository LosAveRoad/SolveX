"""Model 1 figures (F1-F5). Publication style, Agg backend, dpi 300."""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from model1_run import pipeline, SHARED, HERE

plt.rcParams["font.family"] = "serif"
FIGDIR = HERE / "figures"


def main():
    FIGDIR.mkdir(exist_ok=True)
    res = pipeline(verbose=False)
    M = res["M"]
    fan = pd.read_csv(HERE / "model1_fanshare.csv") if (HERE / "model1_fanshare.csv").exists() else None

    # F1 heatmap: mean phi by season x week
    piv = fan.pivot_table(index="season", columns="week", values="phi_share", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    im = ax.imshow(piv.values, aspect="auto", cmap="viridis", vmin=0, vmax=0.4)
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels(piv.index, fontsize=6)
    ax.set_xlabel("Week within season")
    ax.set_ylabel("Season")
    ax.set_title("Model 1 mean fan-vote share $\\hat\\phi$ by season and week")
    fig.colorbar(im, ax=ax, label="Mean share (renormalized)")
    fig.savefig(FIGDIR / "F1_phats_heatmap.png", bbox_inches="tight")
    plt.close(fig)

    # F2 Jerry Rice posterior violin (season 2, weeks 1..8)
    cells = np.where((M.season_of_flat == 1) & (M.week_of_flat <= 8))[0]
    names = [M.run_name[M.run_of_flat[c]] for c in cells]
    jerry = [c for c in cells if M.run_name[M.run_of_flat[c]] == "Jerry Rice"]
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    keep = res["keep_idx"]
    data, labels = [], []
    for c in cells:
        col = res["ren_draw"][keep, c]
        data.append(col)
        labels.append(f"w{M.week_of_flat[c]}\n{M.run_name[M.run_of_flat[c]].split()[0]}")
    vp = ax.violinplot(data, showmedians=True)
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, fontsize=7)
    for i, c in enumerate(cells):
        if c in jerry:
            vp["bodies"][i].set_facecolor("crimson")
            vp["bodies"][i].set_alpha(0.8)
    ax.set_ylabel("Posterior fan-vote share $\\phi$")
    ax.set_title("Season 2 weeks 1-8: posterior shares (Jerry Rice in red)")
    fig.savefig(FIGDIR / "F2_jerry_rice_violin.png", bbox_inches="tight")
    plt.close(fig)

    # F3 calibration: per-week capture prob, model vs judge-only, sorted
    ef = pd.read_csv(HERE / "model1_exitfit.csv")
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    s = ef[ef.veto_regime == 0].sort_values("p_capture")
    ax.plot(np.arange(len(s)) / len(s), s.p_capture, label="Model 1 posterior", lw=2)
    sj = ef[ef.veto_regime == 0].sort_values("p_capture_judge")
    ax.plot(np.arange(len(sj)) / len(sj), sj.p_capture_judge, label="Judge-only", lw=2, ls="--")
    ax.axhline(s.p_capture_uniform.mean(), color="gray", ls=":", label="Uniform baseline (mean)")
    ax.set_xlabel("Cumulative fraction of exact-regime exit weeks")
    ax.set_ylabel("Posterior probability of the observed exit set")
    ax.set_title("Exit-recovery probability: model vs judge-only")
    ax.legend()
    fig.savefig(FIGDIR / "F3_calibration.png", bbox_inches="tight")
    plt.close(fig)

    # F4 CV by week number
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    wks = sorted(fan.week.unique())
    box = [fan[fan.week == w].phi_cv.values for w in wks]
    ax.boxplot(box, tick_labels=[int(w) for w in wks], showfliers=False)
    ax.set_xlabel("Week within season")
    ax.set_ylabel("CV of $\\hat\\phi$ (sd/mean)")
    ax.set_title("Posterior certainty by week: early weeks more uncertain")
    fig.savefig(FIGDIR / "F4_cv_by_week.png", bbox_inches="tight")
    plt.close(fig)

    # F5 recovered phi vs judge z (the correlation actually plotted here)
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    zj = M.zsc
    ph = res["rmean"]
    sel = np.arange(M.V)  # all cells
    ax.scatter(zj[sel], ph[sel], s=4, alpha=0.25, color="steelblue")
    # r as plotted: phi_hat vs within-week judge z-score
    r_z = float(np.corrcoef(zj[sel], ph[sel])[0, 1])
    # separate, explicitly-labeled statistic: phi_hat vs weekly judge SHARE
    # (read from the written deliverable CSV so the number matches the table)
    r_share = float(np.corrcoef(fan.phi_share.to_numpy(),
                                fan.judge_share.to_numpy())[0, 1])
    ax.set_xlabel("Judge z-score within week")
    ax.set_ylabel("Mean fan-vote share $\\hat\\phi$")
    ax.set_title(f"Fans vs judges: $\\hat\\phi$ against judge z (Pearson r={r_z:.4f})")
    fig.savefig(FIGDIR / "F5_phi_vs_judge_z.png", bbox_inches="tight")
    plt.close(fig)
    print("figures written to", FIGDIR)
    return dict(r_phi_vs_judgez=r_z, r_phi_vs_judgeshare=r_share)


if __name__ == "__main__":
    main()
