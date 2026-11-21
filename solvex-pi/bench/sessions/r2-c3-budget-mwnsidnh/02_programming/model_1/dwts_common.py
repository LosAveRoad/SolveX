"""
dwts_common.py — shared utilities for Model 1 (2026 MCM Problem C).

Long-panel construction from the wide CSV, logistic-normal prior over weekly
fan-vote shares, and exact rejection sampling of the elimination-constrained
posterior. Also unestrained prior draws for hold-out validation.
"""
import re
import numpy as np
import pandas as pd

DATA_PATH = "data/2026_MCM_Problem_C_Data.csv"

RANK_SEASONS = set(range(1, 3)) | set(range(28, 35))  # S1-2 documented, S28+ assumed

BUCKET_MAP = {
    "Actor/Actress": "Acting",
    "Athlete": "Athlete",
    "TV Personality": "TV Personality",
    "Singer/Rapper": "Singer/Musician",
    "Musician": "Singer/Musician",
    "Model": "Model",
}


def load_panel(data_path=DATA_PATH):
    """Wide CSV -> long panel (one row per season-week-contestant while competing)."""
    df = pd.read_csv(data_path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]

    def parse_exit(res):
        m = re.match(r"Eliminated Week (\d+)", str(res).strip())
        return int(m.group(1)) if m else np.nan

    df["exit_week"] = df["results"].map(parse_exit)
    df["withdrew"] = df["results"].astype(str).str.strip().str.lower().eq("withdrew")
    df["placement"] = pd.to_numeric(df["placement"], errors="coerce")
    df["bucket"] = df["celebrity_industry"].map(BUCKET_MAP).fillna("Other")

    def weeks_comp(row):
        wc = 0
        for k in range(1, 12):
            t = _week_total(row, k)
            if pd.notna(t) and t > 0:
                wc = k
            else:
                break
        return wc

    df["weeks_competed"] = df.apply(weeks_comp, axis=1)

    rows = []
    for _, r in df.iterrows():
        wc = int(r["weeks_competed"])
        for k in range(1, wc + 1):
            t = _week_total(r, k)
            if pd.isna(t) or t <= 0:
                continue  # no judge scores that week -> no vote information
            rows.append(dict(
                season=int(r["season"]), week=k,
                celebrity=r["celebrity_name"],
                partner=r["ballroom_partner"],
                bucket=r["bucket"],
                age=float(r["celebrity_age_during_season"]),
                judge_total=float(t),
                eliminated=bool(pd.notna(r["exit_week"]) and int(r["exit_week"]) == k),
                placement=float(r["placement"]) if pd.notna(r["placement"]) else np.nan,
            ))
    panel = pd.DataFrame(rows)
    gsum = panel.groupby(["season", "week"])["judge_total"].transform("sum")
    panel["judge_share"] = panel["judge_total"] / gsum
    panel["judge_rank"] = panel.groupby(["season", "week"])["judge_total"] \
                               .rank(ascending=False, method="dense").astype(int)
    return panel, df


def _week_total(row, k):
    vals = [row.get(f"week{k}_judge{j}_score") for j in (1, 2, 3, 4)]
    nums = [float(v) for v in vals if isinstance(v, (int, float)) and pd.notna(v)]
    return sum(nums) if nums else np.nan


def fit_prior(panel):
    """Hazard GLM: P(eliminated | alive) ~ judge share, week, age, industry.
    Attaches prior_share = softmax(-hazard) within each week; returns (panel, GLM fit)."""
    import statsmodels.api as sm
    X = pd.DataFrame(index=panel.index)
    X["judge_share"] = panel["judge_share"]
    X["week10"] = panel["week"] / 10.0
    X["age10"] = panel["age"] / 10.0
    for b in ["Acting", "Athlete", "TV Personality", "Singer/Musician", "Model"]:
        X[f"bucket_{b}"] = (panel["bucket"] == b).astype(float)
    X = sm.add_constant(X)
    y = panel["eliminated"].astype(int)
    glm = sm.GLM(y, X, family=sm.families.Binomial())
    res = glm.fit()
    panel = panel.copy()
    panel["prior_logit_q"] = -np.asarray(res.predict(X))  # popularity = -hazard
    emax = panel.groupby(["season", "week"])["prior_logit_q"].transform("max")
    e = np.exp(panel["prior_logit_q"] - emax)
    esum = e.groupby([panel["season"], panel["week"]]).transform("sum")
    ps = (e / esum).clip(lower=1e-6)
    panel["prior_share"] = ps / ps.groupby([panel["season"], panel["week"]]).transform("sum")
    return panel, res


def prior_log_shares(sub, mu_col="prior_share"):
    """Mean vector of log prior shares for one week's sub-panel."""
    return np.log(sub[mu_col].values)


def draw_prior(sub, m, sigma, rng):
    """m logistic-normal draws on the simplex for one week (n columns)."""
    mu = np.clip(sub["prior_share"].values, 1e-8, None)
    y = np.log(mu)[None, :] + sigma * rng.standard_normal((m, len(mu)))
    f = np.exp(y)
    return f / f.sum(axis=1, keepdims=True)


def draw_rank_rule(f, rJ, e_idx):
    """Boolean: does the rank rule eliminate e_idx given fan shares f (m, n)?"""
    order = np.argsort(-f, axis=1)              # fans' favourite first
    rF = np.empty_like(order)
    rows = np.arange(f.shape[0])[:, None]
    rF[rows, order] = np.arange(1, f.shape[1] + 1)[None, :]
    R = rJ[None, :] + rF
    return R.argmax(axis=1) == e_idx


def weighted_stats(draws, logw=None):
    """Self-normalized importance-sampling mean, sd, equal-tailed 95% CI per column."""
    if logw is None:
        logw = np.zeros(draws.shape[0])
    w = np.exp(logw - logw.max())
    w /= w.sum()
    mean = w @ draws
    sd = np.sqrt(w @ (draws - mean) ** 2)
    o = np.argsort(draws, axis=0)
    cw = np.cumsum(w[o], axis=0)
    cw /= cw[-1, :]
    lo = np.empty(draws.shape[1])
    hi = np.empty(draws.shape[1])
    for c in range(draws.shape[1]):
        col = draws[o[:, c], c]
        lo[c] = col[np.searchsorted(cw[:, c], 0.025)]
        hi[c] = col[np.searchsorted(cw[:, c], 0.975)]
    ess = 1.0 / np.sum(w ** 2)
    return mean, sd, lo, hi, ess
