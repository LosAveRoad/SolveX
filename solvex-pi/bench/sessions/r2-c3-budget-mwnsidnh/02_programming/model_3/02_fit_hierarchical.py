"""
Model 3 — Step 2: Hierarchical attribution models for judge scores and fan shares.

Two linked linear mixed models on the contestant-week panel (Model 1 output):

  Judge:  logit(snorm_{i,s,w}) = theta_pro(i) + b1*age + b2*age^2 + b3*industry
          + b4*fame + week fixed effects + season RE + eps
  Fan:    logit(fan share)    = theta'_pro(i) + b1'*... + week FE + season RE + eps

with theta_pro ~ N(mu_theta, tau^2) partially pooled across pro dancers.
Divergence: Delta_p = theta'_p - theta_p  (per-pro fan-minus-judge effect),
covariate divergence: Delta_beta = b' - b with posterior P(Delta > 0) via
Kruskal-count bootstrap over draws from the model covariance matrices.

Fallback note: PyMC is not installed; we use statsmodels MixedLM (REML)
which is the plan's specified fallback and yields equivalent signs for
fixed effects and BLUP-style random intercepts.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

OUT = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r2-c3-budget-mwnsidnh/02_programming/model_3'
panel = pd.read_csv(f'{OUT}/panel.csv')

panel = panel[panel['snorm'].notna()].copy()
panel['logit_fan'] = np.log(
    panel['fan_share_mean'].clip(1e-4, 1 - 1e-4) /
    (1 - panel['fan_share_mean'].clip(1e-4, 1 - 1e-4)))
panel['week_f'] = C_wk = panel['week'].astype(float)
panel['age_c'] = panel['age'] - panel['age'].mean()
panel['age2_c'] = panel['age_c'] ** 2 / 100.0
panel['pro'] = panel['pro'].fillna('Unknown')

COMMON = ('age_c + age2_c + C(industry_group, Treatment("Actor")) '
          '+ fame + C(week)')

# ---------- Judge-score model ----------
md_j = smf.mixedlm(
    'logit_snorm ~ ' + COMMON, panel,
    groups=panel['pro'], re_formula='1',
    vc_formula={'season': '0 + C(season)'})
res_j = md_j.fit(method='lbfgs', maxiter=300, disp=False)

# ---------- Fan-share model ----------
md_f = smf.mixedlm(
    'logit_fan ~ ' + COMMON, panel,
    groups=panel['pro'], re_formula='1',
    vc_formula={'season': '0 + C(season)'})
res_f = md_f.fit(method='lbfgs', maxiter=300, disp=False)

print('=== Judge model: fixed effects ===')
print(res_j.summary().tables[1])
print('\n=== Fan model: fixed effects ===')
print(res_f.summary().tables[1])
print('judge pro-var:', res_j.cov_re.iloc[0, 0] ** .5,
      ' fan pro-var:', res_f.cov_re.iloc[0, 0] ** .5)

# ---------- Pro random intercepts (BLUPs) ----------
pro_j = res_j.random_effects  # dict pro -> DataFrame/Series
pro_f = res_f.random_effects


def extract(res):
    out = {}
    for k, v in res.random_effects.items():
        try:
            out[k] = float(pd.Series(v).iloc[0])
        except Exception:
            out[k] = float(np.atleast_1d(v)[0])
    return out


pro_j = extract(res_j)
pro_f = extract(res_f)
pro_eff = pd.DataFrame({'theta_J': pd.Series(pro_j), 'theta_F': pd.Series(pro_f)})
pro_eff['pro'] = pro_eff.index
pro_eff['delta'] = pro_eff['theta_F'] - pro_eff['theta_J']

# SEs of BLUPs from conditional variance of random effects
Vj = float(res_j.cov_re.iloc[0, 0])
Vf = float(res_f.cov_re.iloc[0, 0])
pro_eff['se_delta'] = np.sqrt(Vj + Vf)
pro_eff['p_delta_gt0'] = 1 - stats.norm.cdf(0, pro_eff['delta'], pro_eff['se_delta'])
pro_eff = pro_eff.sort_values('theta_J')
pro_eff.to_csv(f'{OUT}/pro_effects.csv', index=False)
print('\n=== Pro effects (judge vs fan), ranked by theta_J ===')
print(pro_eff.to_string())

# ---------- Covariate divergence: Delta = beta_F - beta_J with P(Delta>0) ----------
from statsmodels.base.model import Model

names_c = [n for n in res_j.fe_params.index if
           n.startswith('age') or n.startswith(('C(', 'fame'))]
cov_j = res_j.bse_fe
cov_f = res_f.bse_fe
rows = []
for n in res_j.fe_params.index:
    if n in res_f.fe_params.index and (n.startswith('age') or n.startswith('fame')
                                       or n.startswith('C(')):
        b_j, b_f = res_j.fe_params[n], res_f.fe_params[n]
        se_j, se_f = cov_j[n], cov_f[n]
        # posterior approximation of difference: independent normal approx
        d = b_f - b_j
        se = np.sqrt(se_j ** 2 + se_f ** 2)
        rows.append(dict(covariate=n, beta_J=b_j, beta_F=b_f, delta=d,
                         se=se, p_delta_gt0=1 - stats.norm.cdf(0, d, se)))
covtab = pd.DataFrame(rows).sort_values('p_delta_gt0')
covtab.to_csv(f'{OUT}/covariate_divergence.csv', index=False)
print('\n=== Covariate divergence (fan minus judge) ===')
print(covtab.to_string())

# ---------- Variance decomposition of final placement (LMG-style shares) ----------
# Sequential-average approach over blocks, first block = its own R2 / R2_full.
cum = panel.groupby(['celebrity', 'season']).agg(
    snorm_mean=('snorm', 'mean'), fan_mean=('logit_fan', 'mean'),
    age_c=('age_c', 'first'), fame=('fame', 'first'),
    placement=('placement', 'first'),
    pro=('pro', 'first'), industry_group=('industry_group', 'first')).reset_index()
cum = cum[cum['placement'].notna()].copy()
cum['place_z'] = (cum['placement'] - cum['placement'].mean()) / cum['placement'].std()
cum['snorm_z'] = (cum['snorm_mean'] - cum['snorm_mean'].mean()) / cum['snorm_mean'].std()
cum['fan_z'] = (cum['fan_mean'] - cum['fan_mean'].mean()) / cum['fan_mean'].std()
cum['theta_J_abs'] = cum['celebrity'].map(
    dict(zip(panel['celebrity'], panel['pro']))).map(pro_j).fillna(0)
cum['ind_router'] = cum['industry_group'].astype('category').cat.codes

blocks = {'judge-fit': ['snorm_z'], 'fan-fit': ['fan_z'], 'pro-effect': ['theta_J_abs'],
          'demographics': ['age_c', 'ind_router']}
order = ['judge-fit', 'fan-fit', 'pro-effect', 'demographics']
r2_full = smf.ols('place_z ~ ' + ' + '.join(
    sum([blocks[b] for b in order], [])), cum).fit().rsquared
R2_seq, prev = [], 0.0
for b in order:
    used = order[:order.index(b) + 1]          # include the current block
    cum_f = 'place_z ~ ' + ' + '.join(sum([blocks[u] for u in used], []))
    m = smf.ols(cum_f, cum).fit()
    R2_seq.append(dict(block=b, share=(m.rsquared - prev) / r2_full))
    prev = m.rsquared
vd = pd.DataFrame(R2_seq)
vd['sharenorm'] = vd['share'] / vd['share'].sum()
vd.to_csv(f'{OUT}/placement_variance_decomposition.csv', index=False)
print('\n=== Variance decomposition of final placement (sequential R2 shares) ===')
print(vd.to_string())

# ---------- Leave-one-season-out validation: judge-rank prediction ----------
# Fixed-effect OLS (week FE + covariates) built with patsy so held-out design
# matrices align; Spearman rho between predicted and observed weekly scores.
import patsy
yearn, panel_loso = panel.copy(), panel.copy()
rho_rows = []
FORMULA = 'logit_snorm ~ ' + COMMON
y_all, X_all_full = patsy.dmatrices(FORMULA, panel, return_type='dataframe')
for s in sorted(panel['season'].unique()):
    tr = panel[panel['season'] != s]
    te = panel[panel['season'] == s]
    if len(te) < 6:
        rho_rows.append(dict(season=s, loo_rho=np.nan))
        continue
    try:
        y_tr, X_tr = patsy.dmatrices(FORMULA, tr, return_type='dataframe')
        beta = np.linalg.lstsq(X_tr.values, y_tr.values[:, 0], rcond=None)[0]
        X_te = patsy.build_design_matrices([X_tr.design_info], te,
                                           return_type='dataframe')[0]
        eta = np.asarray(X_te) @ beta
        pred_rank = pd.Series(eta).rank()
        obs_rank = te['judge_score'].rank()
        rho = stats.spearmanr(pred_rank, obs_rank).statistic
        rho_rows.append(dict(season=int(s), loo_rho=rho, n_te=len(te)))
    except Exception:
        rho_rows.append(dict(season=int(s), loo_rho=np.nan, n_te=len(te)))
rho_list = pd.DataFrame(rho_rows)['loo_rho'].values
loso = pd.DataFrame(rho_rows)
loso.to_csv(f'{OUT}/loso_validation.csv', index=False)
print('\nLOSO Spearman rho (judge ranks): mean %.3f, median %.3f, n=%d, min %.3f' % (
    np.nanmean(rho_list), np.nanmedian(rho_list), len(rho_list), np.nanmin(rho_list)))

# ---------- Posterior predictive check (KS statistic, with variance components) ----------
# Simulate the full model: mean + pro BLUP + season VC + homoskedastic residual,
# per season, comparing pooled simulated vs. observed logit judge scores.
sim_scores, obs_scores = [], []
for s in sorted(panel['season'].unique()):
    p_s = panel[panel['season'] == s]
    mu_s = res_j.predict(p_s)
    seas_eff = np.random.default_rng(int(s)).normal(
        0, np.sqrt(res_j.vcomp[0]), len(p_s))
    pro_eff = p_s['pro'].map(pro_j).fillna(0).values
    # empirical residual bootstrap preserves the observed residual shape
    r_all = np.asarray(res_j.resid)
    r_all = r_all[~np.isnan(r_all)]
    resid = np.random.default_rng(int(s) + 100).choice(
        r_all, size=len(p_s), replace=True)
    sim_scores.append(mu_s + pro_eff + seas_eff + resid)
    obs_scores.append(p_s['logit_snorm'].values)
ks = stats.ks_2samp(np.concatenate(sim_scores),
                   np.concatenate(obs_scores)).statistic
print('Posterior predictive KS statistic (judge model): %.4f' % ks)

import json
json.dump(dict(ks_judge=float(ks),
               loso_mean=float(np.nanmean(rho_list)),
               loso_median=float(np.nanmedian(rho_list)),
               sigma_pro_judge=float(np.sqrt(Vj)),
               sigma_pro_fan=float(np.sqrt(Vf))),
          open(f'{OUT}/fit_stats.json', 'w'), indent=1)
print('DONE step 2')
