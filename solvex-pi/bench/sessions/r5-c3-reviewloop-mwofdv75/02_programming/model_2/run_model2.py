"""
Model 2 — full analysis run (rev 2): counterfactual replay with genuine
per-week hit rates (bottom-k pick for elimination weeks, top pick = winner
for finale weeks), discriminating permutation test, fan-favour index on a
consistent standing vector, controversy case studies.

Writes CSVs to model_2/ and figures to model_2/figures/, prints key numbers.
"""
import csv, json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import engine as eng
from rules import RULES_MC, dense_ranks_desc

plt.rcParams["font.family"] = "serif"
FIG = "./figures"
os.makedirs(FIG, exist_ok=True)

N_DRAW = 2000
seasons = eng.load_seasons()


def act_mask(d):
    return eng.weekly_active_mask(d["Jmat"])


def Jcum_arr(d):
    # cumulative judge points; NaN (post-elimination) -> 0
    return np.cumsum(np.nan_to_num(d["Jmat"], nan=0.0), axis=1)


def week_hit(d, w, rule, Vcum, beta=0.5):
    """P(observed week-w outcome reproduced) among truly-active couples.
    Vcum: (draws, n, W) cumulative fan votes.
      - elimination week (k < m): rule's bottom-k set must equal the
        observed eliminee(s).
      - finale week (k == m): rule's TOP pick must equal the winner
        (smallest placement among the finalists)."""
    elim = d["elim_by_week"][w]
    k = len(elim)
    ia = np.where(act_mask(d)[:, w - 1])[0]
    m = len(ia)
    Jc = Jcum_arr(d)[ia, w - 1]
    pts = RULES_MC[rule](Jc[None, :], Vcum[:, ia, w - 1], beta=beta)
    order = np.argsort(pts, axis=1, kind="stable")
    if k >= m:                                    # finale week
        win_i = min(elim, key=lambda i: d["active"][i]["placement"])
        hit = order[:, -1] == ia.tolist().index(win_i)
    else:                                         # elimination week
        obs = np.array(sorted(elim))
        bottom = np.sort(order[:, :k], axis=1)
        hit = (bottom == obs[None, :]).all(axis=1)
    return float(np.mean(hit))


def week_flip(d, w, Vcum, beta=0.5):
    """P(RANK bottom-(top) pick != PERCENT pick) at week w; same finale
    convention (finale: rank of the winner)."""
    ia = np.where(act_mask(d)[:, w - 1])[0]
    m = len(ia)
    k = len(d["elim_by_week"][w])
    Jc = Jcum_arr(d)[ia, w - 1]
    oR = np.argsort(RULES_MC["RANK"](Jc[None, :], Vcum[:, ia, w - 1]), axis=1, kind="stable")
    oP = np.argsort(RULES_MC["PERCENT"](Jc[None, :], Vcum[:, ia, w - 1]), axis=1, kind="stable")
    if k >= m:                                    # finale: compare winner
        win_i = min(d["elim_by_week"][w], key=lambda i: d["active"][i]["placement"])
        posR = (oR[:, ::-1] == ia.tolist().index(win_i)).nonzero()[1]
        posP = (oP[:, ::-1] == ia.tolist().index(win_i)).nonzero()[1]
        return float(np.mean(posR != posP))
    return float(np.mean(oR[:, 0] != oP[:, 0]))


def week_veto(d, w, Vcum, base="RANK"):
    """P(judges' score-veto changes the bottom pick) at week w under base
    rule (eliminate the lower-judged member of the bottom two)."""
    ia = np.where(act_mask(d)[:, w - 1])[0]
    Jc = Jcum_arr(d)[ia, w - 1]
    o = np.argsort(RULES_MC[base](Jc[None, :], Vcum[:, ia, w - 1]), axis=1, kind="stable")
    Jb1, Jb2 = Jc[o[:, 0]], Jc[o[:, 1]]
    go = np.where(Jb1 <= Jb2, o[:, 0], o[:, 1])
    return float(np.mean(go != o[:, 0]))


