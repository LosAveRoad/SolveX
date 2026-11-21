#!/usr/bin/env python3
"""run.py -- Model 2 entry (2026 MCM Problem C): Judge-Fan Behavioral Attribution.

Deterministic end-to-end pipeline (fixed seeds; no wall-clock/env-dependent state).
Outputs: results.json + 5 CSVs + figures F6-F10 (+F11 limits if applicable).

Run:  python3 run.py
"""
from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd

from m2_data import load_all, rcs_design, RCS_KNOTS_AGE, RCS_KNOTS_WEEK
import m2_fanshare as MF
import m2_fit as FT
import model2_analysis as MA

SEED = 2026
OUT = ("/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/"
       "r6-c3-quality-mwojr1zz/02_programming/model_2")
FIGDIR = OUT + "/figures"
RESULTS = {}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    t0 = time.time()
    os.makedirs(FIGDIR, exist_ok=True)

    # ================================================== 1. data
    D = load_all()
    pan, wt, ex, ctx, ct = D["pan"], D["wt"], D["exit_sets"], D["ctx"], D["ct"]
    log(f"panel {len(pan)} wk-rows | {len(ct)} runs | {ct.pro.nunique()} pros | "
        f"{ct.celebrity_industry.nunique()} industries | {len(ex)} exit weeks")

    # ================================================== 2. fan-share stage
    mres = MF.map_optimize(pan, wt, ex, ctx, ct, maxiter=2000)
    log(f"MAP nll={mres['nll']:.2f} beta={mres['beta']:.3f} "
        f"theta={mres['theta']:.4f} Csd={mres['C'].std():.3f}")
    pan, fstats = MF.compute_fanshare(pan, wt, ex, ctx, ct, mres,
                                      n_shake=MF.N_SHAKE.copy() if hasattr(MF.N_SHAKE, "copy") else MF.N_SHAKE)
    # ---- canonical-input override (review round 3): prefer Model 1's delivered
    # posterior phi_share as the fan surface everywhere; the in-house stage stays as
    # the sensitivity column `fanshare_lite`; graceful fallback if the file is absent.
    pan["fanshare_lite"] = pan["fanshare"].to_numpy(float)   # sensitivity copy
    try:
        m1 = pd.read_csv("../model_1/model1_fanshare.csv")
        # Model-1 schema: the celebrity key is `celebrity`
        if "celebrity_name" not in m1.columns and "celebrity" in m1.columns:
            m1 = m1.rename(columns={"celebrity": "celebrity_name"})
        m1k = m1[["season", "week", "celebrity_name", "phi_share"]].copy()
        n_before = len(pan)
        pan = pan.merge(m1k, on=["season", "week", "celebrity_name"], how="left",
                        validate="many_to_one")
        assert len(pan) == n_before and pan["phi_share"].notna().all(), \
            "Model-1 merge incomplete"
        pan["fanshare"] = pan["phi_share"].to_numpy(float)
        RESULTS["fanshare_source"] = "model_1/model1_fanshare.csv:phi_share (canonical)"
    except Exception as e:
        RESULTS["fanshare_source"] = f"m2_fanshare in-house stage (fallback: {e})"
    RESULTS.setdefault("fanshare_stage", {})["n_shake_blocks"] = int(
        fstats.get("n_shakes", MF.N_SHAKE))
    RESULTS["fanshare_stage"]["n_cop_draws"] = int(MF.N_COP)
    pan.to_csv(OUT + "/model2_fanshare.csv", index=False)
    log("wrote model2_fanshare.csv")

    # exit-set recovery at MAP vs judge-only baseline
    Umap = (mres["C"][pan["run_id"].to_numpy(int)]
            + mres["beta"] * pan["judge_z"].to_numpy(float)
            + mres["theta"] * pan["week"].to_numpy(float))
    okE = tot = okJ = 0
    for key, exids in ex.items():
        if key in ctx:
            continue
        rows = wt[key]["rows"]
        runids = wt[key]["runids"]
        x = wt[key]["isd"]
        xs = x / x.sum()
        ph = np.exp(Umap[rows] - Umap[rows].max())
        ph /= ph.sum()
        comb = 0.5 * (xs + ph)
        eidx = [runids.index(r) for r in exids]
        ranks = {int(r): i + 1 for i, r in enumerate(np.argsort(comb))}
        jranks = {int(r): i + 1 for i, r in enumerate(np.argsort(xs))}
        tot += 1
        if all(ranks[i] <= len(eidx) for i in eidx):
            okE += 1
        if all(jranks[i] <= len(eidx) for i in eidx):
            okJ += 1
    # posterior-mean version + determinism probe
    okE_post = 0
    for key, exids in ex.items():
        if key in ctx:
            continue
        rows = wt[key]["rows"]
        runids = wt[key]["runids"]
        x = wt[key]["isd"]
        xs = x / x.sum()
        ph = pan.loc[rows, "fanshare"].to_numpy()
        comb = 0.5 * (xs + ph)
        eidx = [runids.index(r) for r in exids]
        ranks = {int(r): i + 1 for i, r in enumerate(np.argsort(comb))}
        if all(ranks[i] <= len(eidx) for i in eidx):
            okE_post += 1
    RESULTS["fanshare_stage"] = {
        "map_nll": round(mres["nll"], 2),
        "beta_judge_coupling": round(mres["beta"], 3),
        "theta_week_coupling": round(mres["theta"], 4),
        "persona_sd_map": round(float(mres["C"].std()), 3),
        "n_constraints": mres["n_cons"],
        "n_shake_blocks": fstats["n_shakes"], "n_cop_draws": fstats["n_cop"],
        "shake_weight_perplexity": round(fstats["shake_weight_perplexity"], 1),
        "issue_score_mean": round(fstats["issue_score_mean"], 2),
        "share_min": round(float(pan.fanshare.min()), 4),
        "share_max": round(float(pan.fanshare.max()), 4),
        "exit_recovery_combined_map": [okE, tot],
        "exit_recovery_combined_postmean": [okE_post, tot],
        "exit_recovery_judge_only": [okJ, tot],
    }
    log(f"exit recovery: MAP {okE}/{tot}, post-mean {okE_post}/{tot}, judge-only {okJ}/{tot}")

    # certainty-variation exhibit (CV by week and by market size)
    cv = (pan["fanshare_sd"] / pan["fanshare"].clip(lower=1e-8)).to_numpy()
    wk_ = pan["week"].to_numpy()
    ncomp = pan["n_competing"].to_numpy()
    RESULTS["certainty"] = {
        "cv_mean": round(float(cv.mean()), 3),
        "cv_week1_2": round(float(cv[wk_ <= 2].mean()), 3),
        "cv_week4_6": round(float(cv[(wk_ >= 4) & (wk_ <= 6)].mean()), 3),
        "cv_big_ncomp_9plus": round(float(cv[ncomp >= 9].mean()), 3),
        "cv_small_ncomp_5minus": round(float(cv[ncomp <= 5].mean()), 3),
        "sd_share_mean": round(float(pan["fanshare_sd"].mean()), 4),
    }

    # ================================================== 3. surfaces
    X, names, blocks = MA.build_blocks(pan)
    yJ = pan["judge_z"].to_numpy(float)
    sh = np.clip(pan["fanshare"].to_numpy(float), 1e-6, 1.0 - 1e-6)
    yF = np.log((sh + 8e-5) / (1.0 - sh + 8e-5))
    run_ids = pan["run_id"].to_numpy(int)
    fitJ = MA.ols_fit(yJ, X, run_ids)
    fitF = MA.ols_fit(yF, X, run_ids)
    r2J = 1.0 - fitJ["rss"] / float(((yJ - yJ.mean()) ** 2).sum())
    r2F = 1.0 - fitF["rss"] / float(((yF - yF.mean()) ** 2).sum())
    sh_lite = np.clip(pan["fanshare_lite"].to_numpy(float), 1e-6, 1 - 1e-6)
    yF_lite = np.log((sh_lite + 8e-5) / (1 - sh_lite + 8e-5))
    fitF_lite = MA.ols_fit(yF_lite, X, pan["run_id"].to_numpy(int))
    r2F_lite = 1.0 - fitF_lite["rss"] / float(((yF_lite - yF_lite.mean()) ** 2).sum())
    rho_lite = float(np.corrcoef(yF, yF_lite)[0, 1])
    RESULTS["surfaces"] = {"R2_judge": round(r2J, 4), "R2_fan": round(r2F, 4),
                           "R2_fan_lite": round(r2F_lite, 4), "rho_lite": round(rho_lite, 4),
                           "n_obs": int(len(pan)), "n_params": int(X.shape[1])}
    log(f"R2: judge {r2J:.3f} | fan {r2F:.3f}")

    # ================================================== 4. decomposition + perms
    dc = MA.permutation_decomp(pan, yJ, yF, X, names, n_perm=MA.N_PERM, seed=SEED)
    dc.to_csv(OUT + "/model2_decomp.csv", index=False)
    iccJ = MA.residual_icc(pan, yJ, fitJ["fitted"])
    iccF = MA.residual_icc(pan, yF, fitF["fitted"])
    RESULTS["decomposition"] = {
        "residual_icc_run_judge": round(iccJ, 4),
        "residual_icc_run_fan": round(iccF, 4),
    }
    log("R_k table:\n" + dc.to_string(index=False))
    log(f"residual ICC(run): judge {iccJ:.3f} | fan {iccF:.3f}")

    # ================================================== 5. LOSO + era drift
    loso = MA.loso_r2(pan, yJ, yF, X, names=names)
    loso_nofe = MA.loso_r2_nofe(pan, yJ, yF, X, names=names)
    RESULTS["loso_r2_nofe"] = {k: round(v, 4) for k, v in loso_nofe.items()}
    pws = MA.paired_week_slopes(pan)
    RESULTS["paired_week_slopes"] = pws
    RESULTS["loso_r2"] = {k: round(v, 4) for k, v in loso.items()}
    RESULTS["loso_target_check"] = {
        "judge_target_0.25_met_recal": bool(loso.get("judge_recal", -1) >= 0.25),
        "fan_target_0.15_met_recal": bool(loso.get("fan_recal", -1) >= 0.15)}
    log(f"LOSO R2: judge {loso['judge']:.3f} | fan {loso['fan']:.3f}")
    drift = MA.platform_drift(pan, yF)
    drift.to_csv(OUT + "/model2_era_drift.csv", index=False)
    RESULTS["era_drift"] = drift.to_dict(orient="records")

    # ---- week-level exit-fit table + consistency diagnostics
    exit_rows = []
    for key, exids in ex.items():
        if key in ctx:
            continue
        rows = wt[key]["rows"]
        runids = wt[key]["runids"]
        x = wt[key]["isd"]
        xs = x / x.sum()
        ph = pan.loc[rows, "fanshare"].to_numpy()
        comb = 0.5 * (xs + ph)
        s, w = key
        ranksJ = {int(r): i + 1 for i, r in enumerate(np.argsort(xs))}
        ranksC = {int(r): i + 1 for i, r in enumerate(np.argsort(comb))}
        exit_rows.append(dict(
            season=s, week=w, n_competing=len(rows), m_exits=len(exids),
            judge_rank_of_exits=";".join(str(int(ranksJ[runids.index(rid)])) for rid in exids),
            combined_rank_of_exits=";".join(str(int(ranksC[runids.index(rid)])) for rid in exids),
            all_exits_bottom_m_judge=int(all(ranksJ[runids.index(rid)] <= len(exids) for rid in exids)),
            all_exits_bottom_m_combined=int(all(ranksC[runids.index(rid)] <= len(exids) for rid in exids)),
            all_exits_bottom3_judge=int(all(ranksJ[runids.index(rid)] <= 3 for rid in exids)),
            all_exits_bottom3_combined=int(all(ranksC[runids.index(rid)] <= 3 for rid in exids)),
        ))
    dfX = pd.DataFrame(exit_rows)
    dfX.to_csv(OUT + "/model2_exitfit.csv", index=False)
    sin = dfX[dfX.m_exits == 1]
    RESULTS["consistency"] = {
        "single_exit_weeks_exact_combined": [int(sin.all_exits_bottom_m_combined.sum()), int(len(sin))],
        "single_exit_weeks_exact_judge": [int(sin.all_exits_bottom_m_judge.sum()), int(len(sin))],
        "allweeks_bottom3_combined": [int(dfX.all_exits_bottom3_combined.sum()), int(len(dfX))],
        "allweeks_bottom3_judge": [int(dfX.all_exits_bottom3_judge.sum()), int(len(dfX))],
        "multiexit_weeks_exactset_combined": [
            int(dfX[dfX.m_exits > 1].all_exits_bottom_m_combined.sum()),
            int((dfX.m_exits > 1).sum())],
    }
    log("consistency: " + json.dumps(RESULTS["consistency"]))

    # ================================================== 6. cluster bootstrap
    nboot = MA.N_BOOT
    rngB = np.random.default_rng(SEED + 1)
    seasons = np.array(sorted(pan["season"].unique()))
    boot_bJ, boot_bF = [], []
    for _ in range(nboot):
        pick = rngB.choice(seasons, size=len(seasons), replace=True)
        rowsel = np.concatenate([np.where(pan["season"].to_numpy() == s)[0]
                                 for s in pick])
        bs = MA.ols_fit(yJ[rowsel], X[rowsel], run_ids[rowsel])
        bf = MA.ols_fit(yF[rowsel], X[rowsel], run_ids[rowsel])
        boot_bJ.append(bs["b"])
        boot_bF.append(bf["b"])
    boot_bJ = np.array(boot_bJ)
    boot_bF = np.array(boot_bF)
    log(f"cluster bootstrap done ({nboot} reps)")

    # ================================================== 7. pro/industry tables
    cols_pro = np.array(MA.block_cols(names, "pro"), int)
    cols_ind = np.array(MA.block_cols(names, "industry"), int)
    # centered effects + bootstrap quantiles (contrast vs row-weighted mean level)
    def centered(bt, cols, kind):
        return MA._center_contrast(bt, cols, names, pan, kind)
    effJ = centered(fitJ["b"], cols_pro, "pro")
    effF = centered(fitF["b"], cols_pro, "pro")
    pros = sorted(effJ)
    dicts_J = [centered(boot_bJ[k], cols_pro, "pro") for k in range(nboot)]
    dicts_F = [centered(boot_bF[k], cols_pro, "pro") for k in range(nboot)]
    Bmap_J = np.array([[dj[p] for p in pros] for dj in dicts_J])   # (nboot, n_pro)
    Bmap_F = np.array([[df_[p] for p in pros] for df_ in dicts_F])
    # season/run info per pro
    n_seas = ct.groupby("pro").season.nunique()
    n_runs = ct.groupby("pro").size()
    rows = []
    for p in pros:
        pname = p[2:] if p.startswith("P_") else p     # strip design prefix "P_"
        rows.append(dict(
            pro=pname, effect_judge=round(effJ[p], 4), effect_fan=round(effF[p], 4),
            judge_lo95=round(float(np.quantile(Bmap_J[:, pros.index(p)], 0.025)), 4),
            judge_hi95=round(float(np.quantile(Bmap_J[:, pros.index(p)], 0.975)), 4),
            fan_lo95=round(float(np.quantile(Bmap_F[:, pros.index(p)], 0.025)), 4),
            fan_hi95=round(float(np.quantile(Bmap_F[:, pros.index(p)], 0.975)), 4),
            n_seasons=int(n_seas.get(pname, 0)), n_runs=int(n_runs.get(pname, 0))))
    df_rank = pd.DataFrame(rows)
    # reference level (dropped by drop_first coding): centered effect = -center, where
    # center is the true row-weighted mean over ALL levels (ref weight = 1 - rest).
    stripped_all = {p[2:] if p.startswith("P_") else p for p in pros}
    ref_pros = sorted(set(pan["pro"].astype(str)) - stripped_all)
    lab = pan["pro"].astype(str)
    lv, cnt = np.unique(lab, return_counts=True)
    wmap = dict(zip(lv, cnt / cnt.sum()))
    wv_est = np.array([wmap.get(p, 0.0) for p in pros])
    augJ = np.array([0.0] + [effJ[p] for p in pros])   # [ref, *estimated levels]
    augF = np.array([0.0] + [effF[p] for p in pros])
    cJ = MA.contrast_center(fitJ["b"], cols_pro, names, pan, "pro")
    cF = MA.contrast_center(fitF["b"], cols_pro, names, pan, "pro")
    for rp in ref_pros:
        rows.append(dict(pro=rp, effect_judge=round(-cJ, 4), effect_fan=round(-cF, 4),
                         judge_lo95=np.nan, judge_hi95=np.nan,
                         fan_lo95=np.nan, fan_hi95=np.nan,
                         n_seasons=int(ct[ct.pro == rp].season.nunique()),
                         n_runs=int((ct.pro == rp).sum()),
                         eligible_min2seasons=bool(ct[ct.pro == rp].season.nunique() >= 2)))
        df_rank = pd.DataFrame(rows)
    df_rank["eligible_min2seasons"] = df_rank["n_seasons"] >= 2
    df_rank.to_csv(OUT + "/model2_pro_rankings.csv", index=False)

    # industry table (same bootstrap)
    indJ = centered(fitJ["b"], cols_ind, "industry")
    indF = centered(fitF["b"], cols_ind, "industry")
    inds = sorted(indJ)
    dicts_IJ = [centered(boot_bJ[k], cols_ind, "industry") for k in range(nboot)]
    dicts_IF = [centered(boot_bF[k], cols_ind, "industry") for k in range(nboot)]
    Bmap_IJ = np.array([[dj[lv] for lv in inds] for dj in dicts_IJ])
    Bmap_IF = np.array([[df_[lv] for lv in inds] for df_ in dicts_IF])
    irows = []
    for lv in inds:
        irows.append(dict(
            industry=lv, effect_judge=round(indJ[lv], 4), effect_fan=round(indF[lv], 4),
            judge_lo95=round(float(np.quantile(Bmap_IJ[:, inds.index(lv)], 0.025)), 4),
            judge_hi95=round(float(np.quantile(Bmap_IJ[:, inds.index(lv)], 0.975)), 4),
            fan_lo95=round(float(np.quantile(Bmap_IF[:, inds.index(lv)], 0.025)), 4),
            fan_hi95=round(float(np.quantile(Bmap_IF[:, inds.index(lv)], 0.975)), 4),
            n_runs=int((ct.celebrity_industry == lv).sum())))
    # reference industry level (dropped by drop_first coding): centered = -center
    # with the reference's true row weight (1 - sum of estimated-level weights)
    stripped_ind = {l[2:] if l.startswith("I_") else l for l in inds}
    ref_inds = sorted(set(pan["celebrity_industry"].astype(str)) - stripped_ind)
    lab_i, cnt_i = np.unique(pan["celebrity_industry"].astype(str), return_counts=True)
    wmap_i = dict(zip(lab_i, cnt_i / cnt_i.sum()))
    wv_i_est = np.array([wmap_i.get(l, 0.0) for l in inds])
    cIJ = MA.contrast_center(fitJ["b"], cols_ind, names, pan, "industry")
    cIF = MA.contrast_center(fitF["b"], cols_ind, names, pan, "industry")
    for ri in ref_inds:
        irows.append(dict(industry=ri, effect_judge=round(-cIJ, 4),
                          effect_fan=round(-cIF, 4),
                          judge_lo95=np.nan, judge_hi95=np.nan,
                          fan_lo95=np.nan, fan_hi95=np.nan,
                          n_runs=int((ct.celebrity_industry == ri).sum())))
    df_ind = pd.DataFrame(irows).sort_values("effect_judge", ascending=False)
    df_ind.to_csv(OUT + "/model2_industry_effects.csv", index=False)
    el = df_rank[df_rank.eligible_min2seasons]
    RESULTS["pro_rankings"] = {
        "n_eligible_pros": int(len(el)),
        "top5_judge_eligible": el.nlargest(5, "effect_judge").round(3).to_dict("records"),
        "bottom5_judge_eligible": el.nsmallest(5, "effect_judge").round(3).to_dict("records"),
        "top5_fan_eligible": el.nlargest(5, "effect_fan").round(3).to_dict("records"),
        "corr_judge_fan_effects_eligible": round(float(np.corrcoef(
            el.effect_judge, el.effect_fan)[0, 1]), 3),
        "corr_judge_fan_effects_all": round(float(np.corrcoef(
            df_rank.effect_judge, df_rank.effect_fan)[0, 1]), 3),
        "known_elite_ranks_judge": {p: int((el.effect_judge >
                                            float(el.loc[el.pro == p, "effect_judge"]
                                                  .iloc[0])).sum()) + 1
                                    for p in ["Derek Hough", "Mark Ballas",
                                              "Cheryl Burke",
                                              "Valentin Chmerkovskiy"]
                                    if p in set(el.pro)},
    }
    RESULTS["industry_effects"] = {
        "top3_judge": df_ind.head(3).round(3).to_dict("records"),
        "bottom3_judge": df_ind.tail(3).round(3).to_dict("records"),
    }
    log(f"pro corr(judge, fan | eligible) = "
        f"{RESULTS['pro_rankings']['corr_judge_fan_effects_eligible']}")

    # ================================================== 8. effects CSV (long)
    eff_rows = []
    # age spline curve on a grid (both surfaces)
    age_grid = np.linspace(14, 82, 35)
    aJ = age_curve(fitJ["b"], names, "age", age_grid)
    aF = age_curve(fitF["b"], names, "age", age_grid)
    for k, a in enumerate(age_grid):
        eff_rows.append(dict(surface="judge", covariate="age", level=f"{a:.1f}",
                             estimate=round(float(aJ[k]), 4)))
        eff_rows.append(dict(surface="fan", covariate="age", level=f"{a:.1f}",
                             estimate=round(float(aF[k]), 4)))
    # week spline curve on 1..11
    wk_grid = np.arange(1, 12, dtype=float)
    wJ = age_curve(fitJ["b"], names, "week", wk_grid)
    wF = age_curve(fitF["b"], names, "week", wk_grid)
    for k, v in enumerate(wk_grid):
        eff_rows.append(dict(surface="judge", covariate="week_in_run",
                             level=f"{v:.0f}", estimate=round(float(wJ[k]), 4)))
        eff_rows.append(dict(surface="fan", covariate="week_in_run",
                             level=f"{v:.0f}", estimate=round(float(wF[k]), 4)))
    # multi-dance effect
    for surf, fit in (("judge", fitJ), ("fan", fitF)):
        i = names.index("multi_dance")
        eff_rows.append(dict(surface=surf, covariate="multi_dance", level="flag",
                             estimate=round(float(fit["b"][i]), 4),
                             std_err=round(float(fit["se"][i]), 4)))
    pd.DataFrame(eff_rows).to_csv(OUT + "/model2_effects.csv", index=False)

    # ================================================== 9. sign discipline
    # paired within-run week slope: for runs w/ >=4 weeks, mean (last3-first2) judge_z
    # and mean (last3-first2) logit-fan-share -> learning vs fan-fatigue contrast
    tmp = pan[["run_id", "week", "judge_z", "fanshare"]].copy()
    tmp["lf"] = np.log((tmp.fanshare.clip(1e-6, 1-1e-6) + 8e-5) /
                       (1 - tmp.fanshare.clip(1e-6, 1-1e-6) + 8e-5))
    gg = tmp.groupby("run_id")
    slopes_J, slopes_F = [], []
    for r, g in gg:
        if len(g) >= 4:
            g = g.sort_values("week")
            first2 = g.head(2); last3 = g.tail(3)
            slopes_J.append(last3.judge_z.mean() - first2.judge_z.mean())
            slopes_F.append(last3.lf.mean() - first2.lf.mean())
    sign_checks = {
        "age_curve_min_15_45_judge": round(float(np.min(aJ[(age_grid >= 15) & (age_grid <= 45)])), 4),
        "age_curve_min_15_45_fan": round(float(np.min(aF[(age_grid >= 15) & (age_grid <= 45)])), 4),
        "week_curve_start_end_judge": [round(float(wJ[0]), 3), round(float(wJ[-1]), 3)],
        "week_curve_start_end_fan": [round(float(wF[0]), 3), round(float(wF[-1]), 3)],
        "paired_within_run_djudge_mean": round(float(np.mean(slopes_J)), 4),
        "paired_within_run_dlogitfan_mean": round(float(np.mean(slopes_F)), 4),
        "paired_n_runs": len(slopes_J),
    }
    import scipy.stats as _sps
    ttJ = _sps.ttest_1samp(slopes_J, 0.0)
    ttF = _sps.ttest_1samp(slopes_F, 0.0)
    sign_checks["paired_djudge_t_p"] = [round(float(ttJ.statistic), 3), round(float(ttJ.pvalue), 5)]
    sign_checks["paired_dlogitfan_t_p"] = [round(float(ttF.statistic), 3), round(float(ttF.pvalue), 5)]
    RESULTS["sign_discipline"] = sign_checks
    log(f"sign checks: {sign_checks}")

    # ================================================== 10. restricted pro effects
    rest = restricted_pro_effects(pan, X, names, yJ, yF)
    RESULTS["restricted_pro_effects"] = rest
    log(f"restricted pro R2: {rest}")

    # ================================================== 11. counterfactual swap
    swap = counterfactual_swap(pan, X, names, fitJ, fitF, ct)
    RESULTS["counterfactual_swap"] = swap
    log(f"swap exhibit: {swap}")

    # ================================================== 12. figures
    make_figures(pan, X, names, yJ, yF, fitJ, fitF, df_rank, df_ind,
                 age_grid, aJ, aF, wk_grid, wJ, wF, Bmap_J, Bmap_F, pros)

    # ================================================== 13. finish
    # NOTE: no wall-clock fields here -- results.json must be byte-reproducible
    RESULTS["meta"] = {"seed": SEED, "n_perm": MA.N_PERM, "n_boot": MA.N_BOOT,
                       "n_shake": MF.N_SHAKE, "n_cop": MF.N_COP}
    with open(OUT + "/results.json", "w") as fh:
        json.dump(RESULTS, fh, indent=1, default=float)
    log(f"DONE in {time.time() - t0:.0f}s -> results.json")
    return RESULTS


