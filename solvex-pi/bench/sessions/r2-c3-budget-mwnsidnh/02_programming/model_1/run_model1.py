"""
run_model1.py — Model 1 driver (2026 MCM Problem C).

Constrained Bayesian inverse model for hidden fan votes.

Posterior model (exact, rejection-sampled):
    prior:  log f_i ~ N(log mu_i - sigma^2, sigma^2),  sum_i f_i = 1
            mu_i = softmax(-hazard_i),  hazard from a logistic GLM on
            judge share / week / age / industry (fans weakly track quality)
    likelihood-free constraint (exact): the observed eliminated couple must be
    the rule's loser, i.e.
      percentage rule (S3-27): argmin_i (0.5 s_i + 0.5 f_i) = e*
      rank rule (S1-2, S28-34): argmax_i (rJ_i + rF_i) = e*
    posterior = prior restricted to the feasible set (sampled by rejection).

Outputs: per contestant-week posterior mean/sd/95% CI of the fan share,
week-level diagnostics, hold-out validation (prior-only top-1 elimination
accuracy, Brier score), controversy-case estimates, sigma sensitivity.
"""
import json
import time
import numpy as np
import pandas as pd

import dwts_common as dc

SIGMA = 0.35            # baseline logistic-normal sd on log fan shares
SIGMA_GRID = [0.20, 0.35, 0.75]
BATCH = 4000
MAX_PROP = 600_000      # rejection cap per week
OUT = dc.DATA_PATH and "02_programming/model_1"


def sample_week(sub, rng, sigma=SIGMA, n_keep=2000):
    """Rejection-sample the constrained posterior for one (season, week)."""
    e_arr = np.where(sub["eliminated"].values)[0]
    if len(e_arr) != 1:
        return None, dict(reason="no_unique_elimination")
    e = int(e_arr[0])
    s = int(sub["season"].iloc[0])
    rank_rule = s in dc.RANK_SEASONS
    n = len(sub)
    rJ = sub["judge_rank"].values.astype(float)
    js = sub["judge_share"].values
    mu = np.clip(sub["prior_share"].values, 1e-8, None)

    kept, n_prop = [], 0
    while sum(k.shape[0] for k in kept) < n_keep and n_prop < MAX_PROP:
        f = dc.draw_prior(sub, BATCH, sigma, rng)
        if rank_rule:
            ok = dc.draw_rank_rule(f, rJ, e)
        else:
            p = 0.5 * js[None, :] + 0.5 * f
            ok = p.argmin(axis=1) == e
        kept.append(f[ok])
        n_prop += f.shape[0]
    if sum(k.shape[0] for k in kept) == 0:
        return None, dict(reason="no_feasible_draws")
    draws = np.vstack(kept)[:n_keep]
    rate = draws.shape[0] / n_prop
    return dict(draws=draws, rank_rule=rank_rule, e=e, accepted_rate=rate), dict()


def prior_elim_prob(sub, rng, sigma=SIGMA, m=4000):
    """Hold-out proxy: prior-only (no elimination info) probability that the
    season's rule would have eliminated the couple actually eliminated."""
    s = int(sub["season"].iloc[0])
    rank_rule = s in dc.RANK_SEASONS
    f = dc.draw_prior(sub, m, sigma, rng)
    e_arr = np.where(sub["eliminated"].values)[0]
    if len(e_arr) != 1:
        return None
    e = int(e_arr[0])
    if rank_rule:
        ok = dc.draw_rank_rule(f, sub["judge_rank"].values.astype(float), e)
    else:
        p = 0.5 * sub["judge_share"].values[None, :] + 0.5 * f
        ok = p.argmin(axis=1) == e
    return ok.mean()  # scalar P(replay observed elimination) under prior only