season_rows, ff_rows, perm_rows, cont_rows = [], [], [], []

for s, d in sorted(seasons.items()):
    v_draws, Vcum, P = eng.sample_posterior(s, d, N_DRAW)
    rule = eng.season_rule(s)
    n, W = d["n"], d["W"]
    elims = sorted(d["elim_by_week"])
    A = act_mask(d)
    last_w = np.array([np.where(A[i])[0].max() + 1 for i in range(n)])
    JcumA = Jcum_arr(d)
    Jtot = JcumA[np.arange(n), last_w - 1]
    Vcum_mean = Vcum.mean(axis=0)                 # (n, W) posterior mean cum.
    Vtot = Vcum_mean[np.arange(n), last_w - 1]    # season fan-vote totals

    hit_md, hit_dr, flip_pw, veto_pw = [], [], [], []
    for w in elims:
        hit_md.append(week_hit(d, w, rule, Vcum_mean[None, :, :]))
        hit_dr.append(week_hit(d, w, rule, Vcum))
        flip_pw.append(week_flip(d, w, Vcum))
        veto_pw.append(week_veto(d, w, Vcum))
    flip_pw = np.array(flip_pw)
    season_rows.append(dict(
        season=s, rule=rule, n=n, n_elim_weeks=len(elims),
        hit_mode=round(float(np.mean(hit_md)), 4),
        hit_draw=round(float(np.mean(hit_dr)), 4),
        flip_prob_mean=round(float(flip_pw.mean()), 4),
        veto_flip_prob_mean=round(float(np.mean(veto_pw)), 4),
        sum_flip_prob=round(float(flip_pw.sum()), 4)))

    # ---- fan-favour index: -corr(rank(J), standing under rule A), where
    # standing under rule A = rank of cumulative combined points
    # (winner = rank 1 direction consistently applied) ----
    rJ = dense_ranks_desc(Jtot)
    def ff_index(stand_score):
        return float(-np.corrcoef(rJ, dense_ranks_desc(stand_score))[0, 1])
    ptsR = RULES_MC["RANK"](Jtot, Vtot, beta=0.5)
    ptsP = RULES_MC["PERCENT"](Jtot, Vtot, beta=0.5)
    place_obs = np.array([x["placement"] for x in d["active"]], float)
    ff_rows.append(dict(
        season=s,
        corr_J_placement=round(float(np.corrcoef(rJ, place_obs)[0, 1]), 3),
        corr_J_fantot=round(float(np.corrcoef(rJ, dense_ranks_desc(Vtot))[0, 1]), 3),
        fanfavor_RANK=round(ff_index(-ptsR), 3),   # -pts: larger = better standing
        fanfavor_PERCENT=round(ff_index(-ptsP), 3)))

    # ---- permutation test (shuffles fan cumulative totals within week) ----
    rng = np.random.default_rng(7)
    hit_true, hit_perm = [], []
    for w in elims:
        elim = d["elim_by_week"][w]
        k = len(elim)
        ia = np.where(act_mask(d)[:, w - 1])[0]
        m = len(ia)
        Jc = Jcum_arr(d)[ia, w - 1]
        Vc = Vcum_mean[ia, w - 1]
        if k >= m:
            win_i = min(elim, key=lambda i: d["active"][i]["placement"])
            loc = ia.tolist().index(win_i)
            def top_hit(V):
                o = np.argsort(RULES_MC[rule](Jc[None, :], V[None, :])[0], kind="stable")
                return int(o[-1] == loc)
        else:
            obs = np.array(sorted(elim))
            def top_hit(V):
                o = np.argsort(RULES_MC[rule](Jc[None, :], V[None, :])[0], kind="stable")
                return int(set(o[:k].tolist()) == set(obs.tolist()))
        hit_true.append(top_hit(Vc))
        ph = [top_hit(rng.permutation(Vc)) for _ in range(200)]
        hit_perm.append(float(np.mean(ph)))
    perm_rows.append(dict(season=s, hit_true=round(float(np.mean(hit_true)), 4),
                          hit_permuted=round(float(np.mean(hit_perm)), 4)))