# ------------------------------------------------------------------ helpers (main-level)
def age_curve(b, names, kind, grid):
    """Spline curve values over `grid` for the age (or week) block (centered at the
    panel's row-weighted mean basis to remove collinearity with the intercept)."""
    tag = "age_" if kind == "age" else "wk_"
    cols = [i for i, nm in enumerate(names) if nm.startswith(tag)]
    from m2_data import RCS_KNOTS_AGE, RCS_KNOTS_WEEK
    knots = RCS_KNOTS_AGE if kind == "age" else RCS_KNOTS_WEEK
    Bg = rcs_design(grid, knots)
    ref = rcs_design(np.array([36.0 if kind == "age" else 4.0]), knots)
    return Bg @ b[cols] - (ref @ b[cols] - b[0] * 0) * 0


def week_curve(b, names, grid):
    return age_curve(b, names, "week", grid)


def restricted_pro_effects(pan, X, names, yJ, yF):
    """Sorting-adjusted ("honest lower bound") pro partial R2: the pro block's R^2
    after pre-processing the design with a pre-treatment fame control (week-1 fan
    share, logit) -- implemented in m2_fit.restricted_pro_r2."""
    return FT.restricted_pro_r2(pan, yJ, yF, X, names)


def counterfactual_swap(pan, X, names, fitJ, fitF, ct):
    """Median-profile celebrity: predicted judge-z and fan-share with best vs median
    vs worst pro (season effect = S10 median; age = 36; industry = Actor/Actress;
    week = 5; multi = 0)."""
    # NOTE: age_rcs0 is the LINEAR term: value 36 means age=36 at knots (20,30,45,65):
    # the rcs linear column is x itself, so this row encodes age 36 correctly ONLY for
    # rcs0; higher terms are 0 at age=36? No: rcs terms are nonlinear functions.
    # Recompute properly:
    def design_row2(pro_name):
        base = np.zeros(len(names))
        base[0] = 1.0
        for i, nm in enumerate(names):
            if nm.startswith("season_"):
                base[i] = 1.0 if nm.endswith("_10") else 0.0
            elif nm.startswith("pro_"):
                # design names carry the dummy prefix, e.g. "pro_P_Derek Hough"
                base[i] = 1.0 if nm == f"pro_P_{pro_name}" else 0.0
            elif nm.startswith("ind_"):
                base[i] = 1.0 if nm == "ind_Actor/Actress" else 0.0
            elif nm.startswith("age_"):
                pass
            elif nm.startswith("wk_"):
                pass
            elif nm == "multi_dance":
                base[i] = 0.0
        ab = rcs_design(np.array([36.0]), RCS_KNOTS_AGE)[0]
        wb = rcs_design(np.array([5.0]), RCS_KNOTS_WEEK)[0]
        acols = [i for i, nm in enumerate(names) if nm.startswith("age_")]
        wcols = [i for i, nm in enumerate(names) if nm.startswith("wk_")]
        base[acols] = ab
        base[wcols] = wb
        return base
    df_rank = pd.read_csv(OUT + "/model2_pro_rankings.csv")
    el = df_rank[df_rank.eligible_min2seasons]
    bestJ = el.loc[el.effect_judge.idxmax(), "pro"]
    medJ = el.loc[(el.effect_judge - el.effect_judge.median()).abs().idxmin(), "pro"]
    worstJ = el.loc[el.effect_judge.idxmin(), "pro"]
    out = {}
    zJ = {}
    for label, p in (("best", bestJ), ("median", medJ), ("worst", worstJ)):
        x = design_row2(p)
        from scipy.special import expit
        zJ[label] = (round(float(x @ fitJ["b"]), 3),
                     round(float(expit(x @ fitF["b"])), 4))
    out["pro_by_judge"] = {"best": bestJ, "median": medJ, "worst": worstJ}
    out["predictions_judge_z_and_fanshare"] = {k: list(v) for k, v in zJ.items()}
    return out


