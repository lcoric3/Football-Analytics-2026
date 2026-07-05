# Football-Analytics-2026

A football data science and machine learning pipeline for Croatian HNL (1. HNL)
2025/2026 player statistics, built on the [SportMonks](https://www.sportmonks.com/)
Football API.

## What it does

The pipeline turns raw SportMonks player statistics into scouting-ready
rankings, charts, and an ML-ready dataset:

```
SportMonks API -> raw data -> cleaned data -> feature engineering
-> scouting scores -> analysis rankings -> visualizations -> ML dataset
-> Markdown report
```

## Setup

### 1. Get a SportMonks API token

Sign up at SportMonks and copy your API token. **Never hardcode the token
in code** - it is always read from the environment variable
`SPORTMONKS_API_TOKEN`.

Set it for your current PowerShell session:

```powershell
$env:SPORTMONKS_API_TOKEN = "your_token_here"
```

Or create a `.env` file in the project root (already covered by
`.gitignore`, never commit it):

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

## Project structure

```
Football-Analytics-2026/
├── main.py                  # Orchestrator - runs each pipeline stage in order
├── requirements.txt
├── src/
│   ├── sportmonks_client.py # API client: auth, pagination, retries, rate limits
│   ├── fetch_data.py        # Finds HNL league/season, fetches player stats
│   ├── clean_data.py        # Raw JSON/CSV -> clean flat schema
│   ├── feature_engineering.py # Per-90 metrics and ratios
│   ├── scouting_scores.py   # Attacking/creative/defensive/discipline/overall scores
│   ├── analysis.py          # Ranking tables (top scorers, best defenders, etc.)
│   ├── visualization.py     # matplotlib charts
│   ├── ml_models.py         # Similarity, clustering, optional regression
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

  Example - find players similar to Ismaël Bennacer, and to Sergi
  Domínguez specifically as a passer-defender:

  ```python
  from src import ml_models
  import pandas as pd

  scored_df = pd.read_csv("data/processed/hnl_player_scored_2025_2026.csv")
  ml_df = ml_models.build_ml_dataset(scored_df)

  ml_models.find_similar_players(ml_df, "Ismaël Bennacer", role="overall", top_n=10)
  ml_models.find_similar_players(ml_df, "Sergi Domínguez", role="passer_defender", top_n=10)
  ml_models.find_similar_players(ml_df, "Dion Beljo", role="attacker", top_n=10)
  ```

  A handful of example searches (including the three above) are saved to
  `data/output/player_similarity_results.csv` on every pipeline run.
- **KMeans clustering:** groups players into 4 clusters purely by
  statistical similarity, with no notion of position or team - useful for
  discovering play-style archetypes (e.g. a "destroyer" cluster with high
  tackles/interceptions and low pass volume vs. a "deep playmaker"
  cluster with the opposite profile).
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