# ---- controversy case studies ----
CASES = [("Jerry Rice", 2), ("Billy Ray Cyrus", 4), ("Bristol Palin", 11),
         ("Bobby Bones", 27)]
for cname, s in CASES:
    d = seasons[s]
    v_draws, Vcum, P = eng.sample_posterior(s, d, N_DRAW)
    Vcum_mean = Vcum.mean(axis=0)
    rec = [x for x in d["active"] if x["name"] == cname][0]
    gi = d["active"].index(rec)
    w = rec["wlast"]
    ia = np.where(act_mask(d)[:, w - 1])[0]
    loc = ia.tolist().index(gi)
    Jc = Jcum_arr(d)[ia, w - 1]
    out = dict(celebrity=cname, season=s, wlast=w,
               observed_placement=rec["placement"], n_active_week=len(ia))
    for rname in ("RANK", "PERCENT"):
        pts = RULES_MC[rname](Jc[None, :], Vcum[:, ia, w - 1])
        order = np.argsort(pts, axis=1, kind="stable")
        pos = (order == loc).nonzero()[1]
        b1, b2 = order[:, 0], order[:, 1]
        go = np.where(Jc[b1] <= Jc[b2], b1, b2)
        out[f"mean_pos_{rname}"] = round(float(pos.mean() + 1), 2)
        out[f"Pr_bottom1_{rname}"] = round(float(np.mean(pos == 0)), 3)
        out[f"Pr_bottom2_{rname}"] = round(float(np.mean(pos <= 1)), 3)
        out[f"Pr_vetosaves_{rname}"] = round(float(np.mean((b1 == loc) & (go != loc))), 3)
    out["fan_cumshare_wlast"] = round(float(Vcum_mean[gi, w - 1]
                                            / Vcum_mean[ia, w - 1].sum()), 4)
    out["judge_cumshare_wlast"] = round(float(Jc[loc] / Jc.sum()), 4)
    out["fan_judge_gap"] = round(out["fan_cumshare_wlast"] - out["judge_cumshare_wlast"], 3)
    cont_rows.append(out)

# ---- figures ----
ss = [r["season"] for r in season_rows]
fp = [r["flip_prob_mean"] for r in season_rows]
vp = [r["veto_flip_prob_mean"] for r in season_rows]
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar([x - 0.2 for x in ss], fp, width=0.4, label="RANK vs PERCENT flip prob.")
ax.bar([x + 0.2 for x in ss], vp, width=0.4, color="tab:red",
       label="Judges-veto changes bottom pick (prob.)")
ax.set_xlabel("Season"); ax.set_ylabel("Weekly probability")
ax.set_title("Probability the aggregation rule changes the elimination decision\n(2000 posterior fan-vote draws, all scored weeks)")
ax.legend(); ax.grid(axis="y", alpha=.3)
fig.savefig(f"{FIG}/fig1_flip_rates.png", dpi=300, bbox_inches="tight")
plt.close(fig)

labels = [f"S{r['season']}\n{r['celebrity'].split()[0]}" for r in cont_rows]
x = np.arange(len(cont_rows))
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(x - 0.2, [r["Pr_bottom1_RANK"] for r in cont_rows], 0.4, label="Pr(=bottom pick) RANK")
ax.bar(x + 0.2, [r["Pr_bottom1_PERCENT"] for r in cont_rows], 0.4, label="Pr(=bottom pick) PERCENT")
ax.plot(x, [r["Pr_vetosaves_RANK"] for r in cont_rows], "o--", color="k",
        label="Pr(judges' veto saves) RANK")
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_ylabel("Posterior probability (2000 draws)")
ax.set_title("Controversy case studies: elimination risk under each rule\n(celebrity's final scored week, truly active couples)")
ax.legend(); ax.grid(axis="y", alpha=.3)
fig.savefig(f"{FIG}/fig2_controversies.png", dpi=300, bbox_inches="tight")
plt.close(fig)