def main():
    t0 = time.time()
    rng = np.random.default_rng(20260101)
    panel, wide = dc.load_panel()
    panel, glm = dc.fit_prior(panel)
    print(f"panel {panel.shape}")
    print(glm.params.round(4).to_string())

    rows, week_diag, holdout, hpred = [], [], [], []
    sens_store = []
    week_no = 0
    for (s, w), sub in panel.groupby(["season", "week"], sort=True):
        sub = sub.sort_values("celebrity").reset_index(drop=True)
        out, _info = sample_week(sub, rng)
        e_arr = np.where(sub["eliminated"].values)[0]
        if out is None or len(e_arr) != 1:
            week_diag.append(dict(season=s, week=w, n=len(sub), kept=False,
                                  accepted_rate=np.nan))
            continue
        week_no += 1
        draws = out["draws"]
        mean, sd, lo, hi, ess = dc.weighted_stats(draws)
        e = int(e_arr[0])
        # Spearman rho between posterior fan mean and prior share (prior transport)
        rho = float(pd.Series(mean).corr(pd.Series(sub["prior_share"].values),
                                         method="spearman"))
        for i, cel in enumerate(sub["celebrity"]):
            rows.append(dict(
                season=int(s), week=int(w), celebrity=cel,
                partner=sub["partner"].iloc[i], bucket=sub["bucket"].iloc[i],
                age=float(sub["age"].iloc[i]),
                judge_total=float(sub["judge_total"].iloc[i]),
                judge_share=float(sub["judge_share"].iloc[i]),
                judge_rank=int(sub["judge_rank"].iloc[i]),
                eliminated=bool(sub["eliminated"].iloc[i]),
                fan_mean=float(mean[i]), fan_sd=float(sd[i]),
                fan_lo=float(lo[i]), fan_hi=float(hi[i]),
                fan_cv=float(sd[i] / max(mean[i], 1e-9)),
                rule="rank" if out["rank_rule"] else "pct",
            ))
        week_diag.append(dict(
            season=int(s), week=int(w), n=len(sub), kept=True,
            accepted_rate=float(out["accepted_rate"]),
            mean_ci_width=float((hi - lo).mean()),
            mean_ess=float(ess), spearman_prior=rho,
            replay_p=float((draws[:, e] == draws.min(axis=1)).mean())
            if not out["rank_rule"] else
            float(np.mean(np.argmax(sub["judge_rank"].values[None, :].astype(float)
                                    + draws.argsort(axis=1).argsort(axis=1) + 1,
                                    axis=1) == e)),
        ))
        # hold-out (prior only)
        pe = prior_elim_prob(sub, rng)
        if pe is not None:
            holdout.append(dict(season=int(s), week=int(w),
                                rule="rank" if out["rank_rule"] else "pct",
                                n=len(sub), replay_p=float(pe)))
        # sigma sensitivity (subset of weeks)
        if (s + w) % 7 == 0:
            for sg in SIGMA_GRID:
                f2 = dc.draw_prior(sub, 3000, sg, rng)
                e = int(e_arr[0])
                if out["rank_rule"]:
                    ok = dc.draw_rank_rule(f2, sub["judge_rank"].values.astype(float), e)
                else:
                    p = 0.5 * sub["judge_share"].values[None, :] + 0.5 * f2
                    ok = p.argmin(axis=1) == e
                d2 = f2[ok]
                if len(d2) > 50:
                    m2, s2, l2, h2, _ = dc.weighted_stats(d2)
                    sens_store.append(dict(season=int(s), week=int(w), sigma=sg,
                                           mean_ci_width=float((h2 - l2).mean()),
                                           accepted_rate=float(ok.mean())))
        if week_no % 25 == 0:
            print(f"  {week_no} weeks done ({time.time()-t0:.0f}s)")

    post = pd.DataFrame(rows)
    diag = pd.DataFrame(week_diag)
    hold = pd.DataFrame(holdout)
    sens = pd.DataFrame(sens_store)

    # controversy cases
    HOF_SEASONS = {("Jerry Rice", 2), ("Billy Ray Cyrus", 4),
                   ("Bristol Palin", 11), ("Bobby Bones", 27)}
    mask = post.apply(lambda r: (r["celebrity"], r["season"]) in HOF_SEASONS, axis=1)
    cont = post[mask].copy()
    cont["fan_rank_in_week"] = cont.groupby(["season", "week"])["fan_mean"] \
                                   .rank(ascending=False, method="dense")

    # ---- headline metrics ----
    print("\n=== HEADLINE ===")
    print(f"weeks sampled: {week_no}, mean accepted rate: "
          f"{diag.accepted_rate.mean():.3f}")
    print(f"mean prior replay probability of observed elimination: {hold.replay_p.mean():.3f}")
    print(f"weeks with prior replay P >= 0.5: {hold.replay_p.ge(0.5).mean():.3f}")
    print(f"mean Spearman(posterior fan, prior): {diag.spearman_prior.mean():.3f}")
    print(f"mean CI width (fan share): {diag.mean_ci_width.mean():.4f}")

    post.to_csv("02_programming/model_1/fan_votes_posterior.csv", index=False)
    diag.to_csv("02_programming/model_1/week_diagnostics.csv", index=False)
    hold.to_csv("02_programming/model_1/holdout_results.csv", index=False)
    sens.to_csv("02_programming/model_1/sigma_sensitivity.csv", index=False)
    cont.to_csv("02_programming/model_1/controversy_estimates.csv", index=False)
    glm.params.to_csv("02_programming/model_1/prior_glm_params.csv")
    print("\nsaved outputs; elapsed", round(time.time() - t0), "s")


if __name__ == "__main__":
    main()
