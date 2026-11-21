"""
Model 3 — Step 1: Data preparation and latent fan-vote reconstruction.

Builds a contestant-week panel from the raw CSV and estimates latent fan-vote
shares via constrained Dirichlet sampling (feasible-set posterior, the scheme
from the shared master plan's Model 1, re-implemented here so Model 3 is
self-contained):

  f_w ~ Dirichlet(kappa * softmax(mu_w))  per week w, with
  mu_i,w = a + b1*(jury-percentile of judge score) + b2*(weeks survived)
           + b3*(industry fame proxy)
  subject to the observed elimination constraint under the season's rule:
    - PCT rule (seasons 3-27): eliminated couple has min  0.5*jhat + 0.5*f
    - RANK rule (seasons 1-2, 28-34): eliminated couple within bottom-2 of
      combined rank-sum (judges-save regime => must be in bottom 2, not
      necessarily the worst).

Outputs: panel.csv (one row per contestant-week, posterior mean/sd fan share),
fan_draws.csv (a subset of full posterior draws for downstream uncertainty
propagation), fan_weekly_summary.csv.
"""
import numpy as np
import pandas as pd
from scipy import stats

RNG = np.random.default_rng(2026)
DATA = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r2-c3-budget-mwnsidnh/data/2026_MCM_Problem_C_Data.csv'
OUT = '/Users/mac/Documents/学习/找工作/SolveX/bench/sessions/r2-c3-budget-mwnsidnh/02_programming/model_3'

N_WEEKS = 11  # data carries week1..week10 scores (+11 judge columns)
N_DRAWS_KEEP = 200          # draws kept per contestant-week for propagation
N_DRAWS_REJECT = 6000       # rejection-sampling draws per week
KAPPA = 25.0                # Dirichlet concentration around prior softmax

# Industry fame proxy (prior TV prominence, documented heuristic coding):
# high-name-recognition industries get larger base fan pull.
FAME = {
    'Actor/Actress': 1.0, 'Athlete': 0.9, 'Singer/Rapper': 1.0,
    'TV Personality': 0.7, 'Model': 0.6, 'Comedian': 0.6,
    'Social Media Personality': 0.6, 'social media personality': 0.6,
    'Racing Driver': 0.5, 'Radio Personality': 0.4, 'Entrepreneur': 0.3,
    'News Anchor': 0.5, 'Politician': 0.5, 'Sports Broadcaster': 0.5,
}
DEFAULT_FAME = 0.3  # niche industries

df = pd.read_csv(DATA, encoding='utf-8-sig')

# Industry consolidation into 6 groups (Model 3 covariates)
IND_MAP = {
    'Actor/Actress': 'Actor', 'Athlete': 'Athlete', 'Singer/Rapper': 'Musician',
    'Racing Driver': 'Athlete', 'TV Personality': 'TV Host',
    'Model': 'Model/Other', 'Comedian': 'Comedian',
    'Social Media Personality': 'TV Host', 'social media personality': 'TV Host',
    'Radio Personality': 'TV Host', 'News Anchor': 'TV Host',
    'Sports Broadcaster': 'TV Host',
    'Beauty Pagent': 'Model/Other', 'Magician': 'Comedian',
    'Astronaut': 'Model/Other', 'Fashion Designer': 'Model/Other',
    'Motivational Speaker': 'TV Host', 'Military': 'Model/Other',
    'Journalist': 'TV Host', 'Musician': 'Musician', 'Producer': 'Model/Other',
    'Fitness Instructor': 'Athlete', 'Con artist': 'TV Host',
    'Conservationist': 'Model/Other',
}
df['industry_group'] = df['celebrity_industry'].map(IND_MAP).fillna('Model/Other')
df['fame'] = df['celebrity_industry'].map(FAME).fillna(DEFAULT_FAME)


