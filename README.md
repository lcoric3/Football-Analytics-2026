# Football-Analytics-2026

A football data science and machine learning pipeline for Croatian HNL (1. HNL)
2025/2026 player statistics, built on the [SportMonks](https://www.sportmonks.com/)
Football API.

**The problem it solves:** raw player statistics (goals, tackles, passes...)
aren't directly comparable - players differ in position, playing time, and
role. This project turns a raw SportMonks API response into an explainable
scouting system: per-90 normalized metrics, percentile-based scouting scores
that account for position, and ML-driven similarity search - the kind of
first-pass shortlisting a recruitment analyst would build before handing
names to a human scout.

## What it does

The pipeline turns raw SportMonks player statistics into scouting-ready
rankings, charts, and an ML-ready dataset:

```
SportMonks API -> raw data -> cleaned data -> feature engineering
-> scouting scores -> analysis rankings -> visualizations -> ML dataset
-> Markdown report
```

## Screenshots

A few of the 19 charts generated in `reports/figures/` (see the full,
narrated set in [`reports/hnl_2025_2026_scouting_report.md`](reports/hnl_2025_2026_scouting_report.md)):

| | |
|---|---|
| ![Top 15 overall players](reports/figures/top_overall_players.png) | ![Team talent map](reports/figures/team_talent_map.png) |
| Top overall players by `overall_score` | Average outfield `overall_score` per club |
| ![Role radar comparison](reports/figures/role_radar_examples.png) | ![Overall score distribution by position](reports/figures/position_score_distribution.png) |
| Statistical "shape" of three example players | Why scoring is position-aware |

## Setup

### 1. Get a SportMonks API token

Sign up at SportMonks and copy your API token. **Never hardcode the token
in code** - it is always read from the environment variable
`SPORTMONKS_API_TOKEN`.

Set it for your current PowerShell session:

```powershell
$env:SPORTMONKS_API_TOKEN = "your_token_here"
```

Or copy the example env file and fill in your token - `.env` is already
covered by `.gitignore`, so it never gets committed:

```powershell
copy .env.example .env
```

```
SPORTMONKS_API_TOKEN=your_token_here
```

### 2. (Optional) override league/season lookup

`fetch_data.py` automatically searches SportMonks for the "HNL" league and
its "2025/2026" season. If your subscription names them differently (or
the search returns more than one candidate), skip the lookup by setting:

```
HNL_LEAGUE_ID=<id>
HNL_SEASON_ID=<id>
```

### 3. Install requirements

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Run the pipeline

```powershell
python main.py
```

### 5. Run the tests

The test suite (`tests/`) uses small synthetic data fixtures - it never
calls the SportMonks API and never needs `SPORTMONKS_API_TOKEN` or a `.env`
file:

```powershell
pip install -r requirements.txt
pytest
```

### 6. Run the dashboard

The Streamlit dashboard is a read-only view over the CSVs, charts, and
reports `python main.py` already produced - it never calls the SportMonks
API and never writes any data file, so run the pipeline at least once
first:

```powershell
streamlit run app.py
```

## Project structure

```
Football-Analytics-2026/
├── main.py                  # Orchestrator - runs each pipeline stage in order
├── app.py                   # Streamlit dashboard - reads data/reports only, no API calls
├── requirements.txt
├── .env.example              # Template for SPORTMONKS_API_TOKEN - copy to .env
├── tests/                    # pytest suite - synthetic data, no API/.env needed
├── src/
│   ├── sportmonks_client.py # API client: auth, pagination, retries, rate limits
│   ├── fetch_data.py        # Finds HNL league/season, fetches player stats
│   ├── clean_data.py        # Raw JSON/CSV -> clean flat schema
│   ├── feature_engineering.py # Per-90 metrics and ratios
│   ├── scouting_scores.py   # Attacking/creative/defensive/discipline/overall scores
│   ├── analysis.py          # Ranking tables (top scorers, best defenders, etc.)
│   ├── visualization.py     # matplotlib charts
│   ├── ml_models.py         # Similarity, clustering, optional regression
│   ├── replacement_scouting.py # Replacement-target shortlists (statistical, not a verdict)
│   └── report.py            # Markdown scouting report
├── data/
│   ├── raw/                 # Raw SportMonks JSON + CSV
│   ├── processed/           # Cleaned + feature-engineered CSVs
│   └── output/               # Final ranking CSVs
├── notebooks/                # Exploratory analysis
└── reports/figures/          # Generated charts
```

## Generated files

| File | Produced by | Description |
|---|---|---|
| `data/raw/hnl_player_stats_raw_2025_2026.json` / `.csv` | `fetch_data.py` | Raw SportMonks API response |
| `data/processed/hnl_player_stats_clean_2025_2026.csv` | `clean_data.py` | Cleaned, flat player statistics |
| `data/processed/hnl_player_features_2025_2026.csv` | `feature_engineering.py` | Adds per-90 metrics and ratios |
| `data/processed/hnl_player_scored_2025_2026.csv` | `scouting_scores.py` | Adds scouting scores |
| `data/output/top_players_hnl_2025_2026.csv` | `analysis.py` | Ranking tables (top scorers, defenders, etc.) |
| `data/output/specialist_rankings_hnl_2025_2026.csv` | `analysis.py` | Dribblers, passers, duel defenders, progressive midfielders, passer/ball-playing defenders, creators, ball winners, and U23 versions of those |
| `reports/figures/*.png` | `visualization.py` | Charts (19 total - leaderboards, scatter plots, a radar chart) |
| `data/processed/hnl_ml_features_2025_2026.csv` | `ml_models.py` | ML-ready dataset |
| `data/output/player_similarity_results.csv` | `ml_models.py` | Example player-similarity searches |
| `data/output/player_clusters.csv` | `ml_models.py` | Every eligible player's cluster assignment and name |
| `reports/player_cluster_profiles.md` | `ml_models.py` | Per-cluster profile: top players, average age/minutes, playing-style description |
| `data/output/replacement_targets.csv` | `replacement_scouting.py` | Example replacement-target shortlists |
| `reports/hnl_2025_2026_scouting_report.md` | `report.py` | Markdown scouting report - embeds every chart with an explanation |

## Scouting scores

Raw per-90 metrics live on very different scales (a good `goals_per90` is
~0.5, a good `passes_per90` is ~50), so they can't be averaged directly.
Every score below is built from **percentile ranks**: each metric is
converted to "this player is better than X% of HNL players in this stat"
(0-100), which puts everything on the same scale before combining it.

Scores are only computed for players with at least 450 minutes played
(~5 full matches) - below that, per-90 rates are too noisy (a single
lucky goal in 30 minutes would look like a superstar rate) and the score
is left blank (`NaN`) instead of being misleading.

| Score | Built from (percentile of...) | Position-aware? |
|---|---|---|
| `attacking_score` | `goals_per90`, `shots_on_target_per90`, `goal_conversion` | Yes - vs. same position |
| `creative_score` | `assists_per90`, `passes_per90`, `pass_accuracy_ratio` | Yes - vs. same position |
| `defensive_score` | `tackles_per90`, `interceptions_per90`, `duel_success_rate` | Yes - vs. same position |
| `discipline_score` | 100 minus percentile of `cards_per90` (fewer cards = higher score) | No - whole pool |
| `overall_score` | `0.3 * attacking + 0.3 * creative + 0.3 * defensive + 0.1 * discipline` | Inherits the above |
| `dribbling_score` | `successful_dribbles_per90`, `dribble_success_rate`, `fouls_drawn_per90` | No - whole pool |
| `passing_score` | `passes_per90`, `key_passes_per90`, `accurate_crosses_per90`, `accurate_long_balls_per90`, `pass_accuracy_ratio` | No - whole pool |
| `duel_defending_score` | `tackles_per90`, `interceptions_per90`, `duel_success_rate`, `aerials_won_per90`, `clearances_per90`, minus a light `cards_per90` penalty | No - whole pool |
| `progressive_midfielder_score` | `key_passes_per90`, `long_balls_per90`, `successful_dribbles_per90`, `assists_per90` (a proxy - SportMonks doesn't expose true progressive passes/carries on this plan) | Yes - vs. same position |
| `passer_defender_score` (a.k.a. ball-playing defender) | 50% passing (within-position `passes_per90`/accuracy/long balls/key passes) + 50% `defensive_score` | Yes - vs. same position |
| `goalkeeper_score` | `saves_per90`, `clean_sheet_rate`, `goals_conceded_per90` (inverted), `penalties_saved`, `pass_accuracy_ratio` | Goalkeepers only |

**Goalkeepers are excluded from `overall_score`-based rankings**
(`best_overall`, `best_u23`, and the corresponding charts) because that
score is built entirely from outfield actions goalkeepers essentially
never record - it isn't a meaningful measure of goalkeeping quality (see
`position_score_distribution.png` for the evidence). They get their own
`best_goalkeepers` ranking instead, sorted by `goalkeeper_score`. They are
never removed from the underlying data - `hnl_player_stats_clean_2025_2026.csv`
and the ML dataset both keep every goalkeeper.

"Position-aware" means the percentile is computed *within* each position
group (Defender vs. Defender, Midfielder vs. Midfielder, ...) instead of
against the whole pool. This matters for two reasons: (1) a defender's
`attacking_score` computed against the whole pool is mostly noise, since
it's really just measuring "is this player not a defender"; and (2) it
stops `overall_score` from structurally favoring all-round midfielders
over positional specialists, since a specialist is now judged against
players who do the same job, not against the whole league.

`dribbling_score`, `passing_score`, and `duel_defending_score` are kept
pool-wide on purpose - they answer "who's the best dribbler/passer/
ball-winner in the whole league", the same kind of open leaderboard as
`top_scorers`/`top_assists`, not "best dribbler for a full-back".

## Young talent and age-aware potential scoring

`overall_score` answers "who's producing well right now" - it says
nothing about whether a player is young enough to still be improving, or
whether their output is backed by real, proven playing time.
`age_potential_score` adds that lens, as a simple additive formula:

```
age_potential_score = overall_score + age_bonus + reliability_bonus
```

- **`age_bonus`**: +2.0 points for every year younger than 23 (this
  project's U23 cutoff), capped at 6 years below it - so a 17-year-old
  and a 15-year-old both get the same capped maximum of +12, rather than
  an ever-larger reward the younger a player gets.
- **`reliability_bonus`**: a percentile rank of minutes played (0-100)
  among scoring-eligible players, scaled down to at most +8 points -
  rewards a young player who's already earning real first-team minutes,
  not just a promising cameo.

Like `overall_score`, this is an outfield-only lens (not meaningful for
goalkeepers). Three rankings use it, saved to
`data/output/top_players_hnl_2025_2026.csv`:

- **`best_young_talents`** / **`best_u23_players_by_potential`** - the
  same U23 pool (age <= 23) and sort order under two category labels:
  `best_young_talents` is the natural headline name, while
  `best_u23_players_by_potential` sits next to `best_u23` in the output so
  the "current output" vs. "potential-adjusted" comparison for the same
  age bracket is explicit.
- **`best_u21_players`** - a stricter age <= 21 bracket, sorted by
  `age_potential_score`.

## Team-context and underrated scoring

`overall_score` is computed against the *whole* HNL player pool, so it
never asks "compared to their own teammates". Three extra columns add
that context:

| Column | Meaning |
|---|---|
| `team_average_score` | Mean `overall_score` of a team's own eligible outfield players (goalkeepers excluded, same reasoning as `best_overall`). |
| `score_above_team_average` | `overall_score - team_average_score` - a literal gap, positive means "outperforms their own teammates". |
| `underrated_score` | `overall_score + standout_bonus + weak_team_bonus` - see `scouting_scores.py` for the exact caps/weights. |

**Important - `underrated_players` can still include big-club players.**
`underrated_players` is sorted by `underrated_score`, which rewards
outperforming your *own* teammates regardless of how strong the squad
around you is - so a Dinamo Zagreb or Hajduk Split player who clearly
outshines their (already strong) teammates can legitimately top this
list. It is **not** a "small club only" list. For that, use:

- **`hidden_gems`** - requires *both* outperforming your own team **and**
  playing for a squad whose average outfield output sits below the
  league's average team (a computed proxy for a smaller/weaker club,
  replacing an earlier fixed list of "big clubs").
- **`small_club_standouts`** - requires only the second condition (a
  below-average squad), sorted by plain `overall_score` rather than the
  blended score - "who's the best individual performer at a smaller
  club", regardless of the gap to their own teammates.

None of these are a market-value or "true team strength" model - they're
reproducible statistical proxies for visibility, not scouting verdicts.

`analysis.py` still filters to a position group before sorting for
position-specific rankings (e.g. "best defenders", "best progressive
midfielders") - position-aware scoring and position-filtered rankings are
complementary, not the same thing.

## Machine learning notes

`ml_models.py` builds `data/processed/hnl_ml_features_2025_2026.csv` from
players who cleared the same 450-minute eligibility bar, using only
per-90/ratio features (never raw totals, so playing time doesn't bias
the comparison). Three things are done with it:

- **Player similarity (cosine similarity):** standardizes each feature,
  then measures the angle between two players' stat vectors. Close to
  1.0 means "similar statistical profile", independent of team or league
  position.

  **In simple scouting terms:** picture each player as a list of numbers -
  their rates in the stats that matter for a role (a striker's list might
  be `[goals_per90, shots_per90, shot_accuracy, ...]`). That list is a
  point in space. Cosine similarity measures the *angle* between two
  players' points, not the distance - so it compares *playing style*, not
  *playing time*. A bench player with 400 minutes and a nailed-on starter
  with 2500 minutes can still score close to 1.0 if their per-90 rates
  have the same shape (e.g. both take a lot of shots but rarely score),
  even though a raw-totals comparison would say they have nothing in
  common just because one has played far more matches.

  Comparing a striker to a centre-back on `shots_per90` isn't useful (the
  centre-back will always look like an outlier), so similarity search is
  **role-based** - it only compares players on the stats relevant to the
  chosen role:

  | Role | Compares players on |
  |---|---|
  | `overall` | every per-90/ratio feature (general "who plays like this player") |
  | `attacker` | goals, shots, shot accuracy, conversion, goal contribution |
  | `midfielder` | passing, key passes, assists, tackles, interceptions, dribbling |
  | `defender` | tackles, interceptions, duel success, aerials, clearances, cards |
  | `dribbler` | successful dribbles, dribble success rate, fouls drawn |
  | `passer` | passes, key passes, pass accuracy, long balls, crosses |
  | `progressive_midfielder` | key passes, long balls, dribbles, assists |
  | `duel_defender` | tackles, interceptions, duel success, aerials, clearances |
  | `passer_defender` / `ball_playing_defender` | passing volume/quality + tackles/interceptions/duel success (same feature set for both - they share one score, see above) |
  | `goalkeeper` | saves, clean sheet rate, goals conceded, pass accuracy - almost always combine with `same_position_only=True` (below), since a goalkeeper's near-zero outfield numbers otherwise still get compared against every outfield player |

  **Optional filters** (applied to candidates only, after similarity is
  computed against the full pool - see `ml_models.find_similar_players`):
  `same_position_only` (exact `position` match), `same_team_exclude`
  (drop the query player's own club), `min_minutes` (a stricter
  reliability floor), `max_age` (e.g. for "similar young players").

  Example - find midfielders similar to Ismaël Bennacer (strict,
  same-position match), and players similar to Sergi Domínguez as a
  passer-defender:

  ```python
  from src import ml_models
  import pandas as pd

  scored_df = pd.read_csv("data/processed/hnl_player_scored_2025_2026.csv")
  ml_df = ml_models.build_ml_dataset(scored_df)

  ml_models.find_similar_players(ml_df, "Ismaël Bennacer", role="midfielder", same_position_only=True, top_n=10)
  ml_models.find_similar_players(ml_df, "Sergi Domínguez", role="passer_defender", top_n=10)
  ml_models.find_similar_players(ml_df, "Dion Beljo", role="attacker", top_n=10)
  ml_models.find_similar_players(ml_df, "Adriano Jagusic", role="overall", max_age=23, top_n=10)
  ```

  A handful of example searches (including all four above) are saved to
  `data/output/player_similarity_results.csv` on every pipeline run.
- **KMeans clustering:** groups players into named playing-style
  archetypes purely by statistical shape - see the dedicated "Player
  clustering" section below.
- **Optional supervised prediction (rating, goals):** both are skipped
  automatically, with an explanation logged, if there are fewer than 30
  eligible players. Even when they run, treat the results cautiously:
  - `rating` is itself partly derived from the same match events as our
    features, so a good R2 mostly confirms the features are sensible
    rather than predicting something genuinely new.
  - `goals` prediction deliberately excludes any feature derived from
    goals (`goals_per90`, `goal_conversion`, etc.) to avoid leaking the
    answer into the input - it predicts from raw shot/pass/defensive
    volume instead.

**Bottom line:** with one HNL season (a few hundred players), this
project is currently a stronger fit for scouting/ranking and unsupervised
ML (similarity, clustering) than for supervised prediction. Multiple
seasons of history would give a regression model enough rows and a
clearer signal to be worth trusting.

## Player clustering

**Clustering groups players by statistical profile, not by absolute
quality.** KMeans has no notion of "good" or "bad" - it only finds
players whose per-90 rates sit close together in feature space, the same
underlying idea as the cosine-similarity search above but grouping many
players instead of comparing two. An elite player and a modest one can
land in the same cluster if their rates have a similar *shape* (e.g. both
pass a lot and rarely shoot) - a cluster describes a **playing style**,
not a tier.

Goalkeepers are clustered separately from outfield players (their
near-zero outfield stats would otherwise just form one arbitrary
"goalkeeper" cluster and add noise to the outfield archetypes): 8 KMeans
clusters for outfield players (on the same per-90/ratio features used
elsewhere in this project), 2 for goalkeepers (on saves, clean sheets,
goals conceded, and pass accuracy).

Each cluster is named by comparing its own average stats against the
population average (a z-score per feature), then checking how well that
profile matches one of a set of predefined "archetype signatures" - e.g.
a cluster with above-average tackles/interceptions and below-average
passing matches "defensive ball winners". **If no archetype clears a
confidence bar, the cluster keeps a neutral name** like `balanced profile`
instead of a forced/misleading label - see `OUTFIELD_ARCHETYPE_SIGNATURES`
in `ml_models.py` for the full list of named archetypes and their
signatures.

**Cluster names describe playing style, not literal position** -
clustering looks only at per-90 stats, never at the `position` column, so
an archetype like "ball-playing defenders" can include a deep-lying
midfielder whose tackle/pass profile matches that style.

Outputs, saved on every pipeline run:

- `data/output/player_clusters.csv` - every eligible player with their
  `cluster_id`, `cluster_name`, and a `quality_score` (`overall_score` for
  outfield players, `goalkeeper_score` for goalkeepers - used only to
  pick example players to display, never as a clustering input).
- `reports/player_cluster_profiles.md` - one section per cluster: player
  count, average age/minutes, a plain-English "playing style" description,
  and a table of top players by `quality_score`.

## Replacement scouting

**This is a statistical shortlist, not a final transfer recommendation.**
`src/replacement_scouting.py` builds on the similarity search above:
given a departing player, it re-ranks the filtered candidate pool by a
`replacement_score` that blends four signals plus one small tie-breaker:

```
replacement_score = 0.4 * (similarity * 100)
                   + 0.3 * age_potential_score
                   + 0.2 * underrated_score
                   + 0.1 * reliability_percentile
                   + younger_bonus (+5 if candidate is younger than the departing player)
```

- **similarity** (highest weight) - is the candidate actually the same
  *kind* of player? A statistically dissimilar candidate isn't a real
  replacement no matter how good their other numbers are.
- **`age_potential_score`** - good now, with runway to keep improving
  (see the young-talent scoring above).
- **`underrated_score`** - a nod toward value, not just quality (see
  team-context scoring above).
- **`reliability_percentile`** - minutes rank *within this specific
  candidate pool* - has this candidate already proven they can start.

By default, `same_position_only=True` and `same_team_exclude=True` (a
replacement is normally sought at the same position, outside the
player's own squad), and the role defaults to whatever matches the
departing player's own position.

```python
from src import replacement_scouting

replacement_scouting.find_replacement_targets(ml_df, "Dion Beljo")
replacement_scouting.find_replacement_targets(ml_df, "Ismaël Bennacer")
replacement_scouting.find_replacement_targets(ml_df, "Sergi Domínguez")
replacement_scouting.find_replacement_targets(ml_df, "Gabriel Vidovic", max_age=23)
```

Examples for all four are saved to `data/output/replacement_targets.csv`
on every pipeline run. **It says nothing about video-scouted technique,
tactical fit, injury history, character, or transfer feasibility (fee,
release clause, wages, contract length)** - treat it as a reproducible
first-pass shortlist for a human scout to start from, not a conclusion.

## Specialist rankings

Besides `data/output/top_players_hnl_2025_2026.csv` (top scorers, U23,
defenders, midfield creators, attackers, overall, and one list per
position), `analysis.py` also saves
`data/output/specialist_rankings_hnl_2025_2026.csv` with 11 more
categories built on the Stage 1 scores: `best_dribblers`, `best_passers`,
`best_duel_defenders`, `best_creators`, `best_ball_winners`,
`best_progressive_midfielders`, `best_passer_defenders`,
`best_ball_playing_defenders`, and U23 versions of the dribbler/
progressive-midfielder/passer-defender lists. See `scouting_scores.py`'s
module docstring for why each list is filtered/sorted the way it is.

## Charts and the scouting report

`visualization.py` saves 19 charts to `reports/figures/` - leaderboards
(top overall, top U23, top goals/assists per 90), scatter plots (dribbling
volume vs. efficiency, safe vs. creative passing, defender/passer-defender
profiles, age/minutes vs. overall score, position score distribution,
team talent map), a grouped-bar specialist comparison, three
player-similarity bar charts, and a radar chart comparing three example
players.

`report.py` reads those charts plus every CSV in `data/processed/` and
`data/output/` and writes a single self-contained summary to
`reports/hnl_2025_2026_scouting_report.md` - project summary, dataset
stats, every ranking category, similarity examples, an explanation of
cosine similarity, and a limitations/next-improvements section. It runs
automatically as the last step of `python main.py`; to regenerate just
the report (e.g. after re-running only the earlier stages) without
re-fetching from the API:

```python
from src import report
report.run()
```

## Dashboard

`app.py` is a Streamlit dashboard over the pipeline's existing outputs -
it **never calls the SportMonks API and never writes or recomputes any
data**, it only reads the CSVs in `data/processed/` and `data/output/`,
the charts in `reports/figures/`, and the Markdown reports. Run
`python main.py` at least once first, then:

```powershell
streamlit run app.py
```

Pages (sidebar navigation):

- **Overview** - dataset summary (player/team/eligible-player counts) and
  the full scouting report.
- **Player rankings** - top overall/U23/attackers/creators/defenders/
  dribblers/passers/progressive midfielders/passer defenders/goalkeepers.
- **Player search / profile** - search by name, see age/team/position/
  minutes, every scouting score, and key per-90 stats.
- **Similarity search** - a UI over `ml_models.find_similar_players`
  (role, same-position/same-team/min-minutes/max-age filters).
- **Replacement scouting** - a UI over
  `replacement_scouting.find_replacement_targets`, with `replacement_score`
  explained inline.
- **Hidden gems** - underrated players, hidden gems, and small-club
  standouts (team-context scoring).
- **Clusters** - cluster sizes/names, players per cluster, and the full
  cluster profiles report.
- **Charts / report** - every chart in `reports/figures/` plus the full
  Markdown scouting report.

If a required CSV/chart/report is missing, the affected page shows an
error pointing at `python main.py` instead of crashing the app.

## Limitations

- **One season only.** All scores and percentiles are relative to this
  HNL 2025/2026 player pool - they say nothing about how a player would
  rank in a different league or season.
- **Coarse SportMonks positions.** Only `Defender` / `Midfielder` /
  `Attacker` / `Goalkeeper` are exposed here, with no centre-back/
  full-back/wing-back split.
- **No true progressive passes/carries or expected assists (xA).**
  `progressive_midfielder_score` is a proxy built from key passes, long
  balls, dribbles, and assists - not the tracking-data metric a platform
  like Opta/StatsBomb would compute.
- **Scores are explainable proxies, not ground truth.** This includes
  `age_potential_score`, `underrated_score`, and `replacement_score` -
  each combines already-approximate scores with simple, capped bonuses.
  They rank statistical output, not talent, tactical fit, potential, or
  transfer feasibility (fee, release clause, wages, contract length).
- **`underrated_score` is a team-context proxy, not a market-value or
  true-team-strength model.** `team_average_score` only reflects this
  season's statistical output of a team's eligible outfield players.
- **Similarity search and replacement scouting do not replace video
  scouting.** They surface statistically comparable players as a
  first-pass shortlist; a human scout still has to watch the games.
- **Player clusters describe playing style, not quality or literal
  position.** An elite and a modest player can share a cluster if their
  per-90 rates have a similar shape; a cluster's archetype name is
  demoted to a neutral one if the cluster's actual position makeup
  doesn't back up a position-specific claim.

(The generated [scouting report](reports/hnl_2025_2026_scouting_report.md)
carries a fuller version of this section, regenerated from live data on
every pipeline run.)

## Future improvements

- Better position groups if SportMonks exposes detailed positions for
  this competition/plan - would sharpen every position-aware score and
  cluster archetype (e.g. separating centre-backs from full-backs).
- Real market value as an extra lens alongside `underrated_score`.
- Multiple seasons of history, to support more robust percentile
  baselines, more stable cluster archetypes, and a meaningful supervised
  prediction model.
- Cross-league benchmarking - all scores here are relative to the HNL
  player pool only.
- Refine the cluster archetype signatures with feedback from reviewing a
  season's worth of assignments against known player profiles.
- Dashboard filters by team/age/position/minutes on the rankings page
  (currently category-only) - see the "Dashboard" section above for
  what `app.py` covers today.

## About this project

Built as a portfolio project to demonstrate an end-to-end football data
science workflow: REST API integration with pagination/retry handling,
ETL into a clean tabular schema, feature engineering (per-90
normalization), explainable scoring-model design (percentile ranks,
position-aware comparisons), unsupervised ML (cosine similarity, KMeans
clustering), and automated reporting - all reproducible from a single
`python main.py` run given a SportMonks API token.