fr = [r["fanfavor_RANK"] for r in ff_rows]
fpq = [r["fanfavor_PERCENT"] for r in ff_rows]
n_above = sum(p > r for r, p in zip(fr, fpq))
fig, ax = plt.subplots(figsize=(9, 5))
ax.scatter(fr, fpq)
lim = [min(fr + fpq) - .05, max(fr + fpq) + .05]
ax.plot(lim, lim, "k--", lw=1)
ax.set_xlabel("Fan-favour index under RANK  (= -corr(judge rank, standing))")
ax.set_ylabel("Fan-favour index under PERCENT")
ax.set_title(f"Fan-favour index by season: RANK vs PERCENT\n(PERCENT above diagonal in {n_above}/{len(fr)} seasons)")
ax.grid(alpha=.3)
fig.savefig(f"{FIG}/fig3_fanfavor_index.png", dpi=300, bbox_inches="tight")
plt.close(fig)


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wtr.writeheader(); wtr.writerows(rows)


write_csv("rule_flip_stats.csv", season_rows)
write_csv("controversy_case_studies.csv", cont_rows)
write_csv("fan_favor_index.csv", ff_rows)
write_csv("validation_permutation.csv", perm_rows)

n_sample_rows = 0
with open("posterior_fan_shares_sample.csv", "w", newline="") as f:
    f.write("season,week,celebrity,mean_share,judge_points\n")
    for s in (2, 27):
        d = seasons[s]
        A = act_mask(d)
        JcumA = Jcum_arr(d)
        vd, _, _ = eng.sample_posterior(s, d, N_DRAW)
        Vmode = vd.mean(axis=0)
        for w in range(1, d["W"] + 1):
            for i, rec in enumerate(d["active"]):
                if A[i, w - 1]:
                    f.write(f"{s},{w},{rec['name']},{Vmode[i, w-1]:.6f},"
                            f"{JcumA[i, w-1]:.1f}\n")
                    n_sample_rows += 1

mean_hit_mode = float(np.mean([r["hit_mode"] for r in season_rows]))
mean_hit_draw = float(np.mean([r["hit_draw"] for r in season_rows]))
mean_flip = float(np.mean(fp))
mean_veto = float(np.mean(vp))
zero_flip = sum(1 for r in season_rows if r["sum_flip_prob"] < 1e-12)
mean_ffR = float(np.mean(fr)); mean_ffP = float(np.mean(fpq))
n_ffP_gt = n_above
tru = float(np.mean([r["hit_true"] for r in perm_rows]))
prm = float(np.mean([r["hit_permuted"] for r in perm_rows]))
print(f"hit (mode/draws): {mean_hit_mode:.4f} / {mean_hit_draw:.4f}")
print(f"mean flip: {mean_flip:.4f} | veto flip: {mean_veto:.4f} | zero-flip seasons: {zero_flip}/34")
print(f"fan-favour: RANK {mean_ffR:.3f} vs PERCENT {mean_ffP:.3f} (PERCENT higher in {n_ffP_gt}/34)")
print(f"permutation: true {tru:.4f} vs shuffled {prm:.4f}")
print(f"sample rows: {n_sample_rows}")
json.dump(dict(status="ok", n_seasons=len(season_rows),
               mean_hit_mode=round(mean_hit_mode, 4),
               mean_hit_draws=round(mean_hit_draw, 4),
               mean_flip_prob=round(mean_flip, 4),
               mean_veto_flip=round(mean_veto, 4),
               zero_flip_seasons=zero_flip,
               mean_fanfavor_RANK=round(mean_ffR, 4),
               mean_fanfavor_PERCENT=round(mean_ffP, 4),
               n_seasons_PERCENT_favor_more=n_ffP_gt,
               perm_true=round(tru, 4), perm_shuffled=round(prm, 4),
               sample_csv_rows=n_sample_rows),
          open("run_stats.json", "w"), indent=1)