def parse_results(r):
    if r.startswith('Eliminated Week'):
        return int(r.split()[-1]), None   # (elimination week, no finale place)
    place = None
    for p in ('1st', '2nd', '3rd', '4th', '5th'):
        if r.startswith(p):
            place = int(p[0]) if p[0].isdigit() else None
    if '1st Place' in r: place = 1
    elif '2nd Place' in r: place = 2
    elif '3rd Place' in r: place = 3
    elif '4th Place' in r: place = 4
    elif '5th Place' in r: place = 5
    return 99, place  # finalists: "eliminated" at week 99


def week_judge_score(row, w):
    """Mean of available judge scores in week w (0 / N/A after elimination)."""
    vals = []
    for j in range(1, 5):
        v = row.get(f'week{w}_judge{j}_score', 'N/A')
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > 0:
            vals.append(fv)
    return np.mean(vals) if vals else np.nan


rows = []
for _, r in df.iterrows():
    elim_week, place = parse_results(str(r['results']))
    last_comp = N_WEEKS
    scores = {}
    for w in range(1, N_WEEKS + 1):
        s = week_judge_score(r, w)
        if not np.isnan(s):
            scores[w] = s
        else:
            break
    last_comp = max(scores) if scores else 0
    rows.append(dict(
        celebrity=r['celebrity_name'], pro=r['ballroom_partner'],
        industry=r['celebrity_industry'], industry_group=r['industry_group'],
        fame=r['fame'], age=int(r['celebrity_age_during_season']),
        homestate=r['celebrity_homestate'], season=int(r['season']),
        elimination_week=min(elim_week, last_comp + 1) if elim_week < 99 else 99,
        placement=place, scores=scores, last_comp_week=last_comp))

panel_rows = []
weekly_summary = []
fan_draw_records = []
rule_check_log = []

seasons = sorted({rr['season'] for rr in rows})
for s in seasons:
    srows = [rr for rr in rows if rr['season'] == s]
    rank_rule = (s <= 2) or (s >= 28)   # documented regime assumption
    max_week = max(rr['last_comp_week'] for rr in srows)
    n_finalists = sum(1 for rr in srows if rr['placement'] is not None)

    # elimination ordering: week k -> set of contestants whose last week is k
    for w in range(1, max_week + 1):
        active = [rr for rr in srows
                  if w <= rr['last_comp_week']]
        # some seasons have non-elimination weeks: if nobody's last competition
        # week is w and w < max_week, no couple was cut that week.
        n_cut = sum(1 for rr in srows if rr['last_comp_week'] == w)
        if n_cut == 0 and w < max_week:
            continue
        scores = np.array([rr['scores'].get(w, np.nan) for rr in active])
        good = ~np.isnan(scores)
        if good.sum() < 2:
            continue
        active_g = [rr for rr, g in zip(active, good) if g]
        sc = scores[good]
        # judge percentile within week
        pct_rank = stats.rankdata(sc) / len(sc)
        # ---- prior mean utilities ----
        mu = np.zeros(len(active_g))
        for k, rr in enumerate(active_g):
            surv = min(w, rr['last_comp_week']) / max(max_week, 1)
            mu[k] = 0.5 + 2.0 * pct_rank[k] + 1.5 * surv + 0.6 * rr['fame']
        mu = mu - mu.mean()
        base_p = np.exp(mu) / np.exp(mu).sum()

        # indices in active_g corresponding to contestants cut this week
        cut_idx = [k for k, rr in enumerate(active_g) if rr['last_comp_week'] == w]

        def satisfies(f):
            if n_cut == 0:
                return True
            if rank_rule:
                # RANK rule (+ judges-save for s>=28): eliminated couple must be
                # in the bottom-2 of the combined rank sum
                rJ = np.argsort(np.argsort(-sc)) + 1          # 1 = best judge
                rF = np.argsort(np.argsort(-f)) + 1           # 1 = most fans
                comb = (rJ + rF).astype(float)
                order = np.argsort(-comb)
                bottom2 = set(order[:min(2, len(order))])
                return all(ci in bottom2 for ci in cut_idx)
            else:
                # PCT rule: eliminated couple has minimum combined percentage
                jhat = sc / sc.sum()
                combined = 0.5 * jhat + 0.5 * f
                elim_set = set(np.argsort(combined)[:max(1, n_cut)])
                return all(ci in elim_set for ci in cut_idx)

        # ---- rejection sampling on the feasible polytope ----
        accepted = []
        tries = 0
        n_dir = KAPPA
        while len(accepted) < N_DRAWS_KEEP and tries < N_DRAWS_REJECT:
            draws = RNG.dirichlet(np.maximum(n_dir * base_p, 1e-3),
                                  size=min(200, N_DRAWS_REJECT - tries))
            tries += len(draws)
            for d in draws:
                if satisfies(d):
                    accepted.append(d)
                    if len(accepted) >= N_DRAWS_KEEP:
                        break
            if tries >= N_DRAWS_REJECT:
                break
        acc = np.array(accepted) if accepted else np.tile(
            base_p / base_p.sum(), (N_DRAWS_KEEP, 1))
        rate = len(accepted) / max(tries, 1)
        rule_check_log.append(dict(season=s, week=w, n_active=len(active_g),
                                   n_cut=n_cut, accept_rate=rate,
                                   rule='RANK' if rank_rule else 'PCT',
                                   constrained=n_cut > 0))

        fmean, fsd = acc.mean(axis=0), acc.std(axis=0)
        flog = np.log(acc)                # logit-scale draws for Model 3 weights
        mu_draws = acc.mean(axis=0)
        for k, rr in enumerate(active_g):
            panel_rows.append(dict(
                celebrity=rr['celebrity'], pro=rr['pro'],
                industry=rr['industry'], industry_group=rr['industry_group'],
                fame=rr['fame'], age=rr['age'], season=s, week=w,
                judge_score=sc[k], judge_pct_in_week=pct_rank[k],
                n_active_week=len(active_g), n_cut=n_cut,
                fan_share_mean=fmean[k], fan_share_sd=fsd[k],
                rule='RANK' if rank_rule else 'PCT',
                constrained=n_cut > 0))
            if k == 0 and w <= 6:  # keep draw matrix sample for one star/week
                pass
        # store draws keyed for join
        for k, rr in enumerate(active_g):
            fan_draw_records.append((s, w, rr['celebrity'],
                                     acc[:, k].tolist()))
    # end weeks

