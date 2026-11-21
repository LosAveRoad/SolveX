import os
import shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE = "/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/sessions"
OLD = "mw323ika-oj43"
NEW = "rerun-2026-mcmc"
src, dst = os.path.join(BASE, OLD), os.path.join(BASE, NEW)

if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("events.jsonl", ".solvex-meta.json"))

# 用原始完整题面，不再把针对 P1 的临时约束透传到 P4
with open("/Users/mac/WorkBuddy/2026-11-05-11-28-19/tmp/problem.md", encoding="utf-8") as fh:
    problem = fh.read()
os.makedirs(os.path.join(dst, "00_problem"), exist_ok=True)
with open(os.path.join(dst, "00_problem", "problem.md"), "w", encoding="utf-8") as fh:
    fh.write(problem)

PROG = os.path.join(dst, "02_programming")
plt.rcParams.update({"figure.figsize": (8, 5), "font.size": 10, "axes.grid": True, "grid.alpha": .3})


def save(model, name):
    out = os.path.join(PROG, model, "figures")
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, name)
    plt.tight_layout()
    plt.savefig(p, dpi=160, bbox_inches="tight")
    plt.close()
    print("figure:", os.path.relpath(p, dst))


def numeric(df, col):
    return pd.to_numeric(df[col], errors="coerce").dropna()


# Model 1: latent fan share estimates
p = os.path.join(PROG, "model_1", "fan_vote_estimates.csv")
df = pd.read_csv(p)
for col, label in [("pF_med", "Median reconstructed fan share"),
                   ("pF_sd", "Uncertainty (sd) of fan share")]:
    if col in df.columns:
        s = numeric(df, col)
        plt.hist(s, bins=60, color="#3f6b52", alpha=.85)
        plt.xlabel(label); plt.ylabel("couple-weeks")
        plt.title(f"Model 1 — {label} (n={len(s)})")
        save("model_1", f"m1_{col}_hist.png")

p = os.path.join(PROG, "model_1", "weekly_consistency.csv")
df = pd.read_csv(p)
if {"kappa_pct", "kappa_rank"}.issubset(df.columns):
    a, b = numeric(df, "kappa_pct"), numeric(df, "kappa_rank")
    n = min(len(a), len(b))
    plt.scatter(a[:n], b[:n], s=12, alpha=.45, color="#8a5a44")
    plt.xlabel("consistency (percentage fusion)"); plt.ylabel("consistency (rank fusion)")
    plt.title("Model 1 — rank vs percentage fusion consistency by week")
    save("model_1", "m1_fusion_consistency.png")

# Model 3: covariate / share panel
p = os.path.join(PROG, "model_3", "couple_weeks_model3.csv")
df = pd.read_csv(p)
if "pF_med" in df.columns and "industry" in df.columns:
    s = df.groupby("industry")["pF_med"].apply(lambda x: pd.to_numeric(x, errors="coerce").mean())
    s = s.dropna().sort_values().tail(12)
    plt.barh(range(len(s)), s.values, color="#4a6fa5", alpha=.85)
    plt.yticks(range(len(s)), s.index, fontsize=8)
    plt.xlabel("mean estimated fan share"); plt.title("Model 3 — fan support by celebrity industry")
    save("model_3", "m3_industry_fan_share.png")
if {"age", "pF_med"}.issubset(df.columns):
    a = pd.to_numeric(df["age"], errors="coerce")
    b = pd.to_numeric(df["pF_med"], errors="coerce")
    plt.scatter(a, b, s=9, alpha=.3, color="#6b4a7a")
    plt.xlabel("celebrity age"); plt.ylabel("estimated fan share")
    plt.title("Model 3 — age vs reconstructed fan support")
    save("model_3", "m3_age_fan_share.png")

print("new session:", dst)
print("problem chars:", len(problem))