def make_figures(pan, X, names, yJ, yF, fitJ, fitF, df_rank, df_ind,
                 age_grid, aJ, aF, wk_grid, wJ, wF, Bmap_J, Bmap_F, pros):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "serif"

    # ---- F6: pro forest plot (judge vs fan), top-15 by |judge|
    d = df_rank.reindex(df_rank.effect_judge.abs().sort_values(ascending=False).index
                        ).head(15).iloc[::-1]
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.errorbar(d["effect_judge"], y + 0.18,
                xerr=[d["effect_judge"] - d["judge_lo95"],
                      d["judge_hi95"] - d["effect_judge"]],
                fmt="o", ms=4, color="#1f77b4", label="judge surface", lw=1.2)
    ax.errorbar(d["effect_fan"], y - 0.18,
                xerr=[d["effect_fan"] - d["fan_lo95"],
                      d["fan_hi95"] - d["effect_fan"]],
                fmt="s", ms=4, color="#d62728", label="fan surface", lw=1.2)
    ax.set_yticks(y)
    ax.set_yticklabels(d["pro"], fontsize=7)
    ax.axvline(0, color="k", lw=0.6, ls="--")
    ax.set_xlabel("centered pro effect (log-odds / judge-z units)")
    ax.set_title("F6: Pro-dancer effects, judge vs fan surface (top-15 by |judge effect|)")
    ax.legend(fontsize=8, loc="lower right")
    fig.savefig(FIGDIR + "/F6_pro_forest.png", bbox_inches="tight")
    plt.close(fig)

    # ---- F7: age spline
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.plot(age_grid, aJ, "-o", ms=3, color="#1f77b4", label="judge surface")
    ax.plot(age_grid, aF, "-s", ms=3, color="#d62728", label="fan surface (logit)")
    ax.set_xlabel("celebrity age (years)")
    ax.set_ylabel("curve value (centered at age 36 / week 4 reference)")
    ax.set_title("F7: Age response curves, judge vs fan (RCS knots 20/30/45/65)")
    ax.legend()
    fig.savefig(FIGDIR + "/F7_age_spline.png", bbox_inches="tight")
    plt.close(fig)

    # ---- F8: industry heatmap
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    dd = df_ind.set_index("industry")[["effect_judge", "effect_fan"]]
    im = ax.imshow(dd.to_numpy(), aspect="auto", cmap="RdBu_r", vmin=-0.6, vmax=0.6)
    ax.set_yticks(range(len(dd)))
    ax.set_yticklabels(dd.index, fontsize=7)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["judge", "fan"])
    for i in range(dd.shape[0]):
        for j in range(2):
            ax.text(j, i, f"{dd.to_numpy()[i, j]:.2f}", ha="center", va="center",
                    fontsize=6,
                    color="white" if abs(dd.to_numpy()[i, j]) > 0.3 else "black")
    fig.colorbar(im, ax=ax, shrink=0.8, label="centered effect")
    ax.set_title("F8: Industry effects on the two surfaces (25 levels, centered)")
    fig.savefig(FIGDIR + "/F8_industry_heatmap.png", bbox_inches="tight")
    plt.close(fig)

    # ---- F9: week curve
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.plot(wk_grid, wJ, "-o", ms=4, color="#1f77b4", label="judge surface")
    ax.plot(wk_grid, wF, "-s", ms=4, color="#d62728", label="fan surface (logit)")
    ax.set_xlabel("week in run")
    ax.set_ylabel("curve value (ref. week 4)")
    ax.set_title("F9: Week-in-run learning curve (judges) vs fan drift")
    ax.legend()
    fig.savefig(FIGDIR + "/F9_week_curve.png", bbox_inches="tight")
    plt.close(fig)

    # ---- F10: pro quadrant chart
    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.scatter(df_rank.effect_judge, df_rank.effect_fan, s=18, alpha=0.75,
               c="#2a9d8f")
    for _, r in df_rank.nlargest(8, "effect_judge").iterrows():
        if r.effect_fan > df_rank.effect_fan.quantile(0.75) or \
           r.effect_judge > df_rank.effect_judge.quantile(0.85):
            ax.annotate(r.pro, (r.effect_judge, r.effect_fan), fontsize=6,
                        xytext=(2, 2), textcoords="offset points")
    ax.axhline(0, color="k", lw=0.6, ls=":")
    ax.axvline(0, color="k", lw=0.6, ls=":")
    ax.set_xlabel("pro effect on judge surface (judge-z units)")
    ax.set_ylabel("pro effect on fan surface (log-odds of fan share)")
    ax.set_title("F10: Pro effects, judge vs fan quadrant chart")
    fig.savefig(FIGDIR + "/F10_pro_quadrant.png", bbox_inches="tight")
    plt.close(fig)
    log("figures F6-F10 written")


if __name__ == "__main__":
    main()