panel = pd.DataFrame(panel_rows)
panel = panel.merge(
    df[['celebrity_name', 'season', 'placement']],
    left_on=['celebrity', 'season'], right_on=['celebrity_name', 'season'],
    how='left')
panel['snorm'] = panel['judge_score'] / 10.0   # max possible per-judge = 10
panel['logit_snorm'] = np.log(panel['snorm'].clip(1e-3, 1 - 1e-3) /
                              (1 - panel['snorm'].clip(1e-3, 1 - 1e-3)))

panel.to_csv(f'{OUT}/panel.csv', index=False)
pd.DataFrame(rule_check_log).to_csv(f'{OUT}/fan_reconstruction_diagnostics.csv',
                                    index=False)

# keep posterior draws for a manageable subset (first 60 weeks overall)
fd = pd.DataFrame(fan_draw_records, columns=['season', 'week', 'celebrity',
                                             'draws'])
fd_head = fd.head(400)
fd_head.to_json(f'{OUT}/fan_draws_sample.json', orient='records')

print('panel rows:', len(panel))
print('contestants:', panel['celebrity'].nunique(),
      ' pros:', panel['pro'].nunique())
print('accept-rate summary (constrained weeks):')
diag = pd.DataFrame(rule_check_log)
print(diag.groupby('rule')['accept_rate'].agg(['mean', 'median', 'min']))
print(diag[diag.constrained].accept_rate.describe())
print('\nSanity: top fan-share celebrities (cumulative):')
top = panel.groupby('celebrity')['fan_share_mean'].mean().sort_values(
    ascending=False).head(8)
print(top)
print('\nBobby Bones grand mean fan share:',
      round(panel[panel.celebrity == 'Bobby Bones']['fan_share_mean'].mean(), 3))
